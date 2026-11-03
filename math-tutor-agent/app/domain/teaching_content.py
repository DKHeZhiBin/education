from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain.tutoring import HintLevel


class HintStage(StrEnum):
    """中文：定义“提示·stage”类，封装该职责相关的数据与行为。
    English: Defines the hint stage class and encapsulates data and behavior for that responsibility.
    """
    DIRECTION = "direction"
    KEY_RELATION = "key_relation"
    LOCAL_STEP = "local_step"
    FULL_EXPLANATION = "full_explanation"


class RevealScope(StrEnum):
    """中文：定义“reveal·范围”类，封装该职责相关的数据与行为。
    English: Defines the reveal scope class and encapsulates data and behavior for that responsibility.
    """
    DIRECTION_ONLY = "direction_only"
    RELATION_ONLY = "relation_only"
    SINGLE_STEP = "single_step"
    VERIFIED_SOLUTION = "verified_solution"


class HintReviewStatus(StrEnum):
    """中文：定义“提示·复核·状态”类，封装该职责相关的数据与行为。
    English: Defines the hint review status class and encapsulates data and behavior for that responsibility.
    """
    CANDIDATE = "candidate"
    APPROVED = "approved"
    RETIRED = "retired"


class HintSourceType(StrEnum):
    """中文：定义“提示·source·type”类，封装该职责相关的数据与行为。
    English: Defines the hint source type class and encapsulates data and behavior for that responsibility.
    """
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
    """中文：定义“error·pattern·definition”类，封装该职责相关的数据与行为。
    English: Defines the error pattern definition class and encapsulates data and behavior for that responsibility.
    """
    code: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    severity: int = Field(default=3, ge=1, le=5)
    detection_rule: dict[str, Any] = Field(default_factory=dict)
    remediation: dict[str, Any] = Field(default_factory=dict)


class ProblemErrorPatternUpsert(BaseModel):
    """中文：定义“题目·error·pattern·upsert”类，封装该职责相关的数据与行为。
    English: Defines the problem error pattern upsert class and encapsulates data and behavior for that responsibility.
    """
    solution_id: str
    solution_step_key: str = Field(min_length=1, max_length=64)
    pattern: ErrorPatternDefinition
    trigger_evidence: dict[str, Any] = Field(default_factory=dict)
    diagnostic_prompt: str = Field(min_length=1, max_length=1000)
    remediation_goal: str = Field(min_length=1, max_length=1000)
    priority: int = Field(default=50, ge=1, le=100)
    active: bool = True


class HintBlueprintUpsert(BaseModel):
    """中文：定义“提示·blueprint·upsert”类，封装该职责相关的数据与行为。
    English: Defines the hint blueprint upsert class and encapsulates data and behavior for that responsibility.
    """
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
        """中文：处理“验证·提示·范围”相关操作。
        English: Handles the validate hint scope operation.
        """
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
    """中文：定义“解答·step·view”类，封装该职责相关的数据与行为。
    English: Defines the solution step view class and encapsulates data and behavior for that responsibility.
    """
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
    """中文：定义“error·pattern·link·view”类，封装该职责相关的数据与行为。
    English: Defines the error pattern link view class and encapsulates data and behavior for that responsibility.
    """
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
    """中文：定义“提示·blueprint·view”类，封装该职责相关的数据与行为。
    English: Defines the hint blueprint view class and encapsulates data and behavior for that responsibility.
    """
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
    """中文：定义“教学·解答·view”类，封装该职责相关的数据与行为。
    English: Defines the teaching solution view class and encapsulates data and behavior for that responsibility.
    """
    solution_id: str
    method_name: str
    verification_status: str
    verification_coverage: dict[str, Any]
    steps: list[SolutionStepView]


class ProblemTeachingMap(BaseModel):
    """中文：定义“题目·教学·map”类，封装该职责相关的数据与行为。
    English: Defines the problem teaching map class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str
    problem_status: str
    solutions: list[TeachingSolutionView]
    error_pattern_links: list[ErrorPatternLinkView]
    hints: list[HintBlueprintView]
