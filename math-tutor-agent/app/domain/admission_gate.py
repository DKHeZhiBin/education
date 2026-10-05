from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.domain.generation import AdmissionEvidence, AdmissionEvidenceStatus
from app.domain.knowledge import ProblemContentStatus
from app.domain.problem_lifecycle import (
    ProblemTransitionResult,
    REQUIRED_APPROVAL_EVIDENCE,
)
from app.domain.verification_scope_policy import (
    ProblemVerificationScope,
    restricted_coverage_reason,
)


DETERMINISTIC_EVIDENCE_TYPES = frozenset({
    "solution_independence",
    "symbolic_verification",
    "numeric_verification",
    "constraint_verification",
    "duplicate_detection",
    "evaluation_leakage_detection",
    "source_rights_clearance",
})

IMMEDIATE_QUARANTINE_EVIDENCE_TYPES = frozenset({
    "duplicate_detection",
    "evaluation_leakage_detection",
    "source_rights_clearance",
})


class AdmissionGateDecision(StrEnum):
    APPROVE = "approve"
    REVISE = "revise"
    QUARANTINE = "quarantine"
    WAIT = "wait"


class AdmissionGateContext(BaseModel):
    problem_id: str
    generation_batch_id: str
    problem_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status_version: int = Field(ge=1)
    current_status: ProblemContentStatus
    revision_attempts: int = Field(ge=0)
    max_revision_attempts: int = Field(ge=0, le=2)
    structured_problem_complete: bool
    index_is_active: bool = False
    selected_solution_id: str | None = None
    selected_solution_content_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    has_fully_verified_solution: bool = False
    verification_scope: ProblemVerificationScope = ProblemVerificationScope.PROGRAMMATIC
    has_authoritative_full_coverage: bool = True
    selected_solution_verification_status: str | None = None
    selected_solution_coverage_level: str | None = None
    evidence: list[AdmissionEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self) -> AdmissionGateContext:
        if self.current_status != ProblemContentStatus.VALIDATING:
            raise ValueError("automatic admission gate requires validating status")
        if (self.selected_solution_id is None) != (
            self.selected_solution_content_hash is None
        ):
            raise ValueError("selected solution id and content hash must be supplied together")
        for item in self.evidence:
            if item.problem_id != self.problem_id:
                raise ValueError("admission evidence belongs to another problem")
            if item.generation_batch_id != self.generation_batch_id:
                raise ValueError("admission evidence belongs to another generation batch")
            if item.solution_id is not None and item.solution_id != self.selected_solution_id:
                raise ValueError("admission evidence belongs to another solution")
        return self


class AdmissionGateResult(BaseModel):
    problem_id: str
    decision: AdmissionGateDecision
    target_status: ProblemContentStatus | None = None
    reason: str
    selected_solution_id: str | None = None
    deterministic_failures: list[str] = Field(default_factory=list)
    other_failures: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    inconclusive_evidence: list[str] = Field(default_factory=list)
    checked_evidence_ids: list[str] = Field(default_factory=list)
    ignored_model_pass: bool = False

    @model_validator(mode="after")
    def validate_decision(self) -> AdmissionGateResult:
        expected_target = {
            AdmissionGateDecision.APPROVE: ProblemContentStatus.APPROVED,
            AdmissionGateDecision.REVISE: ProblemContentStatus.REVISION_REQUIRED,
            AdmissionGateDecision.QUARANTINE: ProblemContentStatus.QUARANTINED,
            AdmissionGateDecision.WAIT: None,
        }[self.decision]
        if self.target_status != expected_target:
            raise ValueError("admission decision and target status do not match")
        if self.deterministic_failures and self.decision not in {
            AdmissionGateDecision.REVISE,
            AdmissionGateDecision.QUARANTINE,
        }:
            raise ValueError("deterministic failures must revise or quarantine content")
        return self


class PersistedAdmissionGateResult(BaseModel):
    gate_result: AdmissionGateResult
    decision_evidence: AdmissionEvidence
    transition: ProblemTransitionResult | None = None
    status_version: int = Field(ge=1)


class RuleBasedAdmissionGate:
    """Choose the admission outcome without accepting a model-selected target status."""

    def evaluate(self, context: AdmissionGateContext) -> AdmissionGateResult:
        latest = self._latest_by_type(context.evidence)
        checked_ids = sorted(item.id for item in latest.values())
        deterministic_failures = sorted(
            evidence_type
            for evidence_type in DETERMINISTIC_EVIDENCE_TYPES
            if (
                evidence_type in latest
                and latest[evidence_type].status == AdmissionEvidenceStatus.FAILED
            )
        )
        model_passed = (
            latest.get("pedagogical_review") is not None
            and latest["pedagogical_review"].status == AdmissionEvidenceStatus.PASSED
        )
        if (
            context.verification_scope != ProblemVerificationScope.PROGRAMMATIC
            and not context.has_authoritative_full_coverage
        ):
            return self._result(
                context,
                AdmissionGateDecision.QUARANTINE,
                restricted_coverage_reason(context.verification_scope),
                deterministic_failures=deterministic_failures,
                other_failures=["verification_coverage_policy"],
                checked_evidence_ids=checked_ids,
                ignored_model_pass=model_passed,
            )
        if deterministic_failures:
            quarantine = bool(
                set(deterministic_failures) & IMMEDIATE_QUARANTINE_EVIDENCE_TYPES
            ) or context.revision_attempts >= context.max_revision_attempts
            decision = (
                AdmissionGateDecision.QUARANTINE
                if quarantine
                else AdmissionGateDecision.REVISE
            )
            return self._result(
                context,
                decision,
                self._failure_reason("确定性校验失败", deterministic_failures),
                deterministic_failures=deterministic_failures,
                checked_evidence_ids=checked_ids,
                ignored_model_pass=model_passed,
            )

        other_failures = sorted(
            evidence_type
            for evidence_type, item in latest.items()
            if evidence_type != "admission_decision"
            and item.is_blocking
            and item.status == AdmissionEvidenceStatus.FAILED
        )
        if other_failures:
            decision = self._revision_or_quarantine(context)
            return self._result(
                context,
                decision,
                self._failure_reason("其他阻断检查失败", other_failures),
                other_failures=other_failures,
                checked_evidence_ids=checked_ids,
            )

        if not context.structured_problem_complete:
            decision = self._revision_or_quarantine(context)
            return self._result(
                context,
                decision,
                "题目结构化条件、目标或题型信息不完整。",
                other_failures=["structured_problem_complete"],
                checked_evidence_ids=checked_ids,
            )

        missing = sorted(REQUIRED_APPROVAL_EVIDENCE - latest.keys())
        inconclusive = sorted({
            evidence_type
            for evidence_type, item in latest.items()
            if (evidence_type in REQUIRED_APPROVAL_EVIDENCE or item.is_blocking)
            and item.status in {
                AdmissionEvidenceStatus.NOT_RUN,
                AdmissionEvidenceStatus.INCONCLUSIVE,
            }
        })
        if missing or inconclusive:
            return self._result(
                context,
                AdmissionGateDecision.WAIT,
                "准入证据尚未齐全或仍无法形成结论。",
                missing_evidence=missing,
                inconclusive_evidence=inconclusive,
                checked_evidence_ids=checked_ids,
            )

        non_passed = sorted(
            evidence_type
            for evidence_type in REQUIRED_APPROVAL_EVIDENCE
            if latest[evidence_type].status != AdmissionEvidenceStatus.PASSED
        )
        if non_passed:
            decision = self._revision_or_quarantine(context)
            return self._result(
                context,
                decision,
                self._failure_reason("准入检查未通过", non_passed),
                other_failures=non_passed,
                checked_evidence_ids=checked_ids,
            )

        if not context.has_fully_verified_solution:
            decision = self._revision_or_quarantine(context)
            return self._result(
                context,
                decision,
                "没有与本轮证据一致且达到完整验证覆盖的题解。",
                other_failures=["fully_verified_solution"],
                checked_evidence_ids=checked_ids,
            )

        if context.index_is_active:
            return self._result(
                context,
                AdmissionGateDecision.WAIT,
                "候选题在批准前不应存在活动生产索引。",
                inconclusive_evidence=["inactive_index_entry"],
                checked_evidence_ids=checked_ids,
            )

        return self._result(
            context,
            AdmissionGateDecision.APPROVE,
            "结构、题解和全部最新准入证据均满足自动批准规则。",
            checked_evidence_ids=checked_ids,
        )

    @staticmethod
    def _latest_by_type(
        evidence: list[AdmissionEvidence],
    ) -> dict[str, AdmissionEvidence]:
        latest: dict[str, AdmissionEvidence] = {}
        for item in sorted(evidence, key=lambda value: (value.created_at, value.id)):
            if item.evidence_type != "admission_decision":
                latest[item.evidence_type] = item
        return latest

    @staticmethod
    def _revision_or_quarantine(
        context: AdmissionGateContext,
    ) -> AdmissionGateDecision:
        if context.revision_attempts >= context.max_revision_attempts:
            return AdmissionGateDecision.QUARANTINE
        return AdmissionGateDecision.REVISE

    @staticmethod
    def _failure_reason(prefix: str, failures: list[str]) -> str:
        return f"{prefix}：{', '.join(failures)}。"

    @staticmethod
    def _result(
        context: AdmissionGateContext,
        decision: AdmissionGateDecision,
        reason: str,
        **details,
    ) -> AdmissionGateResult:
        target = {
            AdmissionGateDecision.APPROVE: ProblemContentStatus.APPROVED,
            AdmissionGateDecision.REVISE: ProblemContentStatus.REVISION_REQUIRED,
            AdmissionGateDecision.QUARANTINE: ProblemContentStatus.QUARANTINED,
            AdmissionGateDecision.WAIT: None,
        }[decision]
        return AdmissionGateResult(
            problem_id=context.problem_id,
            decision=decision,
            target_status=target,
            reason=reason,
            selected_solution_id=context.selected_solution_id,
            **details,
        )
