from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def new_generation_id() -> str:
    return str(uuid4())


class GenerationBatchStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvidenceProducerType(StrEnum):
    MODEL = "model"
    VERIFIER = "verifier"
    HYBRID = "hybrid"
    SYSTEM = "system"


class AdmissionEvidenceStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
    INCONCLUSIVE = "inconclusive"


class ModelVersion(BaseModel):
    id: str = Field(default_factory=new_generation_id)
    provider: str = Field(min_length=1, max_length=40)
    model_name: str = Field(min_length=1, max_length=100)
    version_label: str = Field(min_length=1, max_length=100)
    api_family: str | None = Field(default=None, max_length=40)
    config_fingerprint: str = Field(min_length=64, max_length=64)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromptVersion(BaseModel):
    id: str = Field(default_factory=new_generation_id)
    prompt_key: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=32)
    purpose: str = Field(min_length=1, max_length=64)
    template_text: str = Field(min_length=1)
    template_hash: str = Field(min_length=64, max_length=64)
    output_schema_version: str = Field(min_length=1, max_length=32)
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VerifierVersion(BaseModel):
    id: str = Field(default_factory=new_generation_id)
    verifier_key: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=32)
    implementation_hash: str = Field(min_length=64, max_length=64)
    ruleset_hash: str | None = Field(default=None, min_length=64, max_length=64)
    supported_problem_types: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GenerationBatch(BaseModel):
    id: str = Field(default_factory=new_generation_id)
    batch_key: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=32)
    subject: str = Field(default="math", max_length=32)
    grade_band: str | None = Field(default=None, max_length=32)
    topic_code: str | None = Field(default=None, max_length=80)
    requested_count: int = Field(ge=1, le=10000)
    generated_count: int = Field(default=0, ge=0)
    approved_count: int = Field(default=0, ge=0)
    quarantined_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    status: GenerationBatchStatus = GenerationBatchStatus.PENDING
    model_version_id: str | None = None
    prompt_version_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_batch(self) -> GenerationBatch:
        if (self.model_version_id is None) != (self.prompt_version_id is None):
            raise ValueError(
                "model_version_id and prompt_version_id must either both be set or both be null"
            )
        classified = self.approved_count + self.quarantined_count
        if classified > self.generated_count:
            raise ValueError("approved and quarantined items cannot exceed generated_count")
        if self.generated_count + self.failed_count > self.requested_count:
            raise ValueError("generated and failed items cannot exceed requested_count")
        if self.status in {
            GenerationBatchStatus.COMPLETED,
            GenerationBatchStatus.PARTIAL_FAILED,
            GenerationBatchStatus.FAILED,
            GenerationBatchStatus.CANCELLED,
        } and self.finished_at is None:
            raise ValueError("a terminal generation batch must have finished_at")
        if self.status in {
            GenerationBatchStatus.RUNNING,
            GenerationBatchStatus.PAUSED,
            GenerationBatchStatus.COMPLETED,
            GenerationBatchStatus.PARTIAL_FAILED,
            GenerationBatchStatus.FAILED,
        } and self.started_at is None:
            raise ValueError("an executed generation batch must have started_at")
        if self.status in {
            GenerationBatchStatus.PENDING,
            GenerationBatchStatus.RUNNING,
            GenerationBatchStatus.PAUSED,
        } and self.finished_at is not None:
            raise ValueError("a non-terminal generation batch cannot have finished_at")
        return self


class AdmissionEvidence(BaseModel):
    id: str = Field(default_factory=new_generation_id)
    generation_batch_id: str
    problem_id: str
    solution_id: str | None = None
    evidence_type: str = Field(min_length=1, max_length=40)
    producer_type: EvidenceProducerType
    status: AdmissionEvidenceStatus
    model_version_id: str | None = None
    prompt_version_id: str | None = None
    verifier_version_id: str | None = None
    is_blocking: bool = False
    summary: str = Field(min_length=1, max_length=1000)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_producer_versions(self) -> AdmissionEvidence:
        has_model = self.model_version_id is not None
        has_prompt = self.prompt_version_id is not None
        has_verifier = self.verifier_version_id is not None
        if self.producer_type == EvidenceProducerType.MODEL:
            valid = has_model and has_prompt and not has_verifier
        elif self.producer_type == EvidenceProducerType.VERIFIER:
            valid = has_verifier and not has_model and not has_prompt
        elif self.producer_type == EvidenceProducerType.HYBRID:
            valid = has_model and has_prompt and has_verifier
        else:
            valid = not has_model and not has_prompt and not has_verifier
        if not valid:
            raise ValueError("producer_type does not match the supplied version references")
        return self
