"""Add validation and generation provenance to production search projections.

Revision ID: 20261004_0016
Revises: 20261004_0015
Create Date: 2026-10-04 06:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261004_0016"
down_revision: str | Sequence[str] | None = "20261004_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_search_documents",
        sa.Column("generation_batch_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "knowledge_search_documents",
        sa.Column("verification_level", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "knowledge_search_documents",
        sa.Column("verification_coverage_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_search_documents",
        sa.Column(
            "verifier_version_ids_json",
            mysql.JSON(),
            nullable=True,
        ),
    )
    op.add_column(
        "knowledge_search_documents",
        sa.Column(
            "verifier_versions_json",
            mysql.JSON(),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE knowledge_search_documents SET "
        "verifier_version_ids_json = JSON_ARRAY(), "
        "verifier_versions_json = JSON_ARRAY()"
    )
    op.alter_column(
        "knowledge_search_documents",
        "verifier_version_ids_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )
    op.alter_column(
        "knowledge_search_documents",
        "verifier_versions_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_knowledge_search_documents_verification_level_allowed",
        "knowledge_search_documents",
        "verification_level IS NULL OR verification_level IN ('none', 'partial', 'full')",
    )
    op.create_index(
        "idx_search_documents_generation_batch",
        "knowledge_search_documents",
        ["generation_batch_id", "index_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_search_documents_generation_batch",
        table_name="knowledge_search_documents",
    )
    op.drop_constraint(
        "ck_knowledge_search_documents_verification_level_allowed",
        "knowledge_search_documents",
        type_="check",
    )
    op.drop_column("knowledge_search_documents", "verifier_versions_json")
    op.drop_column("knowledge_search_documents", "verifier_version_ids_json")
    op.drop_column("knowledge_search_documents", "verification_coverage_json")
    op.drop_column("knowledge_search_documents", "verification_level")
    op.drop_column("knowledge_search_documents", "generation_batch_id")
