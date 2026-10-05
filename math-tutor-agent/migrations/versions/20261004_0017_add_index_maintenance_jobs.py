"""Add persistent production index maintenance jobs.

Revision ID: 20261004_0017
Revises: 20261004_0016
Create Date: 2026-10-04 07:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261004_0017"
down_revision: str | Sequence[str] | None = "20261004_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "search_index_maintenance_jobs",
        sa.Column("problem_id", sa.String(length=36), nullable=False),
        sa.Column("replacement_problem_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("trigger_type", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("expected_content_hash", sa.String(length=64), nullable=False),
        sa.Column("target_index_version", sa.String(length=100), nullable=False),
        sa.Column("point_ids_json", mysql.JSON(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("deletion_completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("rebuild_completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "action IN ('remove', 'rebuild')",
            name="ck_search_index_maintenance_jobs_action_allowed",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('retired', 'revalidation', 'version_update')",
            name="ck_search_index_maintenance_jobs_trigger_type_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'deleting', 'waiting_for_approval', "
            "'rebuilding', 'completed', 'failed', 'cancelled')",
            name="ck_search_index_maintenance_jobs_status_allowed",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_search_index_maintenance_jobs_attempt_count_nonnegative",
        ),
        sa.CheckConstraint(
            "(trigger_type = 'retired' AND action = 'remove') OR "
            "(trigger_type IN ('revalidation', 'version_update') AND action = 'rebuild')",
            name="ck_search_index_maintenance_jobs_trigger_action_match",
        ),
        sa.CheckConstraint(
            "trigger_type <> 'version_update' OR replacement_problem_id IS NOT NULL",
            name="ck_index_jobs_version_replacement",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["knowledge_problems.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replacement_problem_id"],
            ["knowledge_problems.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_search_index_maintenance_jobs"),
        sa.UniqueConstraint(
            "idempotency_key_hash",
            name="index_maintenance_idempotency",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_index_maintenance_work",
        "search_index_maintenance_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_index_maintenance_problem",
        "search_index_maintenance_jobs",
        ["problem_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_index_maintenance_problem",
        table_name="search_index_maintenance_jobs",
    )
    op.drop_index(
        "idx_index_maintenance_work",
        table_name="search_index_maintenance_jobs",
    )
    op.drop_table("search_index_maintenance_jobs")
