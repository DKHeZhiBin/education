from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.knowledge import (
    KnowledgeCitation,
    RetrievedConcept,
    RetrievedErrorPattern,
    RetrievedHint,
    RetrievedPrinciple,
    RetrievedProblemPattern,
    RetrievedSolutionOutline,
    RetrievedSourceFact,
    SolutionVerificationCoverage,
)


VectorEntityType = Literal[
    "concept",
    "principle",
    "problem_pattern",
    "solution_outline",
    "error_pattern",
    "hint",
    "source_fact",
]


class VerifierVersionPayload(BaseModel):
    """中文：定义“verifier·version·payload”类，封装该职责相关的数据与行为。
    English: Defines the verifier version payload class and encapsulates data and behavior for that responsibility.
    """
    verifier_version_id: str = Field(min_length=1, max_length=36)
    verifier_key: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=32)
    implementation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ruleset_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class QdrantTeachingPayload(BaseModel):
    """中文：定义“Qdrant·教学·payload”类，封装该职责相关的数据与行为。
    English: Defines the qdrant teaching payload class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Versioned payload contract shared by the indexer and retriever.
    """

    schema_version: Literal["1.0", "1.1"] = "1.1"
    index_status: Literal["staging", "active"] = "active"
    content_status: Literal["approved", "indexed"]
    entity_type: VectorEntityType
    entity_id: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="math", min_length=1, max_length=32)
    grade_band: str | None = Field(default=None, max_length=32)
    grade_codes: list[str] = Field(default_factory=list, max_length=12)
    knowledge_point_codes: list[str] = Field(default_factory=list, max_length=20)
    problem_types: list[str] = Field(default_factory=list, max_length=12)
    content_types: list[str] = Field(default_factory=list, max_length=12)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    difficulty_sources: list[str] = Field(default_factory=list, max_length=12)
    curriculum_version: str | None = Field(default=None, max_length=100)
    curriculum_version_id: str | None = None
    language: str = Field(default="zh-CN", min_length=2, max_length=16)
    disclosure_level: int = Field(default=1, ge=1, le=4)
    hint_level: int | None = Field(default=None, ge=1, le=4)
    generation_batch_id: str | None = Field(default=None, max_length=36)
    verification_level: Literal["none", "partial", "full"] | None = None
    verification_coverage: SolutionVerificationCoverage | None = None
    verifier_version_ids: list[str] = Field(default_factory=list, max_length=20)
    verifier_versions: list[VerifierVersionPayload] = Field(
        default_factory=list, max_length=20
    )
    evaluation_only: Literal[False] = False
    search_text: str = Field(min_length=1, max_length=4000)
    teaching_object: dict[str, Any]
    citation: KnowledgeCitation
    source_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_model: str = Field(min_length=1, max_length=200)
    index_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_structured_object(self) -> "QdrantTeachingPayload":
        """中文：处理“验证·structured·object”相关操作。
        English: Handles the validate structured object operation.
        """
        models = {
            "concept": RetrievedConcept,
            "principle": RetrievedPrinciple,
            "problem_pattern": RetrievedProblemPattern,
            "solution_outline": RetrievedSolutionOutline,
            "error_pattern": RetrievedErrorPattern,
            "hint": RetrievedHint,
            "source_fact": RetrievedSourceFact,
        }
        model = models[self.entity_type]
        validated = model.model_validate({
            **self.teaching_object,
            "score": 0,
            "citation": self.citation.model_dump(mode="json"),
        })
        if self.entity_type == "hint":
            if self.hint_level != validated.hint_level:
                raise ValueError("payload hint_level must match teaching_object")
            if self.disclosure_level != validated.hint_level:
                raise ValueError("hint disclosure_level must equal hint_level")
        elif self.hint_level is not None:
            raise ValueError("hint_level is only valid for hint entities")
        if hasattr(validated, "disclosure_level") and (
            self.disclosure_level != validated.disclosure_level
        ):
            raise ValueError("payload disclosure_level must match teaching_object")
        if self.verification_coverage is None:
            if self.verification_level is not None:
                raise ValueError(
                    "verification_level requires verification_coverage"
                )
        elif self.verification_level != self.verification_coverage.level:
            raise ValueError(
                "verification_level must match verification_coverage.level"
            )
        version_ids = [item.verifier_version_id for item in self.verifier_versions]
        if len(version_ids) != len(set(version_ids)):
            raise ValueError("verifier_versions must contain unique versions")
        if self.verifier_version_ids != version_ids:
            raise ValueError(
                "verifier_version_ids must match verifier_versions in order"
            )
        return self


class VectorPoint(BaseModel):
    """中文：定义“向量·point”类，封装该职责相关的数据与行为。
    English: Defines the vector point class and encapsulates data and behavior for that responsibility.
    """
    id: UUID
    vector: list[float] = Field(min_length=1)
    payload: QdrantTeachingPayload


class CollectionProvisionResult(BaseModel):
    """中文：定义“collection·provision·结果”类，封装该职责相关的数据与行为。
    English: Defines the collection provision result class and encapsulates data and behavior for that responsibility.
    """
    collection: str
    created: bool
    vector_name: str
    vector_size: int
    payload_indexes: list[str]
