"""Add capability points and curriculum prerequisite relations.

Revision ID: 20261002_0005
Revises: 20260930_0004
Create Date: 2026-10-02 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261002_0005"
down_revision: str | Sequence[str] | None = "20260930_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.add_column(
        "knowledge_points",
        sa.Column("description", sa.String(length=1000), nullable=False, server_default=""),
    )
    op.add_column(
        "knowledge_points",
        sa.Column("category", sa.String(length=24), nullable=False, server_default="core"),
    )
    op.add_column(
        "knowledge_points",
        sa.Column(
            "sort_order", mysql.INTEGER(unsigned=True), nullable=False, server_default="0"
        ),
    )

    op.create_table(
        "knowledge_point_prerequisites",
        sa.Column("knowledge_point_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("prerequisite_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("strength", sa.String(length=16), nullable=False),
        sa.Column("required_level", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.String(length=500), nullable=False),
        sa.CheckConstraint(
            "knowledge_point_id <> prerequisite_id",
            name="ck_knowledge_point_prerequisites_knowledge_prerequisite_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            name="fk_kp_prereq_knowledge_point",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prerequisite_id"],
            ["knowledge_points.id"],
            name="fk_kp_prereq_prerequisite",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "knowledge_point_id",
            "prerequisite_id",
            name="pk_knowledge_point_prerequisites",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_knowledge_prerequisites_reverse",
        "knowledge_point_prerequisites",
        ["prerequisite_id", "knowledge_point_id"],
    )

    op.create_table(
        "capability_points",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("subject", sa.String(length=24), nullable=False),
        sa.Column("grade_band", sa.String(length=24), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("sort_order", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("parent_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["capability_points.id"],
            name="fk_capability_points_parent_id_capability_points",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_capability_points"),
        sa.UniqueConstraint("code", name="uq_capability_points_code"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "capability_point_prerequisites",
        sa.Column("capability_point_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("prerequisite_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("strength", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.String(length=500), nullable=False),
        sa.CheckConstraint(
            "capability_point_id <> prerequisite_id",
            name="ck_capability_prereq_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["capability_point_id"],
            ["capability_points.id"],
            name="fk_capability_prereq_point",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prerequisite_id"],
            ["capability_points.id"],
            name="fk_capability_prereq_prerequisite",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "capability_point_id",
            "prerequisite_id",
            name="pk_capability_point_prerequisites",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_capability_prerequisites_reverse",
        "capability_point_prerequisites",
        ["prerequisite_id", "capability_point_id"],
    )

    op.create_table(
        "capability_knowledge_requirements",
        sa.Column("capability_point_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("knowledge_point_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("required_level", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["capability_point_id"],
            ["capability_points.id"],
            name="fk_capability_knowledge_capability",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            name="fk_capability_knowledge_point",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "capability_point_id",
            "knowledge_point_id",
            "role",
            name="pk_capability_knowledge_requirements",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "idx_capability_knowledge_reverse",
        "capability_knowledge_requirements",
        ["knowledge_point_id", "capability_point_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_capability_knowledge_reverse", table_name="capability_knowledge_requirements"
    )
    op.drop_table("capability_knowledge_requirements")
    op.drop_index(
        "idx_capability_prerequisites_reverse",
        table_name="capability_point_prerequisites",
    )
    op.drop_table("capability_point_prerequisites")
    op.drop_table("capability_points")
    op.drop_index(
        "idx_knowledge_prerequisites_reverse", table_name="knowledge_point_prerequisites"
    )
    op.drop_table("knowledge_point_prerequisites")
    op.drop_column("knowledge_points", "sort_order")
    op.drop_column("knowledge_points", "category")
    op.drop_column("knowledge_points", "description")
