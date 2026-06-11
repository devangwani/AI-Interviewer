import numpy as np
import cv2
from fer import FER

_detector: FER | None = None


def _get_detector() -> FER:
    global _detector
    if _detector is None:
        # mtcnn=True gives better accuracy; set False to save ~300 MB RAM
        _detector = FER(mtcnn=False)
    return _detector


def analyse_frame(image_bytes: bytes) -> dict:
    """
    Decode a JPEG/PNG image from raw bytes and return dominant emotion scores.

    Returns a dict like:
      {"angry": 0.02, "disgust": 0.0, "fear": 0.01,
       "happy": 0.91, "sad": 0.02, "surprise": 0.01,
       "neutral": 0.03, "dominant": "happy", "confidence": 0.91}
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        return {"error": "Could not decode image"}

    detector = _get_detector()
    results = detector.detect_emotions(frame)

    if not results:
        return {"error": "No face detected"}

    # Use the face with the largest bounding box
    largest = max(results, key=lambda r: r["box"][2] * r["box"][3])
    emotions: dict = largest["emotions"]

    dominant = max(emotions, key=emotions.get)
    confidence = round(emotions[dominant], 4)

    return {
        **{k: round(v, 4) for k, v in emotions.items()},
        "dominant": dominant,
        "confidence": confidence,
    }
