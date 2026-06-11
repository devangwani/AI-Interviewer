"""
Standalone response evaluator that combines LLM scoring with
multimodal signals (emotion + speech) into a unified verdict.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MultimodalEvaluation:
    llm_score: float                   # 0–10, from Groq
    llm_strengths: str
    llm_improvements: str
    llm_verdict: str                   # "strong" | "acceptable" | "weak"
    emotion_dominant: Optional[str]
    emotion_confidence: Optional[float]
    speech_rate_wpm: Optional[float]
    pitch_variability: Optional[float]
    filler_total: Optional[int]
    composite_score: float             # weighted final score


def compute_composite_score(
    llm_score: float,
    emotion_scores: Optional[dict] = None,
    speech_metrics: Optional[dict] = None,
    filler_data: Optional[dict] = None,
) -> float:
    """
    Weighted composite:
      - LLM content quality: 60%
      - Delivery (speech rate, pitch variability): 25%
      - Confidence (emotion, filler words): 15%
    """
    content_score = llm_score  # already 0–10

    # Delivery score (0–10)
    delivery_score = 5.0
    if speech_metrics:
        wpm = speech_metrics.get("speaking_rate_wpm", 130)
        # Ideal range ~120–160 wpm for interviews
        wpm_penalty = max(0, abs(wpm - 140) - 20) * 0.05
        pitch_var = speech_metrics.get("pitch_variability", 20)
        # Reward expressiveness; penalise monotone (<10 Hz) or erratic (>80 Hz)
        pitch_bonus = min(pitch_var / 40, 1.0) * 2.0
        delivery_score = max(0.0, min(10.0, 5.0 + pitch_bonus - wpm_penalty))

    # Confidence score (0–10)
    confidence_score = 5.0
    if emotion_scores:
        positive = emotion_scores.get("happy", 0) + emotion_scores.get("neutral", 0)
        negative = emotion_scores.get("angry", 0) + emotion_scores.get("fear", 0) + emotion_scores.get("sad", 0)
        confidence_score = max(0.0, min(10.0, 5.0 + (positive - negative) * 10))
    if filler_data:
        filler_penalty = min(filler_data.get("total_fillers", 0) * 0.3, 3.0)
        confidence_score = max(0.0, confidence_score - filler_penalty)

    composite = (
        content_score * 0.60
        + delivery_score * 0.25
        + confidence_score * 0.15
    )
    return round(composite, 2)


def build_evaluation(
    llm_result: dict,
    emotion_scores: Optional[dict] = None,
    speech_metrics: Optional[dict] = None,
    filler_data: Optional[dict] = None,
) -> MultimodalEvaluation:
    llm_score = float(llm_result.get("score", 5.0))
    composite = compute_composite_score(llm_score, emotion_scores, speech_metrics, filler_data)

    return MultimodalEvaluation(
        llm_score=llm_score,
        llm_strengths=llm_result.get("strengths", ""),
        llm_improvements=llm_result.get("improvements", ""),
        llm_verdict=llm_result.get("verdict", "acceptable"),
        emotion_dominant=emotion_scores.get("dominant") if emotion_scores else None,
        emotion_confidence=emotion_scores.get("confidence") if emotion_scores else None,
        speech_rate_wpm=speech_metrics.get("speaking_rate_wpm") if speech_metrics else None,
        pitch_variability=speech_metrics.get("pitch_variability") if speech_metrics else None,
        filler_total=filler_data.get("total_fillers") if filler_data else None,
        composite_score=composite,
    )
