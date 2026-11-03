from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RevalidationPolicyInput(BaseModel):
    """中文：定义“revalidation·策略·input”类，封装该职责相关的数据与行为。
    English: Defines the revalidation policy input class and encapsulates data and behavior for that responsibility.
    """
    policy_key: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    cadence_hours: int = Field(default=720, ge=1, le=8760)
    max_items_per_run: int = Field(default=50, ge=1, le=500)
    subject: str = Field(default="math", min_length=1, max_length=32)
    topic_code: str | None = Field(default=None, max_length=80)
    problem_type: str | None = Field(default=None, max_length=64)
    execution_model_version_id: str
    review_model_version_id: str
    condition_prompt_version_id: str
    solver_prompt_version_id: str
    review_prompt_version_id: str
    sympy_verifier_version_id: str
    numeric_verifier_version_id: str
    duplicate_verifier_version_id: str
    leakage_verifier_version_id: str
    next_run_at: datetime
    config: dict[str, Any] = Field(default_factory=dict)


class RevalidationPolicyView(RevalidationPolicyInput):
    """中文：定义“revalidation·策略·view”类，封装该职责相关的数据与行为。
    English: Defines the revalidation policy view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RevalidationItemView(BaseModel):
    """中文：定义“revalidation·item·view”类，封装该职责相关的数据与行为。
    English: Defines the revalidation item view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    run_id: str
    problem_id: str
    solution_id: str | None = None
    maintenance_job_id: str | None = None
    problem_content_hash: str
    solution_content_hash: str | None = None
    status: Literal[
        "queued", "suppressing", "validating", "tool_verification",
        "ai_review", "admission", "passed", "failed", "inconclusive",
    ]
    outcome: Literal["passed", "failed", "inconclusive"] | None = None
    tool_evidence_ids: list[str] = Field(default_factory=list)
    condition_evidence_id: str | None = None
    solution_independence_evidence_id: str | None = None
    ai_review_evidence_id: str | None = None
    admission_evidence_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RevalidationRunView(BaseModel):
    """中文：定义“revalidation·执行·view”类，封装该职责相关的数据与行为。
    English: Defines the revalidation run view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    policy_id: str
    run_key: str
    trigger_type: Literal["scheduled", "manual"]
    status: Literal[
        "pending", "running", "completed", "partial_failed", "failed", "cancelled"
    ]
    scheduled_for: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    selected_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    last_error_code: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    items: list[RevalidationItemView] = Field(default_factory=list)


class RevalidationDueRunSummary(BaseModel):
    """中文：定义“revalidation·due·执行·summary”类，封装该职责相关的数据与行为。
    English: Defines the revalidation due run summary class and encapsulates data and behavior for that responsibility.
    """
    selected_policy_count: int = Field(ge=0)
    run_ids: list[str] = Field(default_factory=list)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)


class RevalidationScope(BaseModel):
    """中文：定义“revalidation·范围”类，封装该职责相关的数据与行为。
    English: Defines the revalidation scope class and encapsulates data and behavior for that responsibility.
    """
    policy_key: str | None = None
    force: bool = False

    @model_validator(mode="after")
    def validate_force(self) -> "RevalidationScope":
        """中文：处理“验证·force”相关操作。
        English: Handles the validate force operation.
        """
        if self.force and not self.policy_key:
            raise ValueError("force requires policy_key")
        return self
