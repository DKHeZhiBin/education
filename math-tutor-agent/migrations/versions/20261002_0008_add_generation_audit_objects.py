"""Add generation batches, version registries, and admission evidence.

Revision ID: 20261002_0008
Revises: 20261002_0007
Create Date: 2026-10-02 03:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261002_0008"
down_revision: str | Sequence[str] | None = "20261002_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("version_label", sa.String(length=100), nullable=False),
        sa.Column("api_family", sa.String(length=40), nullable=True),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("capabilities_json", mysql.JSON(), nullable=False),
        sa.Column("metadata_json", mysql.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_model_versions"),
        sa.UniqueConstraint(
            "provider", "model_name", "version_label", name="model_version_identity"
        ),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "prompt_versions",
        sa.Column("prompt_key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("template_hash", sa.String(length=64), nullable=False),
        sa.Column("output_schema_version", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_versions"),
        sa.UniqueConstraint("prompt_key", "version", name="prompt_version_identity"),
        sa.UniqueConstraint("prompt_key", "template_hash", name="prompt_template_hash"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "verifier_versions",
        sa.Column("verifier_key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("implementation_hash", sa.String(length=64), nullable=False),
        sa.Column("ruleset_hash", sa.String(length=64), nullable=True),
        sa.Column("supported_problem_types_json", mysql.JSON(), nullable=False),
        sa.Column("config_json", mysql.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_verifier_versions"),
        sa.UniqueConstraint("verifier_key", "version", name="verifier_version_identity"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "generation_batches",
        sa.Column("batch_key", sa.String(length=100), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=32), nullable=False),
        sa.Column("grade_band", sa.String(length=32), nullable=True),
        sa.Column("topic_code", sa.String(length=80), nullable=True),
        sa.Column("requested_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("generated_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("approved_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("quarantined_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("failed_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("model_version_id", sa.String(length=36), nullable=True),
        sa.Column("prompt_version_id", sa.String(length=36), nullable=True),
        sa.Column("config_json", mysql.JSON(), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'partial_failed', 'failed', "
            "'cancelled')",
            name="ck_generation_batches_status_allowed",
        ),
        sa.CheckConstraint(
            "(model_version_id IS NULL AND prompt_version_id IS NULL) OR "
            "(model_version_id IS NOT NULL AND prompt_version_id IS NOT NULL)",
            name="ck_generation_batches_model_prompt_pair",
        ),
        sa.CheckConstraint(
            "approved_count + quarantined_count + failed_count <= generated_count",
            name="ck_generation_batches_classified_count_valid",
        ),
        sa.CheckConstraint(
            "requested_count >= 1",
            name="ck_generation_batches_requested_count_positive",
        ),
        sa.CheckConstraint(
            "status NOT IN ('completed', 'partial_failed', 'failed', 'cancelled') "
            "OR finished_at IS NOT NULL",
            name="ck_generation_batches_terminal_finished_at_required",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name="fk_generation_batches_model_version_id_model_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name="fk_generation_batches_prompt_version_id_prompt_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generation_batches"),
        sa.UniqueConstraint("batch_key", name="batch_key"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_generation_batches_status", "generation_batches", ["status", "created_at"]
    )
    op.create_index(
        "idx_generation_batches_topic",
        "generation_batches",
        ["subject", "grade_band", "topic_code"],
    )

    op.add_column(
        "knowledge_problems",
        sa.Column("generation_batch_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_knowledge_problems_generation_batch_id_generation_batches",
        "knowledge_problems",
        "generation_batches",
        ["generation_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_knowledge_problems_generation_batch",
        "knowledge_problems",
        ["generation_batch_id"],
    )

    op.create_table(
        "admission_evidence",
        sa.Column("generation_batch_id", sa.String(length=36), nullable=False),
        sa.Column("problem_id", sa.String(length=36), nullable=False),
        sa.Column("solution_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("producer_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model_version_id", sa.String(length=36), nullable=True),
        sa.Column("prompt_version_id", sa.String(length=36), nullable=True),
        sa.Column("verifier_version_id", sa.String(length=36), nullable=True),
        sa.Column("is_blocking", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=False),
        sa.Column("payload_json", mysql.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "producer_type IN ('model', 'verifier', 'hybrid', 'system')",
            name="ck_admission_evidence_producer_type_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'not_run', 'inconclusive')",
            name="ck_admission_evidence_status_allowed",
        ),
        sa.CheckConstraint(
            "(producer_type = 'model' AND model_version_id IS NOT NULL AND "
            "prompt_version_id IS NOT NULL AND verifier_version_id IS NULL) OR "
            "(producer_type = 'verifier' AND verifier_version_id IS NOT NULL AND "
            "model_version_id IS NULL AND prompt_version_id IS NULL) OR "
            "(producer_type = 'hybrid' AND model_version_id IS NOT NULL AND "
            "prompt_version_id IS NOT NULL AND verifier_version_id IS NOT NULL) OR "
            "(producer_type = 'system' AND model_version_id IS NULL AND "
            "prompt_version_id IS NULL AND verifier_version_id IS NULL)",
            name="ck_admission_evidence_producer_versions_valid",
        ),
        sa.ForeignKeyConstraint(
            ["generation_batch_id"],
            ["generation_batches.id"],
            name="fk_admission_evidence_generation_batch_id_generation_batches",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["knowledge_problems.id"],
            name="fk_admission_evidence_problem_id_knowledge_problems",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["solution_id"],
            ["knowledge_solutions.id"],
            name="fk_admission_evidence_solution_id_knowledge_solutions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name="fk_admission_evidence_model_version_id_model_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name="fk_admission_evidence_prompt_version_id_prompt_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verifier_version_id"],
            ["verifier_versions.id"],
            name="fk_admission_evidence_verifier_version_id_verifier_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admission_evidence"),
        sa.UniqueConstraint(
            "generation_batch_id",
            "problem_id",
            "evidence_type",
            "evidence_hash",
            name="batch_problem_evidence_hash",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_admission_evidence_problem",
        "admission_evidence",
        ["problem_id", "evidence_type", "status"],
    )
    op.create_index(
        "idx_admission_evidence_batch",
        "admission_evidence",
        ["generation_batch_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_admission_evidence_batch", table_name="admission_evidence")
    op.drop_index("idx_admission_evidence_problem", table_name="admission_evidence")
    op.drop_table("admission_evidence")
    op.drop_index("idx_knowledge_problems_generation_batch", table_name="knowledge_problems")
    op.drop_constraint(
        "fk_knowledge_problems_generation_batch_id_generation_batches",
        "knowledge_problems",
        type_="foreignkey",
    )
    op.drop_column("knowledge_problems", "generation_batch_id")
    op.drop_index("idx_generation_batches_topic", table_name="generation_batches")
    op.drop_index("idx_generation_batches_status", table_name="generation_batches")
    op.drop_table("generation_batches")
    op.drop_table("verifier_versions")
    op.drop_table("prompt_versions")
    op.drop_table("model_versions")
