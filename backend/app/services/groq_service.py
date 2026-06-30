import json
import uuid
from groq import AsyncGroq
from app.core.config import settings

_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _client


async def generate_interview_questions(
    job_role: str,
    interview_type: str,
    difficulty: str,
    num_questions: int,
) -> list[str]:
    client = get_groq_client()
    prompt = (
        f"Generate {num_questions} {difficulty}-difficulty {interview_type} interview questions "
        f"for a {job_role} position. Return ONLY a numbered list of questions, one per line. "
        "No additional commentary."
    )
    response = await client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1024,
    )
    raw = response.choices[0].message.content or ""
    questions = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            # Strip leading "1. " or "1) " numbering
            parts = line.split(".", 1) if "." in line else line.split(")", 1)
            questions.append(parts[-1].strip() if len(parts) > 1 else line)
    return questions[:num_questions]


async def generate_next_question(
    job_role: str,
    interview_type: str,
    difficulty: str,
    qa_history: list[dict],
    question_number: int,
    total_questions: int,
    resume_context: dict | None = None,
) -> str:
    """
    Dynamically generate the next interview question based on conversation so far.
    Acts as a senior technical recruiter who adapts follow-up questions to the
    candidate's previous answers.

    qa_history: list of {"question": str, "answer": str} dicts
    resume_context: optional {"skills": [...], "projects": [...]} from parsed resume
    """
    client = get_groq_client()

    # UUID nonce added to BOTH the system and user prompt.
    # Groq (and most providers) cache at the system-prompt level — a nonce only
    # in the user prompt is silently ignored when the system prompt matches a
    # cached entry. Putting it in the system prompt defeats that caching.
    nonce = uuid.uuid4().hex[:12]

    history_text = "\n".join([
        f"Q{i+1}: {qa['question']}\nA{i+1}: {qa['answer']}"
        for i, qa in enumerate(qa_history)
    ]) if qa_history else None

    # Build resume snippet if available
    resume_snippet = ""
    if resume_context:
        skills = resume_context.get("skills", [])
        projects = resume_context.get("projects", [])
        if skills:
            resume_snippet += f"\nCandidate's skills from their resume: {', '.join(skills)}."
        if projects:
            project_lines = "; ".join(
                f"{p.get('name', 'Unnamed')}: {p.get('description', '')}"
                for p in projects
            )
            resume_snippet += f"\nCandidate's projects from their resume: {project_lines}."
        if resume_snippet:
            resume_snippet = (
                "\n\nThe candidate has uploaded their resume. Use this context to ask "
                "personalised questions that probe their specific experience:"
                + resume_snippet
            )

    # ── Interview-type-aware guidance ────────────────────────────────────────
    # The type is the PRIMARY driver of what kind of questions to ask.
    # The difficulty is SECONDARY — it controls depth/complexity within that type.

    _type = interview_type.lower().strip()

    if _type in ("behavioral", "behavioural"):
        interviewer_role = "behavioural interviewer"
        type_instruction = (
            "You are conducting a BEHAVIOURAL interview.  Ask ONLY behavioural questions "
            "using STAR-method scenarios (Situation, Task, Action, Result).  Topics must "
            "cover: past work experiences, teamwork, conflict resolution, leadership moments, "
            "handling failure, meeting deadlines, and interpersonal challenges.  "
            "Do NOT ask any technical, coding, or system-design questions whatsoever."
        )
        difficulty_guidance = {
            "beginner": (
                "BEGINNER level — the candidate may have little or no professional work "
                "experience.  Frame scenarios around college projects, group assignments, "
                "internships, or volunteer work.  Keep questions simple enough for a fresher."
            ),
            "intermediate": (
                "INTERMEDIATE level — the candidate has 1-3 years of professional experience.  "
                "Ask about real workplace scenarios: handling conflict with a colleague, "
                "missing a deadline, leading a small initiative, or adapting to change."
            ),
            "advanced": (
                "ADVANCED level — the candidate is experienced.  Probe complex leadership "
                "situations: managing cross-functional conflict, influencing without authority, "
                "recovering from a significant failure, or navigating difficult stakeholders."
            ),
        }.get(difficulty, f"This is a {difficulty}-level behavioural interview.")

    elif _type == "hr":
        interviewer_role = "HR specialist"
        type_instruction = (
            "You are conducting an HR / culture-fit interview.  Ask ONLY HR-focused questions "
            "about: motivation and career goals, values and culture alignment, work-style "
            "preferences, salary expectations, reasons for joining/leaving, long-term vision, "
            "and interpersonal skills.  "
            "Do NOT ask any technical, coding, or system-design questions whatsoever."
        )
        difficulty_guidance = {
            "beginner": (
                "BEGINNER level — suitable for a fresh graduate or early-career candidate.  "
                "Ask straightforward questions about career goals, values, and work preferences."
            ),
            "intermediate": (
                "INTERMEDIATE level — candidate has some professional experience.  "
                "Probe professional growth mindset, preferred work environments, and motivation."
            ),
            "advanced": (
                "ADVANCED level — experienced candidate.  Explore leadership philosophy, "
                "long-term career vision, culture-building perspectives, and compensation."
            ),
        }.get(difficulty, f"This is a {difficulty}-level HR interview.")

    else:
        # Default: technical interview
        interviewer_role = "senior technical recruiter"
        type_instruction = (
            "You are conducting a TECHNICAL interview.  Ask ONLY technical questions that "
            "assess the candidate's knowledge, problem-solving skills, and engineering depth "
            "relevant to the role.  Do NOT ask behavioural or HR questions."
        )
        difficulty_guidance = {
            "beginner": (
                "BEGINNER level — aimed at fresh graduates with little or no professional "
                "experience.  Questions must be simple and foundational: basic definitions, "
                "core concepts, and things covered in a first-year course or introductory "
                "tutorial.  Do NOT ask about system design, architecture trade-offs, "
                "production debugging, or anything requiring industry experience.  "
                "A fresher who has done a few personal projects should be able to answer."
            ),
            "intermediate": (
                "INTERMEDIATE level — candidates with 1-3 years of experience or strong "
                "academic/project backgrounds.  Test practical understanding, common design "
                "patterns, debugging approaches, and real-world application of concepts — "
                "avoid deep system-scale or senior-engineer-level topics."
            ),
            "advanced": (
                "ADVANCED level — experienced engineers.  Probe system design decisions, "
                "performance trade-offs, failure scenarios, large-scale architecture, and "
                "deep technical expertise.  Expect the candidate to justify design choices "
                "and reason about edge cases."
            ),
        }.get(difficulty, f"This is a {difficulty}-level technical interview.")

    system_prompt = (
        f"[sid:{nonce}] "   # session-unique prefix — defeats system-prompt-level caching
        f"You are a {interviewer_role} conducting an interview for a {job_role} position.  "
        f"{type_instruction}  "
        f"{difficulty_guidance}  "
        "Ask varied questions appropriate for the interview type and level above.  "
        "Each interview session must feel unique.  "
        "Build naturally on previous answers when history is present.  "
        "Do NOT revisit topics already covered.  Ask only ONE question.  "
        "Return ONLY the question text — no preamble, no numbering, no explanation."
        + resume_snippet
    )

    if not history_text:
        if _type in ("behavioral", "behavioural"):
            user_prompt = (
                f"This is the opening question (1 of {total_questions}) of a fresh interview. "
                f"Pick a {difficulty}-level behavioural scenario relevant to someone applying "
                f"for a {job_role} role. [session-nonce: {nonce}]"
            )
        elif _type == "hr":
            user_prompt = (
                f"This is the opening question (1 of {total_questions}) of a fresh interview. "
                f"Pick a {difficulty}-level HR / culture-fit question relevant to a {job_role} "
                f"candidate. [session-nonce: {nonce}]"
            )
        elif difficulty == "beginner":
            user_prompt = (
                f"This is the opening question (1 of {total_questions}) of a fresh interview. "
                f"Pick a foundational, entry-level technical topic relevant to {job_role} — "
                f"something a fresh graduate who has done self-study or a college project would "
                f"know.  The question must be simple enough for a complete fresher. "
                f"[session-nonce: {nonce}]"
            )
        else:
            user_prompt = (
                f"This is the opening question (1 of {total_questions}) of a fresh interview. "
                f"Pick a specific, non-obvious technical topic relevant to {job_role} and "
                f"generate a {difficulty}-level opening question that will reveal the "
                f"candidate's depth of understanding. [session-nonce: {nonce}]"
            )
    else:
        user_prompt = (
            f"This is question {question_number} of {total_questions}.\n\n"
            f"Interview so far:\n{history_text}\n\n"
            f"Generate the next question. [session-nonce: {nonce}]"
        )

    response = await client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.9,
        max_tokens=256,
    )
    return (response.choices[0].message.content or "").strip()


async def evaluate_answer(
    question: str,
    answer_transcript: str,
    job_role: str,
) -> dict:
    client = get_groq_client()
    prompt = (
        f"You are a senior {job_role} interviewer. Evaluate the following answer to the question.\n\n"
        f"Question: {question}\n\n"
        f"Candidate Answer: {answer_transcript}\n\n"
        "Respond in JSON with these exact keys:\n"
        '  "score": <float 0-10>,\n'
        '  "strengths": <string>,\n'
        '  "improvements": <string>,\n'
        '  "verdict": <"strong" | "acceptable" | "weak">'
    )
    response = await client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)
