from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.evaluation_leakage import (
    EvaluationLeakageContext,
    EvaluationLeakageReport,
    LeakageCandidateSnapshot,
)
from app.domain.generation import (
    AdmissionEvidence as DomainAdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)
from app.evaluation.leakage import EvaluationDatasetSignatureLoader
from app.models.generation import AdmissionEvidence, VerifierVersion
from app.models.knowledge import KnowledgeProblem


class EvaluationLeakageReferenceInvalid(ValueError):
    pass


class EvaluationLeakageVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluationLeakageDetectorContext:
    leakage_context: EvaluationLeakageContext
    verifier_version_id: str
    verifier_key: str
    verifier_version: str


class EvaluationLeakageRepository:
    """Keep evaluation content on disk and persist only irreversible match evidence."""

    def __init__(
        self,
        dataset_loader: EvaluationDatasetSignatureLoader | None = None,
    ) -> None:
        self.dataset_loader = dataset_loader or EvaluationDatasetSignatureLoader()

    def load_detector_context(
        self,
        session: Session,
        *,
        problem_id: str,
        verifier_version_id: str,
    ) -> EvaluationLeakageDetectorContext:
        problem = session.get(KnowledgeProblem, problem_id)
        if problem is None:
            raise EvaluationLeakageReferenceInvalid("candidate problem not found")
        verifier = self._require_verifier(
            session, verifier_version_id, problem.problem_type
        )
        self._require_scope(problem)
        return EvaluationLeakageDetectorContext(
            leakage_context=self._build_context(problem),
            verifier_version_id=verifier.id,
            verifier_key=verifier.verifier_key,
            verifier_version=verifier.version,
        )

    def persist_report(
        self,
        session: Session,
        *,
        context: EvaluationLeakageDetectorContext,
        report: EvaluationLeakageReport,
    ) -> DomainAdmissionEvidence:
        problem = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == context.leakage_context.candidate.problem_id)
            .with_for_update()
        )
        if problem is None:
            raise EvaluationLeakageReferenceInvalid("candidate problem not found")
        self._require_verifier(
            session, context.verifier_version_id, problem.problem_type
        )
        self._require_scope(problem)
        current = self._build_context(problem)
        if current.fingerprint() != context.leakage_context.fingerprint():
            raise EvaluationLeakageVersionConflict(
                "candidate or frozen evaluation dataset changed during leakage detection"
            )
        if (
            report.problem_id != problem.id
            or report.context_fingerprint != current.fingerprint()
        ):
            raise EvaluationLeakageReferenceInvalid("leakage report context mismatch")

        payload = {
            "schema_version": report.schema_version,
            "problem_content_hash": problem.content_hash,
            "problem_status_version": problem.status_version,
            "context_fingerprint": report.context_fingerprint,
            "dataset_name": report.dataset_name,
            "dataset_sha256": report.dataset_sha256,
            "source_commit": report.source_commit,
            "checked_case_count": report.checked_case_count,
            "matches": [item.model_dump(mode="json") for item in report.matches],
            "thresholds": report.thresholds,
            "limitations": report.limitations,
            "confidence": report.confidence,
            "evaluation_problem_text_persisted": False,
            "reference_answer_in_detection_context": False,
            "reference_solution_in_detection_context": False,
            "verifier_version_id": context.verifier_version_id,
            "verifier_key": context.verifier_key,
            "verifier_version": context.verifier_version,
        }
        evidence_hash = self._hash_json(payload)
        evidence = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "evaluation_leakage_detection",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if evidence is None:
            evidence = AdmissionEvidence(
                generation_batch_id=problem.generation_batch_id,
                problem_id=problem.id,
                solution_id=None,
                evidence_type="evaluation_leakage_detection",
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

    def _build_context(self, problem: KnowledgeProblem) -> EvaluationLeakageContext:
        return EvaluationLeakageContext(
            candidate=LeakageCandidateSnapshot(
                problem_id=problem.id,
                generation_batch_id=problem.generation_batch_id,
                content_hash=problem.content_hash,
                status_version=problem.status_version,
                content_status=problem.content_status,
                statement=problem.statement,
                normalized_statement=problem.normalized_statement,
                explicit_conditions=problem.explicit_conditions_json,
                implicit_conditions=problem.implicit_conditions_json,
            ),
            dataset=self.dataset_loader.load(),
        )

    @staticmethod
    def _require_scope(problem: KnowledgeProblem) -> None:
        if problem.generation_batch_id is None:
            raise EvaluationLeakageReferenceInvalid("generated candidate batch is required")
        if problem.content_status not in {"candidate", "validating", "revision_required"}:
            raise EvaluationLeakageReferenceInvalid(
                "leakage detector only accepts pre-admission content"
            )
        if not problem.statement.strip():
            raise EvaluationLeakageReferenceInvalid("candidate statement is required")

    @staticmethod
    def _require_verifier(
        session: Session,
        verifier_version_id: str,
        problem_type: str,
    ) -> VerifierVersion:
        verifier = session.get(VerifierVersion, verifier_version_id)
        if (
            verifier is None
            or not verifier.active
            or verifier.verifier_key != "evaluation_leakage"
            or (
                verifier.supported_problem_types_json
                and problem_type not in verifier.supported_problem_types_json
            )
        ):
            raise EvaluationLeakageReferenceInvalid(
                "active evaluation_leakage verifier version is required"
            )
        return verifier

    @staticmethod
    def _summary(report: EvaluationLeakageReport) -> str:
        if report.status.value == "passed":
            return (
                f"已对冻结评估集 {report.dataset_name} 的 "
                f"{report.checked_case_count} 道题执行泄漏检查，未发现命中。"
            )
        if report.status.value == "failed":
            return f"候选题命中 {len(report.matches)} 道冻结评估题，阻止生产准入。"
        return "冻结评估集缺失、损坏或版本不一致，泄漏检查无法形成结论。"

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
