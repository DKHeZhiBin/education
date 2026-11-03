from enum import StrEnum


class UserRole(StrEnum):
    """中文：定义“用户·role”类，封装该职责相关的数据与行为。
    English: Defines the user role class and encapsulates data and behavior for that responsibility.
    """
    STUDENT = "student"
    GUARDIAN = "guardian"
    ADMIN = "admin"
    TEACHER_REVIEWER = "teacher_reviewer"


class AccountStatus(StrEnum):
    """中文：定义“account·状态”类，封装该职责相关的数据与行为。
    English: Defines the account status class and encapsulates data and behavior for that responsibility.
    """
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class GradeBand(StrEnum):
    """中文：定义“grade·band”类，封装该职责相关的数据与行为。
    English: Defines the grade band class and encapsulates data and behavior for that responsibility.
    """
    PRIMARY_LOWER = "primary_lower"
    PRIMARY_UPPER = "primary_upper"
    MIDDLE = "middle"
    HIGH = "high"


class SessionStatus(StrEnum):
    """中文：定义“会话·状态”类，封装该职责相关的数据与行为。
    English: Defines the session status class and encapsulates data and behavior for that responsibility.
    """
    COLLECTING = "collecting"
    CLARIFYING = "clarifying"
    DIAGNOSING = "diagnosing"
    HINTING = "hinting"
    CHECKING_ATTEMPT = "checking_attempt"
    EXPLAINING = "explaining"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TurnIntent(StrEnum):
    """中文：定义“turn·intent”类，封装该职责相关的数据与行为。
    English: Defines the turn intent class and encapsulates data and behavior for that responsibility.
    """
    ANSWER = "answer"
    ASK_HINT = "ask_hint"
    ASK_SOLUTION = "ask_solution"
    PRACTICE = "practice"
    COMPLETE = "complete"


class AgentRunStatus(StrEnum):
    """中文：定义“智能体·执行·状态”类，封装该职责相关的数据与行为。
    English: Defines the agent run status class and encapsulates data and behavior for that responsibility.
    """
    RUNNING = "running"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"


class AgentStepStatus(StrEnum):
    """中文：定义“智能体·step·状态”类，封装该职责相关的数据与行为。
    English: Defines the agent step status class and encapsulates data and behavior for that responsibility.
    """
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MasteryStatus(StrEnum):
    """中文：定义“掌握度·状态”类，封装该职责相关的数据与行为。
    English: Defines the mastery status class and encapsulates data and behavior for that responsibility.
    """
    TO_REVIEW = "to_review"
    REVIEWING = "reviewing"
    MASTERED = "mastered"


class KnowledgeRelationType(StrEnum):
    """中文：定义“知识·relation·type”类，封装该职责相关的数据与行为。
    English: Defines the knowledge relation type class and encapsulates data and behavior for that responsibility.
    """
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    MISCONCEPTION = "misconception"


class ReviewResult(StrEnum):
    """中文：定义“复核·结果”类，封装该职责相关的数据与行为。
    English: Defines the review result class and encapsulates data and behavior for that responsibility.
    """
    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"


class ReportPeriodType(StrEnum):
    """中文：定义“报告·period·type”类，封装该职责相关的数据与行为。
    English: Defines the report period type class and encapsulates data and behavior for that responsibility.
    """
    SESSION = "session"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReportStatus(StrEnum):
    """中文：定义“报告·状态”类，封装该职责相关的数据与行为。
    English: Defines the report status class and encapsulates data and behavior for that responsibility.
    """
    DRAFT = "draft"
    READY = "ready"
    DELIVERED = "delivered"


class MediaType(StrEnum):
    """中文：定义“media·type”类，封装该职责相关的数据与行为。
    English: Defines the media type class and encapsulates data and behavior for that responsibility.
    """
    IMAGE = "image"
    AUDIO = "audio"
    TTS = "tts"


class ProcessingStatus(StrEnum):
    """中文：定义“processing·状态”类，封装该职责相关的数据与行为。
    English: Defines the processing status class and encapsulates data and behavior for that responsibility.
    """
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
