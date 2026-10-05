from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class DuplicateDetectionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class DuplicateProblemSnapshot(BaseModel):
    problem_id: str
    content_hash: str = Field(min_length=64, max_length=64)
    statement: str
    normalized_statement: str | None = None
    subject: str
    grade_band: str | None = None
    problem_type: str
    content_status: str
    status_version: int = Field(ge=1)
    generation_batch_id: str | None = None
    mother_problem_id: str | None = None
    explicit_conditions: list[dict[str, Any]] = Field(default_factory=list)
    implicit_conditions: list[dict[str, Any]] = Field(default_factory=list)
    target: dict[str, Any]
    knowledge_point_codes: list[str] = Field(default_factory=list)
    solution_id: str | None = None
    solution_content_hash: str | None = None
    solution_method_name: str | None = None
    solution_steps: list[dict[str, Any]] = Field(default_factory=list)


class DuplicateDetectionContext(BaseModel):
    candidate: DuplicateProblemSnapshot
    references: list[DuplicateProblemSnapshot] = Field(default_factory=list)
    comparison_scope_total: int = Field(ge=0)
    comparison_scope_complete: bool = True

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()


class DuplicateLayerResult(BaseModel):
    layer: Literal["text", "formula_ast", "condition", "solution_structure"]
    available: bool
    exact: bool = False
    similarity: float = Field(default=0, ge=0, le=1)
    candidate_fingerprint: str | None = None
    reference_fingerprint: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DuplicateMatch(BaseModel):
    reference_problem_id: str
    reference_solution_id: str | None = None
    relationship: Literal["mother", "same_batch_peer", "existing_problem"]
    classification: Literal["exact_duplicate", "near_duplicate", "distinct"]
    composite_similarity: float = Field(ge=0, le=1)
    layers: list[DuplicateLayerResult] = Field(min_length=4, max_length=4)
    reasons: list[str] = Field(default_factory=list)


class DuplicateDetectionReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    problem_id: str
    solution_id: str
    context_fingerprint: str = Field(min_length=64, max_length=64)
    status: DuplicateDetectionStatus
    compared_count: int = Field(ge=0)
    comparison_scope_total: int = Field(ge=0)
    comparison_scope_complete: bool
    exact_duplicate_count: int = Field(ge=0)
    near_duplicate_count: int = Field(ge=0)
    matches: list[DuplicateMatch] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_outcome(self) -> DuplicateDetectionReport:
        blocking = self.exact_duplicate_count + self.near_duplicate_count
        if self.status == DuplicateDetectionStatus.FAILED and blocking == 0:
            raise ValueError("failed duplicate detection requires a duplicate match")
        if self.status == DuplicateDetectionStatus.PASSED and blocking:
            raise ValueError("passed duplicate detection cannot contain duplicate matches")
        if self.status == DuplicateDetectionStatus.INCONCLUSIVE and not self.limitations:
            raise ValueError("inconclusive duplicate detection requires limitations")
        return self
