from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.generation import (
    AdmissionEvidence as DomainAdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)
from app.domain.knowledge import KnowledgeSolution as DomainKnowledgeSolution
from app.domain.quadratic_verification import (
    QuadraticCheckStatus,
    QuadraticVerificationContext,
    QuadraticVerificationReport,
)
from app.models.generation import AdmissionEvidence, VerifierVersion
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution


class QuadraticVerificationReferenceInvalid(ValueError):
    pass


class QuadraticVerificationVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class QuadraticVerifierContext:
    verification_context: QuadraticVerificationContext
    verifier_version_id: str
    verifier_key: str
    verifier_version: str


@dataclass(frozen=True)
class PersistedQuadraticVerification:
    solution: DomainKnowledgeSolution
    symbolic_evidence: DomainAdmissionEvidence
    constraint_evidence: DomainAdmissionEvidence


class QuadraticVerificationRepository:
    """Load isolated verifier input and persist deterministic admission evidence."""

    def load_verifier_context(
        self,
        session: Session,
        *,
        problem_id: str,
        solution_id: str,
        verifier_version_id: str,
    ) -> QuadraticVerifierContext:
        verifier = self._require_verifier(session, verifier_version_id)
        problem = session.get(KnowledgeProblem, problem_id)
        solution = session.get(KnowledgeSolution, solution_id)
        if problem is None or solution is None or solution.problem_id != problem.id:
            raise QuadraticVerificationReferenceInvalid("problem or matching solution not found")
        self._require_scope(problem, solution)
        self._require_independent_solution(session, problem, solution)
        context = self._build_context(problem, solution)
        return QuadraticVerifierContext(
            verification_context=context,
            verifier_version_id=verifier.id,
            verifier_key=verifier.verifier_key,
            verifier_version=verifier.version,
        )

    def persist_report(
        self,
        session: Session,
        *,
        context: QuadraticVerifierContext,
        report: QuadraticVerificationReport,
    ) -> PersistedQuadraticVerification:
        self._require_verifier(session, context.verifier_version_id)
        problem = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == context.verification_context.problem_id)
            .with_for_update()
        )
        solution = session.scalar(
            select(KnowledgeSolution)
            .where(KnowledgeSolution.id == context.verification_context.solution_id)
            .with_for_update()
        )
        if problem is None or solution is None or solution.problem_id != problem.id:
            raise QuadraticVerificationReferenceInvalid("problem or matching solution not found")
        self._require_scope(problem, solution)
        current = self._build_context(problem, solution)
        expected = context.verification_context
        if (
            current.problem_content_hash != expected.problem_content_hash
            or current.solution_content_hash != expected.solution_content_hash
            or current.status_version != expected.status_version
            or current.fingerprint() != expected.fingerprint()
        ):
            raise QuadraticVerificationVersionConflict(
                "problem or solution changed while SymPy verification was running"
            )
        if (
            report.problem_id != problem.id
            or report.solution_id != solution.id
            or report.context_fingerprint != current.fingerprint()
        ):
            raise QuadraticVerificationReferenceInvalid("verification report context mismatch")

        coverage = self._solution_coverage(report)
        solution.verification_status = report.verification_status
        solution.verification_coverage_json = coverage
        metadata = dict(solution.metadata_json or {})
        metadata.update({
            "last_verifier_key": context.verifier_key,
            "last_verifier_version": context.verifier_version,
            "last_verifier_version_id": context.verifier_version_id,
            "requires_external_verification": report.verification_status != "verified",
        })
        solution.metadata_json = metadata

        symbolic = self._get_or_create_evidence(
            session,
            problem=problem,
            solution=solution,
            verifier_version_id=context.verifier_version_id,
            evidence_type="symbolic_verification",
            status=self._group_status(report, {
                "solve", "substitution", "root_count", "step_equivalence"
            }),
            summary=self._symbolic_summary(report),
            payload={
                "schema_version": report.schema_version,
                "problem_content_hash": problem.content_hash,
                "problem_status_version": problem.status_version,
                "solution_content_hash": solution.content_hash,
                "context_fingerprint": report.context_fingerprint,
                "equation": report.equation,
                "variable": report.variable,
                "standard_form": report.standard_form,
                "coefficients": report.coefficients,
                "discriminant": report.discriminant,
                "computed_roots": report.computed_roots,
                "claimed_roots": report.claimed_roots,
                "checks": [
                    item.model_dump(mode="json") for item in report.checks
                    if item.check_type in {"solve", "substitution", "root_count", "step_equivalence"}
                ],
                "verification_status": report.verification_status,
                "coverage_level": report.coverage_level,
                "covered_step_ids": report.covered_step_ids,
                "uncovered_step_ids": report.uncovered_step_ids,
            },
        )
        constraint = self._get_or_create_evidence(
            session,
            problem=problem,
            solution=solution,
            verifier_version_id=context.verifier_version_id,
            evidence_type="constraint_verification",
            status=self._group_status(report, {"domain", "boundary"}),
            summary=self._constraint_summary(report),
            payload={
                "schema_version": report.schema_version,
                "problem_content_hash": problem.content_hash,
                "problem_status_version": problem.status_version,
                "solution_content_hash": solution.content_hash,
                "context_fingerprint": report.context_fingerprint,
                "checks": [
                    item.model_dump(mode="json") for item in report.checks
                    if item.check_type in {"domain", "boundary"}
                ],
                "limitations": report.limitations,
            },
        )
        session.flush()
        return PersistedQuadraticVerification(
            solution=self._solution_to_domain(solution),
            symbolic_evidence=self._evidence_to_domain(symbolic),
            constraint_evidence=self._evidence_to_domain(constraint),
        )

    @staticmethod
    def _build_context(
        problem: KnowledgeProblem,
        solution: KnowledgeSolution,
    ) -> QuadraticVerificationContext:
        return QuadraticVerificationContext(
            problem_id=problem.id,
            solution_id=solution.id,
            generation_batch_id=problem.generation_batch_id,
            problem_content_hash=problem.content_hash,
            solution_content_hash=solution.content_hash,
            status_version=problem.status_version,
            content_status=problem.content_status,
            problem_type=problem.problem_type,
            answer_type=problem.answer_type,
            statement=problem.statement,
            normalized_statement=problem.normalized_statement,
            explicit_conditions=problem.explicit_conditions_json,
            implicit_conditions=problem.implicit_conditions_json,
            target=problem.target_json,
            solution_steps=solution.steps_json,
            final_answer=solution.final_answer,
        )

    @staticmethod
    def _require_scope(problem: KnowledgeProblem, solution: KnowledgeSolution) -> None:
        if problem.generation_batch_id is None:
            raise QuadraticVerificationReferenceInvalid("generated candidate batch is required")
        if problem.problem_type != "quadratic_equation":
            raise QuadraticVerificationReferenceInvalid(
                "quadratic SymPy verifier only accepts quadratic_equation"
            )
        if problem.content_status not in {"candidate", "validating", "revision_required"}:
            raise QuadraticVerificationReferenceInvalid(
                "verifier only accepts pre-admission content"
            )
        if not problem.target_json or not problem.explicit_conditions_json:
            raise QuadraticVerificationReferenceInvalid(
                "structured target and explicit conditions are required"
            )
        if not solution.final_answer:
            raise QuadraticVerificationReferenceInvalid("solution final_answer is required")
        if (solution.metadata_json or {}).get("content_origin") != "independent_solving_agent":
            raise QuadraticVerificationReferenceInvalid(
                "only an independently generated solution may be verified"
            )

    @staticmethod
    def _require_independent_solution(
        session: Session,
        problem: KnowledgeProblem,
        solution: KnowledgeSolution,
    ) -> None:
        evidence = session.scalar(
            select(AdmissionEvidence)
            .where(
                AdmissionEvidence.problem_id == problem.id,
                AdmissionEvidence.solution_id == solution.id,
                AdmissionEvidence.evidence_type == "solution_independence",
            )
            .order_by(AdmissionEvidence.created_at.desc(), AdmissionEvidence.id.desc())
            .limit(1)
        )
        if (
            evidence is None
            or evidence.status != "passed"
            or evidence.payload_json.get("solution_content_hash") != solution.content_hash
            or evidence.payload_json.get("problem_content_hash") != problem.content_hash
            or QuadraticVerificationRepository._predates_revalidation(
                problem, evidence
            )
        ):
            raise QuadraticVerificationReferenceInvalid(
                "fresh passed solution_independence evidence is required"
            )

    @staticmethod
    def _predates_revalidation(
        problem: KnowledgeProblem,
        evidence: AdmissionEvidence,
    ) -> bool:
        required = (problem.metadata_json or {}).get(
            "revalidation_started_status_version"
        )
        actual = evidence.payload_json.get("problem_status_version")
        return bool(required) and (
            not isinstance(actual, int) or actual < int(required)
        )

    @staticmethod
    def _require_verifier(session: Session, verifier_version_id: str) -> VerifierVersion:
        verifier = session.get(VerifierVersion, verifier_version_id)
        if (
            verifier is None
            or not verifier.active
            or verifier.verifier_key != "quadratic_sympy"
            or (
                verifier.supported_problem_types_json
                and "quadratic_equation" not in verifier.supported_problem_types_json
            )
        ):
            raise QuadraticVerificationReferenceInvalid(
                "active quadratic_sympy verifier version is required"
            )
        return verifier

    @staticmethod
    def _solution_coverage(report: QuadraticVerificationReport) -> dict:
        if report.verification_status == "unverified":
            return {
                "level": "none",
                "covered_step_ids": [],
                "uncovered_step_ids": [],
                "checks": [],
                "limitations": report.limitations,
                "confidence": report.confidence,
            }
        by_type = {item.check_type: item for item in report.checks}
        symbolic_items = [
            item for item in report.checks
            if item.check_type in {"solve", "step_equivalence"}
        ]
        return {
            "level": report.coverage_level,
            "covered_step_ids": report.covered_step_ids,
            "uncovered_step_ids": report.uncovered_step_ids,
            "checks": [
                {
                    "check_type": "symbolic_equivalence",
                    "status": QuadraticVerificationRepository._solution_check_status(symbolic_items),
                    "verifier": "quadratic_sympy",
                    "covered_step_ids": list(dict.fromkeys(
                        step_id for item in symbolic_items for step_id in item.covered_step_ids
                    )),
                    "evidence": "SymPy 独立求解并检查可解析步骤的解集等价性。",
                },
                QuadraticVerificationRepository._coverage_check(
                    "candidate_substitution", by_type.get("substitution")
                ),
                QuadraticVerificationRepository._coverage_check(
                    "answer_completeness", by_type.get("root_count")
                ),
                QuadraticVerificationRepository._coverage_check(
                    "constraint_satisfaction",
                    [by_type.get("domain"), by_type.get("boundary")],
                ),
            ],
            "limitations": report.limitations,
            "confidence": report.confidence,
        }

    @staticmethod
    def _coverage_check(check_type: str, value) -> dict:
        items = value if isinstance(value, list) else [value]
        items = [item for item in items if item is not None]
        return {
            "check_type": check_type,
            "status": QuadraticVerificationRepository._solution_check_status(items),
            "verifier": "quadratic_sympy",
            "covered_step_ids": list(dict.fromkeys(
                step_id for item in items for step_id in item.covered_step_ids
            )),
            "evidence": "；".join(item.summary for item in items) or "未运行",
        }

    @staticmethod
    def _solution_check_status(items: list) -> str:
        if any(item.status == QuadraticCheckStatus.FAILED for item in items):
            return "failed"
        if items and all(item.status == QuadraticCheckStatus.PASSED for item in items):
            return "passed"
        return "not_run"

    @staticmethod
    def _group_status(report: QuadraticVerificationReport, check_types: set[str]) -> str:
        items = [item for item in report.checks if item.check_type in check_types]
        if any(item.status == QuadraticCheckStatus.FAILED for item in items):
            return "failed"
        if (
            "step_equivalence" in check_types
            and report.verification_status in {"unverified", "partial"}
        ):
            return "inconclusive"
        if items and all(item.status == QuadraticCheckStatus.PASSED for item in items):
            return "passed"
        return "inconclusive"

    def _get_or_create_evidence(
        self,
        session: Session,
        *,
        problem: KnowledgeProblem,
        solution: KnowledgeSolution,
        verifier_version_id: str,
        evidence_type: str,
        status: str,
        summary: str,
        payload: dict,
    ) -> AdmissionEvidence:
        evidence_hash = self._hash_json(payload)
        existing = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == evidence_type,
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if existing is not None:
            return existing
        evidence = AdmissionEvidence(
            generation_batch_id=problem.generation_batch_id,
            problem_id=problem.id,
            solution_id=solution.id,
            evidence_type=evidence_type,
            producer_type="verifier",
            status=status,
            model_version_id=None,
            prompt_version_id=None,
            verifier_version_id=verifier_version_id,
            is_blocking=True,
            summary=summary,
            payload_json=payload,
            evidence_hash=evidence_hash,
        )
        session.add(evidence)
        session.flush()
        return evidence

    @staticmethod
    def _symbolic_summary(report: QuadraticVerificationReport) -> str:
        status = QuadraticVerificationRepository._group_status(
            report, {"solve", "substitution", "root_count", "step_equivalence"}
        )
        return {
            "passed": "SymPy 求解、候选根代回、根数量和可解析步骤均通过。",
            "failed": "SymPy 发现错根、漏根、增根或非等价解题步骤。",
            "inconclusive": "SymPy 只完成部分符号校验，证据不足以通过。",
        }[status]

    @staticmethod
    def _constraint_summary(report: QuadraticVerificationReport) -> str:
        status = QuadraticVerificationRepository._group_status(report, {"domain", "boundary"})
        return {
            "passed": "实数定义域、二次项非退化和分母边界均通过。",
            "failed": "定义域或边界条件存在确定性冲突。",
            "inconclusive": "定义域或边界条件超出当前确定性覆盖范围。",
        }[status]

    @staticmethod
    def _hash_json(payload: dict) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _solution_to_domain(entity: KnowledgeSolution) -> DomainKnowledgeSolution:
        return DomainKnowledgeSolution(
            id=entity.id,
            problem_id=entity.problem_id,
            source_reference_id=entity.source_reference_id,
            method_name=entity.method_name,
            solution_text=entity.solution_text,
            final_answer=entity.final_answer,
            content_hash=entity.content_hash,
            review_status=entity.review_status,
            verification_status=entity.verification_status,
            steps=entity.steps_json,
            key_breakthroughs=entity.key_breakthroughs_json,
            verification_coverage=entity.verification_coverage_json,
            is_preferred=entity.is_preferred,
            language=entity.language,
            metadata=entity.metadata_json,
        )

    @staticmethod
    def _evidence_to_domain(entity: AdmissionEvidence) -> DomainAdmissionEvidence:
        return DomainAdmissionEvidence(
            id=entity.id,
            generation_batch_id=entity.generation_batch_id,
            problem_id=entity.problem_id,
            solution_id=entity.solution_id,
            evidence_type=entity.evidence_type,
            producer_type=EvidenceProducerType(entity.producer_type),
            status=AdmissionEvidenceStatus(entity.status),
            model_version_id=entity.model_version_id,
            prompt_version_id=entity.prompt_version_id,
            verifier_version_id=entity.verifier_version_id,
            is_blocking=entity.is_blocking,
            summary=entity.summary,
            payload=entity.payload_json,
            evidence_hash=entity.evidence_hash,
            created_at=entity.created_at,
        )
