"""Add scheduled approved-content cross review and tool revalidation jobs.

Revision ID: 20261006_0020
Revises: 20261005_0019
Create Date: 2026-10-06 08:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261006_0020"
down_revision: str | Sequence[str] | None = "20261005_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "content_revalidation_policies",
        sa.Column("policy_key", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("cadence_hours", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("max_items_per_run", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("subject", sa.String(32), nullable=False),
        sa.Column("topic_code", sa.String(80), nullable=True),
        sa.Column("problem_type", sa.String(64), nullable=True),
        sa.Column("execution_model_version_id", sa.String(36), nullable=False),
        sa.Column("review_model_version_id", sa.String(36), nullable=False),
        sa.Column("condition_prompt_version_id", sa.String(36), nullable=False),
        sa.Column("solver_prompt_version_id", sa.String(36), nullable=False),
        sa.Column("review_prompt_version_id", sa.String(36), nullable=False),
        sa.Column("sympy_verifier_version_id", sa.String(36), nullable=False),
        sa.Column("numeric_verifier_version_id", sa.String(36), nullable=False),
        sa.Column("duplicate_verifier_version_id", sa.String(36), nullable=False),
        sa.Column("leakage_verifier_version_id", sa.String(36), nullable=False),
        sa.Column("next_run_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_run_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("config_json", mysql.JSON(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("cadence_hours >= 1", name="ck_content_revalidation_policies_cadence_hours_positive"),
        sa.CheckConstraint("max_items_per_run >= 1", name="ck_content_revalidation_policies_max_items_positive"),
        sa.ForeignKeyConstraint(["execution_model_version_id"], ["model_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_model_version_id"], ["model_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["condition_prompt_version_id"], ["prompt_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["solver_prompt_version_id"], ["prompt_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_prompt_version_id"], ["prompt_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sympy_verifier_version_id"], ["verifier_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["numeric_verifier_version_id"], ["verifier_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["duplicate_verifier_version_id"], ["verifier_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["leakage_verifier_version_id"], ["verifier_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_content_revalidation_policies"),
        sa.UniqueConstraint("policy_key", name="content_revalidation_policy_key"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_revalidation_policies_due", "content_revalidation_policies", ["enabled", "next_run_at"])

    op.create_table(
        "content_revalidation_runs",
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("run_key", sa.String(160), nullable=False),
        sa.Column("trigger_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("scheduled_for", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("selected_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("passed_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("failed_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("inconclusive_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("summary_json", mysql.JSON(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("trigger_type IN ('scheduled', 'manual')", name="ck_content_revalidation_runs_trigger_type_allowed"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'partial_failed', 'failed', 'cancelled')",
            name="ck_content_revalidation_runs_status_allowed",
        ),
        sa.CheckConstraint("selected_count >= 0", name="ck_content_revalidation_runs_selected_count_nonnegative"),
        sa.ForeignKeyConstraint(["policy_id"], ["content_revalidation_policies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_content_revalidation_runs"),
        sa.UniqueConstraint("run_key", name="content_revalidation_run_key"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_revalidation_runs_work", "content_revalidation_runs", ["status", "scheduled_for"])
    op.create_index("idx_revalidation_runs_policy", "content_revalidation_runs", ["policy_id", "created_at"])

    op.create_table(
        "content_revalidation_items",
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("problem_id", sa.String(36), nullable=False),
        sa.Column("solution_id", sa.String(36), nullable=True),
        sa.Column("maintenance_job_id", sa.String(36), nullable=True),
        sa.Column("problem_content_hash", sa.String(64), nullable=False),
        sa.Column("solution_content_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("tool_evidence_ids_json", mysql.JSON(), nullable=False),
        sa.Column("condition_evidence_id", sa.String(36), nullable=True),
        sa.Column("solution_independence_evidence_id", sa.String(36), nullable=True),
        sa.Column("ai_review_evidence_id", sa.String(36), nullable=True),
        sa.Column("admission_evidence_id", sa.String(36), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'suppressing', 'validating', 'tool_verification', "
            "'ai_review', 'admission', 'passed', 'failed', 'inconclusive')",
            name="ck_content_revalidation_items_status_allowed",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('passed', 'failed', 'inconclusive')",
            name="ck_content_revalidation_items_outcome_allowed",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["content_revalidation_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["problem_id"], ["knowledge_problems.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["solution_id"], ["knowledge_solutions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["maintenance_job_id"], ["search_index_maintenance_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["condition_evidence_id"], ["admission_evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["solution_independence_evidence_id"], ["admission_evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ai_review_evidence_id"], ["admission_evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["admission_evidence_id"], ["admission_evidence.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_content_revalidation_items"),
        sa.UniqueConstraint("run_id", "problem_id", name="revalidation_run_problem"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_revalidation_items_work", "content_revalidation_items", ["run_id", "status", "created_at"])
    op.create_index("idx_revalidation_items_problem", "content_revalidation_items", ["problem_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_revalidation_items_problem", table_name="content_revalidation_items")
    op.drop_index("idx_revalidation_items_work", table_name="content_revalidation_items")
    op.drop_table("content_revalidation_items")
    op.drop_index("idx_revalidation_runs_policy", table_name="content_revalidation_runs")
    op.drop_index("idx_revalidation_runs_work", table_name="content_revalidation_runs")
    op.drop_table("content_revalidation_runs")
    op.drop_index("idx_revalidation_policies_due", table_name="content_revalidation_policies")
    op.drop_table("content_revalidation_policies")
