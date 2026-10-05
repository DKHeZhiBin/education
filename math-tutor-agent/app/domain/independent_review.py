from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.generation import AdmissionEvidenceStatus
from app.domain.knowledge import ProblemContentStatus


class ReviewDecision(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class ReviewFindingStatus(StrEnum):
    ALIGNED = "aligned"
    CONFLICT = "conflict"
    INSUFFICIENT = "insufficient"


class CandidateAnswerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solution_id: str
    solution_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_answer: str = Field(min_length=1, max_length=10_000)
    answer_type: str = Field(min_length=1, max_length=64)
    method_name: str = Field(min_length=1, max_length=255)
    solution_text: str = Field(min_length=1, max_length=30_000)
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    key_breakthroughs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


class IndependentAnswerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_evidence_type: Literal["symbolic_verification", "numeric_verification"]
    source_evidence_id: str
    verifier_version_id: str
    answers: list[str] = Field(default_factory=list, max_length=100)


class ToolEvidenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_type: Literal[
        "symbolic_verification",
        "numeric_verification",
        "constraint_verification",
    ]
    status: AdmissionEvidenceStatus
    summary: str = Field(min_length=1, max_length=1000)
    verifier_version_id: str
    checks: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=100)


class TeachingLabelsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    grade_band: str
    problem_type: str
    difficulty: int = Field(ge=1, le=5)
    answer_type: str
    knowledge_point_codes: list[str] = Field(min_length=1)
    difficulty_factors: list[dict[str, Any]] = Field(default_factory=list)
    target: dict[str, Any]


class IndependentReviewContext(BaseModel):
    """Complete, versioned projection visible to the independent review model."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    problem_id: str
    generation_batch_id: str
    problem_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status_version: int = Field(ge=1)
    content_status: ProblemContentStatus
    statement: str = Field(min_length=1, max_length=10_000)
    candidate_answer: CandidateAnswerSnapshot
    independent_answers: list[IndependentAnswerSnapshot] = Field(min_length=2, max_length=2)
    tool_evidence: list[ToolEvidenceSnapshot] = Field(min_length=3, max_length=3)
    teaching_labels: TeachingLabelsSnapshot

    @model_validator(mode="after")
    def validate_contract(self) -> IndependentReviewContext:
        if self.content_status not in {
            ProblemContentStatus.CANDIDATE,
            ProblemContentStatus.VALIDATING,
            ProblemContentStatus.REVISION_REQUIRED,
        }:
            raise ValueError("independent review only accepts pre-admission content")
        evidence_types = [item.evidence_type for item in self.tool_evidence]
        required = {
            "symbolic_verification",
            "numeric_verification",
            "constraint_verification",
        }
        if set(evidence_types) != required or len(evidence_types) != len(set(evidence_types)):
            raise ValueError("exactly one item for each required tool evidence is required")
        answer_sources = {item.source_evidence_type for item in self.independent_answers}
        required_answer_sources = {"symbolic_verification", "numeric_verification"}
        if answer_sources != required_answer_sources:
            raise ValueError("symbolic and numeric independent answer sources are required")
        if self.candidate_answer.answer_type != self.teaching_labels.answer_type:
            raise ValueError("candidate and teaching answer types must match")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()


class AnswerComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReviewFindingStatus
    candidate_answer: str = Field(min_length=1, max_length=10_000)
    independent_answers: list[str] = Field(default_factory=list, max_length=100)
    explanation: str = Field(min_length=1, max_length=2000)


class ToolEvidenceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_type: str
    observed_status: AdmissionEvidenceStatus
    assessment: ReviewFindingStatus
    explanation: str = Field(min_length=1, max_length=2000)


class TeachingLabelAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: Literal[
        "grade_band",
        "knowledge_points",
        "difficulty",
        "answer_type",
        "solution_structure",
    ]
    status: ReviewFindingStatus
    explanation: str = Field(min_length=1, max_length=2000)


class IndependentReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    problem_id: str
    solution_id: str
    context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: ReviewDecision
    answer_comparison: AnswerComparison
    tool_assessments: list[ToolEvidenceAssessment] = Field(min_length=3, max_length=3)
    teaching_assessments: list[TeachingLabelAssessment] = Field(
        min_length=5,
        max_length=5,
    )
    blocking_issues: list[str] = Field(default_factory=list, max_length=50)
    strengths: list[str] = Field(default_factory=list, max_length=50)
    revision_instructions: list[str] = Field(default_factory=list, max_length=50)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_outcome(self) -> IndependentReviewReport:
        tool_ids = [item.evidence_id for item in self.tool_assessments]
        dimensions = [item.dimension for item in self.teaching_assessments]
        if len(tool_ids) != len(set(tool_ids)):
            raise ValueError("tool assessment ids must be unique")
        required_dimensions = {
            "grade_band",
            "knowledge_points",
            "difficulty",
            "answer_type",
            "solution_structure",
        }
        if set(dimensions) != required_dimensions:
            raise ValueError("all teaching assessment dimensions are required")
        findings = [
            self.answer_comparison.status,
            *(item.assessment for item in self.tool_assessments),
            *(item.status for item in self.teaching_assessments),
        ]
        has_conflict = ReviewFindingStatus.CONFLICT in findings
        has_insufficient = ReviewFindingStatus.INSUFFICIENT in findings
        if self.decision == ReviewDecision.PASSED:
            if any(item != ReviewFindingStatus.ALIGNED for item in findings):
                raise ValueError("passed review requires every finding to be aligned")
            if self.blocking_issues or self.revision_instructions:
                raise ValueError("passed review cannot contain blocking or revision items")
            if self.confidence < 0.8:
                raise ValueError("passed review requires confidence of at least 0.8")
        if self.decision == ReviewDecision.FAILED and not self.blocking_issues:
            raise ValueError("failed review requires blocking issues")
        if self.decision == ReviewDecision.FAILED and not has_conflict:
            raise ValueError("failed review requires at least one conflicting finding")
        if self.decision == ReviewDecision.INCONCLUSIVE:
            if has_conflict:
                raise ValueError("conflicting findings require a failed review")
            if not has_insufficient:
                raise ValueError("inconclusive review requires an insufficient finding")
        return self
