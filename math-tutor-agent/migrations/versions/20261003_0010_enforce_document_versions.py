"""Enforce immutable document versions and index chunk hashes.

Revision ID: 20261003_0010
Revises: 20261003_0009
Create Date: 2026-10-03 02:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261003_0010"
down_revision: str | Sequence[str] | None = "20261003_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # MySQL may use the composite unique index below to support the
    # source_reference_id foreign key. Give that foreign key its own index
    # before replacing the unique constraint.
    op.create_index(
        "idx_knowledge_documents_source_reference",
        "knowledge_documents",
        ["source_reference_id"],
        unique=False,
    )
    op.drop_constraint(
        "document_source_version_checksum",
        "knowledge_documents",
        type_="unique",
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("document_key", sa.String(length=100), nullable=True),
    )
    op.execute(
        "UPDATE knowledge_documents "
        "SET document_key = SHA2(CONCAT(source_reference_id, '|', title), 256) "
        "WHERE document_key IS NULL"
    )
    op.alter_column(
        "knowledge_documents",
        "document_key",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.create_unique_constraint(
        "document_identity_version",
        "knowledge_documents",
        ["source_reference_id", "document_key", "version_label"],
    )
    op.create_index(
        "idx_document_chunks_content_hash",
        "document_chunks",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_document_chunks_content_hash", table_name="document_chunks")
    op.drop_constraint(
        "document_identity_version",
        "knowledge_documents",
        type_="unique",
    )
    op.drop_column("knowledge_documents", "document_key")
    op.create_unique_constraint(
        "document_source_version_checksum",
        "knowledge_documents",
        ["source_reference_id", "version_label", "content_checksum"],
    )
    op.drop_index(
        "idx_knowledge_documents_source_reference",
        table_name="knowledge_documents",
    )
