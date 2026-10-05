from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import INTEGER, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, TimestampMixin, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.learning import LearningRecord
    from app.models.reporting import ParentReport
    from app.models.session import LearningSession


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    account_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    token_version: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=1, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)

    student_profile: Mapped[StudentProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    guardian_profile: Mapped[GuardianProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    guardian_links: Mapped[list[GuardianStudentLink]] = relationship(
        back_populates="guardian", cascade="all, delete-orphan",
        foreign_keys="GuardianStudentLink.guardian_user_id",
    )


class AccountActionToken(UuidPrimaryKeyMixin, Base):
    __tablename__ = "account_action_tokens"
    __table_args__ = (
        Index("idx_account_tokens_user_purpose", "user_id", "purpose", "created_at"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)


class RefreshSession(UuidPrimaryKeyMixin, Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        Index("idx_refresh_sessions_user", "user_id", "created_at"),
        Index("idx_refresh_sessions_family", "family_id"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    replaced_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    grade_band: Mapped[str] = mapped_column(String(24), nullable=False)
    current_grade: Mapped[int | None] = mapped_column(TINYINT(unsigned=True), nullable=True)
    preferred_explanation_style: Mapped[str] = mapped_column(
        String(24), default="balanced", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="student_profile")
    guardian_links: Mapped[list[GuardianStudentLink]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[LearningSession]] = relationship(back_populates="student")
    learning_records: Mapped[list[LearningRecord]] = relationship(back_populates="student")
    parent_reports: Mapped[list[ParentReport]] = relationship(back_populates="student")


class GuardianProfile(Base):
    __tablename__ = "guardian_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    report_frequency: Mapped[str] = mapped_column(String(16), default="weekly", nullable=False)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="guardian_profile")


class GuardianStudentLink(UuidPrimaryKeyMixin, Base):
    __tablename__ = "guardian_student_links"
    __table_args__ = (
        UniqueConstraint("guardian_user_id", "student_user_id", name="guardian_student"),
    )

    guardian_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_user_id: Mapped[str] = mapped_column(
        ForeignKey("student_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column("relationship", String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    consented_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    guardian: Mapped[User] = relationship(
        back_populates="guardian_links", foreign_keys=[guardian_user_id]
    )
    student: Mapped[StudentProfile] = relationship(back_populates="guardian_links")
