from pydantic import BaseModel, Field
from typing import Literal

from app.domain.schemas import TutoringSession
from app.domain.tutoring import TutorReply


class HarnessBudget(BaseModel):
    """中文：定义“harness·budget”类，封装该职责相关的数据与行为。
    English: Defines the harness budget class and encapsulates data and behavior for that responsibility.
    """
    max_agent_calls: int = Field(default=8, ge=1, le=32)
    max_duration_ms: int = Field(default=60_000, ge=1000)


class HarnessTraceStep(BaseModel):
    """中文：定义“harness·trace·step”类，封装该职责相关的数据与行为。
    English: Defines the harness trace step class and encapsulates data and behavior for that responsibility.
    """
    run_id: str
    agent: str
    artifact_kind: str
    status: str
    confidence: float
    duration_ms: int


class HarnessRunResult(BaseModel):
    """中文：定义“harness·执行·结果”类，封装该职责相关的数据与行为。
    English: Defines the harness run result class and encapsulates data and behavior for that responsibility.
    """
    run_id: str
    session: TutoringSession
    reply: TutorReply
    trace: list[HarnessTraceStep]
    duration_ms: int
    degraded: bool = False
    degradation_code: Literal[
        "run_timeout",
        "llm_provider_unavailable",
        "knowledge_retrieval_degraded",
    ] | None = None
    degradation_reason: str | None = None


class HarnessSessionNotFound(Exception):
    """中文：定义“harness·会话·not·found”类，封装该职责相关的数据与行为。
    English: Defines the harness session not found class and encapsulates data and behavior for that responsibility.
    """
    pass


class HarnessBudgetExceeded(Exception):
    """中文：定义“harness·budget·exceeded”类，封装该职责相关的数据与行为。
    English: Defines the harness budget exceeded class and encapsulates data and behavior for that responsibility.
    """
    pass


class HarnessSessionBusy(Exception):
    """中文：定义“harness·会话·busy”类，封装该职责相关的数据与行为。
    English: Defines the harness session busy class and encapsulates data and behavior for that responsibility.
    """
    pass


class HarnessSessionConflict(Exception):
    """中文：定义“harness·会话·conflict”类，封装该职责相关的数据与行为。
    English: Defines the harness session conflict class and encapsulates data and behavior for that responsibility.
    """
    pass


class HarnessCoordinationUnavailable(Exception):
    """中文：定义“harness·coordination·unavailable”类，封装该职责相关的数据与行为。
    English: Defines the harness coordination unavailable class and encapsulates data and behavior for that responsibility.
    """
    pass


class HarnessPracticeUnavailable(Exception):
    """中文：定义“harness·练习·unavailable”类，封装该职责相关的数据与行为。
    English: Defines the harness practice unavailable class and encapsulates data and behavior for that responsibility.
    """
    pass
