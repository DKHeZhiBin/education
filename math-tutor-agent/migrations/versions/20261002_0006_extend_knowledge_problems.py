"""Extend knowledge problems for structured generation and admission.

Revision ID: 20261002_0006
Revises: 20261002_0005
Create Date: 2026-10-02 01:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261002_0006"
down_revision: str | Sequence[str] | None = "20261002_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_problems",
        sa.Column("mother_problem_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("explicit_conditions_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("implicit_conditions_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("target_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("difficulty_factors_json", mysql.JSON(), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("derivation_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("derivation_note", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column(
            "content_status",
            sa.String(length=24),
            nullable=False,
            server_default="candidate",
        ),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("status_reason", sa.String(length=1000), nullable=True),
    )

    op.execute(
        "UPDATE knowledge_problems SET "
        "explicit_conditions_json = JSON_ARRAY(), "
        "implicit_conditions_json = JSON_ARRAY(), "
        "difficulty_factors_json = JSON_ARRAY()"
    )
    op.alter_column(
        "knowledge_problems",
        "explicit_conditions_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )
    op.alter_column(
        "knowledge_problems",
        "implicit_conditions_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )
    op.alter_column(
        "knowledge_problems",
        "difficulty_factors_json",
        existing_type=mysql.JSON(),
        nullable=False,
    )

    op.create_foreign_key(
        "fk_knowledge_problems_mother_problem_id_knowledge_problems",
        "knowledge_problems",
        "knowledge_problems",
        ["mother_problem_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_knowledge_problems_mother_problem_not_self",
        "knowledge_problems",
        "mother_problem_id IS NULL OR mother_problem_id <> id",
    )
    op.create_check_constraint(
        "ck_knowledge_problems_mother_derivation_pair",
        "knowledge_problems",
        "(mother_problem_id IS NULL AND derivation_type IS NULL) OR "
        "(mother_problem_id IS NOT NULL AND derivation_type IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_knowledge_problems_content_status_allowed",
        "knowledge_problems",
        "content_status IN ('candidate', 'validating', 'revision_required', "
        "'quarantined', 'approved', 'indexed', 'retired')",
    )
    op.create_check_constraint(
        "ck_knowledge_problems_derivation_type_allowed",
        "knowledge_problems",
        "derivation_type IS NULL OR derivation_type IN ('parameter_change', "
        "'condition_change', 'representation_change', 'context_change', "
        "'method_change', 'isomorphic', 'difficulty_change')",
    )
    op.create_check_constraint(
        "ck_knowledge_problems_status_reason_required",
        "knowledge_problems",
        "content_status NOT IN ('revision_required', 'quarantined', 'retired') "
        "OR status_reason IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_knowledge_problems_approved_target_required",
        "knowledge_problems",
        "content_status NOT IN ('approved', 'indexed') OR target_json IS NOT NULL",
    )
    op.create_index(
        "idx_knowledge_problems_content_status",
        "knowledge_problems",
        ["content_status", "subject", "grade_band", "problem_type"],
    )
    op.create_index(
        "idx_knowledge_problems_mother",
        "knowledge_problems",
        ["mother_problem_id", "derivation_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_problems_mother", table_name="knowledge_problems")
    op.drop_index("idx_knowledge_problems_content_status", table_name="knowledge_problems")
    op.drop_constraint(
        "ck_knowledge_problems_approved_target_required",
        "knowledge_problems",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_problems_status_reason_required",
        "knowledge_problems",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_problems_derivation_type_allowed",
        "knowledge_problems",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_problems_content_status_allowed",
        "knowledge_problems",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_problems_mother_derivation_pair",
        "knowledge_problems",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_problems_mother_problem_not_self",
        "knowledge_problems",
        type_="check",
    )
    op.drop_constraint(
        "fk_knowledge_problems_mother_problem_id_knowledge_problems",
        "knowledge_problems",
        type_="foreignkey",
    )
    op.drop_column("knowledge_problems", "status_reason")
    op.drop_column("knowledge_problems", "content_status")
    op.drop_column("knowledge_problems", "derivation_note")
    op.drop_column("knowledge_problems", "derivation_type")
    op.drop_column("knowledge_problems", "difficulty_factors_json")
    op.drop_column("knowledge_problems", "target_json")
    op.drop_column("knowledge_problems", "implicit_conditions_json")
    op.drop_column("knowledge_problems", "explicit_conditions_json")
    op.drop_column("knowledge_problems", "mother_problem_id")
