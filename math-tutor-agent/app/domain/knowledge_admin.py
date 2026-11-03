from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.generation import AdmissionEvidenceStatus, EvidenceProducerType
from app.domain.knowledge import ProblemContentStatus
from app.domain.index_lifecycle import IndexMaintenanceJobView


class ProblemAdminListItem(BaseModel):
    """中文：定义“题目·admin·列出·item”类，封装该职责相关的数据与行为。
    English: Defines the problem admin list item class and encapsulates data and behavior for that responsibility.
    """
    id: str
    statement: str
    subject: str
    grade_band: str | None
    problem_type: str
    content_type: str
    difficulty: int
    difficulty_source_types: list[str]
    grade_codes: list[str]
    knowledge_point_codes: list[str]
    curriculum_version_id: str | None
    content_status: ProblemContentStatus
    status_reason: str | None
    revision_attempts: int
    status_version: int
    status_changed_at: datetime
    source_reference_id: str
    source_title: str
    source_license_name: str
    generation_batch_id: str | None
    generation_batch_key: str | None
    updated_at: datetime


class ProblemAdminPage(BaseModel):
    """中文：定义“题目·admin·page”类，封装该职责相关的数据与行为。
    English: Defines the problem admin page class and encapsulates data and behavior for that responsibility.
    """
    items: list[ProblemAdminListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class ProblemStatusCount(BaseModel):
    """中文：定义“题目·状态·统计”类，封装该职责相关的数据与行为。
    English: Defines the problem status count class and encapsulates data and behavior for that responsibility.
    """
    status: ProblemContentStatus
    count: int = Field(ge=0)


class AdmissionEvidenceView(BaseModel):
    """中文：定义“admission·evidence·view”类，封装该职责相关的数据与行为。
    English: Defines the admission evidence view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    generation_batch_id: str
    evidence_type: str
    producer_type: EvidenceProducerType
    status: AdmissionEvidenceStatus
    is_blocking: bool
    summary: str
    solution_id: str | None
    model_version_id: str | None
    prompt_version_id: str | None
    verifier_version_id: str | None
    evidence_hash: str
    payload: dict[str, Any]
    created_at: datetime


class ProblemStatusTransitionView(BaseModel):
    """中文：定义“题目·状态·transition·view”类，封装该职责相关的数据与行为。
    English: Defines the problem status transition view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    from_status: ProblemContentStatus
    to_status: ProblemContentStatus
    reason: str | None
    revision_attempts: int
    status_version: int
    checked_requirements: list[str]
    actor_type: Literal["admin", "agent", "job", "system"]
    actor_id: str | None
    created_at: datetime


class GenerationAuditRecordView(BaseModel):
    """中文：定义“生成·audit·记录·view”类，封装该职责相关的数据与行为。
    English: Defines the generation audit record view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    stage: Literal[
        "generation",
        "condition_check",
        "independent_solving",
        "tool_verification",
        "independent_review",
        "revision",
        "admission",
        "indexing",
        "state_change",
        "other",
    ]
    event_type: str
    source_type: Literal["admission_evidence", "problem_status_transition"]
    source_id: str
    outcome: str
    summary: str
    solution_id: str | None = None
    model_version_id: str | None = None
    prompt_version_id: str | None = None
    verifier_version_id: str | None = None
    actor_type: str | None = None
    actor_id: str | None = None
    problem_content_hash: str | None = None
    solution_content_hash: str | None = None
    status_version: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ProblemAdminDetail(ProblemAdminListItem):
    """中文：定义“题目·admin·detail”类，封装该职责相关的数据与行为。
    English: Defines the problem admin detail class and encapsulates data and behavior for that responsibility.
    """
    explicit_conditions: list[dict[str, Any]]
    implicit_conditions: list[dict[str, Any]]
    target: dict[str, Any] | None
    difficulty_factors: list[dict[str, Any]]
    solution_count: int = Field(ge=0)
    fully_verified_solution_count: int = Field(ge=0)
    evidence: list[AdmissionEvidenceView]
    transitions: list[ProblemStatusTransitionView]
    audit_timeline: list[GenerationAuditRecordView]


class ProblemStatusChangeRequest(BaseModel):
    """中文：定义“题目·状态·change·请求”类，封装该职责相关的数据与行为。
    English: Defines the problem status change request class and encapsulates data and behavior for that responsibility.
    """
    target_status: ProblemContentStatus
    expected_status_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)
    index_is_active: bool = False


class PersistedProblemTransition(BaseModel):
    """中文：定义“persisted·题目·transition”类，封装该职责相关的数据与行为。
    English: Defines the persisted problem transition class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str
    previous_status: ProblemContentStatus
    current_status: ProblemContentStatus
    changed: bool
    status_reason: str | None
    revision_attempts: int
    status_version: int
    status_changed_at: datetime
    checked_requirements: list[str]


class ProblemRetirementRequest(BaseModel):
    """中文：定义“题目·retirement·请求”类，封装该职责相关的数据与行为。
    English: Defines the problem retirement request class and encapsulates data and behavior for that responsibility.
    """
    expected_status_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class ProblemRetirementResult(BaseModel):
    """中文：定义“题目·retirement·结果”类，封装该职责相关的数据与行为。
    English: Defines the problem retirement result class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str
    previous_status: ProblemContentStatus
    current_status: Literal[ProblemContentStatus.RETIRED]
    status_version: int = Field(ge=2)
    maintenance_job: IndexMaintenanceJobView
    keyword_index_invalidated: Literal[True] = True
    vector_index_invalidated: Literal[True] = True
    redis_cache_invalidated: Literal[True] = True
    knowledge_version: str | None = None
