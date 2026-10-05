from typing import Literal

from pydantic import BaseModel, Field


class LearnerEvidence(BaseModel):
    id: str
    quote: str
    observation: str
    supports: Literal["attempt", "mastery", "misconception", "uncertainty"]


class EvidenceBackedObservation(BaseModel):
    description: str
    evidence_ids: list[str] = Field(default_factory=list)


class MisconceptionHypothesis(EvidenceBackedObservation):
    confidence: float = Field(default=0.0, ge=0, le=1)


class LearnerState(BaseModel):
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
    follow_up_question: str
    confidence: float = Field(default=0.0, ge=0, le=1)
