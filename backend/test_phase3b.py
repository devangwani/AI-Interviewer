"""
Phase 3B test script.
Run from the backend/ directory:  python test_phase3b.py

Tests (in order):
  1. Groq — generate_next_question()
  2. Groq — generate_report_card()
  3. HTTP — POST /api/v1/interviews/  (create session)
  4. HTTP — POST /api/v1/interviews/{id}/start
  5. WebSocket — connect, send end_answer twice, receive interview_complete
"""

import asyncio
import json
import sys
import os

# Allow imports from the backend package
sys.path.insert(0, os.path.dirname(__file__))

import httpx
import websockets

PORT      = os.environ.get("TEST_PORT", "8001")
BASE_HTTP = f"http://localhost:{PORT}"
BASE_WS   = f"ws://localhost:{PORT}"

# ── helpers ───────────────────────────────────────────────────

def ok(label):  print(f"  [PASS] {label}")
def fail(label, reason): print(f"  [FAIL] {label}: {reason}"); sys.exit(1)

# ─────────────────────────────────────────────────────────────
# TEST 1 & 2 — Groq functions (no server needed)
# ─────────────────────────────────────────────────────────────

async def test_groq():
    print("\n=== Test 1: generate_next_question() ===")
    from app.services.groq_service import generate_next_question

    question = await generate_next_question(
        job_role="Backend Engineer",
        interview_type="technical",
        difficulty="intermediate",
        qa_history=[],          # first question — no history yet
        question_number=1,
        total_questions=3,
    )
    if not question or len(question) < 10:
        fail("generate_next_question", f"Got: {question!r}")
    ok(f"generate_next_question -> {question[:80]}...")

    print("\n=== Test 2: generate_report_card() ===")
    from app.services.evaluation_service import generate_report_card

    report = await generate_report_card(
        job_role="Backend Engineer",
        interview_type="technical",
        qa_history=[
            {"question": "What is a REST API?",
             "answer": "REST is an architectural style using HTTP methods."},
            {"question": "Explain async/await in Python.",
             "answer": "Async/await allows non-blocking code execution using coroutines."},
        ],
    )
    for key in ("overall_score", "verdict", "summary", "per_question"):
        if key not in report:
            fail("generate_report_card", f"Missing key: {key}")
    ok(f"generate_report_card -> verdict={report['verdict']}, score={report['overall_score']}")


# ─────────────────────────────────────────────────────────────
# TEST 3 & 4 — HTTP endpoints
# (No auth token — these will return 403, which proves routing works)
# ─────────────────────────────────────────────────────────────

async def test_http():
    print("\n=== Test 3: HTTP health check ===")
    async with httpx.AsyncClient(base_url=BASE_HTTP, timeout=10) as client:
        r = await client.get("/health")
        if r.status_code != 200:
            fail("GET /health", f"status={r.status_code}")
        ok(f"GET /health -> {r.json()}")

        print("\n=== Test 4: HTTP POST /api/v1/interviews/ (expects 403 without token) ===")
        r = await client.post("/api/v1/interviews/", json={
            "user_id": "test",
            "job_role": "Backend Engineer",
            "interview_type": "technical",
            "difficulty": "intermediate",
            "num_questions": 2,
        })
        # 403 = route exists, auth middleware rejected — correct behaviour
        if r.status_code not in (401, 403):
            fail("POST /api/v1/interviews/", f"Expected 401/403, got {r.status_code}: {r.text}")
        ok(f"POST /api/v1/interviews/ -> {r.status_code} (auth guard working)")

        print("\n=== Test 5: WebSocket route registered (import check) ===")
        from app.api.routes.interview import router as iv_router
        ws_paths = [r.path for r in iv_router.routes if hasattr(r, "path") and "ws" in r.path]
        if not ws_paths:
            fail("WebSocket route registered", "No WS route found in router")
        ok(f"WebSocket route registered at: {ws_paths}")


# ─────────────────────────────────────────────────────────────
# TEST 5 — WebSocket full flow (uses a real session in MongoDB)
# ─────────────────────────────────────────────────────────────

async def test_websocket():
    print("\n=== Test 6: WebSocket end-to-end (real MongoDB session) ===")

    # Create a real session in DB via the groq + motor stack directly
    from app.core.database import connect_db, get_database
    from app.services.groq_service import generate_interview_questions
    from app.models.interview import InterviewInDB, InterviewStatus, QuestionAnswer
    from bson import ObjectId

    await connect_db()
    db = get_database()

    questions = await generate_interview_questions(
        job_role="Backend Engineer",
        interview_type="technical",
        difficulty="intermediate",
        num_questions=2,
    )
    qas = [QuestionAnswer(question_id=str(ObjectId()), question_text=q) for q in questions]
    doc = InterviewInDB(
        user_id="test_user",
        job_role="Backend Engineer",
        interview_type="technical",
        difficulty="intermediate",
        num_questions=2,
        status=InterviewStatus.PENDING,
        questions_answers=qas,
    ).model_dump(by_alias=True, exclude={"id"})

    result = await db["interviews"].insert_one(doc)
    session_id = str(result.inserted_id)
    print(f"  Created test session: {session_id}")

    ws_url = f"{BASE_WS}/api/v1/interviews/ws/{session_id}"
    received = []

    async with websockets.connect(ws_url) as ws:
        # Should immediately receive the first ai_question
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        received.append(msg)
        if msg.get("type") != "ai_question":
            fail("WebSocket first message", f"Expected ai_question, got {msg}")
        ok(f"Received ai_question[0]: {msg['text'][:60]}...")

        # Simulate candidate answering Q1
        await ws.send(json.dumps({"type": "end_answer"}))

        # Should receive ai_question for Q2
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        # Might get a transcript first — skip non-question messages
        while msg.get("type") == "transcript":
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        received.append(msg)
        if msg.get("type") != "ai_question":
            fail("WebSocket second question", f"Expected ai_question, got {msg}")
        ok(f"Received ai_question[1]: {msg['text'][:60]}...")

        # Simulate candidate answering Q2
        await ws.send(json.dumps({"type": "end_answer"}))

        # Should receive generating_report then interview_complete
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        while msg.get("type") not in ("generating_report", "interview_complete", "error"):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))

        if msg.get("type") == "error":
            fail("WebSocket report generation", msg.get("message"))

        if msg.get("type") == "generating_report":
            ok("Received generating_report signal")
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))

        if msg.get("type") != "interview_complete":
            fail("WebSocket interview_complete", f"Got {msg}")
        ok(f"interview_complete -> overall_score={msg.get('overall_score')}")

    # Verify report was saved in MongoDB
    saved = await db["interviews"].find_one({"_id": ObjectId(session_id)})
    if saved.get("status") != "completed":
        fail("MongoDB report save", f"status={saved.get('status')}")
    if not saved.get("report_card"):
        fail("MongoDB report save", "report_card field missing")
    ok(f"MongoDB: session marked completed, report_card saved OK")

    # Clean up test session
    await db["interviews"].delete_one({"_id": ObjectId(session_id)})
    print(f"  Cleaned up test session: {session_id}")


# ─────────────────────────────────────────────────────────────

async def main():
    print("=" * 55)
    print("  Phase 3B — Backend Test Suite")
    print("=" * 55)
    print("Make sure the server is running on localhost:8000\n")

    await test_groq()
    await test_http()
    await test_websocket()

    print("\n" + "=" * 55)
    print("  All Phase 3B tests passed OK")
    print("=" * 55)

if __name__ == "__main__":
    asyncio.run(main())
