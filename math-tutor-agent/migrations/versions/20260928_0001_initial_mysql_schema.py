"""Create the initial MySQL schema.

Revision ID: 20260928_0001
Revises:
Create Date: 2026-09-28 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260928_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("account_status", sa.String(length=20), nullable=False),
        sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "student_profiles",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=40), nullable=False),
        sa.Column("grade_band", sa.String(length=24), nullable=False),
        sa.Column("current_grade", mysql.TINYINT(unsigned=True), nullable=True),
        sa.Column("preferred_explanation_style", sa.String(length=24), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_student_profiles_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_student_profiles"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "guardian_profiles",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=40), nullable=False),
        sa.Column("report_frequency", sa.String(length=16), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_guardian_profiles_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_guardian_profiles"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "guardian_student_links",
        sa.Column("guardian_user_id", sa.String(length=36), nullable=False),
        sa.Column("student_user_id", sa.String(length=36), nullable=False),
        sa.Column("relationship", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("consented_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["guardian_user_id"], ["users.id"],
            name="fk_guardian_student_links_guardian_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["student_user_id"], ["student_profiles.user_id"],
            name="fk_guardian_student_links_student_user_id_student_profiles", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_guardian_student_links"),
        sa.UniqueConstraint("guardian_user_id", "student_user_id", name="guardian_student"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "learning_sessions",
        sa.Column("student_user_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=24), nullable=False),
        sa.Column("grade_band", sa.String(length=24), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("normalized_question", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("hint_level", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("attempt_count", mysql.SMALLINT(unsigned=True), nullable=False),
        sa.Column("version", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint("hint_level BETWEEN 0 AND 4", name="ck_learning_sessions_hint_level_range"),
        sa.ForeignKeyConstraint(
            ["student_user_id"], ["student_profiles.user_id"],
            name="fk_learning_sessions_student_user_id_student_profiles", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_sessions"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_sessions_student_status", "learning_sessions", ["student_user_id", "status"]
    )
    op.create_index(
        "idx_sessions_student_updated", "learning_sessions", ["student_user_id", "updated_at"]
    )

    op.create_table(
        "session_messages",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_no", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=24), nullable=True),
        sa.Column("client_turn_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["learning_sessions.id"],
            name="fk_session_messages_session_id_learning_sessions", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_messages"),
        sa.UniqueConstraint("session_id", "client_turn_id", name="session_client_turn"),
        sa.UniqueConstraint("session_id", "sequence_no", name="session_sequence"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_messages_session_created", "session_messages", ["session_id", "created_at"]
    )

    op.create_table(
        "agent_runs",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("max_agent_calls", mysql.SMALLINT(unsigned=True), nullable=False),
        sa.Column("agent_call_count", mysql.SMALLINT(unsigned=True), nullable=False),
        sa.Column("duration_ms", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("degraded", sa.Boolean(), nullable=False),
        sa.Column("degradation_reason", sa.String(length=255), nullable=True),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["learning_sessions.id"],
            name="fk_agent_runs_session_id_learning_sessions", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_runs_session_started", "agent_runs", ["session_id", "started_at"])

    op.create_table(
        "agent_run_steps",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("step_no", mysql.SMALLINT(unsigned=True), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("artifact_kind", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("duration_ms", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("model_provider", sa.String(length=40), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("token_input", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("token_output", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message_safe", sa.String(length=500), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_agent_run_steps_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_runs.id"],
            name="fk_agent_run_steps_run_id_agent_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_run_steps"),
        sa.UniqueConstraint("run_id", "step_no", name="run_step"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "agent_artifacts",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("run_step_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_step_id"], ["agent_run_steps.id"],
            name="fk_agent_artifacts_run_step_id_agent_run_steps", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["learning_sessions.id"],
            name="fk_agent_artifacts_session_id_learning_sessions", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_artifacts"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_artifacts_step", "agent_artifacts", ["run_step_id"])
    op.create_index(
        "idx_artifacts_session_kind", "agent_artifacts", ["session_id", "kind", "created_at"]
    )

    op.create_table(
        "knowledge_points",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("subject", sa.String(length=24), nullable=False),
        sa.Column("grade_band", sa.String(length=24), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("parent_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["knowledge_points.id"],
            name="fk_knowledge_points_parent_id_knowledge_points", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_points"),
        sa.UniqueConstraint("code", name="uq_knowledge_points_code"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "learning_records",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("student_user_id", sa.String(length=36), nullable=False),
        sa.Column("question_snapshot", sa.Text(), nullable=False),
        sa.Column("learner_answer", sa.Text(), nullable=True),
        sa.Column("error_category", sa.String(length=40), nullable=True),
        sa.Column("error_reason", sa.String(length=500), nullable=True),
        sa.Column("correct_approach", sa.Text(), nullable=False),
        sa.Column("difficulty", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("mastery_status", sa.String(length=20), nullable=False),
        sa.Column("review_count", mysql.SMALLINT(unsigned=True), nullable=False),
        sa.Column("next_review_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 3", name="ck_learning_records_difficulty_range"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["learning_sessions.id"],
            name="fk_learning_records_session_id_learning_sessions", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["student_user_id"], ["student_profiles.user_id"],
            name="fk_learning_records_student_user_id_student_profiles", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_records"),
        sa.UniqueConstraint("session_id", name="uq_learning_records_session_id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_records_review_queue",
        "learning_records",
        ["student_user_id", "mastery_status", "next_review_at"],
    )

    op.create_table(
        "learning_record_knowledge",
        sa.Column("learning_record_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_point_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("relation_type", sa.String(length=20), nullable=False),
        sa.Column("evidence", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"],
            name="fk_learning_record_knowledge_knowledge_point_id_knowledge_points", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["learning_record_id"], ["learning_records.id"],
            name="fk_learning_record_knowledge_learning_record_id_learning_records", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "learning_record_id", "knowledge_point_id", "relation_type",
            name="pk_learning_record_knowledge",
        ),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "review_attempts",
        sa.Column("learning_record_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("hint_level", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("mastery_after", sa.String(length=20), nullable=False),
        sa.Column("reviewed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["learning_record_id"], ["learning_records.id"],
            name="fk_review_attempts_learning_record_id_learning_records", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["learning_sessions.id"],
            name="fk_review_attempts_session_id_learning_sessions", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_attempts"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_review_attempts_record_time", "review_attempts", ["learning_record_id", "reviewed_at"]
    )

    op.create_table(
        "parent_reports",
        sa.Column("student_user_id", sa.String(length=36), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("content_markdown", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("generated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_user_id"], ["student_profiles.user_id"],
            name="fk_parent_reports_student_user_id_student_profiles", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parent_reports"),
        sa.UniqueConstraint(
            "student_user_id", "period_type", "period_start", "period_end",
            name="student_report_period",
        ),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "media_assets",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("processing_status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"],
            name="fk_media_assets_owner_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["learning_sessions.id"],
            name="fk_media_assets_session_id_learning_sessions", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_assets"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_media_expiry", "media_assets", ["expires_at"])
    op.create_index("idx_media_session_created", "media_assets", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_media_session_created", table_name="media_assets")
    op.drop_index("idx_media_expiry", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_table("parent_reports")
    op.drop_index("idx_review_attempts_record_time", table_name="review_attempts")
    op.drop_table("review_attempts")
    op.drop_table("learning_record_knowledge")
    op.drop_index("idx_records_review_queue", table_name="learning_records")
    op.drop_table("learning_records")
    op.drop_table("knowledge_points")
    op.drop_index("idx_artifacts_session_kind", table_name="agent_artifacts")
    op.drop_index("idx_artifacts_step", table_name="agent_artifacts")
    op.drop_table("agent_artifacts")
    op.drop_table("agent_run_steps")
    op.drop_index("idx_runs_session_started", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("idx_messages_session_created", table_name="session_messages")
    op.drop_table("session_messages")
    op.drop_index("idx_sessions_student_updated", table_name="learning_sessions")
    op.drop_index("idx_sessions_student_status", table_name="learning_sessions")
    op.drop_table("learning_sessions")
    op.drop_table("guardian_student_links")
    op.drop_table("guardian_profiles")
    op.drop_table("student_profiles")
    op.drop_table("users")
