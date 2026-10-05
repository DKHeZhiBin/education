"""Add immutable generation batch management events.

Revision ID: 20261003_0012
Revises: 20261003_0011
Create Date: 2026-10-03 08:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261003_0012"
down_revision: str | Sequence[str] | None = "20261003_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "generation_batch_management_events",
        sa.Column("generation_batch_id", sa.String(length=36), nullable=False),
        sa.Column("related_batch_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=24), nullable=False),
        sa.Column("current_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("payload_json", mysql.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "action IN ('pause', 'resume', 'cancel', 'retry_created', "
            "'retried_from', 'withdraw_approved')",
            name="ck_generation_batch_management_events_action_allowed",
        ),
        sa.CheckConstraint(
            "actor_type IN ('admin', 'system')",
            name="ck_generation_batch_management_events_actor_type_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["generation_batch_id"],
            ["generation_batches.id"],
            name="fk_batch_events_generation_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_batch_id"],
            ["generation_batches.id"],
            name="fk_batch_events_related_batch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generation_batch_management_events"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_generation_batch_events_batch",
        "generation_batch_management_events",
        ["generation_batch_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_generation_batch_events_batch",
        table_name="generation_batch_management_events",
    )
    op.drop_table("generation_batch_management_events")
