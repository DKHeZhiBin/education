from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


DefinitiveCheckStatus = Literal["passed", "failed", "inconclusive", "not_run"]


class GenerationEvaluationRunRecord(BaseModel):
    """中文：定义“生成·evaluation·执行·记录”类，封装该职责相关的数据与行为。
    English: Defines the generation evaluation run record class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    One isolated pipeline result; the runner never receives the case oracle.
    """

    schema_version: Literal["1.0"] = "1.0"
    run_id: str = Field(min_length=1, max_length=100)
    case_id: str = Field(min_length=1, max_length=100)
    evaluation_only: Literal[True] = True
    generated_statement: str = Field(min_length=1, max_length=10_000)
    normalized_equation: str = Field(min_length=1, max_length=1000)
    independently_solved_real_roots: list[str] = Field(max_length=10)
    condition_check_status: DefinitiveCheckStatus
    deterministic_checks: dict[str, DefinitiveCheckStatus] = Field(default_factory=dict)
    verification_coverage_level: Literal["none", "partial", "full"]
    hard_failure_codes: list[str] = Field(default_factory=list, max_length=50)
    admission_decision: Literal["approve", "revise", "quarantine", "wait"]
    model_version: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=100)
    verifier_versions: dict[str, str] = Field(default_factory=dict)
    code_revision: str = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_record(self) -> "GenerationEvaluationRunRecord":
        """中文：处理“验证·记录”相关操作。
        English: Handles the validate record operation.
        """
        if len(self.independently_solved_real_roots) != len(
            set(self.independently_solved_real_roots)
        ):
            raise ValueError("independently_solved_real_roots must be unique")
        if len(self.hard_failure_codes) != len(set(self.hard_failure_codes)):
            raise ValueError("hard_failure_codes must be unique")
        return self


class GenerationCaseQuality(BaseModel):
    """中文：定义“生成·case·质量”类，封装该职责相关的数据与行为。
    English: Defines the generation case quality class and encapsulates data and behavior for that responsibility.
    """
    case_id: str
    answer_correct: bool
    equation_roots_correct: bool
    independent_roots_correct: bool
    verification_fully_covered: bool
    admitted: bool
    erroneous_admission: bool
    condition_check_status: DefinitiveCheckStatus
    admission_decision: Literal["approve", "revise", "quarantine", "wait"]
    missing_deterministic_checks: list[str] = Field(default_factory=list)
    failed_deterministic_checks: list[str] = Field(default_factory=list)
    hard_failure_codes: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class FixedGenerationQualityMetric(BaseModel):
    """中文：定义“fixed·生成·质量·指标”类，封装该职责相关的数据与行为。
    English: Defines the fixed generation quality metric class and encapsulates data and behavior for that responsibility.
    """
    key: Literal[
        "erroneous_admission_rate",
        "answer_correctness_rate",
        "deterministic_verification_coverage_rate",
    ]
    label: str
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    rate: float | None = Field(default=None, ge=0, le=1)
    percentage: float | None = Field(default=None, ge=0, le=100)
    status: Literal["available", "no_samples"]
    definition: str


class FixedGenerationQualityReport(BaseModel):
    """中文：定义“fixed·生成·质量·报告”类，封装该职责相关的数据与行为。
    English: Defines the fixed generation quality report class and encapsulates data and behavior for that responsibility.
    """
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    run_id: str
    suite_name: str
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_version: str
    prompt_version: str
    code_revision: str
    expected_case_count: int = Field(ge=1)
    evaluated_case_count: int = Field(ge=0)
    case_coverage: float = Field(ge=0, le=1)
    metrics: list[FixedGenerationQualityMetric] = Field(min_length=3, max_length=3)
    cases: list[GenerationCaseQuality] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
