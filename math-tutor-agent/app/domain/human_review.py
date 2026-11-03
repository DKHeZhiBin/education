from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ReviewDecision = Literal["approve", "revision_required", "quarantine", "inconclusive"]


class HumanReviewQueueRequest(BaseModel):
    """中文：定义“human·复核·queue·请求”类，封装该职责相关的数据与行为。
    English: Defines the human review queue request class and encapsulates data and behavior for that responsibility.
    """
    problem_ids: list[str] = Field(default_factory=list, max_length=200)
    include_quarantined: bool = True
    include_high_value: bool = True
    minimum_difficulty: int = Field(default=4, ge=1, le=5)
    limit: int = Field(default=50, ge=1, le=200)
    priority: int = Field(default=3, ge=1, le=5)
    review_requirements: dict[str, Any] = Field(default_factory=dict)


class HumanReviewTaskView(BaseModel):
    """中文：定义“human·复核·task·view”类，封装该职责相关的数据与行为。
    English: Defines the human review task view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    problem_id: str
    solution_id: str | None = None
    statement: str
    problem_content_hash: str
    solution_content_hash: str | None = None
    problem_status: str
    problem_status_version: int
    selection_reason: Literal["quarantined", "high_value", "manual"]
    priority: int
    value_score: int
    value_factors: list[str] = Field(default_factory=list)
    review_requirements: dict[str, Any] = Field(default_factory=dict)
    status: Literal["queued", "claimed", "completed", "cancelled", "stale"]
    version: int
    created_by_user_id: str
    assigned_to_user_id: str | None = None
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class HumanReviewTaskPage(BaseModel):
    """中文：定义“human·复核·task·page”类，封装该职责相关的数据与行为。
    English: Defines the human review task page class and encapsulates data and behavior for that responsibility.
    """
    items: list[HumanReviewTaskView]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class HumanReviewQueueResult(BaseModel):
    """中文：定义“human·复核·queue·结果”类，封装该职责相关的数据与行为。
    English: Defines the human review queue result class and encapsulates data and behavior for that responsibility.
    """
    selected_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    task_ids: list[str] = Field(default_factory=list)


class HumanReviewClaimRequest(BaseModel):
    """中文：定义“human·复核·claim·请求”类，封装该职责相关的数据与行为。
    English: Defines the human review claim request class and encapsulates data and behavior for that responsibility.
    """
    expected_version: int = Field(ge=1)


class HumanReviewSubmission(BaseModel):
    """中文：定义“human·复核·submission”类，封装该职责相关的数据与行为。
    English: Defines the human review submission class and encapsulates data and behavior for that responsibility.
    """
    expected_version: int = Field(ge=1)
    decision: ReviewDecision
    coverage_level: Literal["full", "partial", "none"]
    checklist: dict[str, Any] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    summary: str = Field(min_length=3, max_length=5000)

    @model_validator(mode="after")
    def validate_approval(self) -> "HumanReviewSubmission":
        """中文：处理“验证·approval”相关操作。
        English: Handles the validate approval operation.
        """
        if self.decision == "approve" and self.coverage_level != "full":
            raise ValueError("approve requires full human review coverage")
        return self


class HumanReviewResult(BaseModel):
    """中文：定义“human·复核·结果”类，封装该职责相关的数据与行为。
    English: Defines the human review result class and encapsulates data and behavior for that responsibility.
    """
    review_id: str
    task: HumanReviewTaskView
    evidence_id: str
    decision: ReviewDecision
    production_suppression_job_id: str | None = None
