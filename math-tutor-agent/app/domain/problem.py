from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class QuestionType(StrEnum):
    """中文：定义“问题·type”类，封装该职责相关的数据与行为。
    English: Defines the question type class and encapsulates data and behavior for that responsibility.
    """
    ARITHMETIC = "arithmetic"
    ALGEBRAIC_EXPRESSION = "algebraic_expression"
    EQUATION = "equation"
    EQUATION_SYSTEM = "equation_system"
    LINEAR_EQUATION = "linear_equation"
    QUADRATIC_EQUATION = "quadratic_equation"
    INEQUALITY = "inequality"
    FUNCTION = "function"
    TRIGONOMETRY = "trigonometry"
    GEOMETRY = "geometry"
    ANALYTIC_GEOMETRY = "analytic_geometry"
    PROOF = "proof"
    SEQUENCE = "sequence"
    COMBINATORICS = "combinatorics"
    PROBABILITY = "probability"
    STATISTICS = "statistics"
    NUMBER_THEORY = "number_theory"
    OPTIMIZATION = "optimization"
    CALCULUS = "calculus"
    APPLICATION = "application"
    UNKNOWN = "unknown"


class QuestionTypeCandidate(BaseModel):
    """中文：定义“问题·type·候选内容”类，封装该职责相关的数据与行为。
    English: Defines the question type candidate class and encapsulates data and behavior for that responsibility.
    """
    type: QuestionType
    confidence: float = Field(ge=0, le=1)
    evidence: str = ""


class ProblemCondition(BaseModel):
    """中文：定义“题目·condition”类，封装该职责相关的数据与行为。
    English: Defines the problem condition class and encapsulates data and behavior for that responsibility.
    """
    statement: str
    kind: str = "text"
    source: Literal["explicit", "inferred"] = "explicit"
    confidence: float = Field(default=1.0, ge=0, le=1)


class ProblemTarget(BaseModel):
    """中文：定义“题目·target”类，封装该职责相关的数据与行为。
    English: Defines the problem target class and encapsulates data and behavior for that responsibility.
    """
    action: Literal[
        "solve",
        "calculate",
        "prove",
        "find",
        "compare",
        "determine",
        "simplify",
        "graph",
    ]
    object: str
    expected_answer_type: str = "unknown"
    source: Literal["explicit", "inferred"] = "explicit"


class ProblemAmbiguity(BaseModel):
    """中文：定义“题目·ambiguity”类，封装该职责相关的数据与行为。
    English: Defines the problem ambiguity class and encapsulates data and behavior for that responsibility.
    """
    kind: str
    description: str
    severity: Literal["blocking", "warning"] = "blocking"
    clarification_question: str


class ThinkingMethodCandidate(BaseModel):
    """中文：记录题目所体现的数学思想与方法候选项。
    English: Records a mathematical thinking-method candidate found in a problem.
    """
    category_id: str
    category_name: str
    method_id: str
    method_name: str
    role: Literal["primary", "related"] = "related"
    evidence: str
    confidence: float = Field(default=0.5, ge=0, le=1)


class ProblemSpec(BaseModel):
    """中文：定义“题目·spec”类，封装该职责相关的数据与行为。
    English: Defines the problem spec class and encapsulates data and behavior for that responsibility.
    """
    normalized_question: str
    subject: str = "数学"
    grade_band: str = "未知"
    question_type: QuestionType = QuestionType.UNKNOWN
    question_type_candidates: list[QuestionTypeCandidate] = Field(default_factory=list)
    known_conditions: list[ProblemCondition] = Field(default_factory=list)
    target: ProblemTarget | None = None
    ambiguities: list[ProblemAmbiguity] = Field(default_factory=list)
    thinking_methods: list[ThinkingMethodCandidate] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    clarification: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
