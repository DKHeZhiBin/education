"""Add account verification and refresh token rotation.

Revision ID: 20260928_0003
Revises: 20260928_0002
Create Date: 2026-09-28 02:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260928_0003"
down_revision: str | Sequence[str] | None = "20260928_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", mysql.DATETIME(fsp=6), nullable=True))
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")

    op.create_table(
        "account_action_tokens",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("used_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_account_action_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_account_action_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_account_action_tokens_token_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_account_tokens_user_purpose",
        "account_action_tokens",
        ["user_id", "purpose", "created_at"],
    )

    op.create_table(
        "refresh_sessions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("used_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("replaced_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["refresh_sessions.id"],
            name="fk_refresh_sessions_replaced_by_id_refresh_sessions", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index("idx_refresh_sessions_user", "refresh_sessions", ["user_id", "created_at"])
    op.create_index("idx_refresh_sessions_family", "refresh_sessions", ["family_id"])


def downgrade() -> None:
    op.drop_index("idx_refresh_sessions_family", table_name="refresh_sessions")
    op.drop_index("idx_refresh_sessions_user", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
    op.drop_index("idx_account_tokens_user_purpose", table_name="account_action_tokens")
    op.drop_table("account_action_tokens")
    op.drop_column("users", "email_verified_at")
