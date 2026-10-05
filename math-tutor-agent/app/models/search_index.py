from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT, INTEGER, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    MYSQL_DATETIME,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    utc_now,
)


class KnowledgeIndexState(Base):
    """Durable generation for retrieval cache namespace invalidation."""

    __tablename__ = "knowledge_index_states"

    scope: Mapped[str] = mapped_column(String(255), primary_key=True)
    generation: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), default=1, nullable=False
    )
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        MYSQL_DATETIME, default=utc_now, onupdate=utc_now, nullable=False
    )


class KnowledgeSearchDocument(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Canonical MySQL projection shared by keyword and vector indexes."""

    __tablename__ = "knowledge_search_documents"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="search_entity_identity"),
        CheckConstraint(
            "index_status IN ('staging', 'active', 'failed', 'retired')",
            name="index_status_allowed",
        ),
        CheckConstraint(
            "vector_status IN ('pending', 'staged', 'synced', 'failed')",
            name="vector_status_allowed",
        ),
        CheckConstraint(
            "verification_level IS NULL OR "
            "verification_level IN ('none', 'partial', 'full')",
            name="verification_level_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        Index(
            "idx_search_documents_production",
            "index_status",
            "subject",
            "grade_band",
            "entity_type",
        ),
        Index("idx_search_documents_problem", "problem_id", "index_status"),
        Index("idx_search_documents_document", "document_id", "index_status"),
        Index(
            "idx_search_documents_generation_batch",
            "generation_batch_id",
            "index_status",
        ),
        Index("idx_search_documents_vector", "vector_status", "updated_at"),
        Index(
            "ft_search_documents_text",
            "search_text",
            mysql_prefix="FULLTEXT",
            mysql_with_parser="ngram",
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    point_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    problem_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="CASCADE"), nullable=True
    )
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    index_version: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    content_status: Mapped[str] = mapped_column(String(24), nullable=False)
    index_status: Mapped[str] = mapped_column(String(16), default="staging", nullable=False)
    vector_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    subject: Mapped[str] = mapped_column(String(32), default="math", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)
    grade_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    curriculum_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    generation_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verification_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    verification_coverage_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    verifier_version_ids_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    verifier_versions_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    grade_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    knowledge_point_codes_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    problem_types_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    content_types_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    difficulty_sources_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), default=0, nullable=False
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vector_synced_at: Mapped[datetime | None] = mapped_column(MYSQL_DATETIME, nullable=True)


class SearchIndexMaintenanceJob(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Persistent outbox for removing and rebuilding external search indexes."""

    __tablename__ = "search_index_maintenance_jobs"
    __table_args__ = (
        CheckConstraint(
            "action IN ('remove', 'rebuild')",
            name="action_allowed",
        ),
        CheckConstraint(
            "trigger_type IN ('retired', 'revalidation', 'version_update')",
            name="trigger_type_allowed",
        ),
        CheckConstraint(
            "status IN ('pending', 'deleting', 'waiting_for_approval', "
            "'rebuilding', 'completed', 'failed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "(trigger_type = 'retired' AND action = 'remove') OR "
            "(trigger_type IN ('revalidation', 'version_update') AND action = 'rebuild')",
            name="trigger_action_match",
        ),
        CheckConstraint(
            "trigger_type <> 'version_update' OR replacement_problem_id IS NOT NULL",
            name="version_update_replacement_required",
        ),
        UniqueConstraint("idempotency_key_hash", name="index_maintenance_idempotency"),
        Index("idx_index_maintenance_work", "status", "created_at"),
        Index("idx_index_maintenance_problem", "problem_id", "created_at"),
    )

    problem_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=False
    )
    replacement_problem_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_problems.id", ondelete="RESTRICT"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    expected_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_index_version: Mapped[str] = mapped_column(String(100), nullable=False)
    point_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), default=0, nullable=False
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deletion_completed_at: Mapped[datetime | None] = mapped_column(
        MYSQL_DATETIME, nullable=True
    )
    rebuild_completed_at: Mapped[datetime | None] = mapped_column(
        MYSQL_DATETIME, nullable=True
    )
