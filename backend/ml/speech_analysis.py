import io
import re
import numpy as np
import librosa
import soundfile as sf

FILLER_WORDS = {"um", "uh", "like", "you know", "so", "basically", "literally", "actually", "right"}


def analyse_audio(audio_bytes: bytes) -> dict:
    """
    Analyse a WAV audio clip and return speech quality metrics.

    Returns:
      {
        "duration_seconds": float,
        "speaking_rate_wpm": float,        # estimated from tempo
        "average_pitch_hz": float,
        "pitch_variability": float,        # std dev of F0 (expressiveness proxy)
        "energy_mean": float,
        "energy_std": float,
        "silence_ratio": float,            # fraction of frames that are silent
      }
    """
    audio_file = io.BytesIO(audio_bytes)
    y, sr = librosa.load(audio_file, sr=None, mono=True)

    duration = librosa.get_duration(y=y, sr=sr)

    # Pitch (F0) via pyin
    f0, voiced_flag, _ = librosa.pyin(y, fmin=80, fmax=400, sr=sr)
    voiced_f0 = f0[voiced_flag] if voiced_flag is not None else np.array([])
    avg_pitch = float(np.mean(voiced_f0)) if len(voiced_f0) > 0 else 0.0
    pitch_var = float(np.std(voiced_f0)) if len(voiced_f0) > 0 else 0.0

    # Energy / RMS
    rms = librosa.feature.rms(y=y)[0]
    energy_mean = float(np.mean(rms))
    energy_std = float(np.std(rms))

    # Silence ratio: frames below 10% of max RMS
    silence_threshold = 0.1 * float(np.max(rms)) if np.max(rms) > 0 else 0.0
    silence_ratio = float(np.mean(rms < silence_threshold))

    # Rough speaking rate from onset strength (proxy for syllable rate)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    # Convert beats/min to an approximate words-per-minute (1 beat ≈ 1 syllable, ~1.5 syl/word)
    speaking_rate_wpm = float(tempo / 1.5) if duration > 0 else 0.0

    return {
        "duration_seconds": round(duration, 2),
        "speaking_rate_wpm": round(speaking_rate_wpm, 1),
        "average_pitch_hz": round(avg_pitch, 2),
        "pitch_variability": round(pitch_var, 2),
        "energy_mean": round(energy_mean, 4),
        "energy_std": round(energy_std, 4),
        "silence_ratio": round(silence_ratio, 4),
    }


def count_filler_words(transcript: str) -> dict:
    """Count filler words in a transcript string."""
    lower = transcript.lower()
    counts = {}
    for filler in FILLER_WORDS:
        pattern = r"\b" + re.escape(filler) + r"\b"
        count = len(re.findall(pattern, lower))
        if count:
            counts[filler] = count
    total = sum(counts.values())
    return {"filler_counts": counts, "total_fillers": total}
