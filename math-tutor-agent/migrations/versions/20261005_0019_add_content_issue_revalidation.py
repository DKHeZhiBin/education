"""Add content issue reports and bind tutoring sessions to problem-bank items.

Revision ID: 20261005_0019
Revises: 20261005_0018
Create Date: 2026-10-05 02:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261005_0019"
down_revision: str | Sequence[str] | None = "20261005_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.add_column(
        "learning_sessions",
        sa.Column("knowledge_problem_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_learning_sessions_knowledge_problem_id_knowledge_problems",
        "learning_sessions",
        "knowledge_problems",
        ["knowledge_problem_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_sessions_knowledge_problem",
        "learning_sessions",
        ["knowledge_problem_id", "updated_at"],
    )

    op.create_table(
        "content_issue_reports",
        sa.Column("problem_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("reporter_user_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("issue_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_json", mysql.JSON(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("maintenance_job_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "source IN ('student_report', 'runtime_answer_conflict')",
            name="ck_content_issue_reports_source_allowed",
        ),
        sa.CheckConstraint(
            "issue_type IN ('incorrect_answer', 'incorrect_question', "
            "'incorrect_hint', 'ambiguous_content', 'answer_conflict', 'other')",
            name="ck_content_issue_reports_issue_type_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'revalidation_queued', 'validating', "
            "'resolved', 'dismissed')",
            name="ck_content_issue_reports_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["knowledge_problems.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["learning_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["maintenance_job_id"],
            ["search_index_maintenance_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_content_issue_reports"),
        sa.UniqueConstraint(
            "idempotency_key_hash",
            name="content_issue_idempotency",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_content_issues_problem",
        "content_issue_reports",
        ["problem_id", "created_at"],
    )
    op.create_index(
        "idx_content_issues_status",
        "content_issue_reports",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_content_issues_session",
        "content_issue_reports",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_content_issues_session", table_name="content_issue_reports")
    op.drop_index("idx_content_issues_status", table_name="content_issue_reports")
    op.drop_index("idx_content_issues_problem", table_name="content_issue_reports")
    op.drop_table("content_issue_reports")
    op.drop_index("idx_sessions_knowledge_problem", table_name="learning_sessions")
    op.drop_constraint(
        "fk_learning_sessions_knowledge_problem_id_knowledge_problems",
        "learning_sessions",
        type_="foreignkey",
    )
    op.drop_column("learning_sessions", "knowledge_problem_id")
