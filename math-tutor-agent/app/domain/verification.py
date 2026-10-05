from typing import Literal

from pydantic import BaseModel, Field


class VerificationCheck(BaseModel):
    id: str
    kind: str
    status: Literal["passed", "failed", "skipped", "not_applicable"]
    tool: str
    method_id: str | None = None
    step_index: int | None = None
    evidence: str


class ProofCriterionReview(BaseModel):
    criterion: Literal[
        "claim_alignment",
        "condition_usage",
        "logical_continuity",
        "theorem_applicability",
        "case_completeness",
        "conclusion_closure",
    ]
    status: Literal["passed", "failed", "not_applicable", "unverified"]
    evidence: str
    confidence: float = Field(default=0.0, ge=0, le=1)


class ProofReview(BaseModel):
    criteria: list[ProofCriterionReview] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    unverified_claims: list[str] = Field(default_factory=list)
    raw_confidence: float = Field(default=0.0, ge=0, le=1)
    confidence_cap: float = Field(default=0.74, ge=0, le=1)


class RevisionContext(BaseModel):
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=2, ge=0, le=3)
    will_retry: bool = False
    exhausted: bool = False
    termination_reason: Literal[
        "passed",
        "retryable_failure",
        "not_revisable",
        "limit_reached",
    ]


class VerificationReport(BaseModel):
    passed: bool = False
    verifier_type: Literal["cas", "model", "hybrid", "unverified"] = "unverified"
    coverage: Literal["full", "partial", "none"] = "none"
    checks: list[VerificationCheck] = Field(default_factory=list)
    evidence: str = ""
    issues: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    proof_review: ProofReview | None = None
    revision_context: RevisionContext | None = None
