from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import INTEGER, JSON, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class KnowledgeSolutionStep(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Relational projection of one stable step in KnowledgeSolution.steps_json."""

    __tablename__ = "knowledge_solution_steps"
    __table_args__ = (
        UniqueConstraint("solution_id", "step_key", name="solution_step_key"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        Index("idx_solution_steps_problem", "problem_id", "active", "sequence"),
        Index("idx_solution_steps_solution", "solution_id", "active", "sequence"),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", name="fk_kss_problem", ondelete="CASCADE"),
        nullable=False,
    )
    solution_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_solutions.id", name="fk_kss_solution", ondelete="CASCADE"),
        nullable=False,
    )
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    action: Mapped[str] = mapped_column(String(1000), nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    justifications_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    depends_on_step_keys_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    condition_refs_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    knowledge_point_codes_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    problem: Mapped["KnowledgeProblem"] = relationship(
        "KnowledgeProblem", back_populates="solution_steps"
    )
    solution: Mapped["KnowledgeSolution"] = relationship(
        "KnowledgeSolution", back_populates="step_index"
    )
    error_pattern_links: Mapped[list["ProblemErrorPattern"]] = relationship(
        back_populates="solution_step"
    )
    hints: Mapped[list["HintBlueprint"]] = relationship(back_populates="solution_step")


class ErrorPattern(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Reusable evidence pattern describing an observable mistake, never a learner label."""

    __tablename__ = "error_patterns"
    __table_args__ = (
        UniqueConstraint("code", name="error_pattern_code"),
        CheckConstraint("severity BETWEEN 1 AND 5", name="severity_range"),
        Index("idx_error_patterns_scope", "subject", "grade_band", "active"),
    )

    code: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), default="math", nullable=False)
    grade_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    severity: Mapped[int] = mapped_column(TINYINT(unsigned=True), default=3, nullable=False)
    detection_rule_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    remediation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    problem_links: Mapped[list["ProblemErrorPattern"]] = relationship(
        back_populates="error_pattern"
    )


class ProblemErrorPattern(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Binds an observable mistake to one indexed step of one solution."""

    __tablename__ = "problem_error_patterns"
    __table_args__ = (
        UniqueConstraint(
            "solution_step_id", "error_pattern_id", name="solution_step_error_pattern"
        ),
        CheckConstraint("priority BETWEEN 1 AND 100", name="priority_range"),
        Index("idx_problem_error_patterns_problem", "problem_id", "active"),
        Index("idx_problem_error_patterns_solution", "solution_id", "solution_step_id"),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", name="fk_pep_problem", ondelete="CASCADE"),
        nullable=False,
    )
    solution_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_solutions.id", name="fk_pep_solution", ondelete="CASCADE"),
        nullable=False,
    )
    solution_step_id: Mapped[str] = mapped_column(
        ForeignKey(
            "knowledge_solution_steps.id", name="fk_pep_solution_step", ondelete="CASCADE"
        ),
        nullable=False,
    )
    error_pattern_id: Mapped[str] = mapped_column(
        ForeignKey("error_patterns.id", name="fk_pep_error_pattern", ondelete="RESTRICT"),
        nullable=False,
    )
    trigger_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    diagnostic_prompt: Mapped[str] = mapped_column(String(1000), nullable=False)
    remediation_goal: Mapped[str] = mapped_column(String(1000), nullable=False)
    priority: Mapped[int] = mapped_column(TINYINT(unsigned=True), default=50, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    problem: Mapped["KnowledgeProblem"] = relationship(
        "KnowledgeProblem", back_populates="error_pattern_links"
    )
    solution: Mapped["KnowledgeSolution"] = relationship(
        "KnowledgeSolution", back_populates="error_pattern_links"
    )
    solution_step: Mapped[KnowledgeSolutionStep] = relationship(
        back_populates="error_pattern_links"
    )
    error_pattern: Mapped[ErrorPattern] = relationship(back_populates="problem_links")
    hints: Mapped[list["HintBlueprint"]] = relationship(back_populates="problem_error_pattern")


class HintBlueprint(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Hint scaffold with an explicit review state and disclosure boundary."""

    __tablename__ = "hint_blueprints"
    __table_args__ = (
        UniqueConstraint("problem_id", "content_hash", name="problem_hint_content_hash"),
        UniqueConstraint("problem_id", "binding_key", "hint_level", name="hint_binding_level"),
        CheckConstraint("hint_level BETWEEN 1 AND 4", name="hint_level_range"),
        CheckConstraint("priority BETWEEN 1 AND 100", name="priority_range"),
        CheckConstraint(
            "review_status IN ('candidate', 'approved', 'retired')",
            name="review_status_allowed",
        ),
        CheckConstraint(
            "source_type IN ('authored', 'ai_candidate', 'imported')",
            name="source_type_allowed",
        ),
        CheckConstraint(
            "(hint_level = 1 AND hint_stage = 'direction' AND reveal_scope = 'direction_only') OR "
            "(hint_level = 2 AND hint_stage = 'key_relation' AND reveal_scope = 'relation_only') OR "
            "(hint_level = 3 AND hint_stage = 'local_step' AND reveal_scope = 'single_step') OR "
            "(hint_level = 4 AND hint_stage = 'full_explanation' AND reveal_scope = 'verified_solution')",
            name="hint_level_stage_scope_match",
        ),
        CheckConstraint(
            "hint_level <> 3 OR solution_step_id IS NOT NULL",
            name="local_hint_requires_step",
        ),
        Index(
            "idx_hint_blueprints_selection", "problem_id", "hint_level",
            "review_status", "active", "priority",
        ),
        Index("idx_hint_blueprints_error", "problem_error_pattern_id"),
        Index("idx_hint_blueprints_step", "solution_step_id"),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", name="fk_hints_problem", ondelete="CASCADE"),
        nullable=False,
    )
    solution_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_solutions.id", name="fk_hints_solution", ondelete="CASCADE"),
        nullable=False,
    )
    solution_step_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "knowledge_solution_steps.id", name="fk_hints_solution_step", ondelete="CASCADE"
        ),
        nullable=True,
    )
    problem_error_pattern_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "problem_error_patterns.id", name="fk_hints_error_link", ondelete="CASCADE"
        ),
        nullable=True,
    )
    binding_key: Mapped[str] = mapped_column(String(180), nullable=False)
    hint_level: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False)
    hint_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    reveal_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    understanding_check: Mapped[str] = mapped_column(String(1000), nullable=False)
    knowledge_point_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="candidate", nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), default="ai_candidate", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=50, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    problem: Mapped["KnowledgeProblem"] = relationship(
        "KnowledgeProblem", back_populates="hint_blueprints"
    )
    solution: Mapped["KnowledgeSolution"] = relationship(
        "KnowledgeSolution", back_populates="hint_blueprints"
    )
    solution_step: Mapped[KnowledgeSolutionStep | None] = relationship(back_populates="hints")
    problem_error_pattern: Mapped[ProblemErrorPattern | None] = relationship(
        back_populates="hints"
    )
