from __future__ import annotations

from enum import StrEnum
from typing import Any, Iterable

from app.domain.generation import (
    AdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)


class ProblemVerificationScope(StrEnum):
    PROGRAMMATIC = "programmatic"
    PROOF = "proof"
    OPEN_ENDED = "open_ended"


PROOF_PROBLEM_TYPES = frozenset({"proof", "geometric_proof", "proof_problem"})
OPEN_ENDED_PROBLEM_TYPES = frozenset({
    "open_ended",
    "open_problem",
    "exploration",
    "investigation",
    "discussion",
})
OPEN_ENDED_ACTIONS = frozenset({"construct", "explain"})
OPEN_ENDED_ANSWER_TYPES = frozenset({
    "open_ended",
    "explanation",
    "essay",
    "construction",
    "multiple_valid",
    "argument",
})

AUTHORITATIVE_EVIDENCE_TYPES = {
    ProblemVerificationScope.PROOF: frozenset({
        "formal_proof_verification",
        "qualified_human_review",
    }),
    ProblemVerificationScope.OPEN_ENDED: frozenset({
        "exhaustive_rubric_verification",
        "qualified_human_review",
    }),
}


def classify_problem_verification_scope(
    *,
    problem_type: str,
    answer_type: str,
    target: dict[str, Any] | None,
    metadata: dict[str, Any] | None = None,
) -> ProblemVerificationScope:
    normalized_type = problem_type.strip().casefold()
    normalized_answer = answer_type.strip().casefold()
    target = target or {}
    action = str(target.get("action") or "").strip().casefold()
    expected_answer = str(target.get("expected_answer_type") or "").strip().casefold()
    metadata = metadata or {}

    if (
        normalized_type in PROOF_PROBLEM_TYPES
        or action == "prove"
        or normalized_answer == "proof"
        or expected_answer == "proof"
    ):
        return ProblemVerificationScope.PROOF
    if (
        normalized_type in OPEN_ENDED_PROBLEM_TYPES
        or normalized_answer in OPEN_ENDED_ANSWER_TYPES
        or expected_answer in OPEN_ENDED_ANSWER_TYPES
        or action in OPEN_ENDED_ACTIONS
        or metadata.get("open_ended") is True
    ):
        return ProblemVerificationScope.OPEN_ENDED
    return ProblemVerificationScope.PROGRAMMATIC


def has_authoritative_full_coverage(
    *,
    scope: ProblemVerificationScope,
    problem_content_hash: str,
    solution_id: str | None,
    solution_content_hash: str | None,
    evidence: Iterable[AdmissionEvidence],
) -> bool:
    if scope == ProblemVerificationScope.PROGRAMMATIC:
        return True
    if solution_id is None or solution_content_hash is None:
        return False
    allowed_types = AUTHORITATIVE_EVIDENCE_TYPES[scope]
    for item in evidence:
        if (
            item.evidence_type not in allowed_types
            or item.status != AdmissionEvidenceStatus.PASSED
            or item.solution_id != solution_id
            or item.payload.get("problem_content_hash") != problem_content_hash
            or item.payload.get("solution_content_hash") != solution_content_hash
            or item.payload.get("coverage_level") != "full"
        ):
            continue
        if item.evidence_type == "qualified_human_review":
            if (
                item.producer_type == EvidenceProducerType.SYSTEM
                and item.payload.get("reviewer_kind") == "qualified_human"
                and bool(item.payload.get("reviewer_id"))
                and bool(item.payload.get("reviewed_at"))
            ):
                return True
            continue
        if (
            item.producer_type == EvidenceProducerType.VERIFIER
            and item.verifier_version_id is not None
        ):
            return True
    return False


def restricted_coverage_reason(scope: ProblemVerificationScope) -> str:
    if scope == ProblemVerificationScope.PROOF:
        return (
            "证明题缺少形式化证明器或具有身份记录的合格人工完整复核，"
            "现有模型审查只能形成 partial 覆盖。"
        )
    if scope == ProblemVerificationScope.OPEN_ENDED:
        return (
            "开放题缺少穷尽式评分规则验证或具有身份记录的合格人工完整复核，"
            "现有证据不能形成 full 覆盖。"
        )
    return "当前题型允许使用程序化完整验证。"
