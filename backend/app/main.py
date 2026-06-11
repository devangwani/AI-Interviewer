from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import connect_db, close_db
from app.api.routes import auth, interview, analysis
from app.ml.emotion_analysis import emotion_analyzer

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    await connect_db()

    # Load the MobileNetV2 emotion model into memory.
    # If the .h5 file is not present yet, the server still starts — emotion
    # analysis will be silently skipped until the weights file is placed at:
    #   backend/app/ml/models/mobilenet_emotion_model.h5
    try:
        emotion_analyzer.load()
    except FileNotFoundError as exc:
        logger.warning(
            "[Startup] Emotion model not loaded — %s\n"
            "Video frame analysis will be disabled until the model file is present.",
            exc,
        )
    except Exception as exc:
        logger.error("[Startup] Emotion model failed to load: %s", exc)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await close_db()


app = FastAPI(
    title="Real-Time Multimodal AI Interview Framework",
    version="1.0.0",
    description="FastAPI backend powering AI-driven technical interviews with real-time speech, emotion, and LLM analysis.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(interview.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "ai-interviewer-backend"}
