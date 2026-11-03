from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT, INTEGER, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MYSQL_DATETIME, TimestampMixin, UuidPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.learning import KnowledgePoint


class KnowledgeCatalog(TimestampMixin, Base):
    """中文：可由管理端维护的知识目录。 English: Administrator-maintained knowledge catalog."""

    __tablename__ = "knowledge_catalogs"
    __table_args__ = (
        UniqueConstraint("code", "version", name="knowledge_catalog_code_version"),
        Index("idx_knowledge_catalog_scope", "subject", "grade_band", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(24), default="math", nullable=False)
    grade_band: Mapped[str] = mapped_column(String(24), nullable=False)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    version_lock: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=1, nullable=False)

    knowledge_points: Mapped[list[KnowledgePoint]] = relationship(back_populates="catalog")


class KnowledgePointContent(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """中文：知识点下的定义、性质、定理、公式和题型内容。 English: Definition, property, theorem, formula, or problem-type content attached to a knowledge point."""

    __tablename__ = "knowledge_point_contents"
    __table_args__ = (
        UniqueConstraint("knowledge_point_id", "content_type", "content_key", name="knowledge_point_content_key"),
        Index("idx_knowledge_content_listing", "knowledge_point_id", "content_type", "status", "sort_order"),
        CheckConstraint("content_type IN ('definition','property','theorem','formula','problem_type')", name="knowledge_content_type_allowed"),
        CheckConstraint("status IN ('draft','published','archived')", name="knowledge_content_status_allowed"),
    )

    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False)
    content_type: Mapped[str] = mapped_column(String(24), nullable=False)
    content_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    formula_latex: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    solution_framework_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    sort_order: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    version_lock: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=1, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    knowledge_point: Mapped[KnowledgePoint] = relationship(back_populates="contents")


class KnowledgeAdminAudit(UuidPrimaryKeyMixin, Base):
    """中文：记录管理端对知识目录的每次修改。 English: Audit record for every administrator change to curriculum content."""

    __tablename__ = "knowledge_admin_audits"
    __table_args__ = (Index("idx_knowledge_admin_audit_resource", "resource_type", "resource_id", "created_at"),)

    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(80), nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(MYSQL_DATETIME, default=utc_now, nullable=False)
