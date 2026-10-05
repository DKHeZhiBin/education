from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.question_generation import (
    CandidateGenerationOutcome,
    GeneratedQuestionDraft,
    QuestionGenerationCandidateResult,
    QuestionGenerationJobInput,
    QuestionGenerationStoredInput,
    QuestionGenerationUsage,
    TrustedMotherProblemContext,
    candidate_key,
)
from app.models.generation import (
    AdmissionEvidence,
    GenerationBatch,
    ModelVersion,
    PromptVersion,
    QuestionGenerationJob,
)
from app.models.knowledge import KnowledgeProblem, SourceReference
from app.models.learning import CapabilityPoint, KnowledgePoint


class QuestionGenerationIdempotencyConflict(RuntimeError):
    def __init__(self, idempotency_scope: str) -> None:
        super().__init__(
            f"idempotency key was already used with a different request in {idempotency_scope}"
        )


class QuestionGenerationVersionNotFound(LookupError):
    pass


class QuestionGenerationReferenceInvalid(ValueError):
    pass


@dataclass(frozen=True)
class QuestionGenerationRegistration:
    job: QuestionGenerationJob
    batch: GenerationBatch
    created: bool


@dataclass(frozen=True)
class QuestionVariationAgentContext:
    job_id: str
    generation_batch_id: str
    idempotency_key_hash: str
    model_name: str
    generation_input: QuestionGenerationStoredInput
    versioned_prompt: str
    mothers: tuple[TrustedMotherProblemContext, ...]


class QuestionGenerationJobRepository:
    """Register a generation request inside the caller's transaction."""

    def register(
        self,
        session: Session,
        request: QuestionGenerationJobInput,
    ) -> QuestionGenerationRegistration:
        idempotency_hash = request.idempotency_key_hash()
        request_hash = request.request_hash()
        existing = session.scalar(
            select(QuestionGenerationJob).where(
                QuestionGenerationJob.idempotency_key_hash == idempotency_hash
            ).with_for_update()
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise QuestionGenerationIdempotencyConflict(request.idempotency_scope)
            batch = session.get(GenerationBatch, existing.generation_batch_id)
            if batch is None:
                raise RuntimeError("generation job references a missing batch")
            return QuestionGenerationRegistration(existing, batch, False)

        self._require_versions(session, request)
        self._require_generation_scope(session, request)
        batch = GenerationBatch(
            batch_key=request.batch_key(),
            purpose="question_variation",
            subject=request.subject,
            grade_band=request.grade_band,
            topic_code=request.topic_code,
            requested_count=request.requested_count,
            generated_count=0,
            approved_count=0,
            quarantined_count=0,
            failed_count=0,
            status="pending",
            model_version_id=request.model_version_id,
            prompt_version_id=request.prompt_version_id,
            config_json={
                "request_hash": request_hash,
                "verifier_profile": request.verifier_profile,
                "output_schema_version": request.output_schema_version,
                "random_seed": request.random_seed,
            },
        )
        session.add(batch)
        session.flush()
        job = QuestionGenerationJob(
            generation_batch_id=batch.id,
            idempotency_scope=request.idempotency_scope,
            idempotency_key_hash=idempotency_hash,
            request_hash=request_hash,
            input_schema_version=request.schema_version,
            output_schema_version=request.output_schema_version,
            input_json=request.persistence_payload(),
            budget_json=request.budget.model_dump(mode="json"),
            usage_json=QuestionGenerationUsage().model_dump(mode="json"),
            output_json=None,
            attempt_count=0,
        )
        session.add(job)
        session.flush()
        return QuestionGenerationRegistration(job, batch, True)

    def load_agent_context(
        self,
        session: Session,
        job_id: str,
    ) -> QuestionVariationAgentContext:
        """Load solution-free, repository-verified input for the generation agent."""
        job = session.get(QuestionGenerationJob, job_id)
        if job is None:
            raise QuestionGenerationReferenceInvalid("question generation job not found")
        generation_input = QuestionGenerationStoredInput.model_validate(job.input_json)
        model = session.get(ModelVersion, generation_input.model_version_id)
        prompt = session.get(PromptVersion, generation_input.prompt_version_id)
        if model is None or not model.active:
            raise QuestionGenerationVersionNotFound(
                "active generation model version not found"
            )
        if (
            prompt is None
            or not prompt.active
            or prompt.purpose != "question_generation"
            or prompt.output_schema_version != generation_input.output_schema_version
        ):
            raise QuestionGenerationVersionNotFound(
                "active question generation prompt version not found"
            )
        problems = list(session.scalars(
            select(KnowledgeProblem).where(
                KnowledgeProblem.id.in_(generation_input.mother_problem_ids)
            )
        ))
        by_id = {problem.id: problem for problem in problems}
        missing = [
            problem_id
            for problem_id in generation_input.mother_problem_ids
            if problem_id not in by_id
        ]
        if missing:
            raise QuestionGenerationReferenceInvalid(
                "mother problems no longer exist: " + ", ".join(missing)
            )
        mothers = tuple(
            self._to_trusted_mother(by_id[problem_id], generation_input)
            for problem_id in generation_input.mother_problem_ids
        )
        return QuestionVariationAgentContext(
            job_id=job.id,
            generation_batch_id=job.generation_batch_id,
            idempotency_key_hash=job.idempotency_key_hash,
            model_name=model.model_name,
            generation_input=generation_input,
            versioned_prompt=prompt.template_text,
            mothers=mothers,
        )

    def persist_candidate(
        self,
        session: Session,
        *,
        job_id: str,
        ordinal: int,
        mother_problem_id: str,
        draft: GeneratedQuestionDraft,
    ) -> QuestionGenerationCandidateResult:
        """Persist generated content with candidate status; approval is impossible here."""
        job = session.scalar(
            select(QuestionGenerationJob)
            .where(QuestionGenerationJob.id == job_id)
            .with_for_update()
        )
        if job is None:
            raise QuestionGenerationReferenceInvalid("question generation job not found")
        batch = session.scalar(
            select(GenerationBatch)
            .where(GenerationBatch.id == job.generation_batch_id)
            .with_for_update()
        )
        if batch is None:
            raise QuestionGenerationReferenceInvalid("generation batch not found")
        if batch.status != "running":
            raise QuestionGenerationReferenceInvalid(
                "candidates can only be persisted while the batch is running"
            )

        generation_input = QuestionGenerationStoredInput.model_validate(job.input_json)
        if ordinal < 0 or ordinal >= generation_input.requested_count:
            raise QuestionGenerationReferenceInvalid("candidate ordinal is outside the job")
        identity = candidate_key(job.idempotency_key_hash, ordinal)
        existing = session.scalar(select(KnowledgeProblem).where(
            KnowledgeProblem.generation_batch_id == batch.id,
            KnowledgeProblem.external_id == identity,
        ))
        if existing is not None:
            if (
                existing.mother_problem_id != mother_problem_id
                or existing.content_status != "candidate"
                or existing.content_hash != self._draft_hash(draft)
            ):
                raise QuestionGenerationReferenceInvalid(
                    "candidate identity already exists with incompatible provenance"
                )
            self._get_or_create_generation_evidence(
                session,
                job=job,
                problem=existing,
                mother_problem_id=mother_problem_id,
                ordinal=ordinal,
                candidate_identity=identity,
                generation_input=generation_input,
            )
            return self._candidate_result(existing, draft, ordinal, identity)

        mother = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == mother_problem_id)
            .with_for_update()
        )
        if mother is None:
            raise QuestionGenerationReferenceInvalid("mother problem not found")
        self._to_trusted_mother(mother, generation_input)
        self._require_draft_scope(draft, mother, generation_input)

        content_hash = self._draft_hash(draft)
        duplicate = session.scalar(select(KnowledgeProblem).where(
            KnowledgeProblem.content_hash == content_hash
        ))
        if duplicate is not None:
            raise QuestionGenerationReferenceInvalid(
                f"candidate duplicates existing problem {duplicate.id}"
            )
        if batch.generated_count + batch.failed_count >= batch.requested_count:
            raise QuestionGenerationReferenceInvalid("generation batch is already full")

        candidate_source = self._get_or_create_candidate_source(session, mother)
        problem = KnowledgeProblem(
            source_reference_id=candidate_source.id,
            curriculum_version_id=mother.curriculum_version_id,
            mother_problem_id=mother.id,
            generation_batch_id=batch.id,
            external_id=identity,
            statement=draft.statement,
            normalized_statement=draft.normalized_statement,
            subject=generation_input.subject,
            grade_band=generation_input.grade_band,
            grade_codes_json=list(mother.grade_codes_json),
            problem_type=generation_input.problem_type,
            content_type="problem",
            difficulty=draft.difficulty,
            answer_type=draft.answer_type,
            language=generation_input.language,
            content_hash=content_hash,
            review_status="unreviewed",
            explicit_conditions_json=[
                item.model_dump(mode="json") for item in draft.explicit_conditions
            ],
            implicit_conditions_json=[
                item.model_dump(mode="json") for item in draft.implicit_conditions
            ],
            target_json=draft.target.model_dump(mode="json"),
            difficulty_factors_json=[
                item.model_dump(mode="json") for item in draft.difficulty_factors
            ],
            derivation_type=draft.derivation_type.value,
            derivation_note=draft.derivation_note,
            content_status="candidate",
            status_reason=None,
            revision_attempts=0,
            status_version=1,
            knowledge_point_codes_json=draft.knowledge_point_codes,
            metadata_json={
                "content_origin": "ai_mother_problem_variation",
                "candidate_key": identity,
                "generation_job_id": job.id,
                "mother_problem_id": mother.id,
                "mother_source_reference_id": mother.source_reference_id,
                "model_version_id": generation_input.model_version_id,
                "prompt_version_id": generation_input.prompt_version_id,
                "output_schema_version": generation_input.output_schema_version,
                "approval_forbidden_at_generation": True,
                "trusted_mother": False,
            },
        )
        session.add(problem)
        batch.generated_count += 1
        session.flush()
        if problem.content_status != "candidate" or problem.review_status != "unreviewed":
            raise RuntimeError("generation persistence cannot approve content")
        self._get_or_create_generation_evidence(
            session,
            job=job,
            problem=problem,
            mother_problem_id=mother.id,
            ordinal=ordinal,
            candidate_identity=identity,
            generation_input=generation_input,
        )
        return self._candidate_result(problem, draft, ordinal, identity)

    @staticmethod
    def _get_or_create_generation_evidence(
        session: Session,
        *,
        job: QuestionGenerationJob,
        problem: KnowledgeProblem,
        mother_problem_id: str,
        ordinal: int,
        candidate_identity: str,
        generation_input: QuestionGenerationStoredInput,
    ) -> AdmissionEvidence:
        payload = {
            "schema_version": "1.0",
            "event": "candidate_generated",
            "generation_job_id": job.id,
            "request_hash": job.request_hash,
            "candidate_key": candidate_identity,
            "ordinal": ordinal,
            "mother_problem_id": mother_problem_id,
            "problem_content_hash": problem.content_hash,
            "problem_status": problem.content_status,
            "problem_status_version": problem.status_version,
            "model_version_id": generation_input.model_version_id,
            "prompt_version_id": generation_input.prompt_version_id,
            "output_schema_version": generation_input.output_schema_version,
            "approval_granted": False,
        }
        evidence_hash = QuestionGenerationJobRepository._hash_json(payload)
        existing = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "candidate_generation",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if existing is not None:
            return existing
        evidence = AdmissionEvidence(
            generation_batch_id=problem.generation_batch_id,
            problem_id=problem.id,
            solution_id=None,
            evidence_type="candidate_generation",
            producer_type="model",
            status="passed",
            model_version_id=generation_input.model_version_id,
            prompt_version_id=generation_input.prompt_version_id,
            verifier_version_id=None,
            is_blocking=False,
            summary="候选题已由可信母题变式生成，并以 candidate 状态保存。",
            payload_json=payload,
            evidence_hash=evidence_hash,
        )
        session.add(evidence)
        session.flush()
        return evidence

    @staticmethod
    def _require_versions(
        session: Session,
        request: QuestionGenerationJobInput,
    ) -> None:
        model = session.get(ModelVersion, request.model_version_id)
        prompt = session.get(PromptVersion, request.prompt_version_id)
        if model is None or not model.active:
            raise QuestionGenerationVersionNotFound("active model version not found")
        if prompt is None or not prompt.active:
            raise QuestionGenerationVersionNotFound("active prompt version not found")
        if prompt.purpose != "question_generation":
            raise QuestionGenerationVersionNotFound(
                "prompt version is not registered for question_generation"
            )
        if prompt.output_schema_version != request.output_schema_version:
            raise QuestionGenerationVersionNotFound(
                "prompt output schema does not match the generation request"
            )

    @staticmethod
    def _require_generation_scope(
        session: Session,
        request: QuestionGenerationJobInput,
    ) -> None:
        mother_problems = list(session.scalars(
            select(KnowledgeProblem).where(
                KnowledgeProblem.id.in_(request.mother_problem_ids)
            )
        ))
        mothers_by_id = {problem.id: problem for problem in mother_problems}
        missing_mothers = sorted(set(request.mother_problem_ids) - set(mothers_by_id))
        if missing_mothers:
            raise QuestionGenerationReferenceInvalid(
                "mother problems do not exist: " + ", ".join(missing_mothers)
            )

        invalid_mothers: list[str] = []
        available_knowledge_codes: set[str] = set()
        for problem in mother_problems:
            available_knowledge_codes.update(problem.knowledge_point_codes_json)
            trusted = bool(problem.metadata_json.get("trusted_mother"))
            admitted = problem.content_status in {"approved", "indexed"}
            fully_tagged = bool(
                problem.grade_band
                and problem.grade_codes_json
                and problem.knowledge_point_codes_json
                and problem.problem_type
                and problem.content_type
                and problem.difficulty_factors_json
            )
            same_scope = (
                problem.subject == request.subject
                and problem.problem_type == request.problem_type
                and (
                    problem.grade_band is None
                    or problem.grade_band == request.grade_band
                )
            )
            if not trusted or not admitted or not same_scope or not fully_tagged:
                invalid_mothers.append(problem.id)
        if invalid_mothers:
            raise QuestionGenerationReferenceInvalid(
                "mother problems must be trusted, approved, fully tagged and in the "
                "requested scope: "
                + ", ".join(sorted(invalid_mothers))
            )

        requested_codes = set(request.knowledge_point_codes)
        undeclared = sorted(requested_codes - available_knowledge_codes)
        if undeclared:
            raise QuestionGenerationReferenceInvalid(
                "requested knowledge points are absent from the mother problems: "
                + ", ".join(undeclared)
            )
        if not any(
            requested_codes.issubset(set(problem.knowledge_point_codes_json))
            for problem in mother_problems
        ):
            raise QuestionGenerationReferenceInvalid(
                "no single trusted mother covers all requested knowledge points"
            )

        known_knowledge = set(session.scalars(
            select(KnowledgePoint.code).where(
                KnowledgePoint.code.in_(request.knowledge_point_codes)
            )
        ))
        missing_knowledge = sorted(set(request.knowledge_point_codes) - known_knowledge)
        if missing_knowledge:
            raise QuestionGenerationReferenceInvalid(
                "knowledge points do not exist: " + ", ".join(missing_knowledge)
            )

        if request.capability_point_codes:
            known_capabilities = set(session.scalars(
                select(CapabilityPoint.code).where(
                    CapabilityPoint.code.in_(request.capability_point_codes)
                )
            ))
            missing_capabilities = sorted(
                set(request.capability_point_codes) - known_capabilities
            )
            if missing_capabilities:
                raise QuestionGenerationReferenceInvalid(
                    "capability points do not exist: "
                    + ", ".join(missing_capabilities)
                )

    @staticmethod
    def _to_trusted_mother(
        problem: KnowledgeProblem,
        generation_input: QuestionGenerationStoredInput,
    ) -> TrustedMotherProblemContext:
        if problem.id not in generation_input.mother_problem_ids:
            raise QuestionGenerationReferenceInvalid(
                "mother problem is not declared by the generation job"
            )
        if not bool(problem.metadata_json.get("trusted_mother")):
            raise QuestionGenerationReferenceInvalid("mother problem is not trusted")
        if problem.content_status not in {"approved", "indexed"}:
            raise QuestionGenerationReferenceInvalid(
                "trusted mother must remain approved or indexed"
            )
        if (
            problem.subject != generation_input.subject
            or problem.problem_type != generation_input.problem_type
            or (
                problem.grade_band is not None
                and problem.grade_band != generation_input.grade_band
            )
        ):
            raise QuestionGenerationReferenceInvalid(
                "mother problem is outside the registered generation scope"
            )
        if problem.target_json is None:
            raise QuestionGenerationReferenceInvalid("mother problem has no target")
        return TrustedMotherProblemContext(
            id=problem.id,
            source_reference_id=problem.source_reference_id,
            curriculum_version_id=problem.curriculum_version_id,
            statement=problem.statement,
            normalized_statement=problem.normalized_statement,
            subject=problem.subject,
            grade_band=problem.grade_band,
            grade_codes=problem.grade_codes_json,
            problem_type=problem.problem_type,
            content_type=problem.content_type,
            difficulty=problem.difficulty,
            answer_type=problem.answer_type,
            language=problem.language,
            explicit_conditions=problem.explicit_conditions_json,
            implicit_conditions=problem.implicit_conditions_json,
            target=problem.target_json,
            difficulty_factors=problem.difficulty_factors_json,
            knowledge_point_codes=problem.knowledge_point_codes_json,
            content_status=problem.content_status,
            trusted_mother=True,
        )

    @staticmethod
    def _require_draft_scope(
        draft: GeneratedQuestionDraft,
        mother: KnowledgeProblem,
        generation_input: QuestionGenerationStoredInput,
    ) -> None:
        if draft.derivation_type not in generation_input.allowed_derivation_types:
            raise QuestionGenerationReferenceInvalid("draft derivation type is not allowed")
        if not (
            generation_input.difficulty.minimum
            <= draft.difficulty
            <= generation_input.difficulty.maximum
        ):
            raise QuestionGenerationReferenceInvalid("draft difficulty is out of range")
        draft_codes = set(draft.knowledge_point_codes)
        if not set(generation_input.knowledge_point_codes).issubset(draft_codes):
            raise QuestionGenerationReferenceInvalid(
                "draft omits required knowledge points"
            )
        if not draft_codes.issubset(set(mother.knowledge_point_codes_json)):
            raise QuestionGenerationReferenceInvalid(
                "draft introduces knowledge absent from its trusted mother"
            )
        if (
            generation_input.constraints.preserve_answer_type
            and draft.answer_type != mother.answer_type
        ):
            raise QuestionGenerationReferenceInvalid("draft changed the answer type")

    @staticmethod
    def _draft_hash(draft: GeneratedQuestionDraft) -> str:
        payload = {
            "statement": draft.normalized_statement or draft.statement,
            "conditions": [
                item.model_dump(mode="json") for item in draft.explicit_conditions
            ],
            "target": draft.target.model_dump(mode="json"),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()

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
    def _get_or_create_candidate_source(
        session: Session,
        mother: KnowledgeProblem,
    ) -> SourceReference:
        mother_source = session.get(SourceReference, mother.source_reference_id)
        if mother_source is None:
            raise QuestionGenerationReferenceInvalid("mother source reference not found")
        fingerprint = sha256(
            f"ai-candidate-variation:v1:{mother_source.id}".encode("utf-8")
        ).hexdigest()
        existing = session.scalar(select(SourceReference).where(
            SourceReference.fingerprint == fingerprint
        ))
        if existing is not None:
            return existing
        source = SourceReference(
            source_type="local_authoring",
            title=(f"AI candidate variations: {mother_source.title}")[:500],
            authors_json=["Math Tutor Agent"],
            publisher=None,
            canonical_url=mother_source.canonical_url,
            external_id=f"ai-variation:{mother_source.id}",
            license_name=mother_source.license_name,
            rights_note=(
                "AI-generated candidate derivative. Original source attribution and "
                f"license obligations are inherited from source {mother_source.id}."
            ),
            published_at=None,
            accessed_at=mother_source.accessed_at,
            fingerprint=fingerprint,
        )
        session.add(source)
        session.flush()
        return source

    @staticmethod
    def _candidate_result(
        problem: KnowledgeProblem,
        draft: GeneratedQuestionDraft,
        ordinal: int,
        identity: str,
    ) -> QuestionGenerationCandidateResult:
        if problem.mother_problem_id is None or problem.content_status != "candidate":
            raise RuntimeError("generated result must reference a mother and remain candidate")
        return QuestionGenerationCandidateResult(
            ordinal=ordinal,
            candidate_key=identity,
            mother_problem_id=problem.mother_problem_id,
            outcome=CandidateGenerationOutcome.CANDIDATE_CREATED,
            draft=draft,
            problem_id=problem.id,
            content_status=problem.content_status,
        )
