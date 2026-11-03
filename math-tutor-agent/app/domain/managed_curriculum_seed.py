from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ManagedSeedPoint(BaseModel):
    """中文：受管目录初始知识点。 English: Initial knowledge point for a managed catalog."""

    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    category: Literal["foundation", "core", "extension"] = "core"
    parent_code: str | None = Field(default=None, max_length=80)
    sort_order: int = Field(ge=0)


class ManagedSeedCatalog(BaseModel):
    """中文：一次导入中的单个后台知识目录。 English: One managed knowledge catalog in a seed import."""

    code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=255)
    topic: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0)
    status: Literal["draft", "published"] = "published"
    points: list[ManagedSeedPoint]


class ManagedSeedPrerequisite(BaseModel):
    """中文：可跨目录的知识点先修关系。 English: Cross-catalog knowledge-point prerequisite relationship."""

    knowledge_code: str
    prerequisite_code: str
    strength: Literal["required", "recommended"] = "required"
    required_level: Literal["introduced", "familiar", "proficient"] = "familiar"
    rationale: str = Field(min_length=1, max_length=500)


class ManagedCurriculumSeed(BaseModel):
    """中文：版本化后台知识目录种子。 English: Versioned seed for administrator-managed knowledge catalogs."""

    seed_code: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=32)
    subject: str = Field(default="math", max_length=24)
    grade_band: str = Field(max_length=24)
    catalogs: list[ManagedSeedCatalog]
    prerequisites: list[ManagedSeedPrerequisite] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> ManagedCurriculumSeed:
        """中文：校验目录编码、父节点和先修引用。 English: Validates catalog codes, parents, and prerequisite references."""
        catalog_keys = [(item.code, self.version) for item in self.catalogs]
        if len(catalog_keys) != len(set(catalog_keys)):
            raise ValueError("catalog codes must be unique within a seed version")
        points = [point for catalog in self.catalogs for point in catalog.points]
        codes = [point.code for point in points]
        if len(codes) != len(set(codes)):
            raise ValueError("knowledge point codes must be unique")
        code_set = set(codes)
        for point in points:
            if point.parent_code and point.parent_code not in code_set:
                raise ValueError(f"unknown parent code: {point.parent_code}")
        for relation in self.prerequisites:
            if relation.knowledge_code not in code_set or relation.prerequisite_code not in code_set:
                raise ValueError("prerequisite relation references an unknown point")
            if relation.knowledge_code == relation.prerequisite_code:
                raise ValueError("a point cannot depend on itself")
        return self
