from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class QuadraticCheckStatus(StrEnum):
    """中文：定义“quadratic·检查·状态”类，封装该职责相关的数据与行为。
    English: Defines the quadratic check status class and encapsulates data and behavior for that responsibility.
    """
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class QuadraticVerificationCheck(BaseModel):
    """中文：定义“quadratic·校验·检查”类，封装该职责相关的数据与行为。
    English: Defines the quadratic verification check class and encapsulates data and behavior for that responsibility.
    """
    check_type: Literal[
        "solve",
        "substitution",
        "root_count",
        "domain",
        "boundary",
        "step_equivalence",
    ]
    status: QuadraticCheckStatus
    summary: str = Field(min_length=1, max_length=1000)
    evidence: dict[str, Any] = Field(default_factory=dict)
    covered_step_ids: list[str] = Field(default_factory=list)


class QuadraticVerificationContext(BaseModel):
    """中文：定义“quadratic·校验·context”类，封装该职责相关的数据与行为。
    English: Defines the quadratic verification context class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str
    solution_id: str
    generation_batch_id: str
    problem_content_hash: str = Field(min_length=64, max_length=64)
    solution_content_hash: str = Field(min_length=64, max_length=64)
    status_version: int = Field(ge=1)
    content_status: str
    problem_type: str
    answer_type: str
    statement: str
    normalized_statement: str | None = None
    explicit_conditions: list[dict[str, Any]] = Field(default_factory=list)
    implicit_conditions: list[dict[str, Any]] = Field(default_factory=list)
    target: dict[str, Any]
    solution_steps: list[dict[str, Any]] = Field(default_factory=list)
    final_answer: str

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


class QuadraticVerificationReport(BaseModel):
    """中文：定义“quadratic·校验·报告”类，封装该职责相关的数据与行为。
    English: Defines the quadratic verification report class and encapsulates data and behavior for that responsibility.
    """
    schema_version: Literal["1.0"] = "1.0"
    problem_id: str
    solution_id: str
    context_fingerprint: str = Field(min_length=64, max_length=64)
    equation: str | None = None
    variable: str | None = None
    standard_form: str | None = None
    coefficients: dict[str, str] = Field(default_factory=dict)
    discriminant: str | None = None
    computed_roots: list[str] = Field(default_factory=list)
    claimed_roots: list[str] = Field(default_factory=list)
    checks: list[QuadraticVerificationCheck] = Field(min_length=1)
    verification_status: Literal["unverified", "partial", "verified", "failed"]
    coverage_level: Literal["none", "partial", "full"]
    covered_step_ids: list[str] = Field(default_factory=list)
    uncovered_step_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_outcome(self) -> QuadraticVerificationReport:
        """中文：处理“验证·outcome”相关操作。
        English: Handles the validate outcome operation.
        """
        failed = any(check.status == QuadraticCheckStatus.FAILED for check in self.checks)
        if self.verification_status == "failed" and not failed:
            raise ValueError("failed verification requires a failed check")
        if self.verification_status == "verified":
            if any(check.status != QuadraticCheckStatus.PASSED for check in self.checks):
                raise ValueError("verified result requires every check to pass")
            if self.coverage_level != "full" or self.uncovered_step_ids:
                raise ValueError("verified result requires full step coverage")
        if self.verification_status == "partial" and not self.limitations:
            raise ValueError("partial verification requires limitations")
        if self.verification_status == "unverified" and self.coverage_level != "none":
            raise ValueError("unverified result requires coverage level none")
        return self

    def check(self, check_type: str) -> QuadraticVerificationCheck:
        """中文：处理“检查”相关操作。
        English: Handles the check operation.
        """
        return next(item for item in self.checks if item.check_type == check_type)
