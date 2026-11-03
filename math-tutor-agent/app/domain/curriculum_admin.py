from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.product_scope import MVP_GRADE_BAND, MVP_SUBJECT_CODE


ContentType = Literal["definition", "property", "theorem", "formula", "problem_type"]
PublishStatus = Literal["draft", "published", "archived"]


class CatalogWrite(BaseModel):
    """中文：知识目录新增或更新输入。 English: Input for creating or updating a knowledge catalog."""
    code: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    subject: Literal["math"] = MVP_SUBJECT_CODE
    grade_band: Literal["university"] = MVP_GRADE_BAND
    topic: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)
    status: PublishStatus = "draft"
    expected_version: int | None = Field(default=None, ge=1)


class CatalogView(BaseModel):
    """中文：管理端知识目录视图。 English: Knowledge catalog view for administrators."""
    id: int
    code: str
    version: str
    title: str
    subject: str
    grade_band: str
    topic: str
    sort_order: int
    status: str
    version_lock: int
    knowledge_point_count: int = 0
    updated_at: datetime


class KnowledgePointWrite(BaseModel):
    """中文：知识点新增或更新输入。 English: Input for creating or updating a knowledge point."""
    catalog_id: int | None = None
    subject: Literal["math"] = MVP_SUBJECT_CODE
    grade_band: Literal["university"] = MVP_GRADE_BAND
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    category: Literal["foundation", "core", "extension"] = "core"
    parent_code: str | None = Field(default=None, max_length=80)
    sort_order: int = Field(default=0, ge=0)
    active: bool = True
    expected_version: int | None = Field(default=None, ge=1)


class KnowledgePointAdminView(BaseModel):
    """中文：管理端知识点及内容数量视图。 English: Administrator knowledge-point view with content counts."""
    id: int
    catalog_id: int | None
    subject: str
    grade_band: str
    code: str
    name: str
    description: str
    category: str
    parent_code: str | None
    sort_order: int
    active: bool
    version_lock: int
    content_counts: dict[str, int] = Field(default_factory=dict)
    updated_at: datetime | None = None


class PrerequisiteWrite(BaseModel):
    """中文：知识点先修关系输入。 English: Input for a knowledge prerequisite relationship."""
    knowledge_code: str = Field(min_length=1, max_length=80)
    prerequisite_code: str = Field(min_length=1, max_length=80)
    strength: Literal["required", "recommended"] = "required"
    required_level: Literal["introduced", "familiar", "proficient"] = "familiar"
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def prevent_self_reference(self):
        """中文：禁止知识点依赖自身。 English: Prevents a point from depending on itself."""
        if self.knowledge_code == self.prerequisite_code:
            raise ValueError("知识点不能把自己设为先修")
        return self


class PrerequisiteAdminView(PrerequisiteWrite):
    """中文：管理端先修关系视图。 English: Administrator prerequisite relationship view."""
    knowledge_name: str
    prerequisite_name: str


class SolutionFrameworkStep(BaseModel):
    """中文：题型中的一段框架思路及其对应解题步骤。 English: One problem-type framework idea paired with its worked solution step."""

    title: str = Field(min_length=1, max_length=120)
    framework: str = Field(min_length=1, max_length=2000)
    solution_step: str = Field(min_length=1)
    formula_latex: str | None = None


class KnowledgeContentWrite(BaseModel):
    """中文：定义、性质、定理、公式或题型的编辑输入。 English: Input for definition, property, theorem, formula, or problem-type content."""
    content_type: ContentType
    content_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="", max_length=1000)
    body_markdown: str = Field(min_length=1)
    formula_latex: str | None = None
    structured_json: dict[str, Any] = Field(default_factory=dict)
    solution_framework_json: list[SolutionFrameworkStep] = Field(default_factory=list)
    status: PublishStatus = "draft"
    sort_order: int = Field(default=0, ge=0)
    expected_version: int | None = Field(default=None, ge=1)


class KnowledgeContentView(BaseModel):
    """中文：管理端知识内容视图。 English: Administrator knowledge-content view."""
    id: str
    knowledge_point_id: int
    knowledge_point_code: str
    knowledge_point_name: str
    content_type: str
    content_key: str
    title: str
    summary: str
    body_markdown: str
    formula_latex: str | None
    structured_json: dict[str, Any]
    solution_framework_json: list[SolutionFrameworkStep]
    status: str
    sort_order: int
    version_lock: int
    created_at: datetime
    updated_at: datetime


class KnowledgeDashboard(BaseModel):
    """中文：知识管理首页统计。 English: Knowledge administration dashboard statistics."""
    catalogs: int
    knowledge_points: int
    active_points: int
    relations: int
    contents_by_type: dict[str, int]
    draft_contents: int
    published_contents: int


class BulkKnowledgePointDelete(BaseModel):
    """中文：批量安全删除知识点的输入。 English: Input for safely deleting knowledge points in bulk."""
    point_ids: list[int] = Field(min_length=1, max_length=500)


class BulkKnowledgePointDeleteResult(BaseModel):
    """中文：批量知识点删除结果。 English: Result of a bulk knowledge-point deletion."""
    deleted_count: int
    deleted_ids: list[int]
