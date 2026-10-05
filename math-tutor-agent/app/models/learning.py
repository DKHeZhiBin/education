from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.mysql import BIGINT, INTEGER, SMALLINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, TimestampMixin, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.identity import StudentProfile
    from app.models.session import LearningSession


class LearningRecord(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learning_records"
    __table_args__ = (
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty_range"),
        Index("idx_records_review_queue", "student_user_id", "mastery_status", "next_review_at"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    student_user_id: Mapped[str] = mapped_column(
        ForeignKey("student_profiles.user_id", ondelete="RESTRICT"), nullable=False
    )
    question_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    learner_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correct_approach: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[int] = mapped_column(TINYINT(unsigned=True), default=2, nullable=False)
    mastery_status: Mapped[str] = mapped_column(String(20), default="to_review", nullable=False)
    review_count: Mapped[int] = mapped_column(SMALLINT(unsigned=True), default=0, nullable=False)
    next_review_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)

    session: Mapped[LearningSession] = relationship(back_populates="learning_record")
    student: Mapped[StudentProfile] = relationship(back_populates="learning_records")
    knowledge_links: Mapped[list[LearningRecordKnowledge]] = relationship(
        back_populates="learning_record", cascade="all, delete-orphan"
    )
    review_attempts: Mapped[list[ReviewAttempt]] = relationship(
        back_populates="learning_record", cascade="all, delete-orphan"
    )


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(24), nullable=False)
    grade_band: Mapped[str] = mapped_column(String(24), nullable=False)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(24), default="core", nullable=False)
    sort_order: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    parent: Mapped[KnowledgePoint | None] = relationship(
        remote_side="KnowledgePoint.id", back_populates="children"
    )
    children: Mapped[list[KnowledgePoint]] = relationship(back_populates="parent")
    learning_record_links: Mapped[list[LearningRecordKnowledge]] = relationship(
        back_populates="knowledge_point"
    )
    prerequisites: Mapped[list[KnowledgePointPrerequisite]] = relationship(
        foreign_keys="KnowledgePointPrerequisite.knowledge_point_id",
        back_populates="knowledge_point",
        cascade="all, delete-orphan",
    )
    required_by: Mapped[list[KnowledgePointPrerequisite]] = relationship(
        foreign_keys="KnowledgePointPrerequisite.prerequisite_id",
        back_populates="prerequisite",
    )
    capability_requirements: Mapped[list[CapabilityKnowledgeRequirement]] = relationship(
        back_populates="knowledge_point"
    )


class KnowledgePointPrerequisite(Base):
    __tablename__ = "knowledge_point_prerequisites"
    __table_args__ = (
        CheckConstraint(
            "knowledge_point_id <> prerequisite_id", name="knowledge_prerequisite_not_self"
        ),
        Index("idx_knowledge_prerequisites_reverse", "prerequisite_id", "knowledge_point_id"),
    )

    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), primary_key=True
    )
    prerequisite_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), primary_key=True
    )
    strength: Mapped[str] = mapped_column(String(16), default="required", nullable=False)
    required_level: Mapped[str] = mapped_column(String(16), default="familiar", nullable=False)
    rationale: Mapped[str] = mapped_column(String(500), nullable=False)

    knowledge_point: Mapped[KnowledgePoint] = relationship(
        foreign_keys=[knowledge_point_id], back_populates="prerequisites"
    )
    prerequisite: Mapped[KnowledgePoint] = relationship(
        foreign_keys=[prerequisite_id], back_populates="required_by"
    )


class CapabilityPoint(Base):
    __tablename__ = "capability_points"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(24), nullable=False)
    grade_band: Mapped[str] = mapped_column(String(24), nullable=False)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    sort_order: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("capability_points.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    parent: Mapped[CapabilityPoint | None] = relationship(
        remote_side="CapabilityPoint.id", back_populates="children"
    )
    children: Mapped[list[CapabilityPoint]] = relationship(back_populates="parent")
    prerequisites: Mapped[list[CapabilityPointPrerequisite]] = relationship(
        foreign_keys="CapabilityPointPrerequisite.capability_point_id",
        back_populates="capability_point",
        cascade="all, delete-orphan",
    )
    required_by: Mapped[list[CapabilityPointPrerequisite]] = relationship(
        foreign_keys="CapabilityPointPrerequisite.prerequisite_id",
        back_populates="prerequisite",
    )
    knowledge_requirements: Mapped[list[CapabilityKnowledgeRequirement]] = relationship(
        back_populates="capability_point", cascade="all, delete-orphan"
    )


class CapabilityPointPrerequisite(Base):
    __tablename__ = "capability_point_prerequisites"
    __table_args__ = (
        CheckConstraint(
            "capability_point_id <> prerequisite_id", name="capability_prerequisite_not_self"
        ),
        Index("idx_capability_prerequisites_reverse", "prerequisite_id", "capability_point_id"),
    )

    capability_point_id: Mapped[int] = mapped_column(
        ForeignKey("capability_points.id", ondelete="CASCADE"), primary_key=True
    )
    prerequisite_id: Mapped[int] = mapped_column(
        ForeignKey("capability_points.id", ondelete="RESTRICT"), primary_key=True
    )
    strength: Mapped[str] = mapped_column(String(16), default="required", nullable=False)
    rationale: Mapped[str] = mapped_column(String(500), nullable=False)

    capability_point: Mapped[CapabilityPoint] = relationship(
        foreign_keys=[capability_point_id], back_populates="prerequisites"
    )
    prerequisite: Mapped[CapabilityPoint] = relationship(
        foreign_keys=[prerequisite_id], back_populates="required_by"
    )


class CapabilityKnowledgeRequirement(Base):
    __tablename__ = "capability_knowledge_requirements"
    __table_args__ = (
        Index("idx_capability_knowledge_reverse", "knowledge_point_id", "capability_point_id"),
    )

    capability_point_id: Mapped[int] = mapped_column(
        ForeignKey("capability_points.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    required_level: Mapped[str] = mapped_column(String(16), default="familiar", nullable=False)

    capability_point: Mapped[CapabilityPoint] = relationship(
        back_populates="knowledge_requirements"
    )
    knowledge_point: Mapped[KnowledgePoint] = relationship(
        back_populates="capability_requirements"
    )


class LearningRecordKnowledge(Base):
    __tablename__ = "learning_record_knowledge"

    learning_record_id: Mapped[str] = mapped_column(
        ForeignKey("learning_records.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    evidence: Mapped[str | None] = mapped_column(String(500), nullable=True)

    learning_record: Mapped[LearningRecord] = relationship(back_populates="knowledge_links")
    knowledge_point: Mapped[KnowledgePoint] = relationship(back_populates="learning_record_links")


class ReviewAttempt(UuidPrimaryKeyMixin, Base):
    __tablename__ = "review_attempts"
    __table_args__ = (
        Index("idx_review_attempts_record_time", "learning_record_id", "reviewed_at"),
    )

    learning_record_id: Mapped[str] = mapped_column(
        ForeignKey("learning_records.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="SET NULL"), nullable=True
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    hint_level: Mapped[int] = mapped_column(TINYINT(unsigned=True), default=0, nullable=False)
    mastery_after: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)

    learning_record: Mapped[LearningRecord] = relationship(back_populates="review_attempts")
    session: Mapped[LearningSession | None] = relationship(back_populates="review_attempts")
