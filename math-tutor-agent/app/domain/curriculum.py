from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


MasteryLevel = Literal["introduced", "familiar", "proficient"]
PrerequisiteStrength = Literal["required", "recommended"]
KnowledgeRole = Literal["core", "prerequisite", "supporting"]


class CatalogKnowledgePoint(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    category: Literal["foundation", "core", "extension"]
    parent_code: str | None = Field(default=None, max_length=80)
    sort_order: int = Field(ge=0)


class CatalogCapabilityPoint(BaseModel):
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
    knowledge_code: str
    prerequisite_code: str
    strength: PrerequisiteStrength = "required"
    required_level: MasteryLevel = "familiar"
    rationale: str = Field(min_length=1, max_length=500)


class CapabilityPrerequisite(BaseModel):
    capability_code: str
    prerequisite_code: str
    strength: PrerequisiteStrength = "required"
    rationale: str = Field(min_length=1, max_length=500)


class CapabilityKnowledgeRequirement(BaseModel):
    capability_code: str
    knowledge_code: str
    role: KnowledgeRole
    required_level: MasteryLevel = "familiar"


class CurriculumCatalog(BaseModel):
    catalog_code: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    subject: str = Field(default="math", max_length=24)
    grade_band: str = Field(default="middle", max_length=24)
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
