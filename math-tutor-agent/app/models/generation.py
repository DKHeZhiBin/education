from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, TimestampMixin, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeProblem, KnowledgeSolution


class ModelVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("provider", "model_name", "version_label", name="model_version_identity"),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    api_family: Mapped[str | None] = mapped_column(String(40), nullable=True)
    config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    generation_batches: Mapped[list["GenerationBatch"]] = relationship(
        back_populates="model_version"
    )
    admission_evidence: Mapped[list["AdmissionEvidence"]] = relationship(
        back_populates="model_version"
    )


class PromptVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_key", "version", name="prompt_version_identity"),
        UniqueConstraint("prompt_key", "template_hash", name="prompt_template_hash"),
    )

    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    generation_batches: Mapped[list["GenerationBatch"]] = relationship(
        back_populates="prompt_version"
    )
    admission_evidence: Mapped[list["AdmissionEvidence"]] = relationship(
        back_populates="prompt_version"
    )


class VerifierVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "verifier_versions"
    __table_args__ = (
        UniqueConstraint("verifier_key", "version", name="verifier_version_identity"),
    )

    verifier_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    implementation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ruleset_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supported_problem_types_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    admission_evidence: Mapped[list["AdmissionEvidence"]] = relationship(
        back_populates="verifier_version"
    )


class GenerationBatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generation_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'completed', 'partial_failed', 'failed', "
            "'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint(
            "(model_version_id IS NULL AND prompt_version_id IS NULL) OR "
            "(model_version_id IS NOT NULL AND prompt_version_id IS NOT NULL)",
            name="model_prompt_pair",
        ),
        CheckConstraint(
            "approved_count + quarantined_count <= generated_count",
            name="classified_count_valid",
        ),
        CheckConstraint(
            "generated_count + failed_count <= requested_count",
            name="batch_outcome_count_valid",
        ),
        CheckConstraint("requested_count >= 1", name="requested_count_positive"),
        CheckConstraint(
            "status NOT IN ('completed', 'partial_failed', 'failed', 'cancelled') "
            "OR finished_at IS NOT NULL",
            name="terminal_finished_at_required",
        ),
        CheckConstraint(
            "status NOT IN ('running', 'paused', 'completed', 'partial_failed', 'failed') "
            "OR started_at IS NOT NULL",
            name="executed_started_at_required",
        ),
        CheckConstraint(
            "status IN ('completed', 'partial_failed', 'failed', 'cancelled') "
            "OR finished_at IS NULL",
            name="nonterminal_finished_at_forbidden",
        ),
        UniqueConstraint("batch_key", name="batch_key"),
        Index("idx_generation_batches_status", "status", "created_at"),
        Index("idx_generation_batches_topic", "subject", "grade_band", "topic_code"),
    )

    batch_key: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), default="math", nullable=False)
    grade_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    topic_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    requested_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    generated_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    approved_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    quarantined_count: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), default=0, nullable=False
    )
    failed_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    model_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=True
    )
    prompt_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=True
    )
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)

    model_version: Mapped[ModelVersion | None] = relationship(back_populates="generation_batches")
    prompt_version: Mapped[PromptVersion | None] = relationship(back_populates="generation_batches")
    problems: Mapped[list["KnowledgeProblem"]] = relationship(
        "KnowledgeProblem", back_populates="generation_batch"
    )
    admission_evidence: Mapped[list["AdmissionEvidence"]] = relationship(
        back_populates="generation_batch"
    )
    question_generation_job: Mapped["QuestionGenerationJob | None"] = relationship(
        back_populates="generation_batch",
        uselist=False,
    )
    management_events: Mapped[list["GenerationBatchManagementEvent"]] = relationship(
        back_populates="generation_batch",
        foreign_keys="GenerationBatchManagementEvent.generation_batch_id",
        order_by="GenerationBatchManagementEvent.created_at",
    )


class GenerationBatchManagementEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "generation_batch_management_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('pause', 'resume', 'cancel', 'retry_created', "
            "'retried_from', 'withdraw_approved')",
            name="action_allowed",
        ),
        CheckConstraint(
            "actor_type IN ('admin', 'system')",
            name="actor_type_allowed",
        ),
        Index("idx_generation_batch_events_batch", "generation_batch_id", "created_at"),
    )

    generation_batch_id: Mapped[str] = mapped_column(
        ForeignKey("generation_batches.id", ondelete="RESTRICT"), nullable=False
    )
    related_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_batches.id", ondelete="RESTRICT"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    current_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    generation_batch: Mapped[GenerationBatch] = relationship(
        back_populates="management_events",
        foreign_keys=[generation_batch_id],
    )


class QuestionGenerationJob(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "question_generation_jobs"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        UniqueConstraint(
            "generation_batch_id",
            name="question_generation_job_batch",
        ),
        UniqueConstraint(
            "idempotency_key_hash",
            name="question_generation_job_idempotency",
        ),
        Index("idx_question_generation_jobs_scope", "idempotency_scope", "created_at"),
        Index("idx_question_generation_jobs_request", "request_hash"),
    )

    generation_batch_id: Mapped[str] = mapped_column(
        ForeignKey("generation_batches.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    status_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    generation_batch: Mapped[GenerationBatch] = relationship(
        back_populates="question_generation_job"
    )


class AdmissionEvidence(UuidPrimaryKeyMixin, Base):
    __tablename__ = "admission_evidence"
    __table_args__ = (
        CheckConstraint(
            "producer_type IN ('model', 'verifier', 'hybrid', 'system')",
            name="producer_type_allowed",
        ),
        CheckConstraint(
            "status IN ('passed', 'failed', 'not_run', 'inconclusive')",
            name="status_allowed",
        ),
        CheckConstraint(
            "(producer_type = 'model' AND model_version_id IS NOT NULL AND "
            "prompt_version_id IS NOT NULL AND verifier_version_id IS NULL) OR "
            "(producer_type = 'verifier' AND verifier_version_id IS NOT NULL AND "
            "model_version_id IS NULL AND prompt_version_id IS NULL) OR "
            "(producer_type = 'hybrid' AND model_version_id IS NOT NULL AND "
            "prompt_version_id IS NOT NULL AND verifier_version_id IS NOT NULL) OR "
            "(producer_type = 'system' AND model_version_id IS NULL AND "
            "prompt_version_id IS NULL AND verifier_version_id IS NULL)",
            name="producer_versions_valid",
        ),
        UniqueConstraint(
            "generation_batch_id",
            "problem_id",
            "evidence_type",
            "evidence_hash",
            name="batch_problem_evidence_hash",
        ),
        Index("idx_admission_evidence_problem", "problem_id", "evidence_type", "status"),
        Index("idx_admission_evidence_batch", "generation_batch_id", "created_at"),
    )

    generation_batch_id: Mapped[str] = mapped_column(
        ForeignKey("generation_batches.id", ondelete="RESTRICT"), nullable=False
    )
    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=False
    )
    solution_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_solutions.id", ondelete="RESTRICT"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    producer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    model_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=True
    )
    prompt_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=True
    )
    verifier_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("verifier_versions.id", ondelete="RESTRICT"), nullable=True
    )
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    generation_batch: Mapped[GenerationBatch] = relationship(back_populates="admission_evidence")
    problem: Mapped["KnowledgeProblem"] = relationship(
        "KnowledgeProblem", back_populates="admission_evidence"
    )
    solution: Mapped["KnowledgeSolution | None"] = relationship(
        "KnowledgeSolution", back_populates="admission_evidence"
    )
    model_version: Mapped[ModelVersion | None] = relationship(back_populates="admission_evidence")
    prompt_version: Mapped[PromptVersion | None] = relationship(back_populates="admission_evidence")
    verifier_version: Mapped[VerifierVersion | None] = relationship(
        back_populates="admission_evidence"
    )
