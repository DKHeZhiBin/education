from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, MYSQL_DATETIME, TimestampMixin, UuidPrimaryKeyMixin


class ContentRevalidationPolicy(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_revalidation_policies"
    __table_args__ = (
        UniqueConstraint("policy_key", name="content_revalidation_policy_key"),
        CheckConstraint("cadence_hours >= 1", name="cadence_hours_positive"),
        CheckConstraint("max_items_per_run >= 1", name="max_items_positive"),
        Index("idx_revalidation_policies_due", "enabled", "next_run_at"),
    )

    policy_key: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    cadence_hours: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    max_items_per_run: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), default="math", nullable=False)
    topic_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    problem_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False
    )
    review_model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False
    )
    condition_prompt_version_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    solver_prompt_version_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    review_prompt_version_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    sympy_verifier_version_id: Mapped[str] = mapped_column(
        ForeignKey("verifier_versions.id", ondelete="RESTRICT"), nullable=False
    )
    numeric_verifier_version_id: Mapped[str] = mapped_column(
        ForeignKey("verifier_versions.id", ondelete="RESTRICT"), nullable=False
    )
    duplicate_verifier_version_id: Mapped[str] = mapped_column(
        ForeignKey("verifier_versions.id", ondelete="RESTRICT"), nullable=False
    )
    leakage_verifier_version_id: Mapped[str] = mapped_column(
        ForeignKey("verifier_versions.id", ondelete="RESTRICT"), nullable=False
    )
    next_run_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ContentRevalidationRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_revalidation_runs"
    __table_args__ = (
        UniqueConstraint("run_key", name="content_revalidation_run_key"),
        CheckConstraint(
            "trigger_type IN ('scheduled', 'manual')", name="trigger_type_allowed"
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'partial_failed', 'failed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("selected_count >= 0", name="selected_count_nonnegative"),
        Index("idx_revalidation_runs_work", "status", "scheduled_for"),
        Index("idx_revalidation_runs_policy", "policy_id", "created_at"),
    )

    policy_id: Mapped[str] = mapped_column(
        ForeignKey("content_revalidation_policies.id", ondelete="RESTRICT"), nullable=False
    )
    run_key: Mapped[str] = mapped_column(String(160), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(MYSQL_DATETIME, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    selected_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    passed_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    inconclusive_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ContentRevalidationItem(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_revalidation_items"
    __table_args__ = (
        UniqueConstraint("run_id", "problem_id", name="revalidation_run_problem"),
        CheckConstraint(
            "status IN ('queued', 'suppressing', 'validating', 'tool_verification', "
            "'ai_review', 'admission', 'passed', 'failed', 'inconclusive')",
            name="status_allowed",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('passed', 'failed', 'inconclusive')",
            name="outcome_allowed",
        ),
        Index("idx_revalidation_items_work", "run_id", "status", "created_at"),
        Index("idx_revalidation_items_problem", "problem_id", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(
        ForeignKey("content_revalidation_runs.id", ondelete="RESTRICT"), nullable=False
    )
    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=False
    )
    solution_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_solutions.id", ondelete="RESTRICT"), nullable=True
    )
    maintenance_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("search_index_maintenance_jobs.id", ondelete="SET NULL"), nullable=True
    )
    problem_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    solution_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tool_evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    condition_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("admission_evidence.id", ondelete="SET NULL"), nullable=True
    )
    solution_independence_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("admission_evidence.id", ondelete="SET NULL"), nullable=True
    )
    ai_review_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("admission_evidence.id", ondelete="SET NULL"), nullable=True
    )
    admission_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("admission_evidence.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
