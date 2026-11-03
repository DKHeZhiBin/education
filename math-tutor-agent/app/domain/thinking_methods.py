from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.product_scope import MVP_GRADE_BAND


PublishStatus = Literal["draft", "published", "archived"]
MethodKind = Literal["thought", "strategy", "technique", "theorem_tool"]
MethodLevel = Literal["入门", "深化", "进阶"]


class ThinkingMethodCategoryWrite(BaseModel):
    """中文：思想分类新增或更新输入。 English: Input for creating or updating a thinking-method category."""

    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str = Field(min_length=1, max_length=100)
    symbol: str = Field(default="", max_length=16)
    focus: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=1000)
    reminder: str = Field(default="", max_length=1000)
    sort_order: int = Field(default=0, ge=0)
    status: PublishStatus = "draft"
    expected_version: int | None = Field(default=None, ge=1)


class ThinkingMethodCategoryView(BaseModel):
    """中文：管理端思想分类视图。 English: Thinking-method category view for administrators."""

    id: int
    code: str
    label: str
    symbol: str
    focus: str
    description: str
    reminder: str
    sort_order: int
    status: str
    version_lock: int
    method_count: int = 0
    updated_at: datetime


class ThinkingMethodWrite(BaseModel):
    """中文：数学方法新增或更新输入。 English: Input for creating or updating a mathematical method."""

    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    category_id: int
    parent_method_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    kind: MethodKind = "technique"
    level: MethodLevel = "入门"
    goal: str = Field(default="", max_length=1000)
    example: str = Field(default="", max_length=2000)
    grade_bands: list[Literal["university"]] = Field(
        default_factory=lambda: [MVP_GRADE_BAND], min_length=1, max_length=1
    )
    domain_tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0)
    status: PublishStatus = "draft"
    expected_version: int | None = Field(default=None, ge=1)


class ThinkingMethodView(BaseModel):
    """中文：管理端数学方法视图。 English: Mathematical method view for administrators."""

    id: int
    code: str
    category_id: int
    category_code: str
    category_label: str
    parent_method_id: int | None
    parent_method_code: str | None
    name: str
    kind: str
    level: str
    goal: str
    example: str
    grade_bands: list[str]
    domain_tags: list[str]
    aliases: list[str]
    detail: dict[str, Any]
    sort_order: int
    status: str
    version_lock: int
    updated_at: datetime


class PublishedThinkingMethod(BaseModel):
    """中文：学生端可见的已发布数学方法。 English: Published mathematical method visible to learners."""

    code: str
    parent_method_code: str | None
    name: str
    kind: str
    level: str
    goal: str
    example: str
    grade_bands: list[str]
    domain_tags: list[str]
    aliases: list[str]
    detail: dict[str, Any]
    sort_order: int


class PublishedThinkingMethodCategory(BaseModel):
    """中文：学生端方法目录中的一个已发布分类。 English: Published category in the learner method catalog."""

    code: str
    label: str
    symbol: str
    focus: str
    description: str
    reminder: str
    sort_order: int
    methods: list[PublishedThinkingMethod]


class ThinkingMethodDetail(PublishedThinkingMethod):
    """中文：带分类信息的学生端方法详情。 English: Learner method detail with category metadata."""

    category_code: str
    category_label: str
