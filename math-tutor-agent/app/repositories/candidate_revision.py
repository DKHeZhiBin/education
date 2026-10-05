from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.candidate_revision import (
    MAX_CANDIDATE_REVISION_ATTEMPTS,
    CandidateRevisionContext,
    CandidateRevisionDraft,
    PersistedCandidateRevision,
    RevisionFailureEvidence,
)
from app.domain.generation import AdmissionEvidenceStatus, EvidenceProducerType
from app.domain.question_generation import QuestionGenerationBudget, QuestionGenerationStoredInput
from app.models.generation import (
    AdmissionEvidence,
    ModelVersion,
    PromptVersion,
    QuestionGenerationJob,
)
from app.models.knowledge import KnowledgeProblem


class CandidateRevisionReferenceInvalid(ValueError):
    pass


class CandidateRevisionVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateRevisionAgentContext:
    revision_context: CandidateRevisionContext
    model_version_id: str
    prompt_version_id: str
    model_name: str
    versioned_prompt: str


class CandidateRevisionRepository:
    """Build a failure-bounded revision context and persist a new candidate version."""

    PROMPT_PURPOSE = "candidate_question_revision"
    OUTPUT_SCHEMA_VERSION = "1.0"
    NON_REVISABLE_FAILURES = frozenset({
        "duplicate_detection",
        "evaluation_leakage_detection",
        "source_rights_clearance",
    })

    def load_agent_context(
        self,
        session: Session,
        *,
        problem_id: str,
        model_version_id: str,
        prompt_version_id: str,
    ) -> CandidateRevisionAgentContext:
        problem = session.get(KnowledgeProblem, problem_id)
        if problem is None:
            raise CandidateRevisionReferenceInvalid("candidate problem not found")
        model, prompt = self._require_versions(
            session, model_version_id=model_version_id, prompt_version_id=prompt_version_id
        )
        revision_context = self._build_context(session, problem)
        return CandidateRevisionAgentContext(
            revision_context=revision_context,
            model_version_id=model.id,
            prompt_version_id=prompt.id,
            model_name=model.model_name,
            versioned_prompt=prompt.template_text,
        )

    def persist_revision(
        self,
        session: Session,
        *,
        agent_context: CandidateRevisionAgentContext,
        draft: CandidateRevisionDraft,
    ) -> PersistedCandidateRevision:
        source = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == agent_context.revision_context.problem_id)
            .with_for_update()
        )
        if source is None:
            raise CandidateRevisionReferenceInvalid("candidate problem not found")
        self._require_versions(
            session,
            model_version_id=agent_context.model_version_id,
            prompt_version_id=agent_context.prompt_version_id,
        )
        current = self._build_context(session, source)
        if current.fingerprint() != agent_context.revision_context.fingerprint():
            raise CandidateRevisionVersionConflict(
                "candidate, admission decision, or failure evidence changed before persistence"
            )
        validated = self._validate_draft(draft, current)

        root_problem_id = str(
            source.metadata_json.get("revision_root_problem_id") or source.id
        )
        identity = f"candidate-revision:{root_problem_id}:{current.revision_attempt}"
        content_hash = self._draft_hash(validated)
        if content_hash == source.content_hash:
            raise CandidateRevisionReferenceInvalid(
                "revision content hash must differ from the failed candidate"
            )

        existing = session.scalar(select(KnowledgeProblem).where(
            KnowledgeProblem.generation_batch_id == source.generation_batch_id,
            KnowledgeProblem.external_id == identity,
        ))
        if existing is not None:
            return self._existing_result(
                session,
                source=source,
                existing=existing,
                current=current,
                content_hash=content_hash,
            )

        duplicate = session.scalar(select(KnowledgeProblem).where(
            KnowledgeProblem.source_reference_id == source.source_reference_id,
            KnowledgeProblem.content_hash == content_hash,
        ))
        if duplicate is not None:
            raise CandidateRevisionReferenceInvalid(
                f"revision duplicates existing problem {duplicate.id}"
            )

        question = validated.revised_question
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        metadata = dict(source.metadata_json)
        metadata.update({
            "content_origin": "ai_candidate_revision",
            "revision_root_problem_id": root_problem_id,
            "revised_from_problem_id": source.id,
            "revision_attempt": current.revision_attempt,
            "revision_context_fingerprint": current.fingerprint(),
            "admission_decision_id": current.admission_decision_id,
            "failure_evidence_ids": [item.evidence_id for item in current.failures],
            "model_version_id": agent_context.model_version_id,
            "prompt_version_id": agent_context.prompt_version_id,
            "output_schema_version": self.OUTPUT_SCHEMA_VERSION,
            "requires_full_revalidation": True,
            "inherited_admission_evidence": False,
            "approval_forbidden_at_revision": True,
            "trusted_mother": False,
        })
        revised = KnowledgeProblem(
            source_reference_id=source.source_reference_id,
            curriculum_version_id=source.curriculum_version_id,
            document_id=source.document_id,
            source_chunk_id=source.source_chunk_id,
            mother_problem_id=source.mother_problem_id,
            generation_batch_id=source.generation_batch_id,
            external_id=identity,
            statement=question.statement,
            normalized_statement=question.normalized_statement,
            subject=source.subject,
            grade_band=source.grade_band,
            grade_codes_json=list(source.grade_codes_json),
            problem_type=source.problem_type,
            content_type=source.content_type,
            difficulty=question.difficulty,
            answer_type=source.answer_type,
            language=source.language,
            content_hash=content_hash,
            review_status="unreviewed",
            explicit_conditions_json=[
                item.model_dump(mode="json") for item in question.explicit_conditions
            ],
            implicit_conditions_json=[
                item.model_dump(mode="json") for item in question.implicit_conditions
            ],
            target_json=question.target.model_dump(mode="json"),
            difficulty_factors_json=[
                item.model_dump(mode="json") for item in question.difficulty_factors
            ],
            derivation_type=source.derivation_type,
            derivation_note=question.derivation_note,
            content_status="candidate",
            status_reason=None,
            revision_attempts=current.revision_attempt,
            status_version=1,
            status_changed_at=now,
            knowledge_point_codes_json=list(source.knowledge_point_codes_json),
            metadata_json=metadata,
        )
        session.add(revised)
        session.flush()

        evidence = self._create_revision_evidence(
            session,
            source=source,
            revised=revised,
            current=current,
            draft=validated,
            model_version_id=agent_context.model_version_id,
            prompt_version_id=agent_context.prompt_version_id,
        )
        source_metadata = dict(source.metadata_json)
        source_metadata.update({
            "superseded_by_problem_id": revised.id,
            "revision_generated_at": now.isoformat(),
        })
        source.metadata_json = source_metadata
        session.flush()
        return PersistedCandidateRevision(
            source_problem_id=source.id,
            revised_problem_id=revised.id,
            generation_batch_id=revised.generation_batch_id,
            revision_attempt=current.revision_attempt,
            content_status=revised.content_status,
            content_hash=revised.content_hash,
            revision_evidence_id=evidence.id,
            created=True,
        )

    def _build_context(
        self,
        session: Session,
        problem: KnowledgeProblem,
    ) -> CandidateRevisionContext:
        if problem.generation_batch_id is None or problem.mother_problem_id is None:
            raise CandidateRevisionReferenceInvalid(
                "only generated candidates with a trusted mother can be revised"
            )
        if problem.content_status != "revision_required":
            raise CandidateRevisionReferenceInvalid(
                "candidate revision requires revision_required status"
            )
        job = session.scalar(select(QuestionGenerationJob).where(
            QuestionGenerationJob.generation_batch_id == problem.generation_batch_id
        ))
        if job is None:
            raise CandidateRevisionReferenceInvalid("question generation job not found")
        generation_input = QuestionGenerationStoredInput.model_validate(job.input_json)
        budget = QuestionGenerationBudget.model_validate(job.budget_json)
        maximum = min(
            MAX_CANDIDATE_REVISION_ATTEMPTS,
            settings.knowledge_problem_max_revision_attempts,
            budget.max_revision_rounds,
        )
        if maximum < 1 or not 1 <= problem.revision_attempts <= maximum:
            raise CandidateRevisionReferenceInvalid(
                "candidate has exhausted or cannot use the registered revision budget"
            )
        decision = session.scalar(
            select(AdmissionEvidence)
            .where(
                AdmissionEvidence.problem_id == problem.id,
                AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
                AdmissionEvidence.evidence_type == "admission_decision",
            )
            .order_by(AdmissionEvidence.created_at.desc(), AdmissionEvidence.id.desc())
        )
        if decision is None:
            raise CandidateRevisionReferenceInvalid("failed admission decision not found")
        payload = decision.payload_json
        expected_status_version = problem.status_version - 1
        if (
            decision.status != "failed"
            or payload.get("decision") != "revise"
            or payload.get("target_status") != "revision_required"
            or payload.get("problem_content_hash") != problem.content_hash
            or payload.get("problem_status_version") != expected_status_version
        ):
            raise CandidateRevisionReferenceInvalid(
                "latest admission decision does not authorize this candidate revision"
            )
        failure_types = list(dict.fromkeys([
            *payload.get("deterministic_failures", []),
            *payload.get("other_failures", []),
        ]))
        if not failure_types:
            raise CandidateRevisionReferenceInvalid(
                "revision requires at least one explicit failed gate requirement"
            )
        forbidden = sorted(set(failure_types) & self.NON_REVISABLE_FAILURES)
        if forbidden:
            raise CandidateRevisionReferenceInvalid(
                "non-revisable failures must be quarantined: " + ", ".join(forbidden)
            )

        checked_ids = payload.get("checked_evidence_ids", [])
        checked = list(session.scalars(select(AdmissionEvidence).where(
            AdmissionEvidence.id.in_(checked_ids),
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
        ))) if checked_ids else []
        checked_by_type = {item.evidence_type: item for item in checked}
        failures: list[RevisionFailureEvidence] = []
        for failure_type in failure_types:
            item = checked_by_type.get(failure_type)
            if item is not None and item.status == "failed":
                failures.append(self._failure_from_evidence(item))
                continue
            if failure_type not in {"structured_problem_complete", "fully_verified_solution"}:
                raise CandidateRevisionReferenceInvalid(
                    f"explicit failed evidence is missing for {failure_type}"
                )
            failures.append(RevisionFailureEvidence(
                evidence_id=f"{decision.id}#{failure_type}",
                evidence_type=failure_type,
                status=AdmissionEvidenceStatus.FAILED,
                producer_type=EvidenceProducerType.SYSTEM,
                summary=decision.summary,
                public_details={"gate_reason": payload.get("reason")},
                suggested_revisions=[self._synthetic_revision_hint(failure_type)],
            ))

        if problem.target_json is None or problem.derivation_type is None:
            raise CandidateRevisionReferenceInvalid(
                "candidate lacks target or mother derivation provenance"
            )
        return CandidateRevisionContext(
            problem_id=problem.id,
            generation_batch_id=problem.generation_batch_id,
            content_hash=problem.content_hash,
            status_version=problem.status_version,
            content_status=problem.content_status,
            revision_attempt=problem.revision_attempts,
            max_revision_attempts=maximum,
            admission_decision_id=decision.id,
            admission_decision_hash=decision.evidence_hash,
            statement=problem.statement,
            normalized_statement=problem.normalized_statement,
            explicit_conditions=problem.explicit_conditions_json,
            implicit_conditions=problem.implicit_conditions_json,
            target=problem.target_json,
            subject=problem.subject,
            grade_band=problem.grade_band or generation_input.grade_band,
            problem_type=problem.problem_type,
            difficulty=problem.difficulty,
            answer_type=problem.answer_type,
            language=problem.language,
            knowledge_point_codes=problem.knowledge_point_codes_json,
            derivation_type=problem.derivation_type,
            mother_problem_id=problem.mother_problem_id,
            allowed_difficulty_minimum=generation_input.difficulty.minimum,
            allowed_difficulty_maximum=generation_input.difficulty.maximum,
            prohibited_terms=generation_input.constraints.prohibited_terms,
            failures=failures,
        )

    @classmethod
    def _failure_from_evidence(cls, item: AdmissionEvidence) -> RevisionFailureEvidence:
        payload = item.payload_json
        suggested = cls._suggestions(payload)
        return RevisionFailureEvidence(
            evidence_id=item.id,
            evidence_type=item.evidence_type,
            status=AdmissionEvidenceStatus.FAILED,
            producer_type=EvidenceProducerType(item.producer_type),
            summary=item.summary,
            public_details=cls._public_failure_details(payload),
            suggested_revisions=suggested,
        )

    @staticmethod
    def _public_failure_details(payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "issues",
            "blocking_issues",
            "revision_instructions",
            "checks",
            "limitations",
            "answer_comparison",
            "teaching_assessments",
            "independence_checks",
            "coverage",
            "reason",
        }
        return {key: value for key, value in payload.items() if key in allowed}

    @classmethod
    def _suggestions(cls, value: Any) -> list[str]:
        found: list[str] = []

        def visit(current: Any, key: str | None = None) -> None:
            if isinstance(current, dict):
                for nested_key, nested in current.items():
                    visit(nested, str(nested_key))
            elif isinstance(current, list):
                for nested in current:
                    visit(nested, key)
            elif isinstance(current, str) and key in {
                "suggested_revision",
                "revision_instruction",
                "revision_instructions",
            }:
                text = current.strip()
                if text and text not in found:
                    found.append(text[:1000])

        visit(value)
        return found[:50]

    @staticmethod
    def _synthetic_revision_hint(failure_type: str) -> str:
        if failure_type == "structured_problem_complete":
            return "补全题型、显式条件与求解目标，使题意可独立确定。"
        return "修订题干与条件，使独立解题能够产生可完整验证的题解。"

    @staticmethod
    def _require_versions(
        session: Session,
        *,
        model_version_id: str,
        prompt_version_id: str,
    ) -> tuple[ModelVersion, PromptVersion]:
        model = session.get(ModelVersion, model_version_id)
        prompt = session.get(PromptVersion, prompt_version_id)
        if model is None or not model.active:
            raise CandidateRevisionReferenceInvalid("active revision model version not found")
        if (
            prompt is None
            or not prompt.active
            or prompt.purpose != CandidateRevisionRepository.PROMPT_PURPOSE
            or prompt.output_schema_version != CandidateRevisionRepository.OUTPUT_SCHEMA_VERSION
        ):
            raise CandidateRevisionReferenceInvalid("active candidate revision prompt not found")
        return model, prompt

    @classmethod
    def _validate_draft(
        cls,
        draft: CandidateRevisionDraft,
        context: CandidateRevisionContext,
    ) -> CandidateRevisionDraft:
        if draft.context_fingerprint != context.fingerprint():
            raise CandidateRevisionReferenceInvalid(
                "revision output does not match the current failure context"
            )
        expected_ids = {item.evidence_id for item in context.failures}
        actual_ids = {item.evidence_id for item in draft.repairs}
        if actual_ids != expected_ids:
            raise CandidateRevisionReferenceInvalid(
                "repairs must cover every explicit failed evidence id exactly once"
            )
        question = draft.revised_question
        if (
            question.answer_type != context.answer_type
            or question.derivation_type.value != context.derivation_type
            or set(question.knowledge_point_codes) != set(context.knowledge_point_codes)
        ):
            raise CandidateRevisionReferenceInvalid(
                "revision changed the protected answer, derivation, or knowledge scope"
            )
        if not (
            context.allowed_difficulty_minimum
            <= question.difficulty
            <= context.allowed_difficulty_maximum
        ):
            raise CandidateRevisionReferenceInvalid(
                "revision difficulty is outside the registered range"
            )
        if not question.explicit_conditions:
            raise CandidateRevisionReferenceInvalid(
                "revision requires explicit conditions"
            )
        if len(question.explicit_conditions) < len(context.explicit_conditions):
            raise CandidateRevisionReferenceInvalid(
                "revision cannot remove explicit conditions to bypass failed checks"
            )
        matched_terms = sorted({
            term
            for term in context.prohibited_terms
            if term and term.casefold() in question.statement.casefold()
        })
        if matched_terms:
            raise CandidateRevisionReferenceInvalid(
                "revision contains prohibited terms: " + ", ".join(matched_terms)
            )
        normalized_statement = cls._normalize_text(
            question.normalized_statement or question.statement
        )
        revised_question = question.model_copy(
            update={"normalized_statement": normalized_statement}
        )
        return draft.model_copy(update={"revised_question": revised_question})

    @classmethod
    def _create_revision_evidence(
        cls,
        session: Session,
        *,
        source: KnowledgeProblem,
        revised: KnowledgeProblem,
        current: CandidateRevisionContext,
        draft: CandidateRevisionDraft,
        model_version_id: str,
        prompt_version_id: str,
    ) -> AdmissionEvidence:
        payload = {
            "schema_version": "1.0",
            "source_problem_id": source.id,
            "source_content_hash": source.content_hash,
            "revised_problem_id": revised.id,
            "revised_content_hash": revised.content_hash,
            "revision_attempt": current.revision_attempt,
            "max_revision_attempts": current.max_revision_attempts,
            "context_fingerprint": current.fingerprint(),
            "admission_decision_id": current.admission_decision_id,
            "admission_decision_hash": current.admission_decision_hash,
            "failure_evidence_ids": [item.evidence_id for item in current.failures],
            "failure_types": [item.evidence_type for item in current.failures],
            "repairs": [item.model_dump(mode="json") for item in draft.repairs],
            "change_summary": draft.change_summary,
            "requires_full_revalidation": True,
            "inherited_admission_evidence": False,
            "approval_granted": False,
        }
        evidence_hash = cls._hash_json(payload)
        evidence = AdmissionEvidence(
            generation_batch_id=revised.generation_batch_id,
            problem_id=revised.id,
            solution_id=None,
            evidence_type="revision_generation",
            producer_type="model",
            status="passed",
            model_version_id=model_version_id,
            prompt_version_id=prompt_version_id,
            verifier_version_id=None,
            is_blocking=False,
            summary=draft.change_summary,
            payload_json=payload,
            evidence_hash=evidence_hash,
        )
        session.add(evidence)
        session.flush()
        return evidence

    @classmethod
    def _existing_result(
        cls,
        session: Session,
        *,
        source: KnowledgeProblem,
        existing: KnowledgeProblem,
        current: CandidateRevisionContext,
        content_hash: str,
    ) -> PersistedCandidateRevision:
        metadata = existing.metadata_json
        if (
            existing.content_hash != content_hash
            or existing.content_status != "candidate"
            or metadata.get("revised_from_problem_id") != source.id
            or metadata.get("revision_context_fingerprint") != current.fingerprint()
            or metadata.get("revision_attempt") != current.revision_attempt
        ):
            raise CandidateRevisionVersionConflict(
                "revision identity already exists with incompatible provenance"
            )
        evidence = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.problem_id == existing.id,
            AdmissionEvidence.evidence_type == "revision_generation",
        ))
        if evidence is None:
            raise CandidateRevisionVersionConflict(
                "persisted revision is missing its audit evidence"
            )
        return PersistedCandidateRevision(
            source_problem_id=source.id,
            revised_problem_id=existing.id,
            generation_batch_id=existing.generation_batch_id,
            revision_attempt=current.revision_attempt,
            content_status=existing.content_status,
            content_hash=existing.content_hash,
            revision_evidence_id=evidence.id,
            created=False,
        )

    @staticmethod
    def _draft_hash(draft: CandidateRevisionDraft) -> str:
        question = draft.revised_question
        payload = {
            "statement": question.normalized_statement or question.statement,
            "conditions": [
                item.model_dump(mode="json") for item in question.explicit_conditions
            ],
            "target": question.target.model_dump(mode="json"),
        }
        return CandidateRevisionRepository._hash_json(payload)

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _hash_json(payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()
