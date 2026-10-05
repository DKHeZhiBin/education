"""Add the RAG knowledge schema.

Revision ID: 20260930_0004
Revises: 20260928_0003
Create Date: 2026-09-30 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260930_0004"
down_revision: str | Sequence[str] | None = "20260928_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "source_references",
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("authors_json", mysql.JSON(), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("canonical_url", sa.String(length=1000), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("license_name", sa.String(length=100), nullable=False),
        sa.Column("rights_note", sa.String(length=1000), nullable=True),
        sa.Column("published_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("accessed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_source_references"),
        sa.UniqueConstraint("fingerprint", name="uq_source_references_fingerprint"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_source_references_type_title",
        "source_references",
        ["source_type", "title"],
    )

    op.create_table(
        "curriculum_versions",
        sa.Column("source_reference_id", sa.String(length=36), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=32), nullable=False),
        sa.Column("grade_band", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version_code", sa.String(length=80), nullable=False),
        sa.Column("effective_from", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("effective_to", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_reference_id"],
            ["source_references.id"],
            name="fk_curriculum_versions_source_reference_id_source_references",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_curriculum_versions"),
        sa.UniqueConstraint(
            "authority",
            "region_code",
            "subject",
            "grade_band",
            "version_code",
            name="curriculum_identity",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_curriculum_active_scope",
        "curriculum_versions",
        ["status", "subject", "grade_band"],
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("source_reference_id", sa.String(length=36), nullable=False),
        sa.Column("curriculum_version_id", sa.String(length=36), nullable=True),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("version_label", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=32), nullable=False),
        sa.Column("grade_band", sa.String(length=32), nullable=True),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column("ingestion_status", sa.String(length=20), nullable=False),
        sa.Column("knowledge_point_codes_json", mysql.JSON(), nullable=False),
        sa.Column("metadata_json", mysql.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"],
            ["curriculum_versions.id"],
            name="fk_knowledge_documents_curriculum_version_id_curriculum_versions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_reference_id"],
            ["source_references.id"],
            name="fk_knowledge_documents_source_reference_id_source_references",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_documents"),
        sa.UniqueConstraint(
            "source_reference_id",
            "version_label",
            "content_checksum",
            name="document_source_version_checksum",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_knowledge_documents_scope",
        "knowledge_documents",
        ["lifecycle_status", "subject", "grade_band", "document_type"],
    )
    op.create_index(
        "idx_knowledge_documents_curriculum",
        "knowledge_documents",
        ["curriculum_version_id"],
    )

    op.create_table(
        "document_chunks",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("token_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("heading_path_json", mysql.JSON(), nullable=False),
        sa.Column("locator", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("knowledge_point_codes_json", mysql.JSON(), nullable=False),
        sa.Column("metadata_json", mysql.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_document_chunks_document_id_knowledge_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint("document_id", "ordinal", name="document_chunk_ordinal"),
        sa.UniqueConstraint("document_id", "content_hash", name="document_chunk_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_document_chunks_enabled",
        "document_chunks",
        ["document_id", "enabled", "ordinal"],
    )

    op.create_table(
        "knowledge_problems",
        sa.Column("source_reference_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("source_chunk_id", sa.String(length=36), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("normalized_statement", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=32), nullable=False),
        sa.Column("grade_band", sa.String(length=32), nullable=True),
        sa.Column("problem_type", sa.String(length=64), nullable=False),
        sa.Column("difficulty", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("answer_type", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("knowledge_point_codes_json", mysql.JSON(), nullable=False),
        sa.Column("metadata_json", mysql.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "difficulty BETWEEN 1 AND 5",
            name="ck_knowledge_problems_difficulty_range",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_problems_document_id_knowledge_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"],
            ["document_chunks.id"],
            name="fk_knowledge_problems_source_chunk_id_document_chunks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_reference_id"],
            ["source_references.id"],
            name="fk_knowledge_problems_source_reference_id_source_references",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_problems"),
        sa.UniqueConstraint(
            "source_reference_id",
            "content_hash",
            name="problem_source_content_hash",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_knowledge_problems_scope",
        "knowledge_problems",
        ["review_status", "subject", "grade_band", "problem_type", "difficulty"],
    )
    op.create_index(
        "idx_knowledge_problems_document",
        "knowledge_problems",
        ["document_id", "source_chunk_id"],
    )

    op.create_table(
        "knowledge_solutions",
        sa.Column("problem_id", sa.String(length=36), nullable=False),
        sa.Column("source_reference_id", sa.String(length=36), nullable=False),
        sa.Column("method_name", sa.String(length=255), nullable=False),
        sa.Column("solution_text", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("is_preferred", sa.Boolean(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("metadata_json", mysql.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["knowledge_problems.id"],
            name="fk_knowledge_solutions_problem_id_knowledge_problems",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_reference_id"],
            ["source_references.id"],
            name="fk_knowledge_solutions_source_reference_id_source_references",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_solutions"),
        sa.UniqueConstraint("problem_id", "content_hash", name="problem_solution_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_knowledge_solutions_selection",
        "knowledge_solutions",
        ["problem_id", "review_status", "verification_status", "is_preferred"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_solutions_selection", table_name="knowledge_solutions")
    op.drop_table("knowledge_solutions")
    op.drop_index("idx_knowledge_problems_document", table_name="knowledge_problems")
    op.drop_index("idx_knowledge_problems_scope", table_name="knowledge_problems")
    op.drop_table("knowledge_problems")
    op.drop_index("idx_document_chunks_enabled", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("idx_knowledge_documents_curriculum", table_name="knowledge_documents")
    op.drop_index("idx_knowledge_documents_scope", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("idx_curriculum_active_scope", table_name="curriculum_versions")
    op.drop_table("curriculum_versions")
    op.drop_index("idx_source_references_type_title", table_name="source_references")
    op.drop_table("source_references")
