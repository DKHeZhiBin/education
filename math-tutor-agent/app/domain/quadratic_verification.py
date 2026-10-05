from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class QuadraticCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class QuadraticVerificationCheck(BaseModel):
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
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()


class QuadraticVerificationReport(BaseModel):
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
        return next(item for item in self.checks if item.check_type == check_type)
