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
from app.domain.numeric_verification import NumericVerificationReport
from app.domain.quadratic_verification import QuadraticVerificationContext
from app.models.generation import AdmissionEvidence, VerifierVersion
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution


class NumericVerificationReferenceInvalid(ValueError):
    pass


class NumericVerificationVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class NumericVerifierContext:
    verification_context: QuadraticVerificationContext
    verifier_version_id: str
    verifier_key: str
    verifier_version: str


class NumericVerificationRepository:
    """Persist numeric evidence without reading or replacing SymPy evidence."""

    def load_verifier_context(
        self,
        session: Session,
        *,
        problem_id: str,
        solution_id: str,
        verifier_version_id: str,
    ) -> NumericVerifierContext:
        verifier = self._require_verifier(session, verifier_version_id)
        problem = session.get(KnowledgeProblem, problem_id)
        solution = session.get(KnowledgeSolution, solution_id)
        if problem is None or solution is None or solution.problem_id != problem.id:
            raise NumericVerificationReferenceInvalid("problem or matching solution not found")
        self._require_scope(problem, solution)
        self._require_independent_solution(session, problem, solution)
        return NumericVerifierContext(
            verification_context=self._build_context(problem, solution),
            verifier_version_id=verifier.id,
            verifier_key=verifier.verifier_key,
            verifier_version=verifier.version,
        )

    def persist_report(
        self,
        session: Session,
        *,
        context: NumericVerifierContext,
        report: NumericVerificationReport,
    ) -> DomainAdmissionEvidence:
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
            raise NumericVerificationReferenceInvalid("problem or matching solution not found")
        self._require_scope(problem, solution)
        current = self._build_context(problem, solution)
        expected = context.verification_context
        if (
            current.problem_content_hash != expected.problem_content_hash
            or current.solution_content_hash != expected.solution_content_hash
            or current.status_version != expected.status_version
            or current.fingerprint() != expected.fingerprint()
        ):
            raise NumericVerificationVersionConflict(
                "problem or solution changed while numeric verification was running"
            )
        if (
            report.problem_id != problem.id
            or report.solution_id != solution.id
            or report.context_fingerprint != current.fingerprint()
        ):
            raise NumericVerificationReferenceInvalid("numeric report context mismatch")

        payload = {
            "schema_version": report.schema_version,
            "problem_content_hash": problem.content_hash,
            "problem_status_version": problem.status_version,
            "solution_content_hash": solution.content_hash,
            "context_fingerprint": report.context_fingerprint,
            "mode": report.mode,
            "equation": report.equation,
            "variable": report.variable,
            "independently_computed_roots": report.independently_computed_roots,
            "claimed_roots": report.claimed_roots,
            "sample_count": report.sample_count,
            "tolerance": report.tolerance,
            "relative_tolerance": report.relative_tolerance,
            "precision": report.precision,
            "sample_points": report.sample_points,
            "checks": [item.model_dump(mode="json") for item in report.checks],
            "limitations": report.limitations,
            "confidence": report.confidence,
            "sympy_result_read": False,
            "verifier_version_id": context.verifier_version_id,
            "verifier_key": context.verifier_key,
            "verifier_version": context.verifier_version,
        }
        evidence_hash = self._hash_json(payload)
        evidence = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "numeric_verification",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if evidence is None:
            evidence = AdmissionEvidence(
                generation_batch_id=problem.generation_batch_id,
                problem_id=problem.id,
                solution_id=solution.id,
                evidence_type="numeric_verification",
                producer_type="verifier",
                status=report.status.value,
                model_version_id=None,
                prompt_version_id=None,
                verifier_version_id=context.verifier_version_id,
                is_blocking=True,
                summary=self._summary(report),
                payload_json=payload,
                evidence_hash=evidence_hash,
            )
            session.add(evidence)
            session.flush()
        return self._evidence_to_domain(evidence)

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
            raise NumericVerificationReferenceInvalid("generated candidate batch is required")
        if problem.problem_type != "quadratic_equation":
            raise NumericVerificationReferenceInvalid(
                "numeric verifier only accepts quadratic_equation"
            )
        if problem.content_status not in {"candidate", "validating", "revision_required"}:
            raise NumericVerificationReferenceInvalid(
                "numeric verifier only accepts pre-admission content"
            )
        if not problem.target_json or not problem.explicit_conditions_json:
            raise NumericVerificationReferenceInvalid(
                "structured target and explicit conditions are required"
            )
        if not solution.final_answer:
            raise NumericVerificationReferenceInvalid("solution final_answer is required")
        if (solution.metadata_json or {}).get("content_origin") != "independent_solving_agent":
            raise NumericVerificationReferenceInvalid(
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
            or NumericVerificationRepository._predates_revalidation(
                problem, evidence
            )
        ):
            raise NumericVerificationReferenceInvalid(
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
            or verifier.verifier_key != "quadratic_numeric"
            or (
                verifier.supported_problem_types_json
                and "quadratic_equation" not in verifier.supported_problem_types_json
            )
        ):
            raise NumericVerificationReferenceInvalid(
                "active quadratic_numeric verifier version is required"
            )
        return verifier

    @staticmethod
    def _summary(report: NumericVerificationReport) -> str:
        if report.status.value == "passed":
            return (
                "有限整数定义域穷举与候选答案一致。"
                if report.mode == "exhaustive_integer"
                else "Decimal 系数重建、固定点抽样、独立根计算和数值代回均通过。"
            )
        if report.status.value == "failed":
            return "独立数值验证发现系数、采样值、根集合或代回结果冲突。"
        return "独立数值验证未获得足够证据，不能用于自动准入。"

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
