"""
backend/app/ml/emotion_analysis.py
====================================
Facial Emotion Recognition — MobileNetV2 fine-tuned on RAF-DB.

MODEL FILE PLACEMENT
--------------------
After training, copy your weights file to:

    backend/app/ml/models/mobilenet_emotion_model.h5
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^
                          This exact filename is expected.

The `models/` subdirectory already exists (tracked by .gitkeep).
If you rename the file, update MODEL_PATH below.

EMOTION LABEL ORDER
-------------------
The 7 output neurons of your final Dense layer must correspond to:
    Index 0 → Surprise
    Index 1 → Fear
    Index 2 → Disgust
    Index 3 → Happiness
    Index 4 → Sadness
    Index 5 → Anger
    Index 6 → Neutral

This is the standard RAF-DB label ordering. If your training used a
different order (check your ImageDataGenerator class_indices), update
EMOTION_LABELS accordingly.
"""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Label mapping — must match your Dense(7) output order ────────────────────
# RAF-DB standard order (alphabetical by class folder name in the dataset)
EMOTION_LABELS: list[str] = [
    "Surprise",   # index 0
    "Fear",       # index 1
    "Disgust",    # index 2
    "Happiness",  # index 3
    "Sadness",    # index 4
    "Anger",      # index 5
    "Neutral",    # index 6
]

# ── Model path ────────────────────────────────────────────────────────────────
# __file__ resolves to  backend/app/ml/emotion_analysis.py
# .parent   resolves to  backend/app/ml/
# / "models" / ...       resolves to  backend/app/ml/models/mobilenet_emotion_model.h5
MODEL_PATH: Path = Path(__file__).parent / "models" / "mobilenet_emotion_model.h5"

# ── MobileNetV2 input specification ──────────────────────────────────────────
INPUT_SIZE: tuple[int, int] = (224, 224)   # (height, width)

# ── Haar Cascade face detection — minimum face size in pixels ────────────────
# Smaller values catch distant/small faces but increase false positives.
# 40×40 is a good default for interview-distance webcam shots.
_MIN_FACE_PX: int = 40


class EmotionAnalyzer:
    """
    Thin wrapper around a TensorFlow/Keras MobileNetV2 model for per-frame
    facial emotion inference.

    Design decisions
    ----------------
    - TensorFlow is imported INSIDE load() so that the FastAPI process starts
      quickly even on an 8 GB RAM machine where TF initialisation is slow.
    - analyze_frame() is async and offloads all CPU work to a thread-pool
      executor so it never blocks the uvicorn event loop.
    - The module exposes a single `emotion_analyzer` singleton so every
      WebSocket session shares the same loaded model.
    - Haar Cascade face detection runs BEFORE MobileNetV2 inference.  If no
      face is found the frame is skipped and None is returned.  This prevents
      empty / off-camera frames from being miscounted as "Neutral" emotion data.

    Typical usage
    -------------
        # Once at startup (inside lifespan or on_event("startup")):
        emotion_analyzer.load()

        # Inside the WebSocket receive loop for each video frame:
        label = await emotion_analyzer.analyze_frame(base64_string)
        # Returns the top-1 emotion label, or None if no face detected / error.
    """

    def __init__(self) -> None:
        self._model        = None           # tf.keras.Model, populated by load()
        self._face_cascade = None           # cv2.CascadeClassifier, populated by load()
        self._loaded: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self) -> None:
        """
        Load the Keras model and Haar Cascade from disk into memory.

        This is a synchronous call — run it once during application startup
        (not inside an async function) so the heavy TF import does not block
        an event loop.

        Raises
        ------
        FileNotFoundError
            If the .h5 file is missing from backend/app/ml/models/.
        RuntimeError
            If TensorFlow cannot load the model (corrupt file, version mismatch).
        """
        if self._loaded:
            return  # Already loaded — idempotent

        # ── Verify the weights file exists before importing TF ────────────────
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"\n[EmotionAnalyzer] Model weights NOT found at:\n"
                f"    {MODEL_PATH}\n\n"
                f"Steps to fix:\n"
                f"  1. Copy your trained .h5 file into:  backend/app/ml/models/\n"
                f"  2. Rename it to:  mobilenet_emotion_model.h5\n"
                f"  3. Restart the backend server.\n"
            )

        try:
            import tensorflow as tf

            # ── Keras 3 → tf.keras compatibility patch ───────────────────────
            # Google Colab saves models with Keras 3 (TF 2.16+), which adds
            # extra keys to every layer's serialised config:
            #   'quantization_config'  (Dense, Conv2D, BatchNorm, …)
            #   'optional'             (InputLayer)
            # tf.keras (Keras 2) passes those keys straight to __init__ via
            # Layer.from_config → cls(**config), and the constructors reject
            # unknown kwargs.
            #
            # Fix: patch Layer.from_config so it strips the unknown keys before
            # forwarding the config to the constructor.  Layer.from_config is
            # looked up through the class MRO at call time (not captured at
            # import time), so this patch is guaranteed to run for every layer
            # — Dense, Conv2D, DepthwiseConv2D, BatchNorm, etc. — without
            # having to enumerate them all.
            _KERAS3_EXTRAS = frozenset(["quantization_config", "optional"])
            _orig_from_config = tf.keras.layers.Layer.from_config

            @classmethod  # type: ignore[misc]
            def _compat_from_config(cls, config, **kwargs):
                cleaned = {k: v for k, v in config.items()
                           if k not in _KERAS3_EXTRAS}
                return _orig_from_config.__func__(cls, cleaned, **kwargs)

            tf.keras.layers.Layer.from_config = _compat_from_config
            try:
                self._model = tf.keras.models.load_model(
                    str(MODEL_PATH), compile=False
                )
            finally:
                # Always restore — the patch must not outlive the load call
                tf.keras.layers.Layer.from_config = _orig_from_config

            self._loaded = True
            logger.info(
                "[EmotionAnalyzer] MobileNetV2 loaded successfully from %s",
                MODEL_PATH,
            )
        except Exception as exc:
            raise RuntimeError(
                f"[EmotionAnalyzer] Failed to load model from {MODEL_PATH}: {exc}"
            ) from exc

        # ── Load Haar Cascade face detector ──────────────────────────────────
        # This is always available with OpenCV — no extra files needed.
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._face_cascade = cv2.CascadeClassifier(cascade_path)
        if self._face_cascade.empty():
            # Non-fatal: log warning and fall back to running inference on every
            # frame (original behaviour).  This should never happen with a
            # standard OpenCV install.
            logger.warning(
                "[EmotionAnalyzer] Haar Cascade file not found at %s — "
                "face detection disabled; all frames will be analysed.",
                cascade_path,
            )
            self._face_cascade = None

    async def analyze_frame(self, b64_string: str) -> Optional[str]:
        """
        Full inference pipeline for a single video frame received from the browser.

        Parameters
        ----------
        b64_string : str
            Base64-encoded JPEG or PNG image.  The browser may prepend a
            data-URI header (e.g. "data:image/jpeg;base64,...") — this is
            stripped automatically.

        Returns
        -------
        str | None
            The highest-confidence emotion label (e.g. "Happiness"), or None
            if:
              • the frame could not be decoded, OR
              • no face was detected in the frame (candidate off-camera).

            Callers should track how many frames returned None vs. a label to
            compute a "presence rate" for the interview session.

        Notes
        -----
        The actual numpy / TensorFlow work runs inside run_in_executor() so
        this coroutine yields control back to the event loop while waiting.
        """
        if not self._loaded:
            logger.warning(
                "[EmotionAnalyzer] analyze_frame() called before load() — "
                "returning None.  Check startup logs."
            )
            return None

        loop = asyncio.get_event_loop()

        # Offload all blocking CPU work to the default thread-pool executor
        return await loop.run_in_executor(
            None,                   # use the default ThreadPoolExecutor
            self._run_inference,    # the synchronous worker
            b64_string,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _decode_base64_frame(self, b64_string: str) -> Optional[np.ndarray]:
        """
        Convert a base64 string into an OpenCV BGR uint8 array.

        Handles both raw base64 and the data-URI format sent by canvas.toDataURL().
        Returns None on any decoding failure rather than raising.
        """
        try:
            # Strip "data:image/jpeg;base64," or "data:image/png;base64," prefix
            if "," in b64_string:
                b64_string = b64_string.split(",", 1)[1]

            img_bytes = base64.b64decode(b64_string)
            np_arr    = np.frombuffer(img_bytes, dtype=np.uint8)
            frame     = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)  # BGR, uint8

            if frame is None:
                raise ValueError("cv2.imdecode returned None — not a valid image.")

            return frame

        except Exception as exc:
            logger.warning("[EmotionAnalyzer] Frame decode failed: %s", exc)
            return None

    def _has_face(self, frame: np.ndarray) -> bool:
        """
        Return True if at least one face is detected in the frame.

        Uses OpenCV's Haar Cascade frontal face detector on the full-resolution
        frame.  The frontend sends 224×224 JPEG frames — downsampling further
        shrinks faces to ~30 px where JPEG artifacts cause the cascade to fail
        on every frame, so we run on the original size instead.

        If the cascade is unavailable (failed to load), always returns True so
        that every frame is still analysed (graceful degradation).
        """
        if self._face_cascade is None:
            return True  # Cascade unavailable — do not block inference

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=3,       # 5 was too strict for 224×224 JPEG frames
            minSize=(_MIN_FACE_PX, _MIN_FACE_PX),
        )
        return len(faces) > 0

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Prepare a raw BGR frame for MobileNetV2 inference.

        Steps
        -----
        1. Resize to 224 × 224 (MobileNetV2 default input size).
        2. Convert BGR → RGB   (OpenCV reads as BGR; Keras/TF expects RGB).
        3. Scale pixel values from [0, 255] to [-1.0, 1.0]
           using the formula:  x = (x / 127.5) - 1.0
           This matches tf.keras.applications.mobilenet_v2.preprocess_input().

        Returns
        -------
        np.ndarray of shape (1, 224, 224, 3), dtype float32
            Batch dimension added for model.predict().
        """
        # Step 1 — Resize
        resized = cv2.resize(frame, INPUT_SIZE, interpolation=cv2.INTER_LINEAR)

        # Step 2 — BGR → RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        # Step 3 — Normalise to [-1, 1]
        normalized = (rgb.astype(np.float32) / 127.5) - 1.0

        # Step 4 — Add batch dimension:  (224, 224, 3) → (1, 224, 224, 3)
        return np.expand_dims(normalized, axis=0)

    def _run_inference(self, b64_string: str) -> Optional[str]:
        """
        Synchronous inference worker — executed in a thread pool.

        Returns the top-1 emotion label, or None if no face was detected or
        on any failure.
        """
        # ── Decode ────────────────────────────────────────────────────────────
        frame = self._decode_base64_frame(b64_string)
        if frame is None:
            return None  # Decode error already logged

        # ── Face detection gate ───────────────────────────────────────────────
        # If no face is found the candidate is off-camera.  Return None so the
        # caller can track this as an absent frame rather than counting it as
        # "Neutral" emotion data.
        if not self._has_face(frame):
            logger.debug("[EmotionAnalyzer] No face detected — frame skipped.")
            return None

        try:
            # ── Preprocess ────────────────────────────────────────────────────
            tensor = self._preprocess(frame)        # shape: (1, 224, 224, 3)

            # ── Forward pass ──────────────────────────────────────────────────
            # verbose=0 suppresses the Keras progress bar in logs
            predictions = self._model.predict(tensor, verbose=0)[0]  # shape: (7,)

            # ── Argmax → label ────────────────────────────────────────────────
            top_index = int(np.argmax(predictions))
            top_label = EMOTION_LABELS[top_index]

            logger.debug(
                "[EmotionAnalyzer] Detected: %s (conf=%.3f)",
                top_label,
                float(predictions[top_index]),
            )
            return top_label

        except Exception as exc:
            logger.error("[EmotionAnalyzer] Inference error: %s", exc)
            return None


# ── Module-level singleton ────────────────────────────────────────────────────
# Import this object wherever you need emotion inference:
#   from app.ml.emotion_analysis import emotion_analyzer
#
# Call emotion_analyzer.load() ONCE at application startup (see main.py).
# After that, call await emotion_analyzer.analyze_frame(b64) from any coroutine.
emotion_analyzer = EmotionAnalyzer()
