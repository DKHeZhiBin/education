from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EvaluationLeakageStatus(StrEnum):
    """中文：定义“evaluation·leakage·状态”类，封装该职责相关的数据与行为。
    English: Defines the evaluation leakage status class and encapsulates data and behavior for that responsibility.
    """
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class EvaluationCaseSignature(BaseModel):
    """中文：定义“evaluation·case·signature”类，封装该职责相关的数据与行为。
    English: Defines the evaluation case signature class and encapsulates data and behavior for that responsibility.
    """
    case_id: str
    source_commit: str
    source_label: str
    normalized_text_hash: str = Field(min_length=64, max_length=64)
    text_features: list[str] = Field(default_factory=list)
    formula_features: list[str] = Field(default_factory=list)
    numeric_features: list[str] = Field(default_factory=list)
    formula_token_count: int = Field(ge=0)


class EvaluationDatasetSignature(BaseModel):
    """中文：定义“evaluation·dataset·signature”类，封装该职责相关的数据与行为。
    English: Defines the evaluation dataset signature class and encapsulates data and behavior for that responsibility.
    """
    name: str | None = None
    schema_version: str | None = None
    evaluation_only: bool = False
    source_commit: str | None = None
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    expected_case_count: int | None = Field(default=None, ge=0)
    selected_case_ids_hash: str | None = None
    integrity_valid: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    cases: list[EvaluationCaseSignature] = Field(default_factory=list)


class LeakageCandidateSnapshot(BaseModel):
    """中文：定义“leakage·候选内容·snapshot”类，封装该职责相关的数据与行为。
    English: Defines the leakage candidate snapshot class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str
    generation_batch_id: str
    content_hash: str = Field(min_length=64, max_length=64)
    status_version: int = Field(ge=1)
    content_status: str
    statement: str
    normalized_statement: str | None = None
    explicit_conditions: list[dict[str, Any]] = Field(default_factory=list)
    implicit_conditions: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationLeakageContext(BaseModel):
    """中文：定义“evaluation·leakage·context”类，封装该职责相关的数据与行为。
    English: Defines the evaluation leakage context class and encapsulates data and behavior for that responsibility.
    """
    candidate: LeakageCandidateSnapshot
    dataset: EvaluationDatasetSignature

    def fingerprint(self) -> str:
        """中文：处理“fingerprint”相关操作。
        English: Handles the fingerprint operation.
        """
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()


class EvaluationLeakageMatch(BaseModel):
    """中文：定义“evaluation·leakage·match”类，封装该职责相关的数据与行为。
    English: Defines the evaluation leakage match class and encapsulates data and behavior for that responsibility.
    """
    case_id: str
    source_commit: str
    source_label: str
    classification: Literal["exact_text", "near_text", "structural", "combined"]
    text_similarity: float = Field(ge=0, le=1)
    formula_similarity: float = Field(ge=0, le=1)
    numeric_similarity: float = Field(ge=0, le=1)
    composite_similarity: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class EvaluationLeakageReport(BaseModel):
    """中文：定义“evaluation·leakage·报告”类，封装该职责相关的数据与行为。
    English: Defines the evaluation leakage report class and encapsulates data and behavior for that responsibility.
    """
    schema_version: Literal["1.0"] = "1.0"
    problem_id: str
    context_fingerprint: str = Field(min_length=64, max_length=64)
    status: EvaluationLeakageStatus
    dataset_name: str | None = None
    dataset_sha256: str | None = None
    source_commit: str | None = None
    checked_case_count: int = Field(ge=0)
    matches: list[EvaluationLeakageMatch] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_outcome(self) -> EvaluationLeakageReport:
        """中文：处理“验证·outcome”相关操作。
        English: Handles the validate outcome operation.
        """
        if self.status == EvaluationLeakageStatus.FAILED and not self.matches:
            raise ValueError("failed leakage detection requires a match")
        if self.status == EvaluationLeakageStatus.PASSED and self.matches:
            raise ValueError("passed leakage detection cannot contain matches")
        if self.status == EvaluationLeakageStatus.INCONCLUSIVE and not self.limitations:
            raise ValueError("inconclusive leakage detection requires limitations")
        return self
