from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class NumericCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class NumericVerificationCheck(BaseModel):
    check_type: Literal[
        "coefficient_reconstruction",
        "sample_consistency",
        "root_estimation",
        "candidate_substitution",
        "exhaustive_domain",
    ]
    status: NumericCheckStatus
    summary: str = Field(min_length=1, max_length=1000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class NumericVerificationReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    problem_id: str
    solution_id: str
    context_fingerprint: str = Field(min_length=64, max_length=64)
    mode: Literal["numeric_sampling", "exhaustive_integer"]
    equation: str | None = None
    variable: str | None = None
    checks: list[NumericVerificationCheck] = Field(min_length=1)
    status: NumericCheckStatus
    independently_computed_roots: list[str] = Field(default_factory=list)
    claimed_roots: list[str] = Field(default_factory=list)
    sample_count: int = Field(default=0, ge=0)
    tolerance: str
    relative_tolerance: str
    precision: int = Field(ge=16, le=200)
    sample_points: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_status(self) -> NumericVerificationReport:
        if self.status == NumericCheckStatus.PASSED and any(
            item.status != NumericCheckStatus.PASSED for item in self.checks
        ):
            raise ValueError("passed numeric report requires every check to pass")
        if self.status == NumericCheckStatus.FAILED and not any(
            item.status == NumericCheckStatus.FAILED for item in self.checks
        ):
            raise ValueError("failed numeric report requires a failed check")
        if self.status == NumericCheckStatus.INCONCLUSIVE and not self.limitations:
            raise ValueError("inconclusive numeric report requires limitations")
        return self
