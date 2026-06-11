"""
backend/app/api/routes/interview.py
=====================================
Interview routes — HTTP session management + Real-Time Multimodal WebSocket engine.

WebSocket protocol (client → server)
--------------------------------------
  bytes                                     Raw PCM audio (16-bit LE, 16 kHz, mono)
                                            → forwarded directly to Deepgram STT

  {"type": "video_frame", "data": "..."}   Base64-encoded JPEG/PNG from the browser
                                            canvas (captured every N seconds by the
                                            frontend) → passed to EmotionAnalyzer CNN

  {"type": "end_answer"}                   Candidate finished answering current question
  {"type": "ping"}                         Keepalive heartbeat

WebSocket protocol (server → client)
--------------------------------------
  {"type": "ai_question",        "text": str, "question_index": int, "total_questions": int}
  {"type": "transcript",         "text": str, "is_final": bool}
  {"type": "generating_report"}
  {"type": "interview_complete", "session_id": str, "overall_score": float}
  {"type": "error",              "message": str}
  {"type": "pong"}
"""

import asyncio
import json
from datetime import datetime
from typing import List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.api.deps import get_current_user, get_database
from app.core.database import get_database as _get_db
from app.ml.emotion_analysis import emotion_analyzer          # Phase 3C — CNN inference
from app.models.interview import (
    InterviewCreate,
    InterviewInDB,
    InterviewResponse,
    InterviewStatus,
    QuestionAnswer,
)
from app.services.deepgram_service import get_deepgram_client, build_live_options, build_live_options_webm
from app.services.evaluation_service import generate_report_card, save_report_to_db
from app.services.groq_service import (
    generate_next_question,
    evaluate_answer,
)
from app.services.resume_service import parse_resume
from deepgram import LiveTranscriptionEvents

router = APIRouter(prefix="/interviews", tags=["interviews"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    """Convert ObjectId _id to string for JSON serialisation."""
    doc["_id"] = str(doc["_id"])
    return doc


# ── Pydantic request body ─────────────────────────────────────────────────────

class SubmitAnswerBody(BaseModel):
    question_id: str
    transcript:  str


class ScheduleInterviewBody(BaseModel):
    candidate_email: str
    candidate_name:  str = ""
    job_role:        str
    interview_type:  str = "technical"
    difficulty:      str = "intermediate"
    num_questions:   int = 5


# ── HTTP endpoints ────────────────────────────────────────────────────────────

@router.post("/parse-resume")
async def parse_resume_endpoint(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Accept a PDF resume, extract skills and projects via Groq, return structured JSON."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5 MB.")
    return await parse_resume(file_bytes)


@router.post("/schedule", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def schedule_interview(
    body: ScheduleInterviewBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Recruiter schedules an interview for a candidate identified by email."""
    candidate = await db["users"].find_one({"email": body.candidate_email})
    if not candidate:
        raise HTTPException(status_code=404, detail="No candidate found with that email address.")

    qas = [
        QuestionAnswer(question_id=str(ObjectId()), question_text="")
        for _ in range(body.num_questions)
    ]
    interview = InterviewInDB(
        user_id=str(candidate["firebase_uid"]),
        job_role=body.job_role,
        interview_type=body.interview_type,
        difficulty=body.difficulty,
        num_questions=body.num_questions,
        status=InterviewStatus.SCHEDULED,
        scheduled_by=current_user["uid"],
        candidate_name=body.candidate_name.strip() or None,
        questions_answers=qas,
    )
    doc    = interview.model_dump(by_alias=True, exclude={"id"})
    result = await db["interviews"].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return InterviewResponse(id=doc["_id"], **{k: v for k, v in doc.items() if k != "_id"})


@router.get("/recruiter", response_model=List[InterviewResponse])
async def list_recruiter_interviews(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Return all interviews scheduled by the current recruiter."""
    uid    = current_user["uid"]
    cursor = db["interviews"].find({"scheduled_by": uid}).sort("created_at", -1).limit(100)
    results = []
    async for doc in cursor:
        doc = _serialize(doc)
        results.append(InterviewResponse(id=doc["_id"], **{k: v for k, v in doc.items() if k != "_id"}))
    return results


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Delete an interview. Allowed for the candidate who owns it or the recruiter who scheduled it."""
    doc = await db["interviews"].find_one({"_id": ObjectId(interview_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Interview not found.")
    uid = current_user["uid"]
    if doc.get("user_id") != uid and doc.get("scheduled_by") != uid:
        raise HTTPException(status_code=403, detail="Not authorised to delete this interview.")
    await db["interviews"].delete_one({"_id": ObjectId(interview_id)})


@router.post("/", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    payload: InterviewCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Create a new interview session. Questions are generated live during the session."""
    # Placeholder QA entries — question_text is filled in dynamically by the WS engine
    qas = [
        QuestionAnswer(question_id=str(ObjectId()), question_text="")
        for _ in range(payload.num_questions)
    ]

    interview = InterviewInDB(
        **payload.model_dump(),
        status=InterviewStatus.PENDING,
        questions_answers=qas,
    )
    doc    = interview.model_dump(by_alias=True, exclude={"id"})
    result = await db["interviews"].insert_one(doc)
    doc["_id"] = str(result.inserted_id)

    return InterviewResponse(id=doc["_id"], **{k: v for k, v in doc.items() if k != "_id"})


@router.get("/", response_model=List[InterviewResponse])
async def list_interviews(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    uid    = current_user["uid"]
    cursor = db["interviews"].find({"user_id": uid}).sort("created_at", -1).limit(50)
    results = []
    async for doc in cursor:
        doc = _serialize(doc)
        results.append(InterviewResponse(id=doc["_id"], **{k: v for k, v in doc.items() if k != "_id"}))
    return results


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await db["interviews"].find_one({"_id": ObjectId(interview_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Interview not found.")
    doc = _serialize(doc)
    return InterviewResponse(id=doc["_id"], **{k: v for k, v in doc.items() if k != "_id"})


@router.patch("/{interview_id}/resume-context")
async def set_resume_context(
    interview_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Candidate attaches parsed resume context to an existing (scheduled) interview."""
    result = await db["interviews"].update_one(
        {"_id": ObjectId(interview_id)},
        {"$set": {"resume_context": payload}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Interview not found.")
    return {"ok": True}


@router.post("/{interview_id}/start")
async def start_interview(
    interview_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    result = await db["interviews"].update_one(
        {"_id": ObjectId(interview_id)},
        {"$set": {"status": InterviewStatus.IN_PROGRESS, "started_at": datetime.utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Interview not found.")
    return {"message": "Interview started."}


@router.post("/{interview_id}/submit-answer")
async def submit_answer(
    interview_id: str,
    body: SubmitAnswerBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Evaluate a single answer via Groq and persist it."""
    doc = await db["interviews"].find_one({"_id": ObjectId(interview_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Interview not found.")

    qa = next(
        (q for q in doc["questions_answers"] if q["question_id"] == body.question_id),
        None,
    )
    if not qa:
        raise HTTPException(status_code=404, detail="Question not found.")

    evaluation = await evaluate_answer(
        question=qa["question_text"],
        answer_transcript=body.transcript,
        job_role=doc["job_role"],
    )

    await db["interviews"].update_one(
        {"_id": ObjectId(interview_id), "questions_answers.question_id": body.question_id},
        {
            "$set": {
                "questions_answers.$.answer_transcript": body.transcript,
                "questions_answers.$.llm_score":         evaluation.get("score"),
                "questions_answers.$.llm_feedback": (
                    evaluation.get("strengths", "") + "\n" + evaluation.get("improvements", "")
                ),
            }
        },
    )
    return evaluation


@router.post("/{interview_id}/complete")
async def complete_interview(
    interview_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Compute the composite score and mark the session as completed."""
    from ml.response_evaluator import compute_composite_score

    doc = await db["interviews"].find_one({"_id": ObjectId(interview_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Interview not found.")

    composite_scores = []
    for qa in doc.get("questions_answers", []):
        llm_score = qa.get("llm_score")
        if llm_score is None:
            continue
        composite_scores.append(
            compute_composite_score(
                llm_score=llm_score,
                emotion_scores=qa.get("emotion_scores"),
                speech_metrics=qa.get("speech_metrics"),
            )
        )

    overall = round(sum(composite_scores) / len(composite_scores), 2) if composite_scores else None

    await db["interviews"].update_one(
        {"_id": ObjectId(interview_id)},
        {
            "$set": {
                "status":        InterviewStatus.COMPLETED,
                "completed_at":  datetime.utcnow(),
                "overall_score": overall,
            }
        },
    )
    return {"message": "Interview completed.", "overall_score": overall}


# ── WebSocket — Real-Time Multimodal Interview Engine ─────────────────────────

@router.websocket("/ws/{session_id}")
async def interview_websocket(
    websocket: WebSocket,
    session_id: str,
):
    """
    Real-time multimodal interview WebSocket endpoint.

    Multimodal data streams handled
    --------------------------------
    1. AUDIO  (bytes)        → Deepgram STT → transcript → relay to client
    2. VIDEO  (JSON frame)   → EmotionAnalyzer CNN → update session emotion_stats
    3. CONTROL (JSON text)   → end_answer / ping

    Interview flow
    --------------
    1. Fetch session from MongoDB (job_role, questions, difficulty).
    2. Open a Deepgram live-transcription connection.
    3. Send the first pre-generated question to the client.
    4. Loop:
         a. bytes → forward to Deepgram.
         b. {"type":"video_frame"} → run CNN inference → update emotion_stats.
         c. Deepgram callbacks → asyncio.Queue → relay transcripts to client.
         d. {"type":"end_answer"} → save transcript, move to next question.
    5. When all questions answered:
         → build Multimodal Report Card (text + emotion_stats) via Groq
         → save to MongoDB
         → send "interview_complete" to client.
    """
    await websocket.accept()

    # WebSocket handlers cannot use FastAPI Depends() — get DB directly
    db = _get_db()

    # ── Load the interview session from MongoDB ───────────────────────────────
    try:
        doc = await db["interviews"].find_one({"_id": ObjectId(session_id)})
    except Exception:
        await websocket.send_json({"type": "error", "message": "Invalid session ID."})
        await websocket.close()
        return

    if not doc:
        await websocket.send_json({"type": "error", "message": "Session not found."})
        await websocket.close()
        return

    job_role       = doc["job_role"]
    interview_type = doc.get("interview_type", "technical")
    difficulty     = doc.get("difficulty", "intermediate")
    total_q        = doc.get("num_questions", 5)
    stored_qas     = doc.get("questions_answers", [])
    resume_context = doc.get("resume_context")   # {"skills": [...], "projects": [...]}

    # ── Deepgram live-transcription — created lazily per question ────────────
    # Connecting at session start causes a 1011 timeout because Deepgram
    # receives no audio during TTS playback. Instead we open a fresh connection
    # when the first audio bytes arrive and close it on end_answer.
    transcript_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    dg_state: dict = {"connection": None, "active": False}

    def on_transcript(self, result, **kwargs):
        """Deepgram callback — runs in Deepgram's thread, pushes to queue."""
        try:
            alt  = result.channel.alternatives[0]
            text = alt.transcript
            if text:
                asyncio.run_coroutine_threadsafe(
                    transcript_queue.put({"text": text, "is_final": result.is_final}),
                    loop,
                )
        except Exception:
            pass

    def on_error(self, error, **kwargs):
        dg_state["active"] = False   # Mark dead so next audio byte triggers reconnect

    def start_deepgram():
        dg_client = get_deepgram_client()
        conn = dg_client.listen.live.v("1")
        conn.on(LiveTranscriptionEvents.Transcript, on_transcript)
        conn.on(LiveTranscriptionEvents.Error, on_error)
        conn.start(build_live_options())
        dg_state["connection"] = conn
        dg_state["active"] = True

    def stop_deepgram():
        dg_state["active"] = False
        conn = dg_state.get("connection")
        if conn:
            try:
                conn.finish()
            except Exception:
                pass
            dg_state["connection"] = None

    # ── Session state ─────────────────────────────────────────────────────────
    question_index:         int        = 0
    accumulated_transcript: str        = ""
    qa_history:             list[dict] = []
    active_question_text:   str        = ""   # text of the question currently being answered

    # Phase 3C — running emotion counter for the entire session.
    # Structure: {"Happiness": 15, "Neutral": 42, "Fear": 5, ...}
    # Only frames where a face was detected are counted here.
    emotion_stats: dict[str, int] = {}

    # Total video frames received (with or without a face).  Used to compute
    # presence_rate = sum(emotion_stats.values()) / total_video_frames.
    total_video_frames: int = 0

    # ── Generate and send the first question ─────────────────────────────────
    # Always generate dynamically — never use pre-stored text — so every session
    # gets a unique, adaptive question set instead of the same pre-generated list.
    active_question_text = await generate_next_question(
        job_role=job_role,
        interview_type=interview_type,
        difficulty=difficulty,
        qa_history=[],
        question_number=1,
        total_questions=total_q,
        resume_context=resume_context,
    )

    # Persist the generated question text so the report page can reference it later
    if stored_qas:
        await db["interviews"].update_one(
            {"_id": ObjectId(session_id), "questions_answers.question_id": stored_qas[0]["question_id"]},
            {"$set": {"questions_answers.$.question_text": active_question_text}},
        )

    await websocket.send_json({
        "type":            "ai_question",
        "text":            active_question_text,
        "question_index":  0,
        "total_questions": total_q,
    })

    # Mark session as in-progress
    await db["interviews"].update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"status": "in_progress", "started_at": datetime.utcnow()}},
    )

    # ── Background coroutine: relay Deepgram transcripts to client ────────────
    async def relay_transcripts():
        nonlocal accumulated_transcript
        while True:
            item = await transcript_queue.get()
            if item is None:       # None is the shutdown sentinel
                break
            text     = item["text"]
            is_final = item["is_final"]
            if is_final:
                accumulated_transcript += (" " + text)
            try:
                await websocket.send_json({
                    "type":     "transcript",
                    "text":     text,
                    "is_final": is_final,
                })
            except Exception:
                break   # Client disconnected — exit relay loop

    relay_task = asyncio.create_task(relay_transcripts())

    # ── Main receive loop ─────────────────────────────────────────────────────
    try:
        while True:
            message = await websocket.receive()

            # Client closed the connection
            if message["type"] == "websocket.disconnect":
                break

            # ── AUDIO: raw PCM bytes → forward to Deepgram ───────────────────
            if message.get("bytes"):
                audio_bytes = message["bytes"]
                if not dg_state["active"]:
                    start_deepgram()
                if dg_state["connection"]:
                    dg_state["connection"].send(audio_bytes)
                continue

            # ── TEXT: JSON control messages ───────────────────────────────────
            raw_text = message.get("text", "")
            if not raw_text:
                continue

            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                continue    # Ignore malformed messages

            msg_type = data.get("type")

            # ── Keepalive ─────────────────────────────────────────────────────
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # ── VIDEO FRAME: base64 image → CNN → update emotion_stats ────────
            #
            # The frontend should send this message every 2-3 seconds by
            # capturing a frame from the <video> element via an HTML canvas:
            #
            #   canvas.getContext("2d").drawImage(videoEl, 0, 0, 224, 224);
            #   const b64 = canvas.toDataURL("image/jpeg", 0.7);
            #   ws.send(JSON.stringify({ type: "video_frame", data: b64 }));
            #
            if msg_type == "video_frame":
                b64_frame = data.get("data", "")
                if b64_frame and emotion_analyzer._loaded:
                    total_video_frames += 1
                    # analyze_frame() returns None when no face is detected.
                    # Only count frames where a face was actually present so
                    # that absent/off-camera frames don't inflate "Neutral".
                    detected_emotion = await emotion_analyzer.analyze_frame(b64_frame)
                    if detected_emotion:
                        emotion_stats[detected_emotion] = (
                            emotion_stats.get(detected_emotion, 0) + 1
                        )
                continue    # video_frame is fire-and-forget; no response needed

            # ── END_ANSWER: candidate finished speaking ───────────────────────
            if msg_type == "end_answer":
                stop_deepgram()   # Close current connection; will reconnect on next audio
                answer                 = accumulated_transcript.strip()
                accumulated_transcript = ""    # Reset for the next question

                # Persist the answer transcript using the current question's slot
                if stored_qas and question_index < len(stored_qas):
                    q_id = stored_qas[question_index]["question_id"]
                    await db["interviews"].update_one(
                        {
                            "_id": ObjectId(session_id),
                            "questions_answers.question_id": q_id,
                        },
                        {"$set": {"questions_answers.$.answer_transcript": answer}},
                    )
                else:
                    q_id = None

                # Append to in-memory Q&A history using the actively spoken question
                qa_history.append({
                    "question_id": q_id,
                    "question":    active_question_text,
                    "answer":      answer,
                })

                question_index += 1

                if question_index < total_q:
                    # ── Generate the next question dynamically ────────────────
                    # qa_history now contains all previous turns, so the LLM
                    # can ask a contextually relevant follow-up that avoids
                    # repeating topics already covered.
                    active_question_text = await generate_next_question(
                        job_role=job_role,
                        interview_type=interview_type,
                        difficulty=difficulty,
                        qa_history=qa_history,
                        question_number=question_index + 1,
                        total_questions=total_q,
                        resume_context=resume_context,
                    )

                    # Persist question text to MongoDB for the report page
                    if stored_qas and question_index < len(stored_qas):
                        await db["interviews"].update_one(
                            {
                                "_id": ObjectId(session_id),
                                "questions_answers.question_id": stored_qas[question_index]["question_id"],
                            },
                            {"$set": {"questions_answers.$.question_text": active_question_text}},
                        )

                    await websocket.send_json({
                        "type":            "ai_question",
                        "text":            active_question_text,
                        "question_index":  question_index,
                        "total_questions": total_q,
                    })

                else:
                    # ── All questions answered — generate Multimodal Report Card
                    await websocket.send_json({"type": "generating_report"})

                    # presence_stats lets the LLM (and report page) know how
                    # often the candidate was actually on camera.
                    presence_stats = {
                        "total_frames":    total_video_frames,
                        "frames_with_face": sum(emotion_stats.values()),
                    }

                    # Pass Q&A transcript, CNN emotion stats, AND presence data
                    # so the LLM can flag absence as a behavioural signal.
                    report = await generate_report_card(
                        job_role=job_role,
                        interview_type=interview_type,
                        qa_history=qa_history,
                        emotion_stats=emotion_stats,
                        presence_stats=presence_stats,
                    )

                    # Persist report + raw emotion_stats + presence_stats
                    await save_report_to_db(
                        db,
                        session_id,
                        report,
                        qa_history,
                        emotion_stats=emotion_stats,
                        presence_stats=presence_stats,
                    )

                    await websocket.send_json({
                        "type":          "interview_complete",
                        "session_id":    session_id,
                        "overall_score": report.get("overall_score"),
                    })
                    break   # Clean exit — interview is done

    except WebSocketDisconnect:
        pass   # Normal — client navigated away or closed the tab
    except Exception as exc:
        try:
            await websocket.send_json({
                "type":    "error",
                "message": "Server error — interview ended unexpectedly.",
            })
        except Exception:
            pass
    finally:
        # Shut down the transcript relay coroutine gracefully
        await transcript_queue.put(None)   # Sentinel value to stop relay_task
        relay_task.cancel()
        stop_deepgram()


# ── Legacy STT-only stream (used by Phase 2 frontend useDeepgramSTT hook) ─────

@router.websocket("/{interview_id}/stream")
async def stream_transcript(
    websocket: WebSocket,
    interview_id: str,
):
    """
    STT-only WebSocket — forwards raw PCM audio to Deepgram and streams
    transcript events back to the client.
    Kept for backwards-compatibility with the Phase 2 useDeepgramSTT hook.
    """
    await websocket.accept()
    dg_client = get_deepgram_client()
    loop      = asyncio.get_event_loop()

    try:
        connection = dg_client.listen.live.v("1")

        def on_message(self, result, **kwargs):
            try:
                sentence = result.channel.alternatives[0].transcript
                if sentence:
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_json({
                            "type":     "transcript",
                            "text":     sentence,
                            "is_final": result.is_final,
                        }),
                        loop,
                    )
            except Exception:
                pass

        connection.on(LiveTranscriptionEvents.Transcript, on_message)
        connection.start(build_live_options())

        while True:
            audio_chunk = await websocket.receive_bytes()
            connection.send(audio_chunk)

    except WebSocketDisconnect:
        pass
    finally:
        try:
            connection.finish()
        except Exception:
            pass
