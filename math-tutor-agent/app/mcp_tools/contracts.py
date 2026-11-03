from datetime import date

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """中文：定义“工具·结果”类，封装该职责相关的数据与行为。
    English: Defines the tool result class and encapsulates data and behavior for that responsibility.
    """
    ok: bool
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ExpressionResult(ToolResult):
    """中文：定义“expression·结果”类，封装该职责相关的数据与行为。
    English: Defines the expression result class and encapsulates data and behavior for that responsibility.
    """
    original: str
    normalized: str | None = None
    simplified: str | None = None


class EquationSolutionResult(ToolResult):
    """中文：定义“equation·解答·结果”类，封装该职责相关的数据与行为。
    English: Defines the equation solution result class and encapsulates data and behavior for that responsibility.
    """
    equation: str
    variable: str
    solutions: list[str] = Field(default_factory=list)
    verification: list[bool] = Field(default_factory=list)


class CandidateVerificationResult(ToolResult):
    """中文：定义“候选内容·校验·结果”类，封装该职责相关的数据与行为。
    English: Defines the candidate verification result class and encapsulates data and behavior for that responsibility.
    """
    equation: str
    variable: str
    candidate: str
    valid: bool = False
    residual: str | None = None


class StepComparisonResult(ToolResult):
    """中文：定义“step·comparison·结果”类，封装该职责相关的数据与行为。
    English: Defines the step comparison result class and encapsulates data and behavior for that responsibility.
    """
    before: str
    after: str
    variable: str
    equivalent: bool = False
    method: str | None = None


class SimilarProblemResult(ToolResult):
    """中文：定义“similar·题目·结果”类，封装该职责相关的数据与行为。
    English: Defines the similar problem result class and encapsulates data and behavior for that responsibility.
    """
    question: str | None = None
    answer: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=1, ge=1, le=3)


class ReviewScheduleResult(ToolResult):
    """中文：定义“复核·schedule·结果”类，封装该职责相关的数据与行为。
    English: Defines the review schedule result class and encapsulates data and behavior for that responsibility.
    """
    mastery_status: str
    review_count: int
    interval_days: int | None = None
    next_review_date: date | None = None
    rationale: str | None = None
