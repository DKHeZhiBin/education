from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    GUARDIAN = "guardian"
    ADMIN = "admin"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class GradeBand(StrEnum):
    PRIMARY_LOWER = "primary_lower"
    PRIMARY_UPPER = "primary_upper"
    MIDDLE = "middle"
    HIGH = "high"


class SessionStatus(StrEnum):
    COLLECTING = "collecting"
    CLARIFYING = "clarifying"
    DIAGNOSING = "diagnosing"
    HINTING = "hinting"
    CHECKING_ATTEMPT = "checking_attempt"
    EXPLAINING = "explaining"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TurnIntent(StrEnum):
    ANSWER = "answer"
    ASK_HINT = "ask_hint"
    ASK_SOLUTION = "ask_solution"
    PRACTICE = "practice"
    COMPLETE = "complete"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"


class AgentStepStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MasteryStatus(StrEnum):
    TO_REVIEW = "to_review"
    REVIEWING = "reviewing"
    MASTERED = "mastered"


class KnowledgeRelationType(StrEnum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    MISCONCEPTION = "misconception"


class ReviewResult(StrEnum):
    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"


class ReportPeriodType(StrEnum):
    SESSION = "session"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    DELIVERED = "delivered"


class MediaType(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    TTS = "tts"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
