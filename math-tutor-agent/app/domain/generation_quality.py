from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


MetricKey = Literal[
    "problem_validity_rate",
    "answer_correctness_rate",
    "deterministic_verification_coverage_rate",
    "duplicate_block_rate",
    "automatic_admission_rate",
    "erroneous_admission_rate",
]


class QualityMetric(BaseModel):
    key: MetricKey
    label: str
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    unavailable_count: int = Field(default=0, ge=0)
    rate: float | None = Field(default=None, ge=0, le=1)
    percentage: float | None = Field(default=None, ge=0, le=100)
    status: Literal["available", "no_samples"]
    numerator_definition: str
    denominator_definition: str

    @model_validator(mode="after")
    def validate_fraction(self) -> "QualityMetric":
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed denominator")
        if self.denominator == 0:
            if self.rate is not None or self.percentage is not None:
                raise ValueError("empty metrics must not report a numeric rate")
            if self.status != "no_samples":
                raise ValueError("empty metrics must use no_samples status")
        elif self.rate is None or self.percentage is None or self.status != "available":
            raise ValueError("non-empty metrics require rate, percentage and available status")
        return self


class GenerationQualityScope(BaseModel):
    batch_id: str | None = None
    topic_code: str | None = None
    batch_purpose: str | None = "question_variation"
    created_from: datetime | None = None
    created_to: datetime | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "GenerationQualityScope":
        if self.created_from and self.created_to and self.created_from >= self.created_to:
            raise ValueError("created_from must be earlier than created_to")
        return self


class GenerationQualityReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    scope: GenerationQualityScope
    candidate_count: int = Field(ge=0)
    metrics: list[QualityMetric] = Field(min_length=6, max_length=6)
    evidence_policy: str = "latest_current_content_evidence"
    erroneous_admissions: list["ErroneousAdmissionFinding"] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ErroneousAdmissionFinding(BaseModel):
    problem_id: str
    generation_batch_id: str
    problem_content_hash: str
    admission_evidence_id: str
    selected_solution_id: str | None = None
    current_content_status: str
    reason_codes: list[str] = Field(min_length=1)
    failed_evidence_ids: list[str] = Field(default_factory=list)


class ProductionReleaseGate(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["passed", "blocked"]
    reason: Literal["within_threshold", "threshold_exceeded", "insufficient_samples"]
    maximum_erroneous_admission_rate: float = Field(ge=0, le=1)
    minimum_auto_admissions: int = Field(ge=1)
    auto_admission_count: int = Field(ge=0)
    erroneous_admission_count: int = Field(ge=0)
    erroneous_admission_rate: float | None = Field(default=None, ge=0, le=1)
    report: GenerationQualityReport


def build_quality_metric(
    *,
    key: MetricKey,
    label: str,
    numerator: int,
    denominator: int,
    unavailable_count: int,
    numerator_definition: str,
    denominator_definition: str,
) -> QualityMetric:
    rate = numerator / denominator if denominator else None
    return QualityMetric(
        key=key,
        label=label,
        numerator=numerator,
        denominator=denominator,
        unavailable_count=unavailable_count,
        rate=round(rate, 6) if rate is not None else None,
        percentage=round(rate * 100, 2) if rate is not None else None,
        status="available" if denominator else "no_samples",
        numerator_definition=numerator_definition,
        denominator_definition=denominator_definition,
    )
