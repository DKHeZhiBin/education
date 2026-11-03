from typing import Literal

from pydantic import BaseModel, Field


class LearnerEvidence(BaseModel):
    """中文：定义“learner·evidence”类，封装该职责相关的数据与行为。
    English: Defines the learner evidence class and encapsulates data and behavior for that responsibility.
    """
    id: str
    quote: str
    observation: str
    supports: Literal["attempt", "mastery", "misconception", "uncertainty"]


class EvidenceBackedObservation(BaseModel):
    """中文：定义“evidence·backed·observation”类，封装该职责相关的数据与行为。
    English: Defines the evidence backed observation class and encapsulates data and behavior for that responsibility.
    """
    description: str
    evidence_ids: list[str] = Field(default_factory=list)


class MisconceptionHypothesis(EvidenceBackedObservation):
    """中文：定义“misconception·hypothesis”类，封装该职责相关的数据与行为。
    English: Defines the misconception hypothesis class and encapsulates data and behavior for that responsibility.
    """
    barrier_type: Literal[
        "knowledge_gap",
        "strategy_selection",
        "expression_transformation",
        "execution_error",
        "alternative_valid_path",
        "uncertain",
    ] = "uncertain"
    missing_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class LearnerState(BaseModel):
    """中文：定义“learner·state”类，封装该职责相关的数据与行为。
    English: Defines the learner state class and encapsulates data and behavior for that responsibility.
    """
    evidence_scope: Literal["current_turn"] = "current_turn"
    observed_work: str
    attempt_kind: Literal[
        "help_request",
        "partial_work",
        "final_answer",
        "proof_argument",
        "question",
        "other",
    ] = "other"
    has_meaningful_attempt: bool = False
    evidence: list[LearnerEvidence] = Field(default_factory=list)
    mastered_points: list[EvidenceBackedObservation] = Field(default_factory=list)
    misconception_hypotheses: list[MisconceptionHypothesis] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    possible_misconception: str = "需要追问"
    next_hint_level: int = Field(default=1, ge=1, le=3)
    next_solution_step_index: int | None = Field(default=None, ge=1)
    follow_up_question: str
    confidence: float = Field(default=0.0, ge=0, le=1)
