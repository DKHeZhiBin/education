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
from app.domain.problem_condition_check import (
    ProblemConditionCheckContext,
    ProblemConditionCheckReport,
)
from app.models.generation import AdmissionEvidence, ModelVersion, PromptVersion
from app.models.knowledge import KnowledgeProblem


class ProblemConditionCheckReferenceInvalid(ValueError):
    pass


class ProblemConditionCheckVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ProblemConditionCheckAgentContext:
    check_context: ProblemConditionCheckContext
    model_version_id: str
    prompt_version_id: str
    model_name: str
    versioned_prompt: str


class ProblemConditionCheckRepository:
    """Load solution-free candidates and append condition check evidence."""

    def load_agent_context(
        self,
        session: Session,
        *,
        problem_id: str,
        model_version_id: str,
        prompt_version_id: str,
    ) -> ProblemConditionCheckAgentContext:
        model, prompt = self._require_versions(
            session, model_version_id, prompt_version_id
        )
        problem = session.get(KnowledgeProblem, problem_id)
        if problem is None:
            raise ProblemConditionCheckReferenceInvalid("candidate problem not found")
        if problem.generation_batch_id is None:
            raise ProblemConditionCheckReferenceInvalid(
                "condition checker requires a generation batch"
            )
        if problem.grade_band is None:
            raise ProblemConditionCheckReferenceInvalid("candidate grade band is missing")
        if problem.mother_problem_id is None:
            if not bool((problem.metadata_json or {}).get("trusted_mother")):
                raise ProblemConditionCheckReferenceInvalid(
                    "condition checker requires a generated problem or trusted mother"
                )
            mother = problem
        else:
            mother = session.get(KnowledgeProblem, problem.mother_problem_id)
            if mother is None:
                raise ProblemConditionCheckReferenceInvalid("mother problem not found")
            if (
                not bool((mother.metadata_json or {}).get("trusted_mother"))
                or mother.content_status not in {"approved", "indexed"}
            ):
                raise ProblemConditionCheckReferenceInvalid(
                    "mother problem is no longer trusted and admitted"
                )
        context = ProblemConditionCheckContext(
            problem_id=problem.id,
            generation_batch_id=problem.generation_batch_id,
            content_hash=problem.content_hash,
            status_version=problem.status_version,
            content_status=problem.content_status,
            statement=problem.statement,
            normalized_statement=problem.normalized_statement,
            subject=problem.subject,
            grade_band=problem.grade_band,
            problem_type=problem.problem_type,
            difficulty=problem.difficulty,
            answer_type=problem.answer_type,
            explicit_conditions=problem.explicit_conditions_json,
            implicit_conditions=problem.implicit_conditions_json,
            target=problem.target_json,
            knowledge_point_codes=problem.knowledge_point_codes_json,
            mother_problem_id=mother.id,
            mother_grade_band=mother.grade_band,
            mother_problem_type=mother.problem_type,
            mother_knowledge_point_codes=mother.knowledge_point_codes_json,
        )
        return ProblemConditionCheckAgentContext(
            check_context=context,
            model_version_id=model.id,
            prompt_version_id=prompt.id,
            model_name=model.model_name,
            versioned_prompt=prompt.template_text,
        )

    def persist_report(
        self,
        session: Session,
        *,
        context: ProblemConditionCheckAgentContext,
        report: ProblemConditionCheckReport,
    ) -> DomainAdmissionEvidence:
        if report.problem_id != context.check_context.problem_id:
            raise ProblemConditionCheckReferenceInvalid(
                "condition report belongs to another problem"
            )
        self._require_versions(
            session,
            context.model_version_id,
            context.prompt_version_id,
        )
        problem = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == report.problem_id)
            .with_for_update()
        )
        if problem is None:
            raise ProblemConditionCheckReferenceInvalid("candidate problem not found")
        if (
            problem.content_hash != context.check_context.content_hash
            or problem.status_version != context.check_context.status_version
        ):
            raise ProblemConditionCheckVersionConflict(
                "candidate changed while the condition check was running"
            )
        if problem.generation_batch_id != context.check_context.generation_batch_id:
            raise ProblemConditionCheckReferenceInvalid("generation batch changed")
        if problem.content_status not in {
            "candidate",
            "validating",
            "revision_required",
        }:
            raise ProblemConditionCheckReferenceInvalid(
                "condition evidence cannot be added to admitted or retired content"
            )

        payload = {
            "problem_content_hash": problem.content_hash,
            "problem_status_version": problem.status_version,
            "report": report.model_dump(mode="json"),
            "deterministic_solution_count_verification_pending": True,
        }
        evidence_hash = self._hash_payload(payload)
        existing = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "condition_completeness",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if existing is not None:
            return self._to_domain(existing)

        evidence = AdmissionEvidence(
            generation_batch_id=problem.generation_batch_id,
            problem_id=problem.id,
            solution_id=None,
            evidence_type="condition_completeness",
            producer_type="model",
            status=report.overall_status.value,
            model_version_id=context.model_version_id,
            prompt_version_id=context.prompt_version_id,
            verifier_version_id=None,
            is_blocking=True,
            summary=report.summary,
            payload_json=payload,
            evidence_hash=evidence_hash,
        )
        session.add(evidence)
        session.flush()
        return self._to_domain(evidence)

    @staticmethod
    def _require_versions(
        session: Session,
        model_version_id: str,
        prompt_version_id: str,
    ) -> tuple[ModelVersion, PromptVersion]:
        model = session.get(ModelVersion, model_version_id)
        prompt = session.get(PromptVersion, prompt_version_id)
        if model is None or not model.active:
            raise ProblemConditionCheckReferenceInvalid(
                "active condition check model version not found"
            )
        if (
            prompt is None
            or not prompt.active
            or prompt.purpose != "problem_condition_check"
            or prompt.output_schema_version != "1.0"
        ):
            raise ProblemConditionCheckReferenceInvalid(
                "active problem_condition_check prompt version 1.0 not found"
            )
        return model, prompt

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_domain(entity: AdmissionEvidence) -> DomainAdmissionEvidence:
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
