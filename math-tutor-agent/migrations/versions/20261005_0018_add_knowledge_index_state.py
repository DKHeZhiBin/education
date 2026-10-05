"""Add durable knowledge index generations for RAG cache invalidation.

Revision ID: 20261005_0018
Revises: 20261004_0017
Create Date: 2026-10-05 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261005_0018"
down_revision: str | Sequence[str] | None = "20261004_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_index_states",
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column(
            "generation",
            mysql.BIGINT(unsigned=True),
            nullable=False,
            server_default="1",
        ),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "generation >= 1",
            name="ck_knowledge_index_states_generation_positive",
        ),
        sa.PrimaryKeyConstraint("scope", name="pk_knowledge_index_states"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade() -> None:
    op.drop_table("knowledge_index_states")
