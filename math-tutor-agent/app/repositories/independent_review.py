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
from app.domain.independent_review import (
    CandidateAnswerSnapshot,
    IndependentAnswerSnapshot,
    IndependentReviewContext,
    IndependentReviewReport,
    ReviewDecision,
    TeachingLabelsSnapshot,
    ToolEvidenceSnapshot,
)
from app.models.generation import AdmissionEvidence, ModelVersion, PromptVersion
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution


class IndependentReviewReferenceInvalid(ValueError):
    pass


class IndependentReviewVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class IndependentReviewAgentContext:
    review_context: IndependentReviewContext
    model_version_id: str
    prompt_version_id: str
    model_name: str
    versioned_prompt: str


class IndependentReviewRepository:
    """Build a fixed evidence projection and persist a model review audit record."""

    REQUIRED_TOOL_EVIDENCE = (
        "symbolic_verification",
        "numeric_verification",
        "constraint_verification",
    )

    def load_agent_context(
        self,
        session: Session,
        *,
        problem_id: str,
        solution_id: str,
        model_version_id: str,
        prompt_version_id: str,
    ) -> IndependentReviewAgentContext:
        model, prompt = self._require_versions(
            session, model_version_id, prompt_version_id
        )
        problem = session.get(KnowledgeProblem, problem_id)
        solution = session.get(KnowledgeSolution, solution_id)
        if problem is None or solution is None or solution.problem_id != problem.id:
            raise IndependentReviewReferenceInvalid("problem or matching solution not found")
        return IndependentReviewAgentContext(
            review_context=self._build_context(session, problem, solution),
            model_version_id=model.id,
            prompt_version_id=prompt.id,
            model_name=model.model_name,
            versioned_prompt=prompt.template_text,
        )

    def persist_report(
        self,
        session: Session,
        *,
        context: IndependentReviewAgentContext,
        report: IndependentReviewReport,
    ) -> DomainAdmissionEvidence:
        model, prompt = self._require_versions(
            session, context.model_version_id, context.prompt_version_id
        )
        if (
            model.model_name != context.model_name
            or prompt.template_text != context.versioned_prompt
        ):
            raise IndependentReviewVersionConflict(
                "review model or prompt changed during independent review"
            )
        problem = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == context.review_context.problem_id)
            .with_for_update()
        )
        solution = session.scalar(
            select(KnowledgeSolution)
            .where(KnowledgeSolution.id == context.review_context.candidate_answer.solution_id)
            .with_for_update()
        )
        if problem is None or solution is None or solution.problem_id != problem.id:
            raise IndependentReviewReferenceInvalid("problem or matching solution not found")
        current = self._build_context(session, problem, solution)
        if current.fingerprint() != context.review_context.fingerprint():
            raise IndependentReviewVersionConflict(
                "candidate, solution or tool evidence changed during independent review"
            )
        self._validate_report(report, current)

        payload = {
            "schema_version": report.schema_version,
            "problem_content_hash": problem.content_hash,
            "solution_content_hash": solution.content_hash,
            "problem_status_version": problem.status_version,
            "context_fingerprint": report.context_fingerprint,
            "decision": report.decision.value,
            "candidate_answer": report.answer_comparison.candidate_answer,
            "independent_answers": report.answer_comparison.independent_answers,
            "answer_comparison": report.answer_comparison.model_dump(mode="json"),
            "tool_assessments": [
                item.model_dump(mode="json") for item in report.tool_assessments
            ],
            "teaching_assessments": [
                item.model_dump(mode="json") for item in report.teaching_assessments
            ],
            "blocking_issues": report.blocking_issues,
            "strengths": report.strengths,
            "revision_instructions": report.revision_instructions,
            "confidence": report.confidence,
            "source_evidence_ids": [
                item.evidence_id for item in current.tool_evidence
            ],
            "model_version_id": context.model_version_id,
            "prompt_version_id": context.prompt_version_id,
            "deterministic_failures_overridable": False,
        }
        evidence_hash = self._hash_json(payload)
        evidence = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.solution_id == solution.id,
            AdmissionEvidence.evidence_type == "pedagogical_review",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if evidence is None:
            evidence = AdmissionEvidence(
                generation_batch_id=problem.generation_batch_id,
                problem_id=problem.id,
                solution_id=solution.id,
                evidence_type="pedagogical_review",
                producer_type="model",
                status=report.decision.value,
                model_version_id=context.model_version_id,
                prompt_version_id=context.prompt_version_id,
                verifier_version_id=None,
                is_blocking=True,
                summary=self._summary(report),
                payload_json=payload,
                evidence_hash=evidence_hash,
            )
            session.add(evidence)
            session.flush()
        solution.review_status = {
            ReviewDecision.PASSED: "approved",
            ReviewDecision.FAILED: "rejected",
            ReviewDecision.INCONCLUSIVE: "pending",
        }[report.decision]
        session.flush()
        return self._to_domain(evidence)

    def _build_context(
        self,
        session: Session,
        problem: KnowledgeProblem,
        solution: KnowledgeSolution,
    ) -> IndependentReviewContext:
        self._require_scope(problem, solution)
        independence = self._latest_evidence(
            session, problem.id, solution.id, "solution_independence"
        )
        if (
            independence is None
            or independence.status != "passed"
            or independence.payload_json.get("problem_content_hash") != problem.content_hash
            or independence.payload_json.get("solution_content_hash") != solution.content_hash
        ):
            raise IndependentReviewReferenceInvalid(
                "fresh passed solution_independence evidence is required"
            )

        evidence_entities: list[AdmissionEvidence] = []
        for evidence_type in self.REQUIRED_TOOL_EVIDENCE:
            evidence = self._latest_evidence(
                session, problem.id, solution.id, evidence_type
            )
            if evidence is None:
                raise IndependentReviewReferenceInvalid(
                    f"latest {evidence_type} evidence is required"
                )
            self._require_fresh_tool_evidence(evidence, problem, solution)
            evidence_entities.append(evidence)

        independent_answers: list[IndependentAnswerSnapshot] = []
        for evidence in evidence_entities:
            if evidence.evidence_type == "symbolic_verification":
                answer_field = "computed_roots"
            elif evidence.evidence_type == "numeric_verification":
                answer_field = "independently_computed_roots"
            else:
                continue
            answers = evidence.payload_json.get(answer_field)
            if not isinstance(answers, list):
                raise IndependentReviewReferenceInvalid(
                    f"{evidence.evidence_type} has no independent answer set"
                )
            normalized_answers = [str(item) for item in answers if str(item).strip()]
            independent_answers.append(IndependentAnswerSnapshot(
                source_evidence_type=evidence.evidence_type,
                source_evidence_id=evidence.id,
                verifier_version_id=evidence.verifier_version_id,
                answers=normalized_answers,
            ))

        return IndependentReviewContext(
            problem_id=problem.id,
            generation_batch_id=problem.generation_batch_id,
            problem_content_hash=problem.content_hash,
            status_version=problem.status_version,
            content_status=problem.content_status,
            statement=problem.statement,
            candidate_answer=CandidateAnswerSnapshot(
                solution_id=solution.id,
                solution_content_hash=solution.content_hash,
                final_answer=solution.final_answer,
                answer_type=problem.answer_type,
                method_name=solution.method_name,
                solution_text=solution.solution_text,
                steps=solution.steps_json,
                key_breakthroughs=solution.key_breakthroughs_json,
            ),
            independent_answers=independent_answers,
            tool_evidence=[
                ToolEvidenceSnapshot(
                    evidence_id=evidence.id,
                    evidence_type=evidence.evidence_type,
                    status=AdmissionEvidenceStatus(evidence.status),
                    summary=evidence.summary,
                    verifier_version_id=evidence.verifier_version_id,
                    checks=evidence.payload_json.get("checks") or [],
                    limitations=evidence.payload_json.get("limitations") or [],
                )
                for evidence in evidence_entities
            ],
            teaching_labels=TeachingLabelsSnapshot(
                subject=problem.subject,
                grade_band=problem.grade_band,
                problem_type=problem.problem_type,
                difficulty=problem.difficulty,
                answer_type=problem.answer_type,
                knowledge_point_codes=problem.knowledge_point_codes_json,
                difficulty_factors=problem.difficulty_factors_json,
                target=problem.target_json,
            ),
        )

    @staticmethod
    def _require_scope(problem: KnowledgeProblem, solution: KnowledgeSolution) -> None:
        if problem.generation_batch_id is None:
            raise IndependentReviewReferenceInvalid("generated candidate batch is required")
        if problem.content_status not in {"candidate", "validating", "revision_required"}:
            raise IndependentReviewReferenceInvalid(
                "independent review only accepts pre-admission content"
            )
        if problem.grade_band is None or problem.target_json is None:
            raise IndependentReviewReferenceInvalid(
                "grade band and structured target are required"
            )
        if not problem.knowledge_point_codes_json:
            raise IndependentReviewReferenceInvalid("knowledge point labels are required")
        if not solution.final_answer or not solution.steps_json:
            raise IndependentReviewReferenceInvalid(
                "candidate answer and structured solution steps are required"
            )
        if (solution.metadata_json or {}).get("content_origin") != "independent_solving_agent":
            raise IndependentReviewReferenceInvalid(
                "review requires the isolated solver candidate solution"
            )

    @staticmethod
    def _latest_evidence(
        session: Session,
        problem_id: str,
        solution_id: str,
        evidence_type: str,
    ) -> AdmissionEvidence | None:
        return session.scalar(
            select(AdmissionEvidence)
            .where(
                AdmissionEvidence.problem_id == problem_id,
                AdmissionEvidence.solution_id == solution_id,
                AdmissionEvidence.evidence_type == evidence_type,
            )
            .order_by(AdmissionEvidence.created_at.desc(), AdmissionEvidence.id.desc())
            .limit(1)
        )

    @staticmethod
    def _require_fresh_tool_evidence(
        evidence: AdmissionEvidence,
        problem: KnowledgeProblem,
        solution: KnowledgeSolution,
    ) -> None:
        if (
            evidence.producer_type != "verifier"
            or evidence.verifier_version_id is None
            or evidence.payload_json.get("problem_content_hash") != problem.content_hash
            or evidence.payload_json.get("solution_content_hash") != solution.content_hash
            or IndependentReviewRepository._predates_revalidation(problem, evidence)
        ):
            raise IndependentReviewReferenceInvalid(
                f"{evidence.evidence_type} evidence is stale or unversioned"
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
    def _require_versions(
        session: Session,
        model_version_id: str,
        prompt_version_id: str,
    ) -> tuple[ModelVersion, PromptVersion]:
        model = session.get(ModelVersion, model_version_id)
        prompt = session.get(PromptVersion, prompt_version_id)
        if model is None or not model.active:
            raise IndependentReviewReferenceInvalid(
                "active independent review model version not found"
            )
        if (
            prompt is None
            or not prompt.active
            or prompt.purpose != "independent_pedagogical_review"
            or prompt.output_schema_version != "1.0"
        ):
            raise IndependentReviewReferenceInvalid(
                "active independent_pedagogical_review prompt version 1.0 not found"
            )
        return model, prompt

    @staticmethod
    def _validate_report(
        report: IndependentReviewReport,
        context: IndependentReviewContext,
    ) -> None:
        if (
            report.problem_id != context.problem_id
            or report.solution_id != context.candidate_answer.solution_id
            or report.context_fingerprint != context.fingerprint()
            or report.answer_comparison.candidate_answer
            != context.candidate_answer.final_answer
        ):
            raise IndependentReviewReferenceInvalid("review report context mismatch")
        expected_answers = sorted({
            answer for source in context.independent_answers for answer in source.answers
        })
        if sorted(report.answer_comparison.independent_answers) != expected_answers:
            raise IndependentReviewReferenceInvalid("review changed independent answers")
        expected_tools = {
            item.evidence_id: (item.evidence_type, item.status)
            for item in context.tool_evidence
        }
        actual_tools = {
            item.evidence_id: (item.evidence_type, item.observed_status)
            for item in report.tool_assessments
        }
        if actual_tools != expected_tools:
            raise IndependentReviewReferenceInvalid("review changed tool evidence")
        if any(
            item.observed_status == AdmissionEvidenceStatus.FAILED
            and item.assessment.value != "conflict"
            for item in report.tool_assessments
        ):
            raise IndependentReviewReferenceInvalid(
                "failed deterministic evidence must be classified as conflict"
            )
        statuses = {item.status for item in context.tool_evidence}
        if AdmissionEvidenceStatus.FAILED in statuses:
            if report.decision != ReviewDecision.FAILED:
                raise IndependentReviewReferenceInvalid(
                    "failed deterministic evidence cannot be overridden"
                )
        elif statuses - {AdmissionEvidenceStatus.PASSED}:
            if report.decision == ReviewDecision.PASSED:
                raise IndependentReviewReferenceInvalid(
                    "incomplete deterministic evidence cannot be approved"
                )

    @staticmethod
    def _summary(report: IndependentReviewReport) -> str:
        if report.decision == ReviewDecision.PASSED:
            return "候选答案、独立答案、工具证据和教学标签经独立 AI 复核一致。"
        if report.decision == ReviewDecision.FAILED:
            return f"独立 AI 复核发现 {len(report.blocking_issues)} 项阻断问题。"
        return "独立 AI 复核证据不足或存在尚未确认的冲突，不能自动准入。"

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
