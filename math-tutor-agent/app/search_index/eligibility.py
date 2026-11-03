from __future__ import annotations

from collections.abc import Iterable

from app.core.product_scope import MVP_GRADE_BAND, MVP_SUBJECT_CODE
from app.domain.problem_lifecycle import (
    MODEL_APPROVAL_EVIDENCE,
    PROBLEM_CONTENT_BOUND_EVIDENCE,
    PROBLEM_SCOPED_APPROVAL_EVIDENCE,
    REQUIRED_APPROVAL_EVIDENCE,
    SOLUTION_SCOPED_APPROVAL_EVIDENCE,
    VERSIONED_VERIFIER_APPROVAL_EVIDENCE,
)
from app.models.generation import AdmissionEvidence
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution


class ProductionIndexEligibilityError(RuntimeError):
    """中文：定义“production·索引·eligibility·error”类，封装该职责相关的数据与行为。
    English: Defines the production index eligibility error class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Raised when approved content no longer satisfies the production gate.
    """

    def __init__(self, reasons: Iterable[str]) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.reasons = tuple(dict.fromkeys(reasons))
        super().__init__(
            "production_index_blocked:" + ",".join(self.reasons)
        )


def require_problem_index_eligibility(problem: KnowledgeProblem) -> None:
    """中文：处理“require·题目·索引·eligibility”相关操作。
    English: Handles the require problem index eligibility operation.

    原有说明 / Existing notes:
    Fail closed before staging or activating a generated problem.
    """

    reasons: list[str] = []
    if problem.subject != MVP_SUBJECT_CODE or problem.grade_band != MVP_GRADE_BAND:
        reasons.append("problem_outside_product_scope")
    if problem.content_status != "approved":
        reasons.append("problem_not_approved")
    if not problem.generation_batch_id:
        reasons.append("generation_batch_missing")
    if reasons:
        raise ProductionIndexEligibilityError(reasons)

    evidence = [
        item
        for item in problem.admission_evidence
        if item.generation_batch_id == problem.generation_batch_id
    ]
    latest = _latest_by_type(evidence)
    decision = latest.get("admission_decision")
    if decision is None:
        reasons.append("approval_decision_missing")
        decision_payload: dict = {}
    else:
        decision_payload = decision.payload_json or {}
        if decision.status != "passed" or decision_payload.get("decision") != "approve":
            reasons.append("approval_decision_not_passed")
        if decision_payload.get("target_status") != "approved":
            reasons.append("approval_target_invalid")
        if decision_payload.get("problem_content_hash") != problem.content_hash:
            reasons.append("approval_decision_stale")
        for field in (
            "deterministic_failures",
            "other_failures",
            "missing_evidence",
            "inconclusive_evidence",
        ):
            if decision_payload.get(field):
                reasons.append(f"approval_{field}")

    selected_solution = _selected_solution(problem, decision_payload)
    if selected_solution is None:
        reasons.append("fully_verified_solution_missing")
    elif not solution_has_full_coverage(selected_solution):
        reasons.append("verification_coverage_insufficient")

    for evidence_type in sorted(REQUIRED_APPROVAL_EVIDENCE):
        item = latest.get(evidence_type)
        if item is None:
            reasons.append(f"missing:{evidence_type}")
        elif item.status != "passed":
            reasons.append(f"failed:{evidence_type}")

    for item in latest.values():
        if (
            item.evidence_type != "admission_decision"
            and (item.is_blocking or item.evidence_type in REQUIRED_APPROVAL_EVIDENCE)
            and item.status != "passed"
        ):
            reasons.append(f"blocking:{item.evidence_type}")

    leakage = latest.get("evaluation_leakage_detection")
    if leakage is not None and (leakage.payload_json or {}).get("matches"):
        reasons.append("evaluation_set_similarity_match")

    _validate_evidence_provenance(
        problem=problem,
        solution=selected_solution,
        latest=latest,
        reasons=reasons,
    )
    if decision is not None:
        checked_ids = set(decision_payload.get("checked_evidence_ids") or [])
        current_ids = {
            latest[evidence_type].id
            for evidence_type in REQUIRED_APPROVAL_EVIDENCE
            if evidence_type in latest
        }
        if not current_ids.issubset(checked_ids):
            reasons.append("approval_evidence_changed")

    if reasons:
        raise ProductionIndexEligibilityError(reasons)


def solution_has_full_coverage(solution: KnowledgeSolution) -> bool:
    """中文：处理“解答·has·full·coverage”相关操作。
    English: Handles the solution has full coverage operation.
    """
    coverage = solution.verification_coverage_json or {}
    return bool(
        solution.review_status == "approved"
        and solution.verification_status == "verified"
        and solution.steps_json
        and coverage.get("level") == "full"
        and not coverage.get("uncovered_step_ids")
        and not any(
            isinstance(check, dict) and check.get("status") == "failed"
            for check in (coverage.get("checks") or [])
        )
    )


def _latest_by_type(
    evidence: list[AdmissionEvidence],
) -> dict[str, AdmissionEvidence]:
    """中文：处理“latest·by·type”相关操作。
    English: Handles the latest by type operation.
    """
    latest: dict[str, AdmissionEvidence] = {}
    for item in sorted(evidence, key=lambda value: (value.created_at, value.id)):
        latest[item.evidence_type] = item
    return latest


def _selected_solution(
    problem: KnowledgeProblem,
    decision_payload: dict,
) -> KnowledgeSolution | None:
    """中文：处理“selected·解答”相关操作。
    English: Handles the selected solution operation.
    """
    solution_id = decision_payload.get("selected_solution_id")
    solution_hash = decision_payload.get("selected_solution_content_hash")
    return next(
        (
            solution
            for solution in problem.solutions
            if solution.id == solution_id and solution.content_hash == solution_hash
        ),
        None,
    )


def _validate_evidence_provenance(
    *,
    problem: KnowledgeProblem,
    solution: KnowledgeSolution | None,
    latest: dict[str, AdmissionEvidence],
    reasons: list[str],
) -> None:
    """中文：处理“验证·evidence·provenance”相关操作。
    English: Handles the validate evidence provenance operation.
    """
    for evidence_type in VERSIONED_VERIFIER_APPROVAL_EVIDENCE:
        item = latest.get(evidence_type)
        if item is not None and (
            item.producer_type != "verifier" or item.verifier_version_id is None
        ):
            reasons.append(f"unversioned:{evidence_type}")

    for evidence_type in MODEL_APPROVAL_EVIDENCE:
        item = latest.get(evidence_type)
        if item is not None and (
            item.producer_type != "model"
            or item.model_version_id is None
            or item.prompt_version_id is None
        ):
            reasons.append(f"unversioned:{evidence_type}")

    for evidence_type in PROBLEM_SCOPED_APPROVAL_EVIDENCE:
        item = latest.get(evidence_type)
        if item is not None and item.solution_id is not None:
            reasons.append(f"wrong_scope:{evidence_type}")

    for evidence_type in PROBLEM_CONTENT_BOUND_EVIDENCE:
        item = latest.get(evidence_type)
        if item is not None and (
            (item.payload_json or {}).get("problem_content_hash")
            != problem.content_hash
        ):
            reasons.append(f"stale:{evidence_type}")

    for evidence_type in SOLUTION_SCOPED_APPROVAL_EVIDENCE:
        item = latest.get(evidence_type)
        if item is not None and (
            solution is None
            or item.solution_id != solution.id
            or (item.payload_json or {}).get("solution_content_hash")
            != solution.content_hash
        ):
            reasons.append(f"wrong_solution:{evidence_type}")
