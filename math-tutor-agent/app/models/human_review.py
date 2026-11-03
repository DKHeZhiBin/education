from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, MYSQL_DATETIME, TimestampMixin, UuidPrimaryKeyMixin, utc_now


class HumanReviewTask(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """中文：定义“human·复核·task”类，封装该职责相关的数据与行为。
    English: Defines the human review task class and encapsulates data and behavior for that responsibility.
    """
    __tablename__ = "human_review_tasks"
    __table_args__ = (
        CheckConstraint(
            "selection_reason IN ('quarantined', 'high_value', 'manual')",
            name="selection_reason_allowed",
        ),
        CheckConstraint(
            "status IN ('queued', 'claimed', 'completed', 'cancelled', 'stale')",
            name="status_allowed",
        ),
        CheckConstraint("priority BETWEEN 1 AND 5", name="priority_range"),
        CheckConstraint("value_score BETWEEN 0 AND 100", name="value_score_range"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("idx_human_review_queue", "status", "priority", "created_at"),
        Index(
            "idx_human_review_problem_version",
            "problem_id",
            "problem_content_hash",
            "status",
        ),
        Index("idx_human_review_assignee", "assigned_to_user_id", "status", "updated_at"),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=False
    )
    solution_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_solutions.id", ondelete="SET NULL"), nullable=True
    )
    problem_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    solution_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    problem_status_version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    selection_reason: Mapped[str] = mapped_column(String(24), nullable=False)
    priority: Mapped[int] = mapped_column(TINYINT(unsigned=True), default=3, nullable=False)
    value_score: Mapped[int] = mapped_column(TINYINT(unsigned=True), default=0, nullable=False)
    value_factors_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    review_requirements_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=1, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_to_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)


class HumanContentReview(UuidPrimaryKeyMixin, Base):
    """中文：定义“human·内容·复核”类，封装该职责相关的数据与行为。
    English: Defines the human content review class and encapsulates data and behavior for that responsibility.
    """
    __tablename__ = "human_content_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approve', 'revision_required', 'quarantine', 'inconclusive')",
            name="decision_allowed",
        ),
        CheckConstraint(
            "coverage_level IN ('full', 'partial', 'none')",
            name="coverage_level_allowed",
        ),
        UniqueConstraint("task_id", "reviewer_user_id", name="human_review_task_reviewer"),
        Index("idx_human_content_reviews_problem", "problem_id", "submitted_at"),
    )

    task_id: Mapped[str] = mapped_column(
        ForeignKey("human_review_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=False
    )
    solution_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_solutions.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    problem_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    solution_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    coverage_level: Mapped[str] = mapped_column(String(16), nullable=False)
    checklist_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    issues_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("admission_evidence.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)
