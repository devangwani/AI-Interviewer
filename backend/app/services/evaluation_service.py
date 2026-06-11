"""
backend/app/services/evaluation_service.py
============================================
Final interview evaluation service — Multimodal Report Card Generator.

Responsibilities
----------------
1. generate_report_card()
       Takes the full Q&A transcript, the aggregated emotion statistics,
       and the candidate presence stats captured during the live session,
       then sends all three to Groq.  The LLM combines:
         • What the candidate SAID   (technical accuracy, communication)
         • How they LOOKED           (emotion distribution from MobileNetV2)
         • How present they WERE     (frames with face / total frames sent)
       Returns a structured JSON Report Card.

2. save_report_to_db()
       Persists the Report Card, emotion stats, and presence stats to
       MongoDB and marks the session as "completed".
"""

import json
from datetime import datetime
from typing import Optional

from bson import ObjectId
from groq import AsyncGroq
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Helper — compute presence rate
# ─────────────────────────────────────────────────────────────────────────────

def _compute_presence_rate(
    emotion_stats: dict[str, int],
    presence_stats: Optional[dict],
) -> float:
    """
    Return the percentage of video frames in which a face was detected (0–100).

    If no presence_stats are provided (legacy sessions), fall back to 100 % so
    old reports are not retroactively penalised.
    """
    if not presence_stats:
        return 100.0
    total  = presence_stats.get("total_frames", 0)
    with_face = presence_stats.get("frames_with_face", sum(emotion_stats.values()))
    if total == 0:
        return 0.0 if with_face == 0 else 100.0
    return round((with_face / total) * 100, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Helper — format emotion stats for the LLM prompt
# ─────────────────────────────────────────────────────────────────────────────

def _format_emotion_stats(
    emotion_stats: dict[str, int],
    presence_stats: Optional[dict] = None,
) -> str:
    """
    Convert the raw emotion counter dict and presence data into a
    human-readable block that the LLM can reason about.

    Example output
    --------------
    Candidate presence: 87.3% of frames had a face detected (96 / 110 total frames).

    Emotion distribution captured by computer-vision model (face frames only):
      Neutral    : 42 frames (43.8%)
      Happiness  : 20 frames (20.8%)
      ...
    Total face-frames analysed: 96
    """
    presence_rate = _compute_presence_rate(emotion_stats, presence_stats)
    total_frames  = presence_stats.get("total_frames", 0) if presence_stats else 0
    face_frames   = sum(emotion_stats.values())

    lines = []

    # ── Presence section ──────────────────────────────────────────────────────
    if presence_stats and total_frames > 0:
        lines.append(
            f"Candidate camera presence: {presence_rate:.1f}% of frames had a face "
            f"detected ({face_frames} / {total_frames} total frames)."
        )
        if presence_rate < 40:
            lines.append(
                f"  ⚠ CRITICAL ABSENCE: The candidate was absent from the camera "
                f"for {100 - presence_rate:.1f}% of the interview.  "
                f"Visual emotion analysis covers only a small fraction of the session."
            )
        elif presence_rate < 70:
            lines.append(
                f"  ⚠ SIGNIFICANT ABSENCE: The candidate was off-camera for "
                f"{100 - presence_rate:.1f}% of the interview.  "
                f"This should be noted in the visual confidence assessment."
            )
    elif total_frames == 0:
        lines.append(
            "Candidate camera presence: No video frames were received "
            "— camera may have been disabled throughout the interview."
        )

    lines.append("")

    # ── Emotion distribution section ──────────────────────────────────────────
    if not emotion_stats:
        lines.append("No emotion data available (no face detected in any frame).")
        return "\n".join(lines)

    total_face = sum(emotion_stats.values())
    sorted_emotions = sorted(emotion_stats.items(), key=lambda x: x[1], reverse=True)

    lines.append(
        "Emotion distribution captured by computer-vision model "
        "(face frames only — absent frames excluded):"
    )
    for label, count in sorted_emotions:
        pct = (count / total_face) * 100
        lines.append(f"  {label:<12}: {count:>4} frames ({pct:.1f}%)")

    lines.append(f"Total face-frames analysed: {total_face}")
    return "\n".join(lines)


def _derive_visual_confidence(
    emotion_stats: dict[str, int],
    presence_rate: float,
) -> str:
    """
    Produce a short qualitative summary of the candidate's visual confidence
    based on emotion distribution AND presence rate.
    """
    if presence_rate < 40:
        return (
            f"Insufficient data — candidate was on camera for only "
            f"{presence_rate:.1f}% of the interview.  Visual confidence "
            "cannot be reliably assessed."
        )

    if not emotion_stats:
        return "Unknown (no face detected in any frame)"

    total = sum(emotion_stats.values())
    dominant_emotion = max(emotion_stats, key=emotion_stats.get)
    dominant_pct = (emotion_stats[dominant_emotion] / total) * 100

    confidence_map = {
        "Neutral":   "Composed and calm",
        "Happiness": "Positive and engaged",
        "Fear":      "Visibly nervous or anxious",
        "Sadness":   "Low energy or disengaged",
        "Disgust":   "Uncomfortable with certain topics",
        "Anger":     "Defensive or under stress",
        "Surprise":  "Caught off-guard by several questions",
    }

    descriptor = confidence_map.get(dominant_emotion, "Mixed signals")
    suffix = (
        f"  (Note: presence was {presence_rate:.1f}% — interpretation is "
        "partial.)"
        if presence_rate < 70 else ""
    )
    return (
        f"{descriptor} (dominant: {dominant_emotion} at {dominant_pct:.1f}% "
        f"of face frames){suffix}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Core function — Multimodal Report Card generation
# ─────────────────────────────────────────────────────────────────────────────

async def generate_report_card(
    job_role: str,
    interview_type: str,
    qa_history: list[dict],
    emotion_stats: Optional[dict[str, int]] = None,
    presence_stats: Optional[dict] = None,
) -> dict:
    """
    Build a structured Multimodal Report Card for the completed interview.

    Parameters
    ----------
    job_role        : e.g. "Backend Engineer"
    interview_type  : e.g. "technical", "behavioural"
    qa_history      : list of {"question": str, "answer": str} dicts (in order)
    emotion_stats   : dict of {emotion_label: frame_count} from EmotionAnalyzer,
                      e.g. {"Happiness": 20, "Neutral": 42, "Fear": 5}
                      Only frames where a face was detected are counted here.
    presence_stats  : {"total_frames": int, "frames_with_face": int}
                      Used to compute the presence rate for the session.

    Returns
    -------
    dict
        Parsed JSON Report Card.  Includes a `presence_rate` field (float,
        0–100) injected after LLM parsing so it is never hallucinated.
        Falls back to a safe default dict on JSON parse failure.
    """
    client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    emotion_stats   = emotion_stats or {}
    presence_rate   = _compute_presence_rate(emotion_stats, presence_stats)
    total_frames    = (presence_stats or {}).get("total_frames", 0)
    face_frames     = sum(emotion_stats.values())
    absence_pct     = round(100 - presence_rate, 1)

    # ── Build the Q&A transcript section ─────────────────────────────────────
    history_text = "\n\n".join([
        f"Q{i + 1}: {qa['question']}\nA{i + 1}: {qa.get('answer', '(no answer given)')}"
        for i, qa in enumerate(qa_history)
    ])

    # ── Build the visual / emotion section ───────────────────────────────────
    emotion_block  = _format_emotion_stats(emotion_stats, presence_stats)
    visual_summary = _derive_visual_confidence(emotion_stats, presence_rate)

    # ── Absence warning for prompt ────────────────────────────────────────────
    if total_frames == 0:
        absence_instruction = (
            "No video was received for this session.  Set visual_confidence_score "
            "to null and absence_warning to a note that the camera was off."
        )
    elif presence_rate < 40:
        absence_instruction = (
            f"IMPORTANT: The candidate was absent from the camera frame for "
            f"{absence_pct}% of the interview ({total_frames - face_frames} out of "
            f"{total_frames} frames had no face detected).  "
            "You MUST set absence_warning to a clear sentence describing this, "
            "and you MUST reflect this in the visual_confidence_score (significant penalty). "
            "Do NOT infer emotional state from periods where the candidate was absent."
        )
    elif presence_rate < 70:
        absence_instruction = (
            f"NOTE: The candidate was off-camera for {absence_pct}% of the interview "
            f"({total_frames - face_frames} out of {total_frames} frames had no face). "
            "Set absence_warning to a note about this, and apply a moderate penalty "
            "to visual_confidence_score since coverage is partial."
        )
    else:
        absence_instruction = (
            "Good camera presence — no absence penalty needed.  "
            "Set absence_warning to null."
        )

    # ── System prompt ─────────────────────────────────────────────────────────
    system_prompt = (
        f"You are a senior technical recruiter AND a behavioural scientist who just "
        f"completed a {interview_type} interview for a {job_role} position. "
        "You have access to THREE sources of signal:\n"
        "  1. The candidate's spoken answers (text transcript).\n"
        "  2. Real-time facial emotion data captured by a computer-vision model "
        "     during the interview (only frames where a face was detected).\n"
        "  3. Candidate camera presence data (what fraction of the session the "
        "     candidate was actually visible on camera).\n\n"
        "Combine ALL signals to produce a deeply insightful, fair, and actionable "
        "Report Card.  Absence from camera is a behavioural signal and should be "
        "treated as such — it may indicate distraction, disengagement, or technical "
        "issues, and must be clearly flagged when significant.\n\n"
        "Return ONLY valid JSON — no markdown, no explanation, no extra text."
    )

    # ── User prompt ───────────────────────────────────────────────────────────
    user_prompt = f"""
=== INTERVIEW TRANSCRIPT ===
{history_text}

=== VISUAL EMOTION ANALYSIS (MobileNetV2 / RAF-DB model) ===
{emotion_block}

Qualitative visual confidence summary: {visual_summary}

=== ABSENCE INSTRUCTION ===
{absence_instruction}

=== YOUR TASK ===
Act as the final multimodal judge.  Combine the technical accuracy of the
candidate's words, their visual confidence signals, AND their camera presence
data to produce a highly detailed, EXPLAINABLE Report Card.

For every sub-score you assign, you MUST provide a rubric breakdown — a list
of specific criteria that were evaluated, whether the candidate met each one,
the point impact (e.g. "+2.0" or "-1.5"), and a concrete example from the
interview transcript or emotion data where relevant.

Return a JSON object with EXACTLY these keys:

{{
  "overall_score":          <float 0-10, weighted average of all sub-scores>,

  "communication_score":    <float 0-10>,
  "communication_breakdown": [
    {{
      "criterion": <string — specific thing evaluated, e.g. "Clear sentence structure">,
      "met":       <true | false>,
      "impact":    <string — point contribution, e.g. "+2.0" or "-1.5">,
      "note":      <string — one concrete example from the interview>
    }}
  ],

  "technical_score":        <float 0-10>,
  "technical_breakdown": [
    {{
      "criterion": <string — specific technical skill or knowledge area evaluated>,
      "met":       <true | false>,
      "impact":    <string>,
      "note":      <string — reference the specific question and what was said or missed>
    }}
  ],

  "confidence_score":       <float 0-10, derived from BOTH speech content AND emotion data>,
  "confidence_breakdown": [
    {{
      "criterion": <string — specific confidence signal evaluated>,
      "met":       <true | false>,
      "impact":    <string>,
      "note":      <string — cite both verbal signals and emotion frame data where applicable>
    }}
  ],

  "visual_confidence_score": <float 0-10 OR null if no camera data — derived from CNN emotion distribution AND presence rate>,
  "visual_confidence_breakdown": [
    {{
      "criterion": <string — specific visual/emotion signal evaluated>,
      "met":       <true | false>,
      "impact":    <string>,
      "note":      <string — reference specific percentages from the emotion data and/or absence data>
    }}
  ],

  "absence_warning": <string | null — null if presence was >= 70%, otherwise a clear sentence stating the % of interview the candidate was absent from camera and what this means for the assessment>,

  "verdict":        <"Strong Hire" | "Hire" | "Maybe" | "No Hire">,
  "summary":        <string — 3-4 sentences combining verbal and visual observations; explicitly mention camera presence if it was low>,
  "visual_insight": <string — 2-3 sentences on what the emotion data AND presence rate reveal about true confidence>,
  "strengths":      [<string>, ...],
  "improvements":   [<string>, ...],
  "emotion_summary": {{
    "dominant_emotion":    <string — dominant emotion among face frames, or "N/A" if no face frames>,
    "positive_frames_pct": <float, % of Happiness + Neutral among face frames>,
    "stress_frames_pct":   <float, % of Fear + Sadness + Disgust + Anger among face frames>,
    "interpretation":      <string — one sentence; mention absence if significant>
  }},
  "per_question": [
    {{
      "question": <string>,
      "score":    <float 0-10>,
      "feedback": <string — 2-3 sentences: what was strong, what was weak, what the emotion data showed>
    }}
  ]
}}
"""

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"

    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        report = {
            "overall_score":               5.0,
            "communication_score":         5.0,
            "communication_breakdown":     [],
            "technical_score":             5.0,
            "technical_breakdown":         [],
            "confidence_score":            5.0,
            "confidence_breakdown":        [],
            "visual_confidence_score":     5.0,
            "visual_confidence_breakdown": [],
            "absence_warning":             None,
            "verdict":                     "Maybe",
            "summary":                     "Evaluation could not be parsed. Please review manually.",
            "visual_insight":              "No visual insight available.",
            "strengths":                   [],
            "improvements":                [],
            "emotion_summary": {
                "dominant_emotion":    "Unknown",
                "positive_frames_pct": 0.0,
                "stress_frames_pct":   0.0,
                "interpretation":      "Emotion data unavailable.",
            },
            "per_question": [],
        }

    # Inject presence_rate as a fact — never trust the LLM to compute this.
    report["presence_rate"] = presence_rate

    return report


# ─────────────────────────────────────────────────────────────────────────────
# Persistence function
# ─────────────────────────────────────────────────────────────────────────────

async def save_report_to_db(
    db: AsyncIOMotorDatabase,
    session_id: str,
    report: dict,
    qa_history: list[dict],
    emotion_stats: Optional[dict[str, int]] = None,
    presence_stats: Optional[dict] = None,
) -> None:
    """
    Persist the Multimodal Report Card to MongoDB and mark the session completed.

    Writes
    ------
    - status              → "completed"
    - completed_at        → UTC now
    - overall_score       → report["overall_score"]
    - report_card         → full report dict (includes presence_rate, absence_warning)
    - emotion_stats       → the raw per-emotion frame count dict from the CNN
    - presence_stats      → {"total_frames": int, "frames_with_face": int}
    - questions_answers   → updates answer_transcript, llm_score, llm_feedback
                            for each QA pair answered during the live session
    """
    now   = datetime.utcnow()
    per_q = report.get("per_question", [])

    # ── Update each QA sub-document ───────────────────────────────────────────
    for i, qa in enumerate(qa_history):
        q_report = per_q[i] if i < len(per_q) else {}

        if not qa.get("question_id"):
            continue

        await db["interviews"].update_one(
            {
                "_id": ObjectId(session_id),
                "questions_answers.question_id": qa["question_id"],
            },
            {
                "$set": {
                    "questions_answers.$.answer_transcript": qa.get("answer", ""),
                    "questions_answers.$.llm_score":         q_report.get("score"),
                    "questions_answers.$.llm_feedback":      q_report.get("feedback", ""),
                }
            },
        )

    # ── Update top-level session document ─────────────────────────────────────
    await db["interviews"].update_one(
        {"_id": ObjectId(session_id)},
        {
            "$set": {
                "status":          "completed",
                "completed_at":    now,
                "overall_score":   report.get("overall_score"),
                "report_card":     report,
                "emotion_stats":   emotion_stats or {},
                "presence_stats":  presence_stats or {},
            }
        },
    )
