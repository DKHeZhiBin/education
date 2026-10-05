from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class EvaluationSource(BaseModel):
    dataset: str
    upstream_id: str
    repository_url: HttpUrl
    source_file_url: HttpUrl
    source_commit: str
    license: str
    usage: Literal["evaluation_only"] = "evaluation_only"


class HumanReviewProvenance(BaseModel):
    status: Literal["source_committee_reviewed"]
    reviewer_group: str
    review_scope: list[str] = Field(default_factory=list)
    evidence_url: HttpUrl
    local_content_unchanged: bool = True
    local_reviewer: str | None = None


class EvaluationTaxonomy(BaseModel):
    level: str
    source_label: str
    difficulty: Literal["high"] = "high"
    language: str = "en"


class HighDifficultyEvaluationCase(BaseModel):
    id: str
    schema_version: Literal["1.0"] = "1.0"
    evaluation_only: Literal[True] = True
    source: EvaluationSource
    human_review: HumanReviewProvenance
    taxonomy: EvaluationTaxonomy
    problem: str
    reference_answer: str
    reference_solution: str
    evaluation_contract: dict = Field(default_factory=dict)


class GenerationEvaluationInput(BaseModel):
    mother_problem: str = Field(min_length=1, max_length=2000)
    transformation: str = Field(min_length=1, max_length=500)
    grade_band: Literal["middle"] = "middle"
    topic_code: Literal["MS.QE"] = "MS.QE"
    required_knowledge_points: list[str] = Field(min_length=1, max_length=12)


class GenerationEvaluationOracle(BaseModel):
    expected_statement: str = Field(min_length=1, max_length=2000)
    equation: str = Field(min_length=1, max_length=500)
    real_solutions: list[str] = Field(max_length=4)
    real_root_count: int = Field(ge=0, le=2)
    required_properties: list[str] = Field(min_length=1, max_length=20)
    forbidden_properties: list[str] = Field(default_factory=list, max_length=20)


class GenerationEvaluationCase(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    schema_version: Literal["1.0"] = "1.0"
    evaluation_only: Literal[True] = True
    split: Literal["generation_holdout"] = "generation_holdout"
    input: GenerationEvaluationInput
    oracle: GenerationEvaluationOracle
    scoring: dict[str, Any] = Field(default_factory=dict)


class RetrievalEvaluationDocument(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    schema_version: Literal["1.0"] = "1.0"
    evaluation_only: Literal[True] = True
    index_namespace: str = Field(min_length=1, max_length=100)
    entity_type: Literal[
        "concept",
        "principle",
        "problem_pattern",
        "solution_outline",
        "error_pattern",
        "hint",
        "source_fact",
    ]
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=3000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalEvaluationQuery(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    schema_version: Literal["1.0"] = "1.0"
    evaluation_only: Literal[True] = True
    index_namespace: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=1000)
    purpose: Literal[
        "problem_understanding",
        "solution_analysis",
        "hint_teaching",
        "source_lookup",
    ]
    hint_level: int | None = Field(default=None, ge=1, le=4)
    relevant_document_ids: list[str] = Field(min_length=1, max_length=20)
    required_document_ids: list[str] = Field(default_factory=list, max_length=20)
    forbidden_document_ids: list[str] = Field(default_factory=list, max_length=20)
    minimum_recall_at_k: float = Field(default=1.0, ge=0, le=1)
    k: int = Field(default=5, ge=1, le=20)
