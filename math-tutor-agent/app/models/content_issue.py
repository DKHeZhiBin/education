from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class ContentIssueReport(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Auditable signal that removes questionable teaching content from production."""

    __tablename__ = "content_issue_reports"
    __table_args__ = (
        CheckConstraint(
            "source IN ('student_report', 'runtime_answer_conflict')",
            name="source_allowed",
        ),
        CheckConstraint(
            "issue_type IN ('incorrect_answer', 'incorrect_question', "
            "'incorrect_hint', 'ambiguous_content', 'answer_conflict', 'other')",
            name="issue_type_allowed",
        ),
        CheckConstraint(
            "status IN ('received', 'revalidation_queued', 'validating', "
            "'resolved', 'dismissed')",
            name="status_allowed",
        ),
        UniqueConstraint("idempotency_key_hash", name="content_issue_idempotency"),
        Index("idx_content_issues_problem", "problem_id", "created_at"),
        Index("idx_content_issues_status", "status", "created_at"),
        Index("idx_content_issues_session", "session_id", "created_at"),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="SET NULL"), nullable=True
    )
    reporter_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="received", nullable=False)
    maintenance_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("search_index_maintenance_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
