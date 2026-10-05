from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AnswerClaimAssessment(BaseModel):
    claim_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=2000)
    evidence_document_ids: list[str] = Field(default_factory=list, max_length=20)
    support_status: Literal["supported", "unsupported", "not_assessed"]
    assessment_method: Literal["deterministic", "isolated_judge", "manual"]


class AnswerCitationAssessment(BaseModel):
    claim_id: str = Field(min_length=1, max_length=100)
    document_id: str = Field(min_length=1, max_length=100)
    source_version: str = Field(min_length=1, max_length=100)
    locator: str | None = Field(default=None, max_length=255)


class RetrievalEvaluationRunRecord(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str = Field(min_length=1, max_length=100)
    query_id: str = Field(min_length=1, max_length=100)
    evaluation_only: Literal[True] = True
    index_namespace: str = Field(min_length=1, max_length=100)
    initial_document_ids: list[str] = Field(max_length=100)
    reranked_document_ids: list[str] = Field(max_length=100)
    answer_claims: list[AnswerClaimAssessment] = Field(default_factory=list, max_length=50)
    citations: list[AnswerCitationAssessment] = Field(default_factory=list, max_length=100)
    retriever_version: str = Field(min_length=1, max_length=100)
    reranker_version: str = Field(min_length=1, max_length=100)
    answer_model_version: str | None = Field(default=None, max_length=100)
    evidence_judge_version: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_record(self) -> "RetrievalEvaluationRunRecord":
        if len(self.initial_document_ids) != len(set(self.initial_document_ids)):
            raise ValueError("initial_document_ids must be unique")
        if len(self.reranked_document_ids) != len(set(self.reranked_document_ids)):
            raise ValueError("reranked_document_ids must be unique")
        if not set(self.reranked_document_ids) <= set(self.initial_document_ids):
            raise ValueError("reranking cannot introduce documents absent from initial retrieval")
        claim_ids = [item.claim_id for item in self.answer_claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("answer claim IDs must be unique")
        unknown_claims = {item.claim_id for item in self.citations} - set(claim_ids)
        if unknown_claims:
            raise ValueError(f"citations reference unknown claims: {sorted(unknown_claims)}")
        if any(
            item.assessment_method == "isolated_judge"
            and not self.evidence_judge_version
            for item in self.answer_claims
        ):
            raise ValueError("isolated claim judgments require evidence_judge_version")
        return self


class RetrievalQueryQuality(BaseModel):
    query_id: str
    k: int = Field(ge=1, le=20)
    recall_at_k: float = Field(ge=0, le=1)
    recall_threshold_met: bool
    required_hit: bool
    forbidden_hit_count: int = Field(ge=0)
    baseline_ndcg_at_k: float = Field(ge=0, le=1)
    reranked_ndcg_at_k: float = Field(ge=0, le=1)
    rerank_delta: float = Field(ge=-1, le=1)
    assessed_claim_count: int = Field(ge=0)
    consistent_claim_count: int = Field(ge=0)
    citation_count: int = Field(ge=0)
    correct_citation_count: int = Field(ge=0)
    unknown_document_ids: list[str] = Field(default_factory=list)


class RetrievalQualityMetric(BaseModel):
    key: Literal[
        "retrieval_recall_at_k",
        "rerank_ndcg_at_k",
        "answer_evidence_consistency",
        "citation_correctness",
    ]
    label: str
    numerator: float = Field(ge=0)
    denominator: float = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)
    percentage: float | None = Field(default=None, ge=0, le=100)
    status: Literal["available", "no_samples"]
    definition: str
    details: dict[str, Any] = Field(default_factory=dict)


class RetrievalQualityReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    suite_name: str
    index_namespace: str
    expected_query_count: int = Field(ge=1)
    evaluated_query_count: int = Field(ge=0)
    query_coverage: float = Field(ge=0, le=1)
    metrics: list[RetrievalQualityMetric] = Field(min_length=4, max_length=4)
    queries: list[RetrievalQueryQuality] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
