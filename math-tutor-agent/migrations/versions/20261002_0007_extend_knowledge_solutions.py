"""Extend knowledge solutions with structured steps and verification coverage.

Revision ID: 20261002_0007
Revises: 20261002_0006
Create Date: 2026-10-02 02:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261002_0007"
down_revision: str | Sequence[str] | None = "20261002_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_solutions",
        sa.Column("steps_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_solutions",
        sa.Column("key_breakthroughs_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_solutions",
        sa.Column("verification_coverage_json", mysql.JSON(), nullable=True),
    )

    op.execute(
        "UPDATE knowledge_solutions SET "
        "metadata_json = JSON_SET(metadata_json, '$.pre_structure_verification_status', "
        "verification_status), "
        "verification_status = 'unverified', "
        "steps_json = JSON_ARRAY(), "
        "key_breakthroughs_json = JSON_ARRAY(), "
        "verification_coverage_json = JSON_OBJECT("
        "'level', 'none', "
        "'covered_step_ids', JSON_ARRAY(), "
        "'uncovered_step_ids', JSON_ARRAY(), "
        "'checks', JSON_ARRAY(), "
        "'limitations', JSON_ARRAY('需要按结构化步骤重新验证'), "
        "'confidence', 0)"
    )
    op.alter_column(
        "knowledge_solutions",
        "steps_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )
    op.alter_column(
        "knowledge_solutions",
        "key_breakthroughs_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )
    op.alter_column(
        "knowledge_solutions",
        "verification_coverage_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_knowledge_solutions_verification_status_allowed",
        "knowledge_solutions",
        "verification_status IN ('unverified', 'partial', 'verified', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_knowledge_solutions_verification_status_allowed",
        "knowledge_solutions",
        type_="check",
    )
    op.execute(
        "UPDATE knowledge_solutions SET "
        "verification_status = COALESCE("
        "JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.pre_structure_verification_status')), "
        "verification_status), "
        "metadata_json = JSON_REMOVE(metadata_json, '$.pre_structure_verification_status')"
    )
    op.drop_column("knowledge_solutions", "verification_coverage_json")
    op.drop_column("knowledge_solutions", "key_breakthroughs_json")
    op.drop_column("knowledge_solutions", "steps_json")
