from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.knowledge import (
    ImplicitProblemCondition,
    ProblemCondition,
    ProblemContentStatus,
    ProblemTarget,
    SolutionBreakthrough,
    StructuredSolutionStep,
)


class IndependentSolverContext(BaseModel):
    """The complete and exclusive input visible to the independent solver."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    problem_id: str = Field(min_length=1, max_length=36)
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
    language: str = Field(min_length=2, max_length=16)
    explicit_conditions: list[ProblemCondition] = Field(min_length=1)
    implicit_conditions: list[ImplicitProblemCondition] = Field(default_factory=list)
    target: ProblemTarget
    knowledge_point_codes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> IndependentSolverContext:
        if self.content_status not in {
            ProblemContentStatus.CANDIDATE,
            ProblemContentStatus.VALIDATING,
            ProblemContentStatus.REVISION_REQUIRED,
        }:
            raise ValueError("independent solver only accepts pre-admission content")
        if self.target.expected_answer_type != self.answer_type:
            raise ValueError("target answer type must match problem answer type")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"status_version", "content_status"})
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()


class IndependentSolutionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    method_name: str = Field(min_length=1, max_length=255)
    solution_text: str = Field(min_length=1, max_length=30_000)
    final_answer: str = Field(min_length=1, max_length=10_000)
    answer_type: str = Field(min_length=1, max_length=64)
    steps: list[StructuredSolutionStep] = Field(min_length=1, max_length=100)
    key_breakthroughs: list[SolutionBreakthrough] = Field(default_factory=list, max_length=20)
    assumptions_used: list[str] = Field(default_factory=list, max_length=50)
    confidence: float = Field(ge=0, le=1)
    requires_external_verification: Literal[True] = True

    @model_validator(mode="after")
    def validate_structure(self) -> IndependentSolutionDraft:
        step_ids = [step.step_id for step in self.steps]
        sequences = [step.sequence for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("solution step ids must be unique")
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("solution step sequences must be contiguous and ordered")
        sequence_by_id = {
            step.step_id: step.sequence
            for step in self.steps
        }
        for step in self.steps:
            for dependency in step.depends_on_step_ids:
                if dependency not in sequence_by_id:
                    raise ValueError(f"unknown step dependency: {dependency}")
                if sequence_by_id[dependency] >= step.sequence:
                    raise ValueError("steps may only depend on earlier steps")
        breakthrough_ids = [item.breakthrough_id for item in self.key_breakthroughs]
        if len(breakthrough_ids) != len(set(breakthrough_ids)):
            raise ValueError("breakthrough ids must be unique")
        for item in self.key_breakthroughs:
            unknown = set(item.related_step_ids) - set(step_ids)
            if unknown:
                raise ValueError(
                    f"breakthrough references unknown steps: {sorted(unknown)}"
                )
        return self
