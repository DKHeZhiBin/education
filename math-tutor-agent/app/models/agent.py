from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT, INTEGER, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.session import LearningSession


class AgentRun(UuidPrimaryKeyMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("idx_runs_session_started", "session_id", "started_at"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    max_agent_calls: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False)
    agent_call_count: Mapped[int] = mapped_column(SMALLINT(unsigned=True), default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    degradation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)

    session: Mapped[LearningSession] = relationship(back_populates="agent_runs")
    steps: Mapped[list[AgentRunStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentRunStep.step_no"
    )


class AgentRunStep(Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_no", name="run_step"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_no: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    artifact_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    duration_ms: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_input: Mapped[int | None] = mapped_column(INTEGER(unsigned=True), nullable=True)
    token_output: Mapped[int | None] = mapped_column(INTEGER(unsigned=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message_safe: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    run: Mapped[AgentRun] = relationship(back_populates="steps")
    artifacts: Mapped[list[AgentArtifact]] = relationship(
        back_populates="run_step", cascade="all, delete-orphan"
    )


class AgentArtifact(Base):
    __tablename__ = "agent_artifacts"
    __table_args__ = (
        Index("idx_artifacts_session_kind", "session_id", "kind", "created_at"),
        Index("idx_artifacts_step", "run_step_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    run_step_id: Mapped[int] = mapped_column(
        ForeignKey("agent_run_steps.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    run_step: Mapped[AgentRunStep] = relationship(back_populates="artifacts")
    session: Mapped[LearningSession] = relationship(back_populates="artifacts")
