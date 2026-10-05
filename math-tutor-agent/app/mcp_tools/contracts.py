from datetime import date

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    ok: bool
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ExpressionResult(ToolResult):
    original: str
    normalized: str | None = None
    simplified: str | None = None


class EquationSolutionResult(ToolResult):
    equation: str
    variable: str
    solutions: list[str] = Field(default_factory=list)
    verification: list[bool] = Field(default_factory=list)


class CandidateVerificationResult(ToolResult):
    equation: str
    variable: str
    candidate: str
    valid: bool = False
    residual: str | None = None


class StepComparisonResult(ToolResult):
    before: str
    after: str
    variable: str
    equivalent: bool = False
    method: str | None = None


class SimilarProblemResult(ToolResult):
    question: str | None = None
    answer: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=1, ge=1, le=3)


class ReviewScheduleResult(ToolResult):
    mastery_status: str
    review_count: int
    interval_days: int | None = None
    next_review_date: date | None = None
    rationale: str | None = None
