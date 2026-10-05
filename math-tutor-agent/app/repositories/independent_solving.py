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
from app.domain.independent_solving import (
    IndependentSolutionDraft,
    IndependentSolverContext,
)
from app.domain.knowledge import KnowledgeSolution as DomainKnowledgeSolution
from app.models.generation import AdmissionEvidence, ModelVersion, PromptVersion
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution
from app.repositories.teaching_content import TeachingContentRepository


class IndependentSolvingReferenceInvalid(ValueError):
    pass


class IndependentSolvingVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class IndependentSolvingAgentContext:
    solver_context: IndependentSolverContext
    generation_batch_id: str
    source_reference_id: str
    input_fingerprint: str
    model_version_id: str
    prompt_version_id: str
    model_name: str
    versioned_prompt: str


@dataclass(frozen=True)
class PersistedIndependentSolution:
    solution: DomainKnowledgeSolution
    evidence: DomainAdmissionEvidence
    created: bool


class IndependentSolvingRepository:
    """Enforce context isolation and persist an unverified independent solution."""

    def load_agent_context(
        self,
        session: Session,
        *,
        problem_id: str,
        model_version_id: str,
        prompt_version_id: str,
    ) -> IndependentSolvingAgentContext:
        model, prompt = self._require_versions(
            session, model_version_id, prompt_version_id
        )
        problem = session.get(KnowledgeProblem, problem_id)
        if problem is None:
            raise IndependentSolvingReferenceInvalid("candidate problem not found")
        self._require_problem_scope(problem)
        self._require_passed_condition_check(session, problem)
        context = IndependentSolverContext(
            problem_id=problem.id,
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
            language=problem.language,
            explicit_conditions=problem.explicit_conditions_json,
            implicit_conditions=problem.implicit_conditions_json,
            target=problem.target_json,
            knowledge_point_codes=problem.knowledge_point_codes_json,
        )
        return IndependentSolvingAgentContext(
            solver_context=context,
            generation_batch_id=problem.generation_batch_id,
            source_reference_id=problem.source_reference_id,
            input_fingerprint=context.fingerprint(),
            model_version_id=model.id,
            prompt_version_id=prompt.id,
            model_name=model.model_name,
            versioned_prompt=prompt.template_text,
        )

    def persist_solution(
        self,
        session: Session,
        *,
        context: IndependentSolvingAgentContext,
        draft: IndependentSolutionDraft,
    ) -> PersistedIndependentSolution:
        self._require_versions(
            session,
            context.model_version_id,
            context.prompt_version_id,
        )
        problem = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == context.solver_context.problem_id)
            .with_for_update()
        )
        if problem is None:
            raise IndependentSolvingReferenceInvalid("candidate problem not found")
        self._require_problem_scope(problem)
        if (
            problem.content_hash != context.solver_context.content_hash
            or problem.status_version != context.solver_context.status_version
        ):
            raise IndependentSolvingVersionConflict(
                "candidate changed while the independent solver was running"
            )
        if (
            problem.generation_batch_id != context.generation_batch_id
            or problem.source_reference_id != context.source_reference_id
        ):
            raise IndependentSolvingReferenceInvalid(
                "candidate provenance changed while solving"
            )
        self._require_passed_condition_check(session, problem)
        if context.input_fingerprint != context.solver_context.fingerprint():
            raise IndependentSolvingReferenceInvalid(
                "independent solver input fingerprint is invalid"
            )
        if draft.answer_type != problem.answer_type:
            raise IndependentSolvingReferenceInvalid("solution answer type changed")

        content_hash = self._solution_hash(draft)
        existing = session.scalar(select(KnowledgeSolution).where(
            KnowledgeSolution.problem_id == problem.id,
            KnowledgeSolution.content_hash == content_hash,
        ))
        created = existing is None
        if existing is None:
            existing = KnowledgeSolution(
                problem_id=problem.id,
                source_reference_id=problem.source_reference_id,
                method_name=draft.method_name,
                solution_text=draft.solution_text,
                final_answer=draft.final_answer,
                content_hash=content_hash,
                review_status="unreviewed",
                verification_status="unverified",
                steps_json=[item.model_dump(mode="json") for item in draft.steps],
                key_breakthroughs_json=[
                    item.model_dump(mode="json") for item in draft.key_breakthroughs
                ],
                verification_coverage_json={
                    "level": "none",
                    "covered_step_ids": [],
                    "uncovered_step_ids": [],
                    "checks": [],
                    "limitations": ["等待独立确定性数学验证"],
                    "confidence": 0,
                },
                is_preferred=False,
                language=problem.language,
                metadata_json={
                    "content_origin": "independent_solving_agent",
                    "problem_content_hash": problem.content_hash,
                    "solver_input_fingerprint": context.input_fingerprint,
                    "model_version_id": context.model_version_id,
                    "prompt_version_id": context.prompt_version_id,
                    "generation_context_read": False,
                    "mother_problem_read": False,
                    "existing_solution_read": False,
                    "verification_result_read": False,
                    "requires_external_verification": True,
                    "solver_confidence": draft.confidence,
                    "assumptions_used": draft.assumptions_used,
                },
            )
            session.add(existing)
            session.flush()
        elif (
            existing.verification_status != "unverified"
            or existing.metadata_json.get("solver_input_fingerprint")
            != context.input_fingerprint
        ):
            if not (problem.metadata_json or {}).get(
                "revalidation_started_status_version"
            ):
                raise IndependentSolvingReferenceInvalid(
                    "matching solution hash exists with incompatible isolation state"
                )
            existing.review_status = "unreviewed"
            existing.verification_status = "unverified"
            existing.verification_coverage_json = {
                "level": "none",
                "covered_step_ids": [],
                "uncovered_step_ids": [],
                "checks": [],
                "limitations": ["题目收到内容问题报告，等待本轮重新验证"],
                "confidence": 0,
            }
            metadata = dict(existing.metadata_json or {})
            metadata.update({
                "solver_input_fingerprint": context.input_fingerprint,
                "revalidation_status_version": problem.status_version,
                "requires_external_verification": True,
            })
            existing.metadata_json = metadata

        TeachingContentRepository.sync_solution_steps(session, existing)

        evidence = self._get_or_create_independence_evidence(
            session,
            problem=problem,
            solution=existing,
            context=context,
        )
        return PersistedIndependentSolution(
            solution=self._solution_to_domain(existing),
            evidence=self._evidence_to_domain(evidence),
            created=created,
        )

    @staticmethod
    def _require_problem_scope(problem: KnowledgeProblem) -> None:
        if problem.generation_batch_id is None:
            raise IndependentSolvingReferenceInvalid(
                "independent solver requires a generated candidate"
            )
        if problem.grade_band is None or problem.target_json is None:
            raise IndependentSolvingReferenceInvalid(
                "candidate requires grade band and structured target"
            )
        if not problem.explicit_conditions_json:
            raise IndependentSolvingReferenceInvalid(
                "candidate requires explicit conditions"
            )
        if problem.content_status not in {
            "candidate",
            "validating",
            "revision_required",
        }:
            raise IndependentSolvingReferenceInvalid(
                "independent solver only accepts pre-admission content"
            )

    @staticmethod
    def _require_passed_condition_check(
        session: Session,
        problem: KnowledgeProblem,
    ) -> AdmissionEvidence:
        evidence = session.scalar(
            select(AdmissionEvidence)
            .where(
                AdmissionEvidence.problem_id == problem.id,
                AdmissionEvidence.evidence_type == "condition_completeness",
            )
            .order_by(AdmissionEvidence.created_at.desc(), AdmissionEvidence.id.desc())
            .limit(1)
        )
        if evidence is None or evidence.status != "passed":
            raise IndependentSolvingReferenceInvalid(
                "latest condition completeness evidence must be passed"
            )
        payload_hash = evidence.payload_json.get("problem_content_hash")
        if payload_hash != problem.content_hash:
            raise IndependentSolvingReferenceInvalid(
                "condition completeness evidence is stale"
            )
        revalidation_version = (problem.metadata_json or {}).get(
            "revalidation_started_status_version"
        )
        evidence_version = evidence.payload_json.get("problem_status_version")
        if revalidation_version and (
            not isinstance(evidence_version, int)
            or evidence_version < int(revalidation_version)
        ):
            raise IndependentSolvingReferenceInvalid(
                "condition completeness evidence predates current revalidation"
            )
        return evidence

    def _get_or_create_independence_evidence(
        self,
        session: Session,
        *,
        problem: KnowledgeProblem,
        solution: KnowledgeSolution,
        context: IndependentSolvingAgentContext,
    ) -> AdmissionEvidence:
        payload = {
            "solution_id": solution.id,
            "solution_content_hash": solution.content_hash,
            "problem_content_hash": problem.content_hash,
            "problem_status_version": problem.status_version,
            "solver_input_fingerprint": context.input_fingerprint,
            "allowed_context_fields": sorted(
                context.solver_context.model_dump(mode="json").keys()
            ),
            "excluded_context_classes": [
                "generation_agent_output",
                "generation_prompt",
                "mother_problem",
                "knowledge_solution",
                "admission_evidence",
                "verifier_result",
            ],
            "solver_model_version_id": context.model_version_id,
            "solver_prompt_version_id": context.prompt_version_id,
            "correctness_verified": False,
        }
        evidence_hash = self._hash_json(payload)
        existing = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "solution_independence",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if existing is not None:
            return existing
        evidence = AdmissionEvidence(
            generation_batch_id=problem.generation_batch_id,
            problem_id=problem.id,
            solution_id=solution.id,
            evidence_type="solution_independence",
            producer_type="system",
            status="passed",
            model_version_id=None,
            prompt_version_id=None,
            verifier_version_id=None,
            is_blocking=True,
            summary=(
                "独立解题只读取题干、结构化条件、目标和知识点；"
                "未读取生成答案、母题题解、既有题解或验证结果。"
            ),
            payload_json=payload,
            evidence_hash=evidence_hash,
        )
        session.add(evidence)
        session.flush()
        return evidence

    @staticmethod
    def _require_versions(
        session: Session,
        model_version_id: str,
        prompt_version_id: str,
    ) -> tuple[ModelVersion, PromptVersion]:
        model = session.get(ModelVersion, model_version_id)
        prompt = session.get(PromptVersion, prompt_version_id)
        if model is None or not model.active:
            raise IndependentSolvingReferenceInvalid(
                "active independent solving model version not found"
            )
        if (
            prompt is None
            or not prompt.active
            or prompt.purpose != "independent_problem_solving"
            or prompt.output_schema_version != "1.0"
        ):
            raise IndependentSolvingReferenceInvalid(
                "active independent_problem_solving prompt version 1.0 not found"
            )
        return model, prompt

    @staticmethod
    def _solution_hash(draft: IndependentSolutionDraft) -> str:
        return IndependentSolvingRepository._hash_json({
            "method_name": draft.method_name,
            "solution_text": draft.solution_text,
            "final_answer": draft.final_answer,
            "answer_type": draft.answer_type,
            "steps": [item.model_dump(mode="json") for item in draft.steps],
            "key_breakthroughs": [
                item.model_dump(mode="json") for item in draft.key_breakthroughs
            ],
            "assumptions_used": draft.assumptions_used,
        })

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
