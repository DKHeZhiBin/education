from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.mysql import BIGINT, INTEGER, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ThinkingMethodCategory(TimestampMixin, Base):
    """中文：可由管理端维护的数学思想分类。 English: Administrator-managed mathematical thinking category."""

    __tablename__ = "thinking_method_categories"
    __table_args__ = (
        Index("idx_thinking_category_listing", "status", "sort_order"),
        CheckConstraint("status IN ('draft','published','archived')", name="thinking_category_status_allowed"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    focus: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    reminder: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    version_lock: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=1, nullable=False)

    methods: Mapped[list[ThinkingMethod]] = relationship(back_populates="category")


class ThinkingMethod(TimestampMixin, Base):
    """中文：可检索、可分层并带结构化教学正文的数学方法。 English: Searchable, hierarchical mathematical method with structured teaching content."""

    __tablename__ = "thinking_methods"
    __table_args__ = (
        Index("idx_thinking_method_listing", "category_id", "status", "sort_order"),
        CheckConstraint("kind IN ('thought','strategy','technique','theorem_tool')", name="thinking_method_kind_allowed"),
        CheckConstraint("level IN ('入门','深化','进阶')", name="thinking_method_level_allowed"),
        CheckConstraint("status IN ('draft','published','archived')", name="thinking_method_status_allowed"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("thinking_method_categories.id", ondelete="RESTRICT"), nullable=False)
    parent_method_id: Mapped[int | None] = mapped_column(ForeignKey("thinking_methods.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="technique", nullable=False)
    level: Mapped[str] = mapped_column(String(8), default="入门", nullable=False)
    goal: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    example: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    grade_bands_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    domain_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    aliases_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sort_order: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    version_lock: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=1, nullable=False)

    category: Mapped[ThinkingMethodCategory] = relationship(back_populates="methods")
    parent_method: Mapped[ThinkingMethod | None] = relationship(remote_side="ThinkingMethod.id")
