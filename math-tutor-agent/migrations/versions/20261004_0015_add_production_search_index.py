"""Add the canonical production keyword and vector search projection.

Revision ID: 20261004_0015
Revises: 20261003_0014
Create Date: 2026-10-04 05:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261004_0015"
down_revision: str | Sequence[str] | None = "20261003_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "knowledge_search_documents",
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("point_id", sa.String(length=36), nullable=False),
        sa.Column("problem_id", sa.String(length=36), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("index_version", sa.String(length=100), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("content_status", sa.String(length=24), nullable=False),
        sa.Column("index_status", sa.String(length=16), nullable=False),
        sa.Column("vector_status", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("grade_band", sa.String(length=32), nullable=True),
        sa.Column("curriculum_version_id", sa.String(length=36), nullable=True),
        sa.Column("grade_codes_json", mysql.JSON(), nullable=False),
        sa.Column("knowledge_point_codes_json", mysql.JSON(), nullable=False),
        sa.Column("problem_types_json", mysql.JSON(), nullable=False),
        sa.Column("content_types_json", mysql.JSON(), nullable=False),
        sa.Column("difficulty_sources_json", mysql.JSON(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("payload_json", mysql.JSON(), nullable=False),
        sa.Column("attempt_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("vector_synced_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "index_status IN ('staging', 'active', 'failed', 'retired')",
            name="ck_knowledge_search_documents_index_status_allowed",
        ),
        sa.CheckConstraint(
            "vector_status IN ('pending', 'staged', 'synced', 'failed')",
            name="ck_knowledge_search_documents_vector_status_allowed",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_knowledge_search_documents_attempt_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["knowledge_problems.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_search_documents"),
        sa.UniqueConstraint("entity_type", "entity_id", name="search_entity_identity"),
        sa.UniqueConstraint("point_id", name="uq_knowledge_search_documents_point_id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_search_documents_production",
        "knowledge_search_documents",
        ["index_status", "subject", "grade_band", "entity_type"],
    )
    op.create_index(
        "idx_search_documents_problem",
        "knowledge_search_documents",
        ["problem_id", "index_status"],
    )
    op.create_index(
        "idx_search_documents_document",
        "knowledge_search_documents",
        ["document_id", "index_status"],
    )
    op.create_index(
        "idx_search_documents_vector",
        "knowledge_search_documents",
        ["vector_status", "updated_at"],
    )
    op.create_index(
        "ft_search_documents_text",
        "knowledge_search_documents",
        ["search_text"],
        mysql_prefix="FULLTEXT",
        mysql_with_parser="ngram",
    )


def downgrade() -> None:
    op.drop_index("ft_search_documents_text", table_name="knowledge_search_documents")
    op.drop_index("idx_search_documents_vector", table_name="knowledge_search_documents")
    op.drop_index("idx_search_documents_document", table_name="knowledge_search_documents")
    op.drop_index("idx_search_documents_problem", table_name="knowledge_search_documents")
    op.drop_index("idx_search_documents_production", table_name="knowledge_search_documents")
    op.drop_table("knowledge_search_documents")
