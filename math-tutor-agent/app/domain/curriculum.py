from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.product_scope import MVP_GRADE_BAND, MVP_SUBJECT_CODE


MasteryLevel = Literal["introduced", "familiar", "proficient"]
PrerequisiteStrength = Literal["required", "recommended"]
KnowledgeRole = Literal["core", "prerequisite", "supporting"]
KnowledgeGraphRole = Literal["topic", "prerequisite"]


class CatalogKnowledgePoint(BaseModel):
    """中文：定义“catalog·知识·point”类，封装该职责相关的数据与行为。
    English: Defines the catalog knowledge point class and encapsulates data and behavior for that responsibility.
    """
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    category: Literal["foundation", "core", "extension"]
    parent_code: str | None = Field(default=None, max_length=80)
    sort_order: int = Field(ge=0)


class CatalogCapabilityPoint(BaseModel):
    """中文：定义“catalog·capability·point”类，封装该职责相关的数据与行为。
    English: Defines the catalog capability point class and encapsulates data and behavior for that responsibility.
    """
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    category: Literal[
        "recognition",
        "transformation",
        "calculation",
        "reasoning",
        "modeling",
        "verification",
        "transfer",
    ]
    parent_code: str | None = Field(default=None, max_length=80)
    sort_order: int = Field(ge=0)


class KnowledgePrerequisite(BaseModel):
    """中文：定义“知识·prerequisite”类，封装该职责相关的数据与行为。
    English: Defines the knowledge prerequisite class and encapsulates data and behavior for that responsibility.
    """
    knowledge_code: str
    prerequisite_code: str
    strength: PrerequisiteStrength = "required"
    required_level: MasteryLevel = "familiar"
    rationale: str = Field(min_length=1, max_length=500)


class CapabilityPrerequisite(BaseModel):
    """中文：定义“capability·prerequisite”类，封装该职责相关的数据与行为。
    English: Defines the capability prerequisite class and encapsulates data and behavior for that responsibility.
    """
    capability_code: str
    prerequisite_code: str
    strength: PrerequisiteStrength = "required"
    rationale: str = Field(min_length=1, max_length=500)


class CapabilityKnowledgeRequirement(BaseModel):
    """中文：定义“capability·知识·requirement”类，封装该职责相关的数据与行为。
    English: Defines the capability knowledge requirement class and encapsulates data and behavior for that responsibility.
    """
    capability_code: str
    knowledge_code: str
    role: KnowledgeRole
    required_level: MasteryLevel = "familiar"


class CurriculumCatalog(BaseModel):
    """中文：定义“课程·catalog”类，封装该职责相关的数据与行为。
    English: Defines the curriculum catalog class and encapsulates data and behavior for that responsibility.
    """
    catalog_code: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    subject: str = Field(default=MVP_SUBJECT_CODE, max_length=24)
    grade_band: str = Field(default=MVP_GRADE_BAND, max_length=24)
    topic: str = Field(min_length=1, max_length=100)
    knowledge_points: list[CatalogKnowledgePoint]
    capability_points: list[CatalogCapabilityPoint]
    knowledge_prerequisites: list[KnowledgePrerequisite] = Field(default_factory=list)
    capability_prerequisites: list[CapabilityPrerequisite] = Field(default_factory=list)
    capability_knowledge_requirements: list[CapabilityKnowledgeRequirement] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_references_and_cycles(self) -> CurriculumCatalog:
        """中文：处理“验证·references·and·cycles”相关操作。
        English: Handles the validate references and cycles operation.
        """
        knowledge_codes = [item.code for item in self.knowledge_points]
        capability_codes = [item.code for item in self.capability_points]
        if len(knowledge_codes) != len(set(knowledge_codes)):
            raise ValueError("knowledge point codes must be unique")
        if len(capability_codes) != len(set(capability_codes)):
            raise ValueError("capability point codes must be unique")

        knowledge_set = set(knowledge_codes)
        capability_set = set(capability_codes)
        for point in self.knowledge_points:
            if point.parent_code is not None and point.parent_code not in knowledge_set:
                raise ValueError(f"unknown knowledge parent: {point.parent_code}")
        for point in self.capability_points:
            if point.parent_code is not None and point.parent_code not in capability_set:
                raise ValueError(f"unknown capability parent: {point.parent_code}")

        knowledge_edges: list[tuple[str, str]] = []
        for relation in self.knowledge_prerequisites:
            if relation.knowledge_code not in knowledge_set:
                raise ValueError(f"unknown knowledge point: {relation.knowledge_code}")
            if relation.prerequisite_code not in knowledge_set:
                raise ValueError(f"unknown knowledge prerequisite: {relation.prerequisite_code}")
            knowledge_edges.append((relation.prerequisite_code, relation.knowledge_code))

        capability_edges: list[tuple[str, str]] = []
        for relation in self.capability_prerequisites:
            if relation.capability_code not in capability_set:
                raise ValueError(f"unknown capability point: {relation.capability_code}")
            if relation.prerequisite_code not in capability_set:
                raise ValueError(f"unknown capability prerequisite: {relation.prerequisite_code}")
            capability_edges.append((relation.prerequisite_code, relation.capability_code))

        for relation in self.capability_knowledge_requirements:
            if relation.capability_code not in capability_set:
                raise ValueError(f"unknown capability point: {relation.capability_code}")
            if relation.knowledge_code not in knowledge_set:
                raise ValueError(f"unknown knowledge point: {relation.knowledge_code}")

        self._ensure_acyclic(knowledge_set, knowledge_edges, "knowledge prerequisite")
        self._ensure_acyclic(capability_set, capability_edges, "capability prerequisite")
        return self

    @staticmethod
    def _ensure_acyclic(
        nodes: set[str], edges: list[tuple[str, str]], relation_name: str
    ) -> None:
        """中文：处理“ensure·acyclic”相关操作。
        English: Handles the ensure acyclic operation.
        """
        adjacency = {node: [] for node in nodes}
        indegree = {node: 0 for node in nodes}
        for source, target in edges:
            if source == target:
                raise ValueError(f"{relation_name} cannot reference itself: {source}")
            adjacency[source].append(target)
            indegree[target] += 1

        queue = [node for node, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for target in adjacency[current]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        if visited != len(nodes):
            raise ValueError(f"{relation_name} graph must be acyclic")


class KnowledgePointView(BaseModel):
    """中文：定义“知识·point·view”类，封装该职责相关的数据与行为。
    English: Defines the knowledge point view class and encapsulates data and behavior for that responsibility.
    """
    code: str
    name: str
    description: str
    category: str
    parent_code: str | None = None
    sort_order: int
    graph_role: KnowledgeGraphRole


class KnowledgePrerequisiteView(BaseModel):
    """中文：定义“知识·prerequisite·view”类，封装该职责相关的数据与行为。
    English: Defines the knowledge prerequisite view class and encapsulates data and behavior for that responsibility.
    """
    knowledge_code: str
    prerequisite_code: str
    strength: PrerequisiteStrength
    required_level: MasteryLevel
    rationale: str


class KnowledgeGraphView(BaseModel):
    """中文：定义“知识·graph·view”类，封装该职责相关的数据与行为。
    English: Defines the knowledge graph view class and encapsulates data and behavior for that responsibility.
    """
    catalog_code: str
    catalog_version: str
    title: str
    subject: str
    grade_band: str
    root_code: str
    knowledge_points: list[KnowledgePointView]
    prerequisites: list[KnowledgePrerequisiteView]


class CurriculumCatalogSummary(BaseModel):
    """中文：面向学生端的可用知识目录摘要。 English: Available curriculum catalog summary for learner-facing navigation."""

    code: str
    version: str
    title: str
    subject: str
    grade_band: str
    topic: str
    root_code: str


class RelatedKnowledgePoint(BaseModel):
    """中文：知识点详情中的直接先修或后续知识。 English: Direct prerequisite or dependent knowledge in a point detail view."""

    code: str
    name: str
    strength: PrerequisiteStrength
    required_level: MasteryLevel
    rationale: str


class PublishedKnowledgeContent(BaseModel):
    """中文：面向学生展示的已发布知识内容。 English: Published knowledge content shown to learners."""
    content_type: Literal["definition", "property", "theorem", "formula", "problem_type"]
    content_key: str
    title: str
    summary: str
    body_markdown: str
    formula_latex: str | None
    structured_json: dict[str, Any]
    solution_framework_json: list[dict[str, Any]]
    sort_order: int


class KnowledgePracticeSource(BaseModel):
    """中文：用于生成相似练习的已发布题型母题。 English: A published problem-type source used to generate similar practice."""

    knowledge_point_code: str
    knowledge_point_name: str
    subject: str
    grade_band: str
    content_key: str
    title: str
    summary: str
    body_markdown: str
    formula_latex: str | None
    structured_json: dict[str, Any]
    solution_framework_json: list[dict[str, Any]]


class KnowledgePointDetailView(BaseModel):
    """中文：知识点详情及其已发布内容。 English: Knowledge-point details with published content."""
    code: str
    name: str
    description: str
    category: str
    grade_band: str
    parent_code: str | None
    catalog_code: str | None
    catalog_version: str | None
    catalog_title: str | None
    root_code: str
    contents: list[PublishedKnowledgeContent]
    prerequisites: list[RelatedKnowledgePoint]
    dependents: list[RelatedKnowledgePoint]
