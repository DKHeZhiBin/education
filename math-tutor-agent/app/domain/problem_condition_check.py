from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.knowledge import (
    ImplicitProblemCondition,
    ProblemCondition,
    ProblemContentStatus,
    ProblemTarget,
)


class ConditionCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class ConditionIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    severity: Literal["blocking", "warning"]
    message: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    suggested_revision: str | None = Field(default=None, max_length=1000)


class ConditionCheckDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ConditionCheckStatus
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=1000)
    issues: list[ConditionIssue] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_status(self) -> ConditionCheckDimension:
        blocking = any(issue.severity == "blocking" for issue in self.issues)
        if self.status == ConditionCheckStatus.PASSED and blocking:
            raise ValueError("passed dimension cannot contain blocking issues")
        if self.status == ConditionCheckStatus.FAILED and not blocking:
            raise ValueError("failed dimension requires a blocking issue")
        return self


class SolutionCountCheck(ConditionCheckDimension):
    requested_semantics: Literal[
        "all_solutions",
        "exact_count",
        "at_least",
        "at_most",
        "one_solution",
        "unspecified",
    ]
    stated_expected_count: int | None = Field(default=None, ge=0, le=1000)
    predicted_solution_count: int | None = Field(default=None, ge=0, le=1000)
    prediction_basis: Literal[
        "statement",
        "algebraic_structure",
        "model_estimate",
        "undetermined",
    ]
    deterministic_verification_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_count_semantics(self) -> SolutionCountCheck:
        if self.requested_semantics == "exact_count" and self.stated_expected_count is None:
            raise ValueError("exact_count requires stated_expected_count")
        if self.prediction_basis == "undetermined" and self.predicted_solution_count is not None:
            raise ValueError("undetermined count cannot contain a prediction")
        return self


class ProblemConditionCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    problem_id: str = Field(min_length=1, max_length=36)
    ambiguity: ConditionCheckDimension
    condition_completeness: ConditionCheckDimension
    domain: ConditionCheckDimension
    solution_count: SolutionCountCheck
    grade_fit: ConditionCheckDimension
    overall_status: ConditionCheckStatus
    summary: str = Field(min_length=1, max_length=1000)
    approval_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_overall_status(self) -> ProblemConditionCheckReport:
        statuses = {
            self.ambiguity.status,
            self.condition_completeness.status,
            self.domain.status,
            self.solution_count.status,
            self.grade_fit.status,
        }
        expected = (
            ConditionCheckStatus.FAILED
            if ConditionCheckStatus.FAILED in statuses
            else ConditionCheckStatus.INCONCLUSIVE
            if ConditionCheckStatus.INCONCLUSIVE in statuses
            else ConditionCheckStatus.PASSED
        )
        if self.overall_status != expected:
            raise ValueError("overall_status does not match dimension statuses")
        return self


class ProblemConditionCheckContext(BaseModel):
    """Solution-free candidate and mother context used by the checker."""

    model_config = ConfigDict(extra="forbid")

    problem_id: str = Field(min_length=1, max_length=36)
    generation_batch_id: str = Field(min_length=1, max_length=36)
    content_hash: str = Field(min_length=64, max_length=64)
    status_version: int = Field(ge=1)
    content_status: ProblemContentStatus
    statement: str = Field(min_length=1, max_length=10_000)
    normalized_statement: str | None = Field(default=None, max_length=10_000)
    subject: str = Field(min_length=1, max_length=32)
    grade_band: str = Field(min_length=1, max_length=32)
    problem_type: str = Field(min_length=1, max_length=64)
    difficulty: int = Field(ge=1, le=5)
    answer_type: str = Field(min_length=1, max_length=64)
    explicit_conditions: list[ProblemCondition] = Field(default_factory=list)
    implicit_conditions: list[ImplicitProblemCondition] = Field(default_factory=list)
    target: ProblemTarget | None = None
    knowledge_point_codes: list[str] = Field(min_length=1)
    mother_problem_id: str = Field(min_length=1, max_length=36)
    mother_grade_band: str | None = Field(default=None, max_length=32)
    mother_problem_type: str = Field(min_length=1, max_length=64)
    mother_knowledge_point_codes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate_scope(self) -> ProblemConditionCheckContext:
        if self.content_status not in {
            ProblemContentStatus.CANDIDATE,
            ProblemContentStatus.VALIDATING,
            ProblemContentStatus.REVISION_REQUIRED,
        }:
            raise ValueError("condition checker only accepts pre-admission content")
        return self
