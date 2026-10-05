from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.generation import AdmissionEvidenceStatus, EvidenceProducerType
from app.domain.knowledge import ProblemContentStatus
from app.domain.question_generation import GeneratedQuestionDraft


MAX_CANDIDATE_REVISION_ATTEMPTS = 2


class RevisionFailureEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_type: str
    status: AdmissionEvidenceStatus
    producer_type: EvidenceProducerType
    summary: str = Field(min_length=1, max_length=1000)
    public_details: dict[str, Any] = Field(default_factory=dict)
    suggested_revisions: list[str] = Field(default_factory=list, max_length=50)


class CandidateRevisionContext(BaseModel):
    """Only the current candidate and explicit gate failures visible to the reviser."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    problem_id: str
    generation_batch_id: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status_version: int = Field(ge=1)
    content_status: Literal[ProblemContentStatus.REVISION_REQUIRED]
    revision_attempt: int = Field(ge=1, le=MAX_CANDIDATE_REVISION_ATTEMPTS)
    max_revision_attempts: int = Field(
        default=MAX_CANDIDATE_REVISION_ATTEMPTS,
        ge=1,
        le=MAX_CANDIDATE_REVISION_ATTEMPTS,
    )
    admission_decision_id: str
    admission_decision_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    statement: str = Field(min_length=1, max_length=10_000)
    normalized_statement: str | None = Field(default=None, max_length=10_000)
    explicit_conditions: list[dict[str, Any]] = Field(default_factory=list)
    implicit_conditions: list[dict[str, Any]] = Field(default_factory=list)
    target: dict[str, Any]
    subject: str
    grade_band: str
    problem_type: str
    difficulty: int = Field(ge=1, le=5)
    answer_type: str
    language: str
    knowledge_point_codes: list[str] = Field(min_length=1)
    derivation_type: str
    mother_problem_id: str
    allowed_difficulty_minimum: int = Field(ge=1, le=5)
    allowed_difficulty_maximum: int = Field(ge=1, le=5)
    prohibited_terms: list[str] = Field(default_factory=list, max_length=100)
    failures: list[RevisionFailureEvidence] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_contract(self) -> CandidateRevisionContext:
        if self.allowed_difficulty_minimum > self.allowed_difficulty_maximum:
            raise ValueError("revision difficulty range is invalid")
        if self.revision_attempt > self.max_revision_attempts:
            raise ValueError("revision attempt exceeds the registered maximum")
        failure_ids = [item.evidence_id for item in self.failures]
        if len(failure_ids) != len(set(failure_ids)):
            raise ValueError("revision failure evidence ids must be unique")
        if any(item.status != AdmissionEvidenceStatus.FAILED for item in self.failures):
            raise ValueError("revision context may contain only explicit failed evidence")
        return self

    def fingerprint(self) -> str:
        serialized = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()


class FailureRepair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    change: str = Field(min_length=1, max_length=1000)


class CandidateRevisionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    revised_question: GeneratedQuestionDraft
    repairs: list[FailureRepair] = Field(min_length=1, max_length=20)
    change_summary: str = Field(min_length=1, max_length=1000)
    requires_full_revalidation: Literal[True] = True

    @model_validator(mode="after")
    def validate_repairs(self) -> CandidateRevisionDraft:
        repair_ids = [item.evidence_id for item in self.repairs]
        if len(repair_ids) != len(set(repair_ids)):
            raise ValueError("each failure evidence may be repaired only once")
        return self


class PersistedCandidateRevision(BaseModel):
    source_problem_id: str
    revised_problem_id: str
    generation_batch_id: str
    revision_attempt: int = Field(ge=1, le=MAX_CANDIDATE_REVISION_ATTEMPTS)
    content_status: Literal[ProblemContentStatus.CANDIDATE]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision_evidence_id: str
    created: bool
