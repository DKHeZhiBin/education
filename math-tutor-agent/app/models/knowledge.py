from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import INTEGER, JSON, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    MYSQL_DATETIME,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    utc_now,
)

if TYPE_CHECKING:
    from app.models.generation import AdmissionEvidence, GenerationBatch
    from app.models.teaching import HintBlueprint, KnowledgeSolutionStep, ProblemErrorPattern


class SourceReference(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_references"
    __table_args__ = (
        Index("idx_source_references_type_title", "source_type", "title"),
    )

    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    license_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rights_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    accessed_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    curriculum_versions: Mapped[list[CurriculumVersion]] = relationship(
        back_populates="source_reference"
    )
    documents: Mapped[list[KnowledgeDocument]] = relationship(back_populates="source_reference")
    problems: Mapped[list[KnowledgeProblem]] = relationship(back_populates="source_reference")
    solutions: Mapped[list[KnowledgeSolution]] = relationship(back_populates="source_reference")


class CurriculumVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "curriculum_versions"
    __table_args__ = (
        UniqueConstraint(
            "authority",
            "region_code",
            "subject",
            "grade_band",
            "version_code",
            name="curriculum_identity",
        ),
        Index("idx_curriculum_active_scope", "status", "subject", "grade_band"),
    )

    source_reference_id: Mapped[str] = mapped_column(
        ForeignKey("source_references.id", ondelete="RESTRICT"), nullable=False
    )
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    region_code: Mapped[str] = mapped_column(String(32), default="CN", nullable=False)
    subject: Mapped[str] = mapped_column(String(32), default="math", nullable=False)
    grade_band: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_code: Mapped[str] = mapped_column(String(80), nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    source_reference: Mapped[SourceReference] = relationship(back_populates="curriculum_versions")
    documents: Mapped[list[KnowledgeDocument]] = relationship(back_populates="curriculum_version")
    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="curriculum_version")
    problems: Mapped[list[KnowledgeProblem]] = relationship(back_populates="curriculum_version")


class KnowledgeDocument(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "source_reference_id",
            "document_key",
            "version_label",
            name="document_identity_version",
        ),
        Index(
            "idx_knowledge_documents_scope",
            "lifecycle_status",
            "subject",
            "grade_band",
            "document_type",
        ),
        Index("idx_knowledge_documents_curriculum", "curriculum_version_id"),
    )

    source_reference_id: Mapped[str] = mapped_column(
        ForeignKey("source_references.id", ondelete="RESTRICT"), nullable=False
    )
    curriculum_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="SET NULL"), nullable=True
    )
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    document_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    version_label: Mapped[str] = mapped_column(String(100), default="original", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)
    subject: Mapped[str] = mapped_column(String(32), default="math", nullable=False)
    grade_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed", nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    ingestion_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    knowledge_point_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    problem_types_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    difficulty_factors_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    content_types_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    source_reference: Mapped[SourceReference] = relationship(back_populates="documents")
    curriculum_version: Mapped[CurriculumVersion | None] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.ordinal",
    )
    problems: Mapped[list[KnowledgeProblem]] = relationship(back_populates="document")


class DocumentChunk(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="document_chunk_ordinal"),
        UniqueConstraint("document_id", "content_hash", name="document_chunk_hash"),
        Index("idx_document_chunks_enabled", "document_id", "enabled", "ordinal"),
        Index("idx_document_chunks_content_hash", "content_hash"),
        Index(
            "idx_document_chunks_tags",
            "curriculum_version_id",
            "grade_band",
            "content_type",
        ),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    curriculum_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="SET NULL"), nullable=True
    )
    ordinal: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    heading_path_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    locator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(40), default="text", nullable=False)
    grade_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    knowledge_point_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    problem_types_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    difficulty_factors_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
    curriculum_version: Mapped[CurriculumVersion | None] = relationship(
        back_populates="chunks"
    )
    problems: Mapped[list[KnowledgeProblem]] = relationship(back_populates="source_chunk")


class KnowledgeProblem(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_problems"
    __table_args__ = (
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="difficulty_range"),
        UniqueConstraint(
            "source_reference_id",
            "content_hash",
            name="problem_source_content_hash",
        ),
        Index(
            "idx_knowledge_problems_scope",
            "review_status",
            "subject",
            "grade_band",
            "problem_type",
            "difficulty",
        ),
        Index("idx_knowledge_problems_document", "document_id", "source_chunk_id"),
        Index(
            "idx_knowledge_problems_content_status",
            "content_status",
            "subject",
            "grade_band",
            "problem_type",
        ),
        Index("idx_knowledge_problems_mother", "mother_problem_id", "derivation_type"),
        Index("idx_knowledge_problems_generation_batch", "generation_batch_id"),
        Index(
            "idx_knowledge_problems_tags",
            "curriculum_version_id",
            "content_type",
            "grade_band",
            "problem_type",
        ),
        CheckConstraint(
            "mother_problem_id IS NULL OR mother_problem_id <> id",
            name="mother_problem_not_self",
        ),
        CheckConstraint(
            "(mother_problem_id IS NULL AND derivation_type IS NULL) OR "
            "(mother_problem_id IS NOT NULL AND derivation_type IS NOT NULL)",
            name="mother_derivation_pair",
        ),
        CheckConstraint(
            "content_status IN ('candidate', 'validating', 'revision_required', "
            "'quarantined', 'approved', 'indexed', 'retired')",
            name="content_status_allowed",
        ),
        CheckConstraint(
            "derivation_type IS NULL OR derivation_type IN ('parameter_change', "
            "'condition_change', 'representation_change', 'context_change', "
            "'method_change', 'isomorphic', 'difficulty_change')",
            name="derivation_type_allowed",
        ),
        CheckConstraint(
            "content_status NOT IN ('revision_required', 'quarantined', 'retired') "
            "OR status_reason IS NOT NULL",
            name="status_reason_required",
        ),
        CheckConstraint(
            "content_status NOT IN ('approved', 'indexed') OR target_json IS NOT NULL",
            name="approved_target_required",
        ),
        CheckConstraint("revision_attempts >= 0", name="revision_attempts_nonnegative"),
        CheckConstraint("status_version >= 1", name="status_version_positive"),
    )

    source_reference_id: Mapped[str] = mapped_column(
        ForeignKey("source_references.id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True
    )
    source_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    mother_problem_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=True
    )
    generation_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_batches.id", ondelete="RESTRICT"), nullable=True
    )
    curriculum_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("curriculum_versions.id", ondelete="SET NULL"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(32), default="math", nullable=False)
    grade_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    problem_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), default="problem", nullable=False)
    difficulty: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False)
    answer_type: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed", nullable=False)
    explicit_conditions_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    implicit_conditions_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    target_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    difficulty_factors_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    derivation_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    derivation_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content_status: Mapped[str] = mapped_column(String(24), default="candidate", nullable=False)
    status_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    revision_attempts: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), default=0, nullable=False
    )
    status_version: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), default=1, nullable=False
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        MYSQL_DATETIME, default=utc_now, nullable=False
    )
    knowledge_point_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    source_reference: Mapped[SourceReference] = relationship(back_populates="problems")
    document: Mapped[KnowledgeDocument | None] = relationship(back_populates="problems")
    source_chunk: Mapped[DocumentChunk | None] = relationship(back_populates="problems")
    mother_problem: Mapped[KnowledgeProblem | None] = relationship(
        remote_side="KnowledgeProblem.id",
        foreign_keys=[mother_problem_id],
        back_populates="variants",
    )
    variants: Mapped[list[KnowledgeProblem]] = relationship(
        foreign_keys="KnowledgeProblem.mother_problem_id",
        back_populates="mother_problem",
    )
    generation_batch: Mapped["GenerationBatch | None"] = relationship(
        "GenerationBatch", back_populates="problems"
    )
    curriculum_version: Mapped[CurriculumVersion | None] = relationship(
        back_populates="problems"
    )
    admission_evidence: Mapped[list["AdmissionEvidence"]] = relationship(
        "AdmissionEvidence", back_populates="problem"
    )
    status_transitions: Mapped[list[ProblemStatusTransition]] = relationship(
        back_populates="problem",
        order_by="ProblemStatusTransition.created_at",
    )
    solutions: Mapped[list[KnowledgeSolution]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
    )
    solution_steps: Mapped[list["KnowledgeSolutionStep"]] = relationship(
        "KnowledgeSolutionStep", back_populates="problem"
    )
    error_pattern_links: Mapped[list["ProblemErrorPattern"]] = relationship(
        "ProblemErrorPattern", back_populates="problem"
    )
    hint_blueprints: Mapped[list["HintBlueprint"]] = relationship(
        "HintBlueprint", back_populates="problem"
    )


class ProblemStatusTransition(UuidPrimaryKeyMixin, Base):
    __tablename__ = "problem_status_transitions"
    __table_args__ = (
        CheckConstraint(
            "from_status IN ('candidate', 'validating', 'revision_required', "
            "'quarantined', 'approved', 'indexed', 'retired')",
            name="from_status_allowed",
        ),
        CheckConstraint(
            "to_status IN ('candidate', 'validating', 'revision_required', "
            "'quarantined', 'approved', 'indexed', 'retired')",
            name="to_status_allowed",
        ),
        CheckConstraint(
            "actor_type IN ('admin', 'agent', 'job', 'system')",
            name="actor_type_allowed",
        ),
        CheckConstraint("revision_attempts >= 0", name="revision_attempts_nonnegative"),
        CheckConstraint("status_version >= 2", name="status_version_valid"),
        UniqueConstraint("problem_id", "status_version", name="problem_status_version"),
        Index("idx_problem_transitions_problem", "problem_id", "created_at"),
        Index("idx_problem_transitions_target", "to_status", "created_at"),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    revision_attempts: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    status_version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    checked_requirements_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        MYSQL_DATETIME, default=utc_now, nullable=False
    )

    problem: Mapped[KnowledgeProblem] = relationship(back_populates="status_transitions")


class KnowledgeSolution(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_solutions"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('unverified', 'partial', 'verified', 'failed')",
            name="verification_status_allowed",
        ),
        UniqueConstraint("problem_id", "content_hash", name="problem_solution_hash"),
        Index(
            "idx_knowledge_solutions_selection",
            "problem_id",
            "review_status",
            "verification_status",
            "is_preferred",
        ),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="CASCADE"), nullable=False
    )
    source_reference_id: Mapped[str] = mapped_column(
        ForeignKey("source_references.id", ondelete="RESTRICT"), nullable=False
    )
    method_name: Mapped[str] = mapped_column(String(255), nullable=False)
    solution_text: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed", nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(20), default="unverified", nullable=False
    )
    steps_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    key_breakthroughs_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    verification_coverage_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "level": "none",
            "covered_step_ids": [],
            "uncovered_step_ids": [],
            "checks": [],
            "limitations": [],
            "confidence": 0,
        },
        nullable=False,
    )
    is_preferred: Mapped[bool] = mapped_column(default=False, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    problem: Mapped[KnowledgeProblem] = relationship(back_populates="solutions")
    source_reference: Mapped[SourceReference] = relationship(back_populates="solutions")
    admission_evidence: Mapped[list["AdmissionEvidence"]] = relationship(
        "AdmissionEvidence", back_populates="solution"
    )
    step_index: Mapped[list["KnowledgeSolutionStep"]] = relationship(
        "KnowledgeSolutionStep", back_populates="solution"
    )
    error_pattern_links: Mapped[list["ProblemErrorPattern"]] = relationship(
        "ProblemErrorPattern", back_populates="solution"
    )
    hint_blueprints: Mapped[list["HintBlueprint"]] = relationship(
        "HintBlueprint", back_populates="solution"
    )
