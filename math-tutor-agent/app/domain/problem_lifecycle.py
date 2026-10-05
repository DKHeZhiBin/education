from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field, model_validator

from app.domain.generation import (
    AdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)
from app.domain.knowledge import ProblemContentStatus
from app.domain.verification_scope_policy import ProblemVerificationScope


REQUIRED_APPROVAL_EVIDENCE = frozenset(
    {
        "condition_completeness",
        "solution_independence",
        "symbolic_verification",
        "numeric_verification",
        "constraint_verification",
        "duplicate_detection",
        "evaluation_leakage_detection",
        "pedagogical_review",
        "source_rights_clearance",
    }
)

VERSIONED_VERIFIER_APPROVAL_EVIDENCE = frozenset({
    "symbolic_verification",
    "numeric_verification",
    "constraint_verification",
    "duplicate_detection",
    "evaluation_leakage_detection",
})

SOLUTION_SCOPED_APPROVAL_EVIDENCE = frozenset({
    "solution_independence",
    "symbolic_verification",
    "numeric_verification",
    "constraint_verification",
    "duplicate_detection",
    "pedagogical_review",
})

MODEL_APPROVAL_EVIDENCE = frozenset({
    "condition_completeness",
    "pedagogical_review",
})

PROBLEM_SCOPED_APPROVAL_EVIDENCE = frozenset({
    "condition_completeness",
    "evaluation_leakage_detection",
    "source_rights_clearance",
})

PROBLEM_CONTENT_BOUND_EVIDENCE = frozenset(
    REQUIRED_APPROVAL_EVIDENCE - {"source_rights_clearance"}
)


ALLOWED_TRANSITIONS: dict[ProblemContentStatus, frozenset[ProblemContentStatus]] = {
    ProblemContentStatus.CANDIDATE: frozenset(
        {ProblemContentStatus.VALIDATING, ProblemContentStatus.RETIRED}
    ),
    ProblemContentStatus.VALIDATING: frozenset(
        {
            ProblemContentStatus.REVISION_REQUIRED,
            ProblemContentStatus.QUARANTINED,
            ProblemContentStatus.APPROVED,
            ProblemContentStatus.RETIRED,
        }
    ),
    ProblemContentStatus.REVISION_REQUIRED: frozenset(
        {
            ProblemContentStatus.VALIDATING,
            ProblemContentStatus.QUARANTINED,
            ProblemContentStatus.RETIRED,
        }
    ),
    ProblemContentStatus.QUARANTINED: frozenset(
        {ProblemContentStatus.VALIDATING, ProblemContentStatus.RETIRED}
    ),
    ProblemContentStatus.APPROVED: frozenset(
        {
            ProblemContentStatus.INDEXED,
            ProblemContentStatus.VALIDATING,
            ProblemContentStatus.REVISION_REQUIRED,
            ProblemContentStatus.QUARANTINED,
            ProblemContentStatus.RETIRED,
        }
    ),
    ProblemContentStatus.INDEXED: frozenset(
        {ProblemContentStatus.QUARANTINED, ProblemContentStatus.RETIRED}
    ),
    ProblemContentStatus.RETIRED: frozenset(),
}


class InvalidProblemTransition(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        missing_requirements: Iterable[str] = (),
        suggested_status: ProblemContentStatus | None = None,
    ) -> None:
        self.code = code
        self.missing_requirements = tuple(missing_requirements)
        self.suggested_status = suggested_status
        super().__init__(message)


class ProblemTransitionRequest(BaseModel):
    problem_id: str
    generation_batch_id: str | None = None
    current_status: ProblemContentStatus
    target_status: ProblemContentStatus
    current_status_reason: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=1000)
    revision_attempts: int = Field(default=0, ge=0)
    max_revision_attempts: int = Field(default=2, ge=0, le=2)
    structured_problem_complete: bool = False
    source_rights_cleared: bool = False
    has_fully_verified_solution: bool = False
    verification_scope: ProblemVerificationScope = ProblemVerificationScope.PROGRAMMATIC
    has_authoritative_full_coverage: bool = True
    problem_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    fully_verified_solution_id: str | None = None
    fully_verified_solution_content_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    index_is_active: bool = False
    evidence: list[AdmissionEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_scope(self) -> ProblemTransitionRequest:
        foreign_problem_ids = {
            item.problem_id for item in self.evidence if item.problem_id != self.problem_id
        }
        if foreign_problem_ids:
            raise ValueError("transition evidence must belong to the same problem")
        if self.target_status == ProblemContentStatus.APPROVED:
            if self.generation_batch_id is None:
                raise ValueError("approval requires a generation batch")
            if any(
                item.generation_batch_id != self.generation_batch_id
                for item in self.evidence
            ):
                raise ValueError("approval evidence belongs to another generation batch")
        if self.has_fully_verified_solution and (
            self.fully_verified_solution_id is None
            or self.fully_verified_solution_content_hash is None
        ):
            raise ValueError("fully verified solution identity and hash are required")
        return self


class ProblemTransitionResult(BaseModel):
    problem_id: str
    previous_status: ProblemContentStatus
    current_status: ProblemContentStatus
    changed: bool
    status_reason: str | None = None
    revision_attempts: int
    checked_requirements: list[str] = Field(default_factory=list)


class ProblemContentStateMachine:
    def transition(self, request: ProblemTransitionRequest) -> ProblemTransitionResult:
        if request.current_status == request.target_status:
            return ProblemTransitionResult(
                problem_id=request.problem_id,
                previous_status=request.current_status,
                current_status=request.current_status,
                changed=False,
                status_reason=request.current_status_reason,
                revision_attempts=request.revision_attempts,
                checked_requirements=["idempotent_noop"],
            )

        allowed = ALLOWED_TRANSITIONS[request.current_status]
        if request.target_status not in allowed:
            raise InvalidProblemTransition(
                "transition_not_allowed",
                f"cannot transition from {request.current_status.value} "
                f"to {request.target_status.value}",
            )

        checked: list[str] = []
        revision_attempts = request.revision_attempts
        target = request.target_status

        if target in {
            ProblemContentStatus.REVISION_REQUIRED,
            ProblemContentStatus.QUARANTINED,
            ProblemContentStatus.RETIRED,
        }:
            if not request.reason or not request.reason.strip():
                raise InvalidProblemTransition(
                    "status_reason_required",
                    f"{target.value} requires a non-empty reason",
                    missing_requirements=["status_reason"],
                )
            checked.append("status_reason")

        if target == ProblemContentStatus.REVISION_REQUIRED:
            if request.revision_attempts >= request.max_revision_attempts:
                raise InvalidProblemTransition(
                    "revision_limit_exhausted",
                    "the problem has reached the maximum automatic revision attempts",
                    missing_requirements=["remaining_revision_attempt"],
                    suggested_status=ProblemContentStatus.QUARANTINED,
                )
            revision_attempts += 1
            checked.append("revision_limit")

        latest_evidence = self._latest_evidence_by_type(request.evidence)

        if target == ProblemContentStatus.APPROVED:
            if (
                request.verification_scope != ProblemVerificationScope.PROGRAMMATIC
                and not request.has_authoritative_full_coverage
            ):
                raise InvalidProblemTransition(
                    "verification_coverage_insufficient",
                    "proof or open-ended content lacks authoritative full coverage",
                    missing_requirements=[
                        "authoritative_full_verification_coverage"
                    ],
                    suggested_status=ProblemContentStatus.QUARANTINED,
                )
            missing = self._approval_gaps(request, latest_evidence)
            if missing:
                raise InvalidProblemTransition(
                    "approval_gate_failed",
                    "the problem does not satisfy the automatic admission gate",
                    missing_requirements=missing,
                    suggested_status=ProblemContentStatus.REVISION_REQUIRED,
                )
            checked.extend(
                [
                    "structured_problem_complete",
                    "source_rights_cleared",
                    "fully_verified_solution",
                    "no_blocking_evidence",
                    *sorted(REQUIRED_APPROVAL_EVIDENCE),
                ]
            )

        if target == ProblemContentStatus.INDEXED:
            self._require_passed_evidence(latest_evidence, "index_sync")
            if not request.index_is_active:
                raise InvalidProblemTransition(
                    "index_not_active",
                    "indexed status requires a confirmed active production index entry",
                    missing_requirements=["active_index_entry"],
                )
            checked.extend(["index_sync", "active_index_entry"])

        if request.current_status == ProblemContentStatus.INDEXED and target in {
            ProblemContentStatus.QUARANTINED,
            ProblemContentStatus.RETIRED,
        }:
            self._require_passed_evidence(latest_evidence, "index_removal")
            if request.index_is_active:
                raise InvalidProblemTransition(
                    "index_still_active",
                    "indexed content must be removed from production retrieval first",
                    missing_requirements=["inactive_index_entry"],
                )
            checked.extend(["index_removal", "inactive_index_entry"])

        if target != ProblemContentStatus.INDEXED and request.index_is_active:
            raise InvalidProblemTransition(
                "unexpected_active_index",
                f"{target.value} content cannot remain active in the production index",
                missing_requirements=["inactive_index_entry"],
            )

        status_reason = (
            request.reason.strip()
            if request.reason
            and target
            in {
                ProblemContentStatus.REVISION_REQUIRED,
                ProblemContentStatus.QUARANTINED,
                ProblemContentStatus.RETIRED,
            }
            else None
        )
        return ProblemTransitionResult(
            problem_id=request.problem_id,
            previous_status=request.current_status,
            current_status=target,
            changed=True,
            status_reason=status_reason,
            revision_attempts=revision_attempts,
            checked_requirements=checked,
        )

    @staticmethod
    def _latest_evidence_by_type(
        evidence: list[AdmissionEvidence],
    ) -> dict[str, AdmissionEvidence]:
        latest: dict[str, AdmissionEvidence] = {}
        for item in sorted(evidence, key=lambda value: (value.created_at, value.id)):
            latest[item.evidence_type] = item
        return latest

    @staticmethod
    def _require_passed_evidence(
        evidence: dict[str, AdmissionEvidence], evidence_type: str
    ) -> None:
        item = evidence.get(evidence_type)
        if item is None or item.status != AdmissionEvidenceStatus.PASSED:
            raise InvalidProblemTransition(
                "required_evidence_missing",
                f"a passed {evidence_type} evidence record is required",
                missing_requirements=[evidence_type],
            )

    @staticmethod
    def _approval_gaps(
        request: ProblemTransitionRequest,
        evidence: dict[str, AdmissionEvidence],
    ) -> list[str]:
        missing: list[str] = []
        if not request.structured_problem_complete:
            missing.append("structured_problem_complete")
        if not request.source_rights_cleared:
            missing.append("source_rights_cleared")
        if not request.has_fully_verified_solution:
            missing.append("fully_verified_solution")
        if (
            request.verification_scope != ProblemVerificationScope.PROGRAMMATIC
            and not request.has_authoritative_full_coverage
        ):
            missing.append("authoritative_full_verification_coverage")
        if request.problem_content_hash is None:
            missing.append("problem_content_hash")
        if request.generation_batch_id is None:
            missing.append("generation_batch_id")
        if request.index_is_active:
            missing.append("inactive_index_entry")

        for evidence_type in sorted(REQUIRED_APPROVAL_EVIDENCE):
            item = evidence.get(evidence_type)
            if item is None or item.status != AdmissionEvidenceStatus.PASSED:
                missing.append(evidence_type)

        for evidence_type in sorted(VERSIONED_VERIFIER_APPROVAL_EVIDENCE):
            item = evidence.get(evidence_type)
            if item is not None and (
                item.producer_type != EvidenceProducerType.VERIFIER
                or item.verifier_version_id is None
            ):
                missing.append(f"{evidence_type}:versioned_verifier")

        independence = evidence.get("solution_independence")
        if independence is not None and (
            independence.producer_type != EvidenceProducerType.SYSTEM
            or independence.model_version_id is not None
            or independence.prompt_version_id is not None
            or independence.verifier_version_id is not None
        ):
            missing.append("solution_independence:system_projection")

        rights = evidence.get("source_rights_clearance")
        if rights is not None and (
            rights.producer_type != EvidenceProducerType.SYSTEM
            or rights.model_version_id is not None
            or rights.prompt_version_id is not None
            or rights.verifier_version_id is not None
        ):
            missing.append("source_rights_clearance:system_verification")

        for evidence_type in sorted(MODEL_APPROVAL_EVIDENCE):
            item = evidence.get(evidence_type)
            if item is not None and (
                item.producer_type != EvidenceProducerType.MODEL
                or item.model_version_id is None
                or item.prompt_version_id is None
            ):
                missing.append(f"{evidence_type}:versioned_model")

        for evidence_type in sorted(PROBLEM_SCOPED_APPROVAL_EVIDENCE):
            item = evidence.get(evidence_type)
            if item is not None and item.solution_id is not None:
                missing.append(f"{evidence_type}:problem_scope")

        for evidence_type in sorted(PROBLEM_CONTENT_BOUND_EVIDENCE):
            item = evidence.get(evidence_type)
            if item is not None and (
                item.payload.get("problem_content_hash") != request.problem_content_hash
            ):
                missing.append(f"{evidence_type}:current_problem_content")

        for evidence_type in sorted(SOLUTION_SCOPED_APPROVAL_EVIDENCE):
            item = evidence.get(evidence_type)
            if item is not None and (
                item.solution_id != request.fully_verified_solution_id
                or item.payload.get("solution_content_hash")
                != request.fully_verified_solution_content_hash
            ):
                missing.append(f"{evidence_type}:fully_verified_solution")

        for item in evidence.values():
            if item.is_blocking and item.status != AdmissionEvidenceStatus.PASSED:
                missing.append(f"blocking:{item.evidence_type}")
        return list(dict.fromkeys(missing))
