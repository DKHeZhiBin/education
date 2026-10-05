"""Add persistent problem lifecycle state and transition history.

Revision ID: 20261003_0009
Revises: 20261002_0008
Create Date: 2026-10-03 00:30:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261003_0009"
down_revision: str | Sequence[str] | None = "20261002_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}

STATUS_VALUES = (
    "'candidate', 'validating', 'revision_required', 'quarantined', "
    "'approved', 'indexed', 'retired'"
)


def upgrade() -> None:
    op.add_column(
        "knowledge_problems",
        sa.Column(
            "revision_attempts",
            mysql.INTEGER(unsigned=True),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column(
            "status_version",
            mysql.INTEGER(unsigned=True),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "knowledge_problems",
        sa.Column("status_changed_at", mysql.DATETIME(fsp=6), nullable=True),
    )
    op.execute(
        "UPDATE knowledge_problems "
        "SET status_changed_at = COALESCE(updated_at, created_at, UTC_TIMESTAMP(6))"
    )
    op.alter_column(
        "knowledge_problems",
        "status_changed_at",
        existing_type=mysql.DATETIME(fsp=6),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_knowledge_problems_revision_attempts_nonnegative",
        "knowledge_problems",
        "revision_attempts >= 0",
    )
    op.create_check_constraint(
        "ck_knowledge_problems_status_version_positive",
        "knowledge_problems",
        "status_version >= 1",
    )

    op.create_table(
        "problem_status_transitions",
        sa.Column("problem_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("revision_attempts", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("status_version", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("checked_requirements_json", mysql.JSON(), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            f"from_status IN ({STATUS_VALUES})",
            name="ck_problem_status_transitions_from_status_allowed",
        ),
        sa.CheckConstraint(
            f"to_status IN ({STATUS_VALUES})",
            name="ck_problem_status_transitions_to_status_allowed",
        ),
        sa.CheckConstraint(
            "actor_type IN ('admin', 'agent', 'job', 'system')",
            name="ck_problem_status_transitions_actor_type_allowed",
        ),
        sa.CheckConstraint(
            "revision_attempts >= 0",
            name="ck_problem_status_transitions_revision_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "status_version >= 2",
            name="ck_problem_status_transitions_status_version_valid",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["knowledge_problems.id"],
            name="fk_problem_status_transitions_problem_id_knowledge_problems",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_status_transitions"),
        sa.UniqueConstraint(
            "problem_id",
            "status_version",
            name="problem_status_version",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_problem_transitions_problem",
        "problem_status_transitions",
        ["problem_id", "created_at"],
    )
    op.create_index(
        "idx_problem_transitions_target",
        "problem_status_transitions",
        ["to_status", "created_at"],
    )

    op.alter_column(
        "knowledge_problems",
        "revision_attempts",
        existing_type=mysql.INTEGER(unsigned=True),
        server_default=None,
    )
    op.alter_column(
        "knowledge_problems",
        "status_version",
        existing_type=mysql.INTEGER(unsigned=True),
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_problem_transitions_target", table_name="problem_status_transitions"
    )
    op.drop_index(
        "idx_problem_transitions_problem", table_name="problem_status_transitions"
    )
    op.drop_table("problem_status_transitions")
    op.drop_constraint(
        "ck_knowledge_problems_status_version_positive",
        "knowledge_problems",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_problems_revision_attempts_nonnegative",
        "knowledge_problems",
        type_="check",
    )
    op.drop_column("knowledge_problems", "status_changed_at")
    op.drop_column("knowledge_problems", "status_version")
    op.drop_column("knowledge_problems", "revision_attempts")
