from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.generation import GenerationBatchStatus


class BatchActionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason cannot be blank")
        return value


class BatchRetryRequest(BatchActionRequest):
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("idempotency_key cannot contain surrounding whitespace")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("idempotency_key cannot contain control characters")
        return value


class BatchWithdrawalRequest(BatchActionRequest):
    include_indexed: bool = False
    indexed_content_removed: bool = False

    @model_validator(mode="after")
    def validate_index_removal(self) -> BatchWithdrawalRequest:
        if self.indexed_content_removed and not self.include_indexed:
            raise ValueError("indexed_content_removed requires include_indexed=true")
        return self


class GenerationBatchEventView(BaseModel):
    id: str
    action: Literal[
        "pause",
        "resume",
        "cancel",
        "retry_created",
        "retried_from",
        "withdraw_approved",
    ]
    previous_status: GenerationBatchStatus
    current_status: GenerationBatchStatus
    reason: str
    actor_type: Literal["admin", "system"]
    actor_id: str | None
    related_batch_id: str | None
    payload: dict[str, Any]
    created_at: datetime


class GenerationBatchAdminItem(BaseModel):
    id: str
    batch_key: str
    purpose: str
    subject: str
    grade_band: str | None
    topic_code: str | None
    requested_count: int = Field(ge=1)
    generated_count: int = Field(ge=0)
    approved_count: int = Field(ge=0)
    quarantined_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    status: GenerationBatchStatus
    model_version_id: str | None
    prompt_version_id: str | None
    job_id: str | None
    attempt_count: int = Field(ge=0)
    status_reason: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GenerationBatchAdminPage(BaseModel):
    items: list[GenerationBatchAdminItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class GenerationBatchAdminDetail(GenerationBatchAdminItem):
    config: dict[str, Any]
    budget: dict[str, Any] | None
    usage: dict[str, Any] | None
    output: dict[str, Any] | None
    events: list[GenerationBatchEventView]


class GenerationBatchActionResult(BaseModel):
    batch: GenerationBatchAdminDetail
    changed: bool


class GenerationBatchRetryResult(BaseModel):
    source_batch_id: str
    retry_batch: GenerationBatchAdminDetail
    retry_count: int = Field(ge=1)


class BatchWithdrawalResult(BaseModel):
    batch: GenerationBatchAdminDetail
    withdrawn_problem_ids: list[str]
    skipped_indexed_problem_ids: list[str]

