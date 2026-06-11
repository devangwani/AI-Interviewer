from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class InterviewStatus(str, Enum):
    SCHEDULED = "scheduled"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InterviewType(str, Enum):
    TECHNICAL = "technical"
    BEHAVIOURAL = "behavioural"
    SYSTEM_DESIGN = "system_design"
    HR = "hr"


class QuestionAnswer(BaseModel):
    question_id: str
    question_text: str
    answer_transcript: Optional[str] = None
    answer_audio_url: Optional[str] = None
    emotion_scores: Optional[dict] = None
    speech_metrics: Optional[dict] = None
    llm_score: Optional[float] = None
    llm_feedback: Optional[str] = None
    duration_seconds: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class InterviewCreate(BaseModel):
    user_id: str
    job_role: str
    interview_type: InterviewType = InterviewType.TECHNICAL
    difficulty: str = "medium"
    num_questions: int = Field(default=5, ge=1, le=20)
    resume_context: Optional[dict] = None   # {"skills": [...], "projects": [...]}
    candidate_name: Optional[str] = None    # set by recruiter when scheduling


class InterviewInDB(InterviewCreate):
    id: Optional[str] = Field(default=None, alias="_id")
    status: InterviewStatus = InterviewStatus.PENDING
    scheduled_by: Optional[str] = None   # firebase_uid of the recruiter who created this
    questions_answers: List[QuestionAnswer] = []
    overall_score: Optional[float] = None
    overall_feedback: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class InterviewResponse(BaseModel):
    id: str
    user_id: str
    job_role: str
    interview_type: InterviewType
    difficulty: str
    num_questions: int
    status: InterviewStatus
    questions_answers: List[QuestionAnswer]
    overall_score: Optional[float]
    overall_feedback: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    resume_context: Optional[dict] = None
    scheduled_by: Optional[str] = None
    candidate_name: Optional[str] = None
