"""Add retrieval classification tags to documents, chunks, and problems.

Revision ID: 20261003_0013
Revises: 20261003_0012
Create Date: 2026-10-03 09:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261003_0013"
down_revision: str | Sequence[str] | None = "20261003_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("grade_codes_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("problem_types_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("difficulty_factors_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("content_types_json", mysql.JSON(), nullable=True),
    )
    op.execute(
        "UPDATE knowledge_documents SET "
        "grade_codes_json = JSON_ARRAY(), "
        "problem_types_json = JSON_ARRAY(), "
        "difficulty_factors_json = JSON_ARRAY(), "
        "content_types_json = JSON_ARRAY(document_type)"
    )
    for column_name in (
        "grade_codes_json",
        "problem_types_json",
        "difficulty_factors_json",
        "content_types_json",
    ):
        op.alter_column(
            "knowledge_documents",
            column_name,
            existing_type=mysql.JSON(),
            nullable=False,
        )

    op.add_column(
        "document_chunks",
        sa.Column("curriculum_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("grade_band", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("grade_codes_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("problem_types_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("difficulty_factors_json", mysql.JSON(), nullable=True),
    )
    op.execute(
        "UPDATE document_chunks AS chunk "
        "JOIN knowledge_documents AS document ON document.id = chunk.document_id "
        "SET chunk.curriculum_version_id = document.curriculum_version_id, "
        "chunk.grade_band = document.grade_band, "
        "chunk.grade_codes_json = document.grade_codes_json, "
        "chunk.problem_types_json = document.problem_types_json, "
        "chunk.difficulty_factors_json = document.difficulty_factors_json"
    )
    for column_name in (
        "grade_codes_json",
        "problem_types_json",
        "difficulty_factors_json",
    ):
        op.alter_column(
            "document_chunks",
            column_name,
            existing_type=mysql.JSON(),
            nullable=False,
        )
    op.create_foreign_key(
        "fk_document_chunks_curriculum_version_id_curriculum_versions",
        "document_chunks",
        "curriculum_versions",
        ["curriculum_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_document_chunks_tags",
        "document_chunks",
        ["curriculum_version_id", "grade_band", "content_type"],
    )

    op.add_column(
        "knowledge_problems",
        sa.Column("curriculum_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("grade_codes_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column(
            "content_type",
            sa.String(length=40),
            nullable=False,
            server_default="problem",
        ),
    )
    op.execute(
        "UPDATE knowledge_problems SET grade_codes_json = JSON_ARRAY()"
    )
    op.execute(
        "UPDATE knowledge_problems AS problem "
        "JOIN knowledge_documents AS document ON document.id = problem.document_id "
        "SET problem.curriculum_version_id = document.curriculum_version_id, "
        "problem.grade_codes_json = document.grade_codes_json "
        "WHERE problem.curriculum_version_id IS NULL"
    )
    op.alter_column(
        "knowledge_problems",
        "grade_codes_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_knowledge_problems_curriculum_version_id_curriculum_versions",
        "knowledge_problems",
        "curriculum_versions",
        ["curriculum_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_knowledge_problems_tags",
        "knowledge_problems",
        ["curriculum_version_id", "content_type", "grade_band", "problem_type"],
    )
    op.alter_column(
        "knowledge_problems",
        "content_type",
        existing_type=sa.String(length=40),
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_problems_tags", table_name="knowledge_problems")
    op.drop_constraint(
        "fk_knowledge_problems_curriculum_version_id_curriculum_versions",
        "knowledge_problems",
        type_="foreignkey",
    )
    op.drop_column("knowledge_problems", "content_type")
    op.drop_column("knowledge_problems", "grade_codes_json")
    op.drop_column("knowledge_problems", "curriculum_version_id")

    op.drop_index("idx_document_chunks_tags", table_name="document_chunks")
    op.drop_constraint(
        "fk_document_chunks_curriculum_version_id_curriculum_versions",
        "document_chunks",
        type_="foreignkey",
    )
    op.drop_column("document_chunks", "difficulty_factors_json")
    op.drop_column("document_chunks", "problem_types_json")
    op.drop_column("document_chunks", "grade_codes_json")
    op.drop_column("document_chunks", "grade_band")
    op.drop_column("document_chunks", "curriculum_version_id")

    op.drop_column("knowledge_documents", "content_types_json")
    op.drop_column("knowledge_documents", "difficulty_factors_json")
    op.drop_column("knowledge_documents", "problem_types_json")
    op.drop_column("knowledge_documents", "grade_codes_json")
