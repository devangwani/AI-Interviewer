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
import re
from datetime import datetime
from typing import Optional

from bson import ObjectId
from groq import AsyncGroq
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Academic-integrity keyword detection
# ─────────────────────────────────────────────────────────────────────────────

# Each tuple is (regex_pattern, human_readable_reason).
# Patterns are matched case-insensitively against the full answer transcript.
_AI_DISCLOSURE_PATTERNS: list[tuple[str, str]] = [
    (r"i am a large language model",
     "Candidate said 'I am a large language model'"),
    (r"i'?m a large language model",
     "Candidate said 'I'm a large language model'"),
    (r"\bi am an ai\b",
     "Candidate self-identified as an AI"),
    (r"\bi'?m an ai\b",
     "Candidate self-identified as an AI"),
    (r"\bas an ai\b",
     "Candidate used the phrase 'as an AI'"),
    (r"\bas an artificial intelligence\b",
     "Candidate used the phrase 'as an artificial intelligence'"),
    (r"i was (?:created|developed|trained|built) by",
     "Candidate described being created/trained by an organisation"),
    (r"my (?:training|knowledge) (?:data|cutoff)",
     "Candidate mentioned their 'training data' or 'knowledge cutoff'"),
    (r"i cannot (?:browse|access) the internet",
     "Candidate stated inability to access the internet"),
    (r"i don'?t have (?:personal )?(?:experiences?|feelings?|consciousness|emotions?|opinions?)",
     "Candidate denied having human qualities"),
    (r"\b(?:chatgpt|gpt-?[34]|claude|gemini|bard|copilot)\b",
     "Candidate mentioned an AI tool by name"),
    (r"according to (?:chatgpt|claude|an?\s+ai|the ai)",
     "Candidate attributed their answer to an AI tool"),
    (r"i generated this",
     "Candidate stated they generated their answer"),
    (r"as (?:a|an) (?:language|ai|artificial)",
     "Candidate began a sentence with an AI self-description"),
]


def _detect_ai_disclosure(transcript: str) -> list[dict]:
    """
    Keyword-scan a single answer transcript for explicit AI-disclosure phrases.
    Returns a list of {reason, severity, excerpt} dicts — one per unique match.
    """
    text_lower = transcript.lower()
    hits: list[dict] = []
    seen_patterns: set[str] = set()

    for pattern, reason in _AI_DISCLOSURE_PATTERNS:
        if pattern in seen_patterns:
            continue
        m = re.search(pattern, text_lower)
        if m:
            seen_patterns.add(pattern)
            # Grab ~60 chars around the match for the excerpt
            start   = max(0, m.start() - 15)
            end     = min(len(transcript), m.end() + 45)
            excerpt = transcript[start:end].strip()
            hits.append({
                "reason":   reason,
                "severity": "high",
                "excerpt":  f"…{excerpt}…",
            })
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# Linguistic naturalness analyser
# ─────────────────────────────────────────────────────────────────────────────

# Words that appear naturally in human speech but vanish when reading a script.
_DISFLUENCY_WORDS  = {'um', 'uh', 'er', 'hmm', 'like', 'basically', 'right',
                       'okay', 'well', 'anyway', 'alright'}
_DISFLUENCY_PHRASES = ['i mean', 'you know', 'sort of', 'kind of']

# Enumeration markers heavy in AI list-style writing.
_ENUM_WORDS = ['firstly', 'secondly', 'thirdly', 'fourthly', 'additionally',
               'furthermore', 'moreover', 'in addition', 'lastly', 'finally',
               'to begin with', 'to start with']

# (regex, short_label) — formal hedging phrases characteristic of LLM output.
_HEDGING_PATTERNS = [
    (r"it(?:'?s| is) important to (?:note|mention|understand|highlight|emphasize)",
     "it is important to note/mention"),
    (r"in (?:summary|conclusion|essence|brief)\b",
     "in summary/conclusion"),
    (r"it (?:should|must) be (?:noted|mentioned|understood|emphasize)",
     "it should be noted"),
    (r"to (?:summarize|summarise|sum up|conclude)\b",
     "to summarize/conclude"),
    (r"there are (?:several|multiple|various|many|a (?:number|few) of) (?:key |important |main |critical )?",
     "there are several/multiple key…"),
    (r"plays? a (?:crucial|key|vital|pivotal|important|significant|central) role",
     "plays a crucial/key role"),
    (r"is (?:crucial|essential|fundamental|vital|critical|imperative) (?:to|for|in|that)\b",
     "is crucial/essential for"),
    (r"one (?:key|important|crucial|significant|major|notable) (?:aspect|factor|consideration|point|benefit|advantage)",
     "one key aspect/factor"),
    (r"(?:overall|in general|generally speaking),",
     "overall / in general"),
    (r"(?:first and foremost|last but not least)\b",
     "first and foremost / last but not least"),
    (r"leverag(?:e|ing) (?:the power of|various|multiple|different)\b",
     "leveraging the power of"),
    (r"(?:robust|scalable|efficient|comprehensive|seamless|cutting-edge|state-of-the-art)\b",
     "AI-typical adjective (robust/scalable/comprehensive/etc.)"),
]

# Personal-experience markers absent from generic AI answers.
_PERSONAL_MARKERS = [
    'i have worked', "i've worked", 'i worked on', 'i built', 'i developed',
    'i implemented', 'in my experience', 'i once', 'my project', 'my team',
    'when i was', 'i used to', 'personally', 'at my previous', 'i remember',
    'i recall', 'my role', 'i had to',
]


def _analyze_answer_naturalness(transcript: str) -> dict:
    """
    Compute objective linguistic signals that distinguish AI-generated text
    read aloud from natural human spoken responses.

    Returns a dict with:
      - word_count, disfluency_count, disfluency_pct
      - enum_hits, hedging_hits, has_personal
      - signals        : list[str] — human-readable descriptions of each flag
      - suspicion_pts  : int — raw suspicion score (higher = more suspicious)
      - naturalness    : int — 0–10 (10 = clearly natural, 0 = clearly AI-scripted)
    """
    text = transcript.strip()
    if not text:
        return {"word_count": 0, "signals": [], "suspicion_pts": 0, "naturalness": 10}

    text_lower  = text.lower()
    words       = text_lower.split()
    word_count  = len(words)

    if word_count < 15:            # too short to judge
        return {"word_count": word_count, "signals": [], "suspicion_pts": 0, "naturalness": 10}

    signals = []
    pts     = 0   # suspicion points

    # ── 1. Disfluency rate ────────────────────────────────────────────────────
    d_count = sum(1 for w in words if w in _DISFLUENCY_WORDS)
    d_count += sum(text_lower.count(p) for p in _DISFLUENCY_PHRASES)
    d_pct   = round(d_count / word_count * 100, 1)

    if word_count >= 40 and d_count == 0:
        signals.append(
            f"Zero spoken disfluencies over {word_count} words "
            "(no 'um', 'uh', 'like', 'you know') — strongly indicates scripted reading"
        )
        pts += 3
    elif word_count >= 60 and d_pct < 1.0:
        signals.append(
            f"Very low disfluency rate ({d_pct}%) for a {word_count}-word spoken answer"
        )
        pts += 1

    # ── 2. Enumerative structure ──────────────────────────────────────────────
    enum_hits = [w for w in _ENUM_WORDS if w in text_lower]
    if re.search(r'\bfirst\b', text_lower) and re.search(r'\bsecond\b', text_lower):
        enum_hits.append("first/second structure")
    if len(enum_hits) >= 2:
        signals.append(
            f"Heavy enumerative structure ({', '.join(enum_hits[:4])}) "
            "— characteristic of AI list-style writing read aloud"
        )
        pts += 1 + (1 if len(enum_hits) >= 3 else 0)

    # ── 3. AI hedging / formal phrases ───────────────────────────────────────
    hedging_hits = []
    for pattern, label in _HEDGING_PATTERNS:
        if re.search(pattern, text_lower):
            hedging_hits.append(label)
    if hedging_hits:
        signals.append(
            f"AI-characteristic formal phrases: {'; '.join(hedging_hits[:5])}"
        )
        pts += min(len(hedging_hits), 4)

    # ── 4. Absence of personal anecdotes in long answers ─────────────────────
    has_personal = any(m in text_lower for m in _PERSONAL_MARKERS)
    if word_count >= 60 and not has_personal:
        signals.append(
            f"No personal anecdotes or first-person experiences in a "
            f"{word_count}-word answer — typical of generic AI-generated content"
        )
        pts += 1

    # ── 5. Sentence completeness (high = suspicious for unscripted speech) ────
    sentences      = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip().split()) >= 4]
    if len(sentences) >= 4:
        completeness   = sum(1 for s in sentences if len(s.split()) >= 7)
        complete_pct   = round(completeness / len(sentences) * 100, 0)
        if complete_pct >= 95:
            signals.append(
                f"Near-perfect sentence completeness ({int(complete_pct)}% of sentences are "
                "full grammatical sentences) — natural speech typically contains "
                "sentence fragments, restarts, and self-corrections"
            )
            pts += 1

    naturalness = max(0, 10 - pts * 2)

    return {
        "word_count":     word_count,
        "disfluency_count": d_count,
        "disfluency_pct": d_pct,
        "enum_hits":      enum_hits,
        "hedging_hits":   hedging_hits,
        "has_personal":   has_personal,
        "signals":        signals,
        "suspicion_pts":  pts,
        "naturalness":    naturalness,
    }


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
        "(face frames only — absent frames excluded, values are probability-weighted):"
    )
    for label, score in sorted_emotions:
        pct = (score / total_face) * 100
        lines.append(f"  {label:<12}: {pct:.1f}%")

    lines.append(f"Total face-frames analysed: {face_frames}")
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

    # ── Academic integrity — keyword pre-scan + linguistic naturalness ────────
    # Step 1: keyword regex — catches explicit AI self-disclosure phrases.
    # Step 2: linguistic naturalness — computes concrete metrics (disfluency rate,
    #         enumeration patterns, hedging phrases, personal anecdotes) that
    #         expose AI-generated text even when no explicit phrases are used.
    # Both sets of evidence are stated as FACTS in the LLM prompt so the model
    # has hard data rather than being asked to "check for patterns" itself.
    integrity_pre_flags: list[dict] = []
    naturalness_results: list[dict] = []

    for i, qa in enumerate(qa_history):
        answer = qa.get("answer", "")

        # Keyword check
        kw_hits = _detect_ai_disclosure(answer)
        for hit in kw_hits:
            integrity_pre_flags.append({"question_index": i, **hit})

        # Linguistic naturalness
        nat = _analyze_answer_naturalness(answer)
        naturalness_results.append(nat)

    # Build integrity block for the LLM prompt
    integrity_lines: list[str] = []

    # ── Part A: keyword hits ──
    if integrity_pre_flags:
        integrity_lines.append(
            "PART A — Explicit AI-disclosure keywords (automated phrase scan — treat as DEFINITIVE evidence):"
        )
        for flag in integrity_pre_flags:
            integrity_lines.append(
                f"  Q{flag['question_index'] + 1} [HIGH]: {flag['reason']}  —  "
                f"excerpt: \"{flag['excerpt']}\""
            )
    else:
        integrity_lines.append(
            "PART A — No explicit AI-disclosure keywords detected in any answer."
        )

    integrity_lines.append("")

    # ── Part B: per-answer linguistic naturalness metrics ──
    integrity_lines.append(
        "PART B — Per-answer linguistic naturalness analysis (computed from transcript text):"
    )
    integrity_lines.append(
        "  [Scale: naturalness 10 = clearly natural human speech | 0 = clearly AI-scripted]"
    )
    overall_suspicion = 0
    for i, nat in enumerate(naturalness_results):
        level = (
            "HIGHLY SUSPICIOUS" if nat["naturalness"] <= 2
            else "SUSPICIOUS"    if nat["naturalness"] <= 4
            else "BORDERLINE"    if nat["naturalness"] <= 6
            else "NATURAL"
        )
        overall_suspicion += nat["suspicion_pts"]
        integrity_lines.append(
            f"\n  Q{i + 1} — Naturalness: {nat['naturalness']}/10  [{level}]"
            f"  |  Words: {nat['word_count']}  |  Disfluencies: {nat['disfluency_count']} ({nat['disfluency_pct']}%)"
        )
        if nat["signals"]:
            for sig in nat["signals"]:
                integrity_lines.append(f"    ⚑ {sig}")
        else:
            integrity_lines.append("    ✓ No suspicious linguistic signals detected")

    integrity_lines.append("")
    integrity_lines.append(
        "MANDATORY FLAGGING RULES — you MUST apply these regardless of other judgements:"
    )
    integrity_lines.append(
        "  • Naturalness ≤ 2 on ANY answer  →  flag that answer as HIGH severity"
    )
    integrity_lines.append(
        "  • Naturalness ≤ 4 on ANY answer  →  flag that answer as MEDIUM severity minimum"
    )
    integrity_lines.append(
        "  • Zero disfluencies over 40+ words  →  flag as MEDIUM severity minimum"
    )
    integrity_lines.append(
        "  • ANY keyword hit from Part A  →  flag as HIGH severity"
    )
    integrity_lines.append(
        "  • If MULTIPLE answers share the same low-naturalness pattern  →  elevate to HIGH risk"
    )
    integrity_lines.append(
        "  • Absence of explicit AI phrases does NOT mean the candidate is innocent."
    )
    integrity_lines.append(
        "    Candidates routinely copy AI-generated text and read it without disclosing the source."
    )
    integrity_lines.append(
        "    Your default assumption when signals align must be: FLAGGED."
    )

    integrity_block = "\n".join(integrity_lines)

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
        f"You are a senior technical recruiter, a behavioural scientist, AND an "
        f"academic integrity analyst who just completed a {interview_type} interview "
        f"for a {job_role} position. "
        "You have access to FOUR sources of signal:\n"
        "  1. The candidate's spoken answers (text transcript).\n"
        "  2. Real-time facial emotion data captured by a computer-vision model "
        "     during the interview (only frames where a face was detected).\n"
        "  3. Candidate camera presence data (what fraction of the session the "
        "     candidate was actually visible on camera).\n"
        "  4. Academic integrity signals — automated phrase matching PLUS your own "
        "     analysis of whether answers appear to be read from AI-generated scripts.\n\n"
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

=== ACADEMIC INTEGRITY ANALYSIS ===
{integrity_block}

Integrity task instructions:
The naturalness metrics in PART B above are OBJECTIVE measurements computed from
the transcript text — they are not your opinion, they are facts.  Use them as your
primary evidence.  Apply the MANDATORY FLAGGING RULES exactly as stated.

Additionally check for:
  • Cross-answer consistency: are ALL answers equally polished with zero disfluencies?
    A human candidate always shows variation — some answers are rough, some are fluent.
    Uniformly perfect structure across all questions strongly suggests AI use.
  • Vocabulary level shift: does the vocabulary suddenly become significantly more formal
    or technical than what would be expected from the candidate's other signals?
  • Suspiciously comprehensive coverage: does every answer cover every possible subtopic
    of the question with no gaps or "I'm not sure about that" moments?

When computing risk_level for integrity_report:
  "high"   — any keyword hit, OR naturalness ≤ 2 on any answer,
             OR multiple answers all at naturalness ≤ 4
  "medium" — naturalness ≤ 4 on any single answer, OR zero disfluencies across 2+ answers
  "low"    — naturalness 5–6 with minor signals but no definitive evidence
  "none"   — naturalness ≥ 7 on all answers, no signals detected

=== YOUR TASK ===
Act as the final multimodal judge.  Combine the technical accuracy of the
candidate's words, their visual confidence signals, their camera presence
data, AND the academic integrity signals to produce a highly detailed,
EXPLAINABLE Report Card.

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
  ],

  "integrity_report": {{
    "flagged":    <true | false — true if ANY answer shows clear AI-generation signals>,
    "risk_level": <"high" | "medium" | "low" | "none">,
    "flags": [
      {{
        "question_index": <int, 0-based>,
        "reason":   <string — specific reason this answer was flagged>,
        "severity": <"high" | "medium" | "low">,
        "excerpt":  <string — the suspicious portion of the answer, max ~80 chars>
      }}
    ],
    "summary": <string — 1-2 sentences: overall integrity verdict and what evidence was found>
  }}
}}
"""

    response = await client.chat.completions.create(
        model="openai/gpt-oss-120b",
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
            "integrity_report": {
                "flagged": bool(integrity_pre_flags) or any(
                    n.get("naturalness", 10) <= 4 for n in naturalness_results
                ),
                "risk_level": (
                    "high"   if integrity_pre_flags or any(n.get("naturalness", 10) <= 2 for n in naturalness_results)
                    else "medium" if any(n.get("naturalness", 10) <= 4 for n in naturalness_results)
                    else "none"
                ),
                "flags": integrity_pre_flags + [
                    {
                        "question_index": i,
                        "reason":   "Low linguistic naturalness score — possible AI-generated script",
                        "severity": "high" if n["naturalness"] <= 2 else "medium",
                        "excerpt":  "; ".join(n["signals"][:2]) if n["signals"] else "",
                    }
                    for i, n in enumerate(naturalness_results)
                    if n.get("naturalness", 10) <= 4
                ],
                "summary": (
                    "Report parsing failed. Automated analysis detected integrity concerns — manual review required."
                    if (integrity_pre_flags or any(n.get("naturalness", 10) <= 4 for n in naturalness_results))
                    else "Report parsing failed. No automated integrity concerns were detected."
                ),
            },
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
