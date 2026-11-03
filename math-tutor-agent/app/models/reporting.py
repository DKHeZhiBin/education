from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.identity import StudentProfile


class ParentReport(UuidPrimaryKeyMixin, Base):
    """中文：定义“parent·报告”类，封装该职责相关的数据与行为。
    English: Defines the parent report class and encapsulates data and behavior for that responsibility.
    """
    __tablename__ = "parent_reports"
    __table_args__ = (
        UniqueConstraint(
            "student_user_id",
            "period_type",
            "period_start",
            "period_end",
            name="student_report_period",
        ),
    )

    student_user_id: Mapped[str] = mapped_column(
        ForeignKey("student_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_markdown: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    student: Mapped[StudentProfile] = relationship(back_populates="parent_reports")
