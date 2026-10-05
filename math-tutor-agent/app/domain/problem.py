from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class QuestionType(StrEnum):
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
    type: QuestionType
    confidence: float = Field(ge=0, le=1)
    evidence: str = ""


class ProblemCondition(BaseModel):
    statement: str
    kind: str = "text"
    source: Literal["explicit", "inferred"] = "explicit"
    confidence: float = Field(default=1.0, ge=0, le=1)


class ProblemTarget(BaseModel):
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
    kind: str
    description: str
    severity: Literal["blocking", "warning"] = "blocking"
    clarification_question: str


class ProblemSpec(BaseModel):
    normalized_question: str
    subject: str = "数学"
    grade_band: str = "未知"
    question_type: QuestionType = QuestionType.UNKNOWN
    question_type_candidates: list[QuestionTypeCandidate] = Field(default_factory=list)
    known_conditions: list[ProblemCondition] = Field(default_factory=list)
    target: ProblemTarget | None = None
    ambiguities: list[ProblemAmbiguity] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    clarification: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
