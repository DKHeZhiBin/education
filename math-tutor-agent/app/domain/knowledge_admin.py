from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.generation import AdmissionEvidenceStatus, EvidenceProducerType
from app.domain.knowledge import ProblemContentStatus


class ProblemAdminListItem(BaseModel):
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
    items: list[ProblemAdminListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class ProblemStatusCount(BaseModel):
    status: ProblemContentStatus
    count: int = Field(ge=0)


class AdmissionEvidenceView(BaseModel):
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
    target_status: ProblemContentStatus
    expected_status_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)
    index_is_active: bool = False


class PersistedProblemTransition(BaseModel):
    problem_id: str
    previous_status: ProblemContentStatus
    current_status: ProblemContentStatus
    changed: bool
    status_reason: str | None
    revision_attempts: int
    status_version: int
    status_changed_at: datetime
    checked_requirements: list[str]
