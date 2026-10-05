"""Link problems, solution steps, error patterns, and four-level hints.

Revision ID: 20261003_0014
Revises: 20261003_0013
Create Date: 2026-10-03 10:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261003_0014"
down_revision: str | Sequence[str] | None = "20261003_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "error_patterns",
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("subject", sa.String(length=32), nullable=False),
        sa.Column("grade_band", sa.String(length=32), nullable=True),
        sa.Column("severity", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("detection_rule_json", mysql.JSON(), nullable=False),
        sa.Column("remediation_json", mysql.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "severity BETWEEN 1 AND 5", name="ck_error_patterns_severity_range"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_error_patterns"),
        sa.UniqueConstraint("code", name="error_pattern_code"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_error_patterns_scope",
        "error_patterns",
        ["subject", "grade_band", "active"],
    )

    op.create_table(
        "knowledge_solution_steps",
        sa.Column("problem_id", sa.String(length=36), nullable=False),
        sa.Column("solution_id", sa.String(length=36), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("sequence", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("action", sa.String(length=1000), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("justifications_json", mysql.JSON(), nullable=False),
        sa.Column("depends_on_step_keys_json", mysql.JSON(), nullable=False),
        sa.Column("condition_refs_json", mysql.JSON(), nullable=False),
        sa.Column("knowledge_point_codes_json", mysql.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "sequence >= 1", name="ck_knowledge_solution_steps_sequence_positive"
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["knowledge_problems.id"],
            name="fk_kss_problem", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solution_id"], ["knowledge_solutions.id"],
            name="fk_kss_solution", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_solution_steps"),
        sa.UniqueConstraint("solution_id", "step_key", name="solution_step_key"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_solution_steps_problem",
        "knowledge_solution_steps",
        ["problem_id", "active", "sequence"],
    )
    op.create_index(
        "idx_solution_steps_solution",
        "knowledge_solution_steps",
        ["solution_id", "active", "sequence"],
    )

    op.create_table(
        "problem_error_patterns",
        sa.Column("problem_id", sa.String(length=36), nullable=False),
        sa.Column("solution_id", sa.String(length=36), nullable=False),
        sa.Column("solution_step_id", sa.String(length=36), nullable=False),
        sa.Column("error_pattern_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_evidence_json", mysql.JSON(), nullable=False),
        sa.Column("diagnostic_prompt", sa.String(length=1000), nullable=False),
        sa.Column("remediation_goal", sa.String(length=1000), nullable=False),
        sa.Column("priority", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 100",
            name="ck_problem_error_patterns_priority_range",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["knowledge_problems.id"],
            name="fk_pep_problem", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solution_id"], ["knowledge_solutions.id"],
            name="fk_pep_solution", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solution_step_id"], ["knowledge_solution_steps.id"],
            name="fk_pep_solution_step", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["error_pattern_id"], ["error_patterns.id"],
            name="fk_pep_error_pattern", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_error_patterns"),
        sa.UniqueConstraint(
            "solution_step_id", "error_pattern_id", name="solution_step_error_pattern"
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_problem_error_patterns_problem",
        "problem_error_patterns",
        ["problem_id", "active"],
    )
    op.create_index(
        "idx_problem_error_patterns_solution",
        "problem_error_patterns",
        ["solution_id", "solution_step_id"],
    )

    op.create_table(
        "hint_blueprints",
        sa.Column("problem_id", sa.String(length=36), nullable=False),
        sa.Column("solution_id", sa.String(length=36), nullable=False),
        sa.Column("solution_step_id", sa.String(length=36), nullable=True),
        sa.Column("problem_error_pattern_id", sa.String(length=36), nullable=True),
        sa.Column("binding_key", sa.String(length=180), nullable=False),
        sa.Column("hint_level", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("hint_stage", sa.String(length=32), nullable=False),
        sa.Column("reveal_scope", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("understanding_check", sa.String(length=1000), nullable=False),
        sa.Column("knowledge_point_codes_json", mysql.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("priority", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "hint_level BETWEEN 1 AND 4", name="ck_hint_blueprints_hint_level_range"
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 100", name="ck_hint_blueprints_priority_range"
        ),
        sa.CheckConstraint(
            "review_status IN ('candidate', 'approved', 'retired')",
            name="ck_hint_blueprints_review_status_allowed",
        ),
        sa.CheckConstraint(
            "source_type IN ('authored', 'ai_candidate', 'imported')",
            name="ck_hint_blueprints_source_type_allowed",
        ),
        sa.CheckConstraint(
            "(hint_level = 1 AND hint_stage = 'direction' AND reveal_scope = 'direction_only') OR "
            "(hint_level = 2 AND hint_stage = 'key_relation' AND reveal_scope = 'relation_only') OR "
            "(hint_level = 3 AND hint_stage = 'local_step' AND reveal_scope = 'single_step') OR "
            "(hint_level = 4 AND hint_stage = 'full_explanation' AND reveal_scope = 'verified_solution')",
            name="ck_hint_blueprints_hint_level_stage_scope_match",
        ),
        sa.CheckConstraint(
            "hint_level <> 3 OR solution_step_id IS NOT NULL",
            name="ck_hint_blueprints_local_hint_requires_step",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["knowledge_problems.id"],
            name="fk_hints_problem", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solution_id"], ["knowledge_solutions.id"],
            name="fk_hints_solution", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solution_step_id"], ["knowledge_solution_steps.id"],
            name="fk_hints_solution_step", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_error_pattern_id"], ["problem_error_patterns.id"],
            name="fk_hints_error_link", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hint_blueprints"),
        sa.UniqueConstraint(
            "problem_id", "content_hash", name="problem_hint_content_hash"
        ),
        sa.UniqueConstraint(
            "problem_id", "binding_key", "hint_level", name="hint_binding_level"
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_hint_blueprints_selection",
        "hint_blueprints",
        ["problem_id", "hint_level", "review_status", "active", "priority"],
    )
    op.create_index(
        "idx_hint_blueprints_error", "hint_blueprints", ["problem_error_pattern_id"]
    )
    op.create_index(
        "idx_hint_blueprints_step", "hint_blueprints", ["solution_step_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_hint_blueprints_step", table_name="hint_blueprints")
    op.drop_index("idx_hint_blueprints_error", table_name="hint_blueprints")
    op.drop_index("idx_hint_blueprints_selection", table_name="hint_blueprints")
    op.drop_table("hint_blueprints")

    op.drop_index(
        "idx_problem_error_patterns_solution", table_name="problem_error_patterns"
    )
    op.drop_index(
        "idx_problem_error_patterns_problem", table_name="problem_error_patterns"
    )
    op.drop_table("problem_error_patterns")

    op.drop_index("idx_solution_steps_solution", table_name="knowledge_solution_steps")
    op.drop_index("idx_solution_steps_problem", table_name="knowledge_solution_steps")
    op.drop_table("knowledge_solution_steps")

    op.drop_index("idx_error_patterns_scope", table_name="error_patterns")
    op.drop_table("error_patterns")
