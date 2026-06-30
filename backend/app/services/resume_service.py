import io
import json
import pdfplumber
from app.services.groq_service import get_groq_client


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from a PDF byte stream using pdfplumber."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


async def parse_resume(file_bytes: bytes) -> dict:
    """
    Extract skills and projects from a PDF resume.
    Returns {"skills": [...], "projects": [{"name": ..., "description": ...}, ...]}
    """
    raw_text = extract_text_from_pdf(file_bytes)

    if not raw_text.strip():
        return {"skills": [], "projects": []}

    # Truncate to ~6000 chars to stay within token budget
    truncated = raw_text[:6000]

    client = get_groq_client()
    response = await client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a resume parser. Extract structured information from the resume text. "
                    "Return ONLY a JSON object with two keys:\n"
                    '  "skills": an array of individual skill strings (programming languages, frameworks, tools, etc.)\n'
                    '  "projects": an array of objects with "name" (string) and "description" (1-2 sentence summary) fields.\n'
                    "Include up to 20 skills and up to 6 projects. If a field cannot be found return an empty array."
                ),
            },
            {
                "role": "user",
                "content": f"Resume text:\n\n{truncated}",
            },
        ],
        temperature=0.1,
        max_tokens=1024,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {"skills": [], "projects": []}

    return {
        "skills":   result.get("skills", []),
        "projects": result.get("projects", []),
    }
