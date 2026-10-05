from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.tutoring import TutorReply, TutoringStatus


def new_id() -> str:
    return str(uuid4())


class LearnerProfile(BaseModel):
    grade: str = "初中"
    subject: str = "数学"


class Message(BaseModel):
    id: str = Field(default_factory=new_id)
    role: str
    content: str
    intent: str | None = None
    client_turn_id: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LearningRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    date: str = Field(default_factory=lambda: datetime.now().date().isoformat())
    subject: str = "数学"
    grade: str = "初中"
    question: str
    learner_answer: str = ""
    error_reason: str = ""
    correct_approach: str = ""
    knowledge_tags: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=2, ge=1, le=3)
    mastery: str = "待巩固"
    review_count: int = 0


class AgentArtifact(BaseModel):
    run_id: str = "legacy"
    schema_version: str = "1.0"
    agent: str
    kind: str
    payload: dict
    status: str = "completed"
    duration_ms: int = Field(default=0, ge=0)
    confidence: float = Field(default=0.7, ge=0, le=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TutoringSession(BaseModel):
    id: str = Field(default_factory=new_id)
    version: int = Field(default=0, ge=0)
    student_user_id: str
    knowledge_problem_id: str | None = Field(default=None, max_length=36)
    profile: LearnerProfile = Field(default_factory=LearnerProfile)
    question: str
    status: TutoringStatus = TutoringStatus.CLARIFYING
    hint_level: int = 0
    attempts: int = 0
    messages: list[Message] = Field(default_factory=list)
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    record: LearningRecord | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateSessionRequest(BaseModel):
    subject: str = "数学"
    grade: str = "初中"
    question: str = Field(min_length=1, max_length=5000)
    problem_id: str | None = Field(default=None, max_length=36)


class CreateSessionResponse(BaseModel):
    session: TutoringSession
    reply: TutorReply
    run_id: str
    trace: list[dict] = Field(default_factory=list)
    duration_ms: int = 0
    degraded: bool = False
    degradation_reason: str | None = None


class TurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    intent: str = "answer"
    client_turn_id: str = Field(min_length=1, max_length=64)


class TurnResponse(BaseModel):
    session: TutoringSession
    reply: TutorReply
    run_id: str
    trace: list[dict] = Field(default_factory=list)
    duration_ms: int = 0
    degraded: bool = False
    degradation_reason: str | None = None


class SessionSummary(BaseModel):
    id: str
    question: str
    status: TutoringStatus
    updated_at: datetime
