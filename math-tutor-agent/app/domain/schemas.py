from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.product_scope import MVP_GRADE_LABEL, MVP_SUBJECT_LABEL
from app.domain.tutoring import TutorReply, TutoringStatus


def new_id() -> str:
    """中文：处理“new·id”相关操作。
    English: Handles the new id operation.
    """
    return str(uuid4())


class LearnerProfile(BaseModel):
    """中文：定义“learner·profile”类，封装该职责相关的数据与行为。
    English: Defines the learner profile class and encapsulates data and behavior for that responsibility.
    """
    grade: str = MVP_GRADE_LABEL
    subject: str = MVP_SUBJECT_LABEL


class Message(BaseModel):
    """中文：定义“message”类，封装该职责相关的数据与行为。
    English: Defines the message class and encapsulates data and behavior for that responsibility.
    """
    id: str = Field(default_factory=new_id)
    role: str
    content: str
    intent: str | None = None
    client_turn_id: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeLearningEvidence(BaseModel):
    """中文：定义“知识·学习·evidence”类，封装该职责相关的数据与行为。
    English: Defines the knowledge learning evidence class and encapsulates data and behavior for that responsibility.
    """
    code: str = ""
    name: str
    relation_type: str = "primary"
    mistake_detected: bool = False
    error_category: str = ""
    error_reason: str = ""
    hint_level: int = Field(default=0, ge=0, le=4)
    effective_attempt_count: int = Field(default=0, ge=0)
    mastery: str = "待巩固"
    evidence: str = ""


class LearningRecord(BaseModel):
    """中文：定义“学习·记录”类，封装该职责相关的数据与行为。
    English: Defines the learning record class and encapsulates data and behavior for that responsibility.
    """
    id: str = Field(default_factory=new_id)
    date: str = Field(default_factory=lambda: datetime.now().date().isoformat())
    subject: str = MVP_SUBJECT_LABEL
    grade: str = MVP_GRADE_LABEL
    question: str
    learner_answer: str = ""
    error_category: str = ""
    error_reason: str = ""
    correct_approach: str = ""
    knowledge_tags: list[str] = Field(default_factory=list)
    knowledge_points: list[KnowledgeLearningEvidence] = Field(default_factory=list)
    difficulty: int = Field(default=2, ge=1, le=3)
    mastery: str = "待巩固"
    hint_level: int = Field(default=0, ge=0, le=4)
    attempt_count: int = Field(default=0, ge=0)
    review_count: int = 0
    next_review_at: datetime | None = None


class AgentArtifact(BaseModel):
    """中文：定义“智能体·artifact”类，封装该职责相关的数据与行为。
    English: Defines the agent artifact class and encapsulates data and behavior for that responsibility.
    """
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
    """中文：定义“tutoring·会话”类，封装该职责相关的数据与行为。
    English: Defines the tutoring session class and encapsulates data and behavior for that responsibility.
    """
    id: str = Field(default_factory=new_id)
    version: int = Field(default=0, ge=0)
    student_user_id: str
    knowledge_problem_id: str | None = Field(default=None, max_length=36)
    llm_model_id: str | None = Field(default=None, min_length=3, max_length=180)
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
    """中文：定义“创建·会话·请求”类，封装该职责相关的数据与行为。
    English: Defines the create session request class and encapsulates data and behavior for that responsibility.
    """
    question: str = Field(min_length=1, max_length=5000)
    problem_id: str | None = Field(default=None, max_length=36)
    llm_model_id: str | None = Field(default=None, min_length=3, max_length=180)


class CreateSessionResponse(BaseModel):
    """中文：定义“创建·会话·响应”类，封装该职责相关的数据与行为。
    English: Defines the create session response class and encapsulates data and behavior for that responsibility.
    """
    session: TutoringSession
    reply: TutorReply
    run_id: str
    trace: list[dict] = Field(default_factory=list)
    duration_ms: int = 0
    degraded: bool = False
    degradation_code: str | None = None
    degradation_reason: str | None = None


class TurnRequest(BaseModel):
    """中文：定义“turn·请求”类，封装该职责相关的数据与行为。
    English: Defines the turn request class and encapsulates data and behavior for that responsibility.
    """
    message: str = Field(min_length=1, max_length=5000)
    intent: str = "answer"
    client_turn_id: str = Field(min_length=1, max_length=64)


class TurnResponse(BaseModel):
    """中文：定义“turn·响应”类，封装该职责相关的数据与行为。
    English: Defines the turn response class and encapsulates data and behavior for that responsibility.
    """
    session: TutoringSession
    reply: TutorReply
    run_id: str
    trace: list[dict] = Field(default_factory=list)
    duration_ms: int = 0
    degraded: bool = False
    degradation_code: str | None = None
    degradation_reason: str | None = None


class SessionSummary(BaseModel):
    """中文：定义“会话·summary”类，封装该职责相关的数据与行为。
    English: Defines the session summary class and encapsulates data and behavior for that responsibility.
    """
    id: str
    question: str
    status: TutoringStatus
    llm_model_id: str | None = None
    updated_at: datetime
