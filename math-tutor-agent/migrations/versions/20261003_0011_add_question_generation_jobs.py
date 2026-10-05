"""Add question generation job contracts and persistence.

Revision ID: 20261003_0011
Revises: 20261003_0010
Create Date: 2026-10-03 03:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261003_0011"
down_revision: str | Sequence[str] | None = "20261003_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.drop_constraint(
        "ck_generation_batches_status_allowed",
        "generation_batches",
        type_="check",
    )
    op.create_check_constraint(
        "ck_generation_batches_status_allowed",
        "generation_batches",
        "status IN ('pending', 'running', 'paused', 'completed', "
        "'partial_failed', 'failed', 'cancelled')",
    )
    op.drop_constraint(
        "ck_generation_batches_classified_count_valid",
        "generation_batches",
        type_="check",
    )
    op.execute(
        "UPDATE generation_batches "
        "SET config_json = JSON_SET(config_json, '$.legacy_failed_count', failed_count), "
        "failed_count = GREATEST(requested_count - generated_count, 0) "
        "WHERE generated_count + failed_count > requested_count"
    )
    op.create_check_constraint(
        "ck_generation_batches_classified_count_valid",
        "generation_batches",
        "approved_count + quarantined_count <= generated_count",
    )
    op.create_check_constraint(
        "ck_generation_batches_batch_outcome_count_valid",
        "generation_batches",
        "generated_count + failed_count <= requested_count",
    )
    op.execute(
        "UPDATE generation_batches "
        "SET started_at = COALESCE(started_at, created_at, finished_at, UTC_TIMESTAMP(6)), "
        "config_json = JSON_SET(config_json, '$.started_at_backfilled_by_0011', true) "
        "WHERE status IN ('running', 'paused', 'completed', 'partial_failed', 'failed') "
        "AND started_at IS NULL"
    )
    op.execute(
        "UPDATE generation_batches "
        "SET config_json = JSON_SET(config_json, '$.legacy_nonterminal_finished_at', "
        "CAST(finished_at AS CHAR)), finished_at = NULL "
        "WHERE status IN ('pending', 'running', 'paused') AND finished_at IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_generation_batches_executed_started_at_required",
        "generation_batches",
        "status NOT IN ('running', 'paused', 'completed', 'partial_failed', 'failed') "
        "OR started_at IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_generation_batches_nonterminal_finished_at_forbidden",
        "generation_batches",
        "status IN ('completed', 'partial_failed', 'failed', 'cancelled') "
        "OR finished_at IS NULL",
    )

    op.create_table(
        "question_generation_jobs",
        sa.Column("generation_batch_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_scope", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("input_schema_version", sa.String(length=32), nullable=False),
        sa.Column("output_schema_version", sa.String(length=32), nullable=False),
        sa.Column("input_json", mysql.JSON(), nullable=False),
        sa.Column("budget_json", mysql.JSON(), nullable=False),
        sa.Column("usage_json", mysql.JSON(), nullable=False),
        sa.Column("output_json", mysql.JSON(), nullable=True),
        sa.Column("attempt_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("status_reason", sa.String(length=1000), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_question_generation_jobs_attempt_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["generation_batch_id"],
            ["generation_batches.id"],
            name="fk_question_jobs_generation_batch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_question_generation_jobs"),
        sa.UniqueConstraint(
            "generation_batch_id",
            name="question_generation_job_batch",
        ),
        sa.UniqueConstraint(
            "idempotency_key_hash",
            name="question_generation_job_idempotency",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_question_generation_jobs_scope",
        "question_generation_jobs",
        ["idempotency_scope", "created_at"],
    )
    op.create_index(
        "idx_question_generation_jobs_request",
        "question_generation_jobs",
        ["request_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_question_generation_jobs_request",
        table_name="question_generation_jobs",
    )
    op.drop_index(
        "idx_question_generation_jobs_scope",
        table_name="question_generation_jobs",
    )
    op.drop_table("question_generation_jobs")

    op.drop_constraint(
        "ck_generation_batches_nonterminal_finished_at_forbidden",
        "generation_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_generation_batches_executed_started_at_required",
        "generation_batches",
        type_="check",
    )

    op.drop_constraint(
        "ck_generation_batches_batch_outcome_count_valid",
        "generation_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_generation_batches_classified_count_valid",
        "generation_batches",
        type_="check",
    )
    op.execute(
        "UPDATE generation_batches "
        "SET config_json = JSON_SET(config_json, "
        "'$.pre_downgrade_failed_count', failed_count), "
        "failed_count = GREATEST(generated_count - approved_count - quarantined_count, 0) "
        "WHERE approved_count + quarantined_count + failed_count > generated_count"
    )
    op.create_check_constraint(
        "ck_generation_batches_classified_count_valid",
        "generation_batches",
        "approved_count + quarantined_count + failed_count <= generated_count",
    )

    op.drop_constraint(
        "ck_generation_batches_status_allowed",
        "generation_batches",
        type_="check",
    )
    op.execute(
        "UPDATE generation_batches "
        "SET config_json = JSON_SET(config_json, '$.pre_downgrade_status', status), "
        "status = 'cancelled', "
        "finished_at = COALESCE(finished_at, UTC_TIMESTAMP(6)) "
        "WHERE status = 'paused'"
    )
    op.create_check_constraint(
        "ck_generation_batches_status_allowed",
        "generation_batches",
        "status IN ('pending', 'running', 'completed', 'partial_failed', "
        "'failed', 'cancelled')",
    )
