from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.duplicate_detection import (
    DuplicateDetectionContext,
    DuplicateDetectionReport,
    DuplicateProblemSnapshot,
)
from app.domain.generation import (
    AdmissionEvidence as DomainAdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)
from app.models.generation import AdmissionEvidence, VerifierVersion
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution


class DuplicateDetectionReferenceInvalid(ValueError):
    pass


class DuplicateDetectionVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class DuplicateDetectorContext:
    detection_context: DuplicateDetectionContext
    verifier_version_id: str
    verifier_key: str
    verifier_version: str


class DuplicateDetectionRepository:
    """Build a bounded comparison pool and persist four-layer duplicate evidence."""

    def __init__(self, *, maximum_comparison_problems: int = 2000) -> None:
        if maximum_comparison_problems < 1:
            raise ValueError("maximum_comparison_problems must be positive")
        self.maximum_comparison_problems = maximum_comparison_problems

    def load_detector_context(
        self,
        session: Session,
        *,
        problem_id: str,
        solution_id: str,
        verifier_version_id: str,
    ) -> DuplicateDetectorContext:
        verifier = self._require_verifier(session, verifier_version_id)
        problem = session.get(KnowledgeProblem, problem_id)
        solution = session.get(KnowledgeSolution, solution_id)
        if problem is None or solution is None or solution.problem_id != problem.id:
            raise DuplicateDetectionReferenceInvalid("problem or matching solution not found")
        self._require_verifier(session, verifier_version_id, problem.problem_type)
        self._require_scope(problem, solution)
        self._require_independent_solution(session, problem, solution)
        return DuplicateDetectorContext(
            detection_context=self._build_context(session, problem, solution),
            verifier_version_id=verifier.id,
            verifier_key=verifier.verifier_key,
            verifier_version=verifier.version,
        )

    def persist_report(
        self,
        session: Session,
        *,
        context: DuplicateDetectorContext,
        report: DuplicateDetectionReport,
    ) -> DomainAdmissionEvidence:
        self._require_verifier(session, context.verifier_version_id)
        problem = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == context.detection_context.candidate.problem_id)
            .with_for_update()
        )
        solution = session.scalar(
            select(KnowledgeSolution)
            .where(KnowledgeSolution.id == context.detection_context.candidate.solution_id)
            .with_for_update()
        )
        if problem is None or solution is None or solution.problem_id != problem.id:
            raise DuplicateDetectionReferenceInvalid("problem or matching solution not found")
        self._require_verifier(session, context.verifier_version_id, problem.problem_type)
        self._require_scope(problem, solution)
        current = self._build_context(session, problem, solution)
        if current.fingerprint() != context.detection_context.fingerprint():
            raise DuplicateDetectionVersionConflict(
                "candidate or comparison pool changed while duplicate detection was running"
            )
        if (
            report.problem_id != problem.id
            or report.solution_id != solution.id
            or report.context_fingerprint != current.fingerprint()
        ):
            raise DuplicateDetectionReferenceInvalid("duplicate report context mismatch")

        payload = {
            "schema_version": report.schema_version,
            "problem_content_hash": problem.content_hash,
            "problem_status_version": problem.status_version,
            "solution_content_hash": solution.content_hash,
            "context_fingerprint": report.context_fingerprint,
            "compared_count": report.compared_count,
            "comparison_scope_total": report.comparison_scope_total,
            "comparison_scope_complete": report.comparison_scope_complete,
            "exact_duplicate_count": report.exact_duplicate_count,
            "near_duplicate_count": report.near_duplicate_count,
            "thresholds": report.thresholds,
            "matches": [item.model_dump(mode="json") for item in report.matches],
            "limitations": report.limitations,
            "confidence": report.confidence,
            "verifier_version_id": context.verifier_version_id,
            "verifier_key": context.verifier_key,
            "verifier_version": context.verifier_version,
        }
        evidence_hash = self._hash_json(payload)
        evidence = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "duplicate_detection",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if evidence is None:
            evidence = AdmissionEvidence(
                generation_batch_id=problem.generation_batch_id,
                problem_id=problem.id,
                solution_id=solution.id,
                evidence_type="duplicate_detection",
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

    def _build_context(
        self,
        session: Session,
        problem: KnowledgeProblem,
        solution: KnowledgeSolution,
    ) -> DuplicateDetectionContext:
        filters = (
            KnowledgeProblem.id != problem.id,
            KnowledgeProblem.subject == problem.subject,
            KnowledgeProblem.problem_type == problem.problem_type,
            KnowledgeProblem.content_status != "retired",
        )
        total = session.scalar(
            select(func.count(KnowledgeProblem.id)).where(*filters)
        ) or 0
        reference_entities = list(session.scalars(
            select(KnowledgeProblem)
            .options(selectinload(KnowledgeProblem.solutions))
            .where(*filters)
            .order_by(KnowledgeProblem.id)
            .limit(self.maximum_comparison_problems)
        ).unique())
        references = [
            self._snapshot(entity, self._best_solution(entity.solutions))
            for entity in reference_entities
        ]
        return DuplicateDetectionContext(
            candidate=self._snapshot(problem, solution),
            references=references,
            comparison_scope_total=total,
            comparison_scope_complete=total <= self.maximum_comparison_problems,
        )

    @staticmethod
    def _snapshot(
        problem: KnowledgeProblem,
        solution: KnowledgeSolution | None,
    ) -> DuplicateProblemSnapshot:
        return DuplicateProblemSnapshot(
            problem_id=problem.id,
            content_hash=problem.content_hash,
            statement=problem.statement,
            normalized_statement=problem.normalized_statement,
            subject=problem.subject,
            grade_band=problem.grade_band,
            problem_type=problem.problem_type,
            content_status=problem.content_status,
            status_version=problem.status_version,
            generation_batch_id=problem.generation_batch_id,
            mother_problem_id=problem.mother_problem_id,
            explicit_conditions=problem.explicit_conditions_json,
            implicit_conditions=problem.implicit_conditions_json,
            target=problem.target_json or {},
            knowledge_point_codes=problem.knowledge_point_codes_json,
            solution_id=solution.id if solution else None,
            solution_content_hash=solution.content_hash if solution else None,
            solution_method_name=solution.method_name if solution else None,
            solution_steps=solution.steps_json if solution else [],
        )

    @staticmethod
    def _best_solution(
        solutions: list[KnowledgeSolution],
    ) -> KnowledgeSolution | None:
        if not solutions:
            return None
        verification_rank = {"verified": 3, "partial": 2, "unverified": 1, "failed": 0}
        review_rank = {"approved": 2, "pending": 1, "unreviewed": 0, "rejected": -1}
        return max(solutions, key=lambda item: (
            verification_rank.get(item.verification_status, -1),
            review_rank.get(item.review_status, -1),
            int(bool(item.is_preferred)),
            item.updated_at,
            item.id,
        ))

    @staticmethod
    def _require_scope(problem: KnowledgeProblem, solution: KnowledgeSolution) -> None:
        if problem.generation_batch_id is None:
            raise DuplicateDetectionReferenceInvalid("generated candidate batch is required")
        if problem.content_status not in {"candidate", "validating", "revision_required"}:
            raise DuplicateDetectionReferenceInvalid(
                "duplicate detector only accepts pre-admission content"
            )
        if not problem.target_json or not (
            problem.explicit_conditions_json or problem.implicit_conditions_json
        ):
            raise DuplicateDetectionReferenceInvalid(
                "structured conditions and target are required"
            )
        if not solution.steps_json:
            raise DuplicateDetectionReferenceInvalid(
                "four-layer detection requires a structured solution"
            )
        if (solution.metadata_json or {}).get("content_origin") != "independent_solving_agent":
            raise DuplicateDetectionReferenceInvalid(
                "only an independently generated solution may be compared"
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
            or DuplicateDetectionRepository._predates_revalidation(
                problem, evidence
            )
        ):
            raise DuplicateDetectionReferenceInvalid(
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
    def _require_verifier(
        session: Session,
        verifier_version_id: str,
        problem_type: str | None = None,
    ) -> VerifierVersion:
        verifier = session.get(VerifierVersion, verifier_version_id)
        if (
            verifier is None
            or not verifier.active
            or verifier.verifier_key != "four_layer_duplicate"
            or (
                problem_type is not None
                and verifier.supported_problem_types_json
                and problem_type not in verifier.supported_problem_types_json
            )
        ):
            raise DuplicateDetectionReferenceInvalid(
                "active four_layer_duplicate verifier version is required"
            )
        return verifier

    @staticmethod
    def _summary(report: DuplicateDetectionReport) -> str:
        if report.status.value == "passed":
            return (
                f"已完成 {report.compared_count} 道同题型题目的四层重复检测，"
                "未发现确定重复或近重复。"
            )
        if report.status.value == "failed":
            return (
                f"发现 {report.exact_duplicate_count} 个确定重复和 "
                f"{report.near_duplicate_count} 个近重复，阻止自动准入。"
            )
        return "四层重复检测比较池或结构化输入不完整，不能证明内容唯一。"

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
