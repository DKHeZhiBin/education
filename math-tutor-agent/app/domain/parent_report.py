from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.schemas import LearningRecord


class ParentReportSampleScope(BaseModel):
    """中文：定义“parent·报告·sample·范围”类，封装该职责相关的数据与行为。
    English: Defines the parent report sample scope class and encapsulates data and behavior for that responsibility.
    """
    status: Literal["available", "no_samples"]
    scope_type: Literal["all_completed_records"] = "all_completed_records"
    completed_record_count: int = Field(ge=0)
    knowledge_evidence_count: int = Field(ge=0)
    first_record_date: str | None = None
    last_record_date: str | None = None
    subjects: list[str] = Field(default_factory=list)
    grades: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ParentReportOverview(BaseModel):
    """中文：定义“parent·报告·overview”类，封装该职责相关的数据与行为。
    English: Defines the parent report overview class and encapsulates data and behavior for that responsibility.
    """
    completed_questions: int = Field(ge=0)
    subjects: list[str] = Field(default_factory=list)
    mistakes_to_review: int = Field(ge=0)


class ParentKnowledgeSummary(BaseModel):
    """中文：定义“parent·知识·summary”类，封装该职责相关的数据与行为。
    English: Defines the parent knowledge summary class and encapsulates data and behavior for that responsibility.
    """
    code: str
    name: str
    evidence_count: int = Field(ge=1)
    mistake_count: int = Field(ge=0)
    effective_attempt_count: int = Field(ge=0)
    highest_hint_level: int = Field(ge=0, le=4)
    mastered_evidence_count: int = Field(ge=0)
    latest_mastery: str
    latest_record_date: str


class ParentReportResponse(BaseModel):
    """中文：定义“parent·报告·响应”类，封装该职责相关的数据与行为。
    English: Defines the parent report response class and encapsulates data and behavior for that responsibility.
    """
    sample_scope: ParentReportSampleScope
    overview: ParentReportOverview
    knowledge_points: list[str] = Field(default_factory=list)
    knowledge_summary: list[ParentKnowledgeSummary] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    records: list[LearningRecord] = Field(default_factory=list)
    note: str
