from typing import Literal

from pydantic import BaseModel, Field


class SolutionStep(BaseModel):
    index: int = Field(ge=1)
    statement: str
    justification: str
    result: str | None = None


class SolutionMethod(BaseModel):
    id: str
    name: str
    strategy_summary: str
    applicability: str = ""
    steps: list[SolutionStep] = Field(default_factory=list)
    answer: str | None = None
    advantages: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)


class KeyBreakthrough(BaseModel):
    id: str
    title: str
    description: str
    why_it_matters: str
    hint_question: str
    related_method_ids: list[str] = Field(default_factory=list)


class SolutionPlan(BaseModel):
    revision_attempt: int = Field(default=0, ge=0)
    revision_reason: str = ""
    recommended_method_id: str | None = None
    recommendation_reason: str = ""
    methods: list[SolutionMethod] = Field(default_factory=list)
    answer_consistency: Literal["consistent", "unconfirmed", "conflict"] = "unconfirmed"
    key_breakthroughs: list[KeyBreakthrough] = Field(default_factory=list)
    verification_targets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=2, ge=1, le=3)
    confidence: float = Field(default=0.5, ge=0, le=1)
    note: str = ""
    # Compatibility fields consumed by the current verifier, tutor and learning record.
    steps: list[str] = Field(default_factory=list)
    answer: str | None = None
    alternative_methods: list[str] = Field(default_factory=list)
