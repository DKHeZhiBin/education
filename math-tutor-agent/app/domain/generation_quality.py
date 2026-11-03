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
    """中文：定义“质量·指标”类，封装该职责相关的数据与行为。
    English: Defines the quality metric class and encapsulates data and behavior for that responsibility.
    """
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
        """中文：处理“验证·fraction”相关操作。
        English: Handles the validate fraction operation.
        """
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
    """中文：定义“生成·质量·范围”类，封装该职责相关的数据与行为。
    English: Defines the generation quality scope class and encapsulates data and behavior for that responsibility.
    """
    batch_id: str | None = None
    topic_code: str | None = None
    batch_purpose: str | None = "question_variation"
    created_from: datetime | None = None
    created_to: datetime | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "GenerationQualityScope":
        """中文：处理“验证·range”相关操作。
        English: Handles the validate range operation.
        """
        if self.created_from and self.created_to and self.created_from >= self.created_to:
            raise ValueError("created_from must be earlier than created_to")
        return self


class GenerationQualityReport(BaseModel):
    """中文：定义“生成·质量·报告”类，封装该职责相关的数据与行为。
    English: Defines the generation quality report class and encapsulates data and behavior for that responsibility.
    """
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    scope: GenerationQualityScope
    candidate_count: int = Field(ge=0)
    metrics: list[QualityMetric] = Field(min_length=6, max_length=6)
    evidence_policy: str = "latest_current_content_evidence"
    erroneous_admissions: list["ErroneousAdmissionFinding"] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ErroneousAdmissionFinding(BaseModel):
    """中文：定义“erroneous·admission·finding”类，封装该职责相关的数据与行为。
    English: Defines the erroneous admission finding class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str
    generation_batch_id: str
    problem_content_hash: str
    admission_evidence_id: str
    selected_solution_id: str | None = None
    current_content_status: str
    reason_codes: list[str] = Field(min_length=1)
    failed_evidence_ids: list[str] = Field(default_factory=list)


class ProductionReleaseGate(BaseModel):
    """中文：定义“production·release·准入门”类，封装该职责相关的数据与行为。
    English: Defines the production release gate class and encapsulates data and behavior for that responsibility.
    """
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
    """中文：处理“构建·质量·指标”相关操作。
    English: Handles the build quality metric operation.
    """
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
