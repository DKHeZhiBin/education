from pydantic import BaseModel, Field

from app.domain.schemas import TutoringSession
from app.domain.tutoring import TutorReply


class HarnessBudget(BaseModel):
    max_agent_calls: int = Field(default=8, ge=1, le=32)
    max_duration_ms: int = Field(default=60_000, ge=1000)


class HarnessTraceStep(BaseModel):
    run_id: str
    agent: str
    artifact_kind: str
    status: str
    confidence: float
    duration_ms: int


class HarnessRunResult(BaseModel):
    run_id: str
    session: TutoringSession
    reply: TutorReply
    trace: list[HarnessTraceStep]
    duration_ms: int
    degraded: bool = False
    degradation_reason: str | None = None


class HarnessSessionNotFound(Exception):
    pass


class HarnessBudgetExceeded(Exception):
    pass


class HarnessSessionBusy(Exception):
    pass


class HarnessSessionConflict(Exception):
    pass


class HarnessCoordinationUnavailable(Exception):
    pass
