"""Add user authentication fields.

Revision ID: 20260928_0002
Revises: 20260928_0001
Create Date: 2026-09-28 00:30:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260928_0002"
down_revision: str | Sequence[str] | None = "20260928_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            mysql.INTEGER(unsigned=True),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column("users", sa.Column("last_login_at", mysql.DATETIME(fsp=6), nullable=True))

    # Existing development identities cannot be logged into until explicitly
    # registered. The invalid local address keeps every migrated row unique.
    op.execute(
        "UPDATE users "
        "SET email = COALESCE(email, CONCAT('legacy-', id, '@invalid.local')), "
        "password_hash = COALESCE(password_hash, '!')"
    )
    op.alter_column("users", "email", existing_type=sa.String(length=254), nullable=False)
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "users",
        "token_version",
        existing_type=mysql.INTEGER(unsigned=True),
        nullable=False,
        server_default=None,
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "token_version")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
