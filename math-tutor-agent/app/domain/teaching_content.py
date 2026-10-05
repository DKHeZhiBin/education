from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain.tutoring import HintLevel


class HintStage(StrEnum):
    DIRECTION = "direction"
    KEY_RELATION = "key_relation"
    LOCAL_STEP = "local_step"
    FULL_EXPLANATION = "full_explanation"


class RevealScope(StrEnum):
    DIRECTION_ONLY = "direction_only"
    RELATION_ONLY = "relation_only"
    SINGLE_STEP = "single_step"
    VERIFIED_SOLUTION = "verified_solution"


class HintReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    RETIRED = "retired"


class HintSourceType(StrEnum):
    AUTHORED = "authored"
    AI_CANDIDATE = "ai_candidate"
    IMPORTED = "imported"


HINT_BOUNDARIES: dict[int, tuple[HintStage, RevealScope]] = {
    HintLevel.DIRECTION: (HintStage.DIRECTION, RevealScope.DIRECTION_ONLY),
    HintLevel.KEY_RELATION: (HintStage.KEY_RELATION, RevealScope.RELATION_ONLY),
    HintLevel.LOCAL_STEP: (HintStage.LOCAL_STEP, RevealScope.SINGLE_STEP),
    HintLevel.FULL_EXPLANATION: (
        HintStage.FULL_EXPLANATION,
        RevealScope.VERIFIED_SOLUTION,
    ),
}


class ErrorPatternDefinition(BaseModel):
    code: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    severity: int = Field(default=3, ge=1, le=5)
    detection_rule: dict[str, Any] = Field(default_factory=dict)
    remediation: dict[str, Any] = Field(default_factory=dict)


class ProblemErrorPatternUpsert(BaseModel):
    solution_id: str
    solution_step_key: str = Field(min_length=1, max_length=64)
    pattern: ErrorPatternDefinition
    trigger_evidence: dict[str, Any] = Field(default_factory=dict)
    diagnostic_prompt: str = Field(min_length=1, max_length=1000)
    remediation_goal: str = Field(min_length=1, max_length=1000)
    priority: int = Field(default=50, ge=1, le=100)
    active: bool = True


class HintBlueprintUpsert(BaseModel):
    solution_id: str
    solution_step_key: str | None = Field(default=None, max_length=64)
    problem_error_pattern_id: str | None = None
    hint_level: int = Field(ge=1, le=4)
    content: str = Field(min_length=1)
    understanding_check: str = Field(min_length=1, max_length=1000)
    knowledge_point_codes: list[str] = Field(default_factory=list)
    review_status: HintReviewStatus = HintReviewStatus.CANDIDATE
    source_type: HintSourceType = HintSourceType.AI_CANDIDATE
    priority: int = Field(default=50, ge=1, le=100)
    active: bool = True

    @model_validator(mode="after")
    def validate_hint_scope(self) -> "HintBlueprintUpsert":
        if (
            self.hint_level == HintLevel.LOCAL_STEP
            and not self.solution_step_key
            and not self.problem_error_pattern_id
        ):
            raise ValueError(
                "level 3 hint requires solution_step_key or problem_error_pattern_id"
            )
        if len(self.knowledge_point_codes) != len(set(self.knowledge_point_codes)):
            raise ValueError("knowledge_point_codes must be unique")
        return self


class SolutionStepView(BaseModel):
    id: str
    problem_id: str
    solution_id: str
    step_key: str
    sequence: int
    action: str
    result: str
    justifications: list[dict[str, Any]]
    depends_on_step_keys: list[str]
    condition_refs: list[str]
    knowledge_point_codes: list[str]
    content_hash: str
    active: bool
    updated_at: datetime


class ErrorPatternLinkView(BaseModel):
    id: str
    problem_id: str
    solution_id: str
    solution_step_id: str
    solution_step_key: str
    error_pattern_id: str
    pattern_code: str
    pattern_title: str
    pattern_description: str
    severity: int
    detection_rule: dict[str, Any]
    remediation: dict[str, Any]
    trigger_evidence: dict[str, Any]
    diagnostic_prompt: str
    remediation_goal: str
    priority: int
    active: bool
    updated_at: datetime


class HintBlueprintView(BaseModel):
    id: str
    problem_id: str
    solution_id: str
    solution_step_id: str | None
    solution_step_key: str | None
    problem_error_pattern_id: str | None
    hint_level: int
    hint_stage: HintStage
    reveal_scope: RevealScope
    content: str
    understanding_check: str
    knowledge_point_codes: list[str]
    review_status: HintReviewStatus
    source_type: HintSourceType
    priority: int
    active: bool
    content_hash: str
    updated_at: datetime


class TeachingSolutionView(BaseModel):
    solution_id: str
    method_name: str
    verification_status: str
    verification_coverage: dict[str, Any]
    steps: list[SolutionStepView]


class ProblemTeachingMap(BaseModel):
    problem_id: str
    problem_status: str
    solutions: list[TeachingSolutionView]
    error_pattern_links: list[ErrorPatternLinkView]
    hints: list[HintBlueprintView]
