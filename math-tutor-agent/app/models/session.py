from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import INTEGER, SMALLINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.agent import AgentArtifact, AgentRun
    from app.models.identity import StudentProfile
    from app.models.learning import LearningRecord, ReviewAttempt
    from app.models.media import MediaAsset
    from app.models.knowledge import KnowledgeProblem


class LearningSession(UuidPrimaryKeyMixin, Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        CheckConstraint("hint_level BETWEEN 0 AND 4", name="hint_level_range"),
        Index("idx_sessions_student_updated", "student_user_id", "updated_at"),
        Index("idx_sessions_student_status", "student_user_id", "status"),
        Index("idx_sessions_knowledge_problem", "knowledge_problem_id", "updated_at"),
    )

    student_user_id: Mapped[str] = mapped_column(
        ForeignKey("student_profiles.user_id", ondelete="RESTRICT"), nullable=False
    )
    knowledge_problem_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="SET NULL"), nullable=True
    )
    subject: Mapped[str] = mapped_column(String(24), default="math", nullable=False)
    grade_band: Mapped[str] = mapped_column(String(24), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="collecting", nullable=False)
    hint_level: Mapped[int] = mapped_column(TINYINT(unsigned=True), default=0, nullable=False)
    attempt_count: Mapped[int] = mapped_column(SMALLINT(unsigned=True), default=0, nullable=False)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=1, nullable=False)
    started_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, onupdate=utc_now, nullable=False)

    student: Mapped[StudentProfile] = relationship(back_populates="sessions")
    knowledge_problem: Mapped[KnowledgeProblem | None] = relationship()
    messages: Mapped[list[SessionMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SessionMessage.sequence_no"
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    learning_record: Mapped[LearningRecord | None] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    review_attempts: Mapped[list[ReviewAttempt]] = relationship(back_populates="session")
    media_assets: Mapped[list[MediaAsset]] = relationship(back_populates="session")
    artifacts: Mapped[list[AgentArtifact]] = relationship(back_populates="session")


class SessionMessage(UuidPrimaryKeyMixin, Base):
    __tablename__ = "session_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_no", name="session_sequence"),
        UniqueConstraint("session_id", "client_turn_id", name="session_client_turn"),
        Index("idx_messages_session_created", "session_id", "created_at"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(24), nullable=True)
    client_turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    session: Mapped[LearningSession] = relationship(back_populates="messages")
