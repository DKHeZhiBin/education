from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.core.database import create_mysql_engine, create_session_factory
from app.domain.generation import (
    AdmissionEvidence as DomainAdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
    GenerationBatchStatus,
)
from app.domain.generation_admin import (
    BatchWithdrawalResult,
    GenerationBatchActionResult,
    GenerationBatchAdminDetail,
    GenerationBatchAdminItem,
    GenerationBatchAdminPage,
    GenerationBatchEventView,
    GenerationBatchRetryResult,
)
from app.domain.knowledge import ProblemContentStatus
from app.domain.problem_lifecycle import ProblemContentStateMachine, ProblemTransitionRequest
from app.domain.question_generation import (
    GenerationBatchStateMachine,
    QuestionGenerationJobInput,
    candidate_key,
)
from app.models.generation import (
    AdmissionEvidence,
    GenerationBatch,
    GenerationBatchManagementEvent,
    QuestionGenerationJob,
)
from app.models.knowledge import KnowledgeProblem, ProblemStatusTransition
from app.repositories.question_generation import QuestionGenerationJobRepository


class GenerationBatchNotFound(LookupError):
    pass


class GenerationBatchActionConflict(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class GenerationBatchAdminRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        state_machine: ProblemContentStateMachine | None = None,
        job_repository: QuestionGenerationJobRepository | None = None,
    ) -> None:
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())
        self.problem_state_machine = state_machine or ProblemContentStateMachine()
        self.job_repository = job_repository or QuestionGenerationJobRepository()

    def list_batches(
        self,
        *,
        statuses: list[GenerationBatchStatus] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> GenerationBatchAdminPage:
        filters = []
        if statuses:
            filters.append(GenerationBatch.status.in_([item.value for item in statuses]))
        query = (
            select(GenerationBatch)
            .options(selectinload(GenerationBatch.question_generation_job))
            .where(*filters)
            .order_by(GenerationBatch.created_at.desc(), GenerationBatch.id)
            .limit(limit)
            .offset(offset)
        )
        with self.session_factory() as session:
            total = session.scalar(select(func.count(GenerationBatch.id)).where(*filters)) or 0
            items = [self._item(entity) for entity in session.scalars(query).all()]
        return GenerationBatchAdminPage(items=items, total=total, limit=limit, offset=offset)

    def get_batch(self, batch_id: str) -> GenerationBatchAdminDetail | None:
        with self.session_factory() as session:
            entity = session.scalar(self._detail_query().where(GenerationBatch.id == batch_id))
            return self._detail(entity) if entity is not None else None

    def pause(self, batch_id: str, *, reason: str, actor_id: str) -> GenerationBatchActionResult:
        return self._change_status(
            batch_id,
            target=GenerationBatchStatus.PAUSED,
            action="pause",
            reason=reason,
            actor_id=actor_id,
        )

    def resume(self, batch_id: str, *, reason: str, actor_id: str) -> GenerationBatchActionResult:
        with self.session_factory() as session, session.begin():
            batch, job = self._locked_batch_and_job(session, batch_id)
            previous = GenerationBatchStatus(batch.status)
            if previous == GenerationBatchStatus.RUNNING:
                return GenerationBatchActionResult(
                    batch=self._reload_detail(session, batch.id), changed=False
                )
            if job is None:
                raise GenerationBatchActionConflict(
                    "generation_job_missing", "the batch has no resumable generation job"
                )
            budget = job.budget_json
            maximum = int(budget.get("max_execution_attempts", 0))
            if job.attempt_count >= maximum:
                raise GenerationBatchActionConflict(
                    "execution_attempts_exhausted",
                    "the generation job has reached its execution attempt limit",
                )
            self._ensure_budget_available(job)
            current = GenerationBatchStateMachine.transition(
                previous, GenerationBatchStatus.RUNNING
            )
            job.attempt_count += 1
            job.status_reason = None
            job.last_error_code = None
            batch.status = current.value
            batch.finished_at = None
            self._update_nonterminal_output(job, batch, current)
            self._add_event(
                session,
                batch=batch,
                action="resume",
                previous=previous,
                current=current,
                reason=reason,
                actor_id=actor_id,
                payload={"attempt_count": job.attempt_count, "max_attempts": maximum},
            )
            session.flush()
            result = GenerationBatchActionResult(
                batch=self._reload_detail(session, batch.id), changed=True
            )
        return result

    def cancel(self, batch_id: str, *, reason: str, actor_id: str) -> GenerationBatchActionResult:
        with self.session_factory() as session, session.begin():
            batch, job = self._locked_batch_and_job(session, batch_id)
            previous = GenerationBatchStatus(batch.status)
            if previous == GenerationBatchStatus.CANCELLED:
                return GenerationBatchActionResult(
                    batch=self._reload_detail(session, batch.id), changed=False
                )
            current = GenerationBatchStateMachine.transition(
                previous, GenerationBatchStatus.CANCELLED
            )
            changed_at = self._now()
            batch.status = current.value
            batch.finished_at = changed_at
            batch.failed_count = batch.requested_count - batch.generated_count
            if job is not None:
                job.status_reason = reason
                job.last_error_code = "cancelled_by_admin"
                self._write_cancelled_output(session, batch=batch, job=job, reason=reason)
            self._add_event(
                session,
                batch=batch,
                action="cancel",
                previous=previous,
                current=current,
                reason=reason,
                actor_id=actor_id,
                payload={"generated_count": batch.generated_count},
            )
            session.flush()
            result = GenerationBatchActionResult(
                batch=self._reload_detail(session, batch.id), changed=True
            )
        return result

    def retry(
        self,
        batch_id: str,
        *,
        idempotency_key: str,
        reason: str,
        actor_id: str,
    ) -> GenerationBatchRetryResult:
        with self.session_factory() as session, session.begin():
            source, source_job = self._locked_batch_and_job(session, batch_id)
            source_status = GenerationBatchStatus(source.status)
            if source_status not in {
                GenerationBatchStatus.PARTIAL_FAILED,
                GenerationBatchStatus.FAILED,
                GenerationBatchStatus.CANCELLED,
            }:
                raise GenerationBatchActionConflict(
                    "batch_not_retryable", "only failed or cancelled batches can be retried"
                )
            if source_job is None:
                raise GenerationBatchActionConflict(
                    "generation_job_missing", "the batch has no generation job to retry"
                )
            retry_count = source.requested_count - source.generated_count
            if retry_count <= 0:
                raise GenerationBatchActionConflict(
                    "nothing_to_retry", "the batch has no ungenerated positions"
                )
            request_payload = dict(source_job.input_json)
            request_payload["requested_count"] = retry_count
            request_payload["idempotency_key"] = idempotency_key
            request_payload["budget"] = source_job.budget_json
            registration = self.job_repository.register(
                session, QuestionGenerationJobInput.model_validate(request_payload)
            )
            retry_batch = registration.batch
            if registration.created:
                retry_batch.config_json = {
                    **(retry_batch.config_json or {}),
                    "retry_of_batch_id": source.id,
                    "retry_of_job_id": source_job.id,
                    "retry_reason": reason,
                }
                self._add_event(
                    session,
                    batch=source,
                    action="retry_created",
                    previous=source_status,
                    current=source_status,
                    reason=reason,
                    actor_id=actor_id,
                    related_batch_id=retry_batch.id,
                    payload={"retry_count": retry_count},
                )
                self._add_event(
                    session,
                    batch=retry_batch,
                    action="retried_from",
                    previous=GenerationBatchStatus.PENDING,
                    current=GenerationBatchStatus.PENDING,
                    reason=reason,
                    actor_id=actor_id,
                    related_batch_id=source.id,
                    payload={"retry_count": retry_count},
                )
                session.flush()
            elif retry_batch.config_json.get("retry_of_batch_id") != source.id:
                raise GenerationBatchActionConflict(
                    "retry_idempotency_conflict",
                    "the idempotency key belongs to another generation request",
                )
            detail = self._reload_detail(session, retry_batch.id)
            result = GenerationBatchRetryResult(
                source_batch_id=source.id,
                retry_batch=detail,
                retry_count=retry_count,
            )
        return result

    def withdraw_approved(
        self,
        batch_id: str,
        *,
        reason: str,
        include_indexed: bool,
        indexed_content_removed: bool,
        actor_id: str,
    ) -> BatchWithdrawalResult:
        with self.session_factory() as session, session.begin():
            batch, _ = self._locked_batch_and_job(session, batch_id)
            statuses = ["approved", "indexed"] if include_indexed else ["approved"]
            problems = list(session.scalars(
                select(KnowledgeProblem)
                .where(
                    KnowledgeProblem.generation_batch_id == batch.id,
                    KnowledgeProblem.content_status.in_(statuses),
                )
                .order_by(KnowledgeProblem.id)
                .with_for_update()
            ))
            skipped_indexed = [] if include_indexed else list(session.scalars(
                select(KnowledgeProblem.id).where(
                    KnowledgeProblem.generation_batch_id == batch.id,
                    KnowledgeProblem.content_status == "indexed",
                )
            ))
            withdrawn: list[str] = []
            for problem in problems:
                evidence = self._problem_evidence(session, problem.id)
                current_status = ProblemContentStatus(problem.content_status)
                transition = self.problem_state_machine.transition(ProblemTransitionRequest(
                    problem_id=problem.id,
                    generation_batch_id=problem.generation_batch_id,
                    current_status=current_status,
                    target_status=ProblemContentStatus.QUARANTINED,
                    current_status_reason=problem.status_reason,
                    reason=reason,
                    revision_attempts=problem.revision_attempts,
                    index_is_active=(
                        current_status == ProblemContentStatus.INDEXED
                        and not indexed_content_removed
                    ),
                    evidence=evidence,
                ))
                self._persist_problem_transition(
                    session, problem=problem, transition=transition, actor_id=actor_id
                )
                withdrawn.append(problem.id)
            self._refresh_counts(session, batch)
            if withdrawn:
                batch_status = GenerationBatchStatus(batch.status)
                self._add_event(
                    session,
                    batch=batch,
                    action="withdraw_approved",
                    previous=batch_status,
                    current=batch_status,
                    reason=reason,
                    actor_id=actor_id,
                    payload={
                        "withdrawn_problem_ids": withdrawn,
                        "skipped_indexed_problem_ids": skipped_indexed,
                        "indexed_content_removed": indexed_content_removed,
                    },
                )
                session.flush()
            result = BatchWithdrawalResult(
                batch=self._reload_detail(session, batch.id),
                withdrawn_problem_ids=withdrawn,
                skipped_indexed_problem_ids=skipped_indexed,
            )
        return result

    def _change_status(
        self,
        batch_id: str,
        *,
        target: GenerationBatchStatus,
        action: Literal["pause"],
        reason: str,
        actor_id: str,
    ) -> GenerationBatchActionResult:
        with self.session_factory() as session, session.begin():
            batch, job = self._locked_batch_and_job(session, batch_id)
            previous = GenerationBatchStatus(batch.status)
            if previous == target:
                return GenerationBatchActionResult(
                    batch=self._reload_detail(session, batch.id), changed=False
                )
            if job is None:
                raise GenerationBatchActionConflict(
                    "generation_job_missing", "the batch has no pausable generation job"
                )
            current = GenerationBatchStateMachine.transition(previous, target)
            batch.status = current.value
            job.status_reason = reason
            self._update_nonterminal_output(job, batch, current)
            self._add_event(
                session,
                batch=batch,
                action=action,
                previous=previous,
                current=current,
                reason=reason,
                actor_id=actor_id,
                payload={},
            )
            session.flush()
            result = GenerationBatchActionResult(
                batch=self._reload_detail(session, batch.id), changed=True
            )
        return result

    @staticmethod
    def _locked_batch_and_job(
        session: Session, batch_id: str
    ) -> tuple[GenerationBatch, QuestionGenerationJob | None]:
        batch = session.scalar(
            select(GenerationBatch).where(GenerationBatch.id == batch_id).with_for_update()
        )
        if batch is None:
            raise GenerationBatchNotFound(batch_id)
        job = session.scalar(
            select(QuestionGenerationJob)
            .where(QuestionGenerationJob.generation_batch_id == batch.id)
            .with_for_update()
        )
        return batch, job

    @staticmethod
    def _ensure_budget_available(job: QuestionGenerationJob) -> None:
        budget = job.budget_json
        usage = job.usage_json
        limits = {
            "model_calls": "max_model_calls",
            "input_tokens": "max_input_tokens",
            "output_tokens": "max_output_tokens",
            "total_tokens": "max_total_tokens",
            "cost_minor_units": "max_cost_minor_units",
            "duration_ms": "max_duration_seconds",
            "candidates_attempted": "max_candidates",
        }
        exhausted = []
        for usage_key, budget_key in limits.items():
            limit = int(budget.get(budget_key, 0))
            if usage_key == "duration_ms":
                limit *= 1000
            if int(usage.get(usage_key, 0)) >= limit:
                exhausted.append(usage_key)
        if exhausted:
            raise GenerationBatchActionConflict(
                "generation_budget_exhausted",
                "generation budget is exhausted: " + ", ".join(exhausted),
            )

    @staticmethod
    def _update_nonterminal_output(
        job: QuestionGenerationJob,
        batch: GenerationBatch,
        status: GenerationBatchStatus,
    ) -> None:
        if job.output_json is None:
            return
        output = dict(job.output_json)
        output.update({"status": status.value, "stop_reason": None, "finished_at": None})
        output["started_at"] = batch.started_at.isoformat() if batch.started_at else None
        job.output_json = output

    def _write_cancelled_output(
        self,
        session: Session,
        *,
        batch: GenerationBatch,
        job: QuestionGenerationJob,
        reason: str,
    ) -> None:
        existing = dict(job.output_json or {})
        candidates_by_ordinal = {
            int(item["ordinal"]): item
            for item in existing.get("candidates", [])
            if isinstance(item, dict) and "ordinal" in item
        }
        evidence = list(session.scalars(
            select(AdmissionEvidence).where(
                AdmissionEvidence.generation_batch_id == batch.id,
                AdmissionEvidence.evidence_type == "candidate_generation",
            )
        ))
        problems = {
            item.id: item
            for item in session.scalars(
                select(KnowledgeProblem).where(KnowledgeProblem.generation_batch_id == batch.id)
            )
        }
        for item in evidence:
            problem = problems.get(item.problem_id)
            ordinal = (item.payload_json or {}).get("ordinal")
            if problem is None or not isinstance(ordinal, int):
                continue
            candidates_by_ordinal[ordinal] = {
                "ordinal": ordinal,
                "candidate_key": (item.payload_json or {}).get("candidate_key"),
                "mother_problem_id": problem.mother_problem_id,
                "outcome": "candidate_created",
                "draft": {
                    "statement": problem.statement,
                    "normalized_statement": problem.normalized_statement,
                    "explicit_conditions": problem.explicit_conditions_json,
                    "implicit_conditions": problem.implicit_conditions_json,
                    "target": problem.target_json,
                    "difficulty": problem.difficulty,
                    "difficulty_factors": problem.difficulty_factors_json,
                    "answer_type": problem.answer_type,
                    "knowledge_point_codes": problem.knowledge_point_codes_json,
                    "derivation_type": problem.derivation_type,
                    "derivation_note": problem.derivation_note,
                },
                "problem_id": problem.id,
                "content_status": "candidate",
                "failure_code": None,
                "failure_message": None,
            }
        input_payload = job.input_json
        mothers = input_payload.get("mother_problem_ids", [])
        for ordinal in range(batch.requested_count):
            if ordinal in candidates_by_ordinal:
                continue
            candidates_by_ordinal[ordinal] = {
                "ordinal": ordinal,
                "candidate_key": candidate_key(job.idempotency_key_hash, ordinal),
                "mother_problem_id": mothers[ordinal % len(mothers)],
                "outcome": "skipped",
                "draft": None,
                "problem_id": None,
                "content_status": None,
                "failure_code": "cancelled_by_admin",
                "failure_message": reason,
            }
        usage = dict(job.usage_json or {})
        usage["candidates_attempted"] = sum(
            item["outcome"] != "skipped" for item in candidates_by_ordinal.values()
        )
        job.usage_json = usage
        errors = list(existing.get("errors", []))
        errors.append(f"cancelled_by_admin: {reason}"[:1000])
        job.output_json = {
            "schema_version": "1.0",
            "job_id": job.id,
            "generation_batch_id": batch.id,
            "status": "cancelled",
            "stop_reason": "cancelled",
            "candidates": [candidates_by_ordinal[key] for key in sorted(candidates_by_ordinal)],
            "usage": usage,
            "started_at": batch.started_at.isoformat() if batch.started_at else None,
            "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
            "errors": errors[-100:],
        }

    @staticmethod
    def _problem_evidence(session: Session, problem_id: str) -> list[DomainAdmissionEvidence]:
        entities = session.scalars(
            select(AdmissionEvidence)
            .where(AdmissionEvidence.problem_id == problem_id)
            .order_by(AdmissionEvidence.created_at, AdmissionEvidence.id)
        ).all()
        return [
            DomainAdmissionEvidence(
                id=item.id,
                generation_batch_id=item.generation_batch_id,
                problem_id=item.problem_id,
                solution_id=item.solution_id,
                evidence_type=item.evidence_type,
                producer_type=EvidenceProducerType(item.producer_type),
                status=AdmissionEvidenceStatus(item.status),
                model_version_id=item.model_version_id,
                prompt_version_id=item.prompt_version_id,
                verifier_version_id=item.verifier_version_id,
                is_blocking=item.is_blocking,
                summary=item.summary,
                payload=item.payload_json,
                evidence_hash=item.evidence_hash,
                created_at=GenerationBatchAdminRepository._utc(item.created_at),
            )
            for item in entities
        ]

    @staticmethod
    def _persist_problem_transition(
        session: Session, *, problem: KnowledgeProblem, transition, actor_id: str
    ) -> None:
        changed_at = GenerationBatchAdminRepository._now()
        next_version = problem.status_version + 1
        session.add(ProblemStatusTransition(
            problem_id=problem.id,
            from_status=transition.previous_status.value,
            to_status=transition.current_status.value,
            reason=transition.status_reason,
            revision_attempts=transition.revision_attempts,
            status_version=next_version,
            checked_requirements_json=[
                "batch_approved_content_withdrawal",
                *transition.checked_requirements,
            ],
            actor_type="admin",
            actor_id=actor_id,
            created_at=changed_at,
        ))
        problem.content_status = transition.current_status.value
        problem.status_reason = transition.status_reason
        problem.revision_attempts = transition.revision_attempts
        problem.status_version = next_version
        problem.status_changed_at = changed_at

    @staticmethod
    def _refresh_counts(session: Session, batch: GenerationBatch) -> None:
        batch.approved_count = session.scalar(
            select(func.count(KnowledgeProblem.id)).where(
                KnowledgeProblem.generation_batch_id == batch.id,
                KnowledgeProblem.content_status.in_(["approved", "indexed"]),
            )
        ) or 0
        batch.quarantined_count = session.scalar(
            select(func.count(KnowledgeProblem.id)).where(
                KnowledgeProblem.generation_batch_id == batch.id,
                KnowledgeProblem.content_status == "quarantined",
            )
        ) or 0

    @staticmethod
    def _add_event(
        session: Session,
        *,
        batch: GenerationBatch,
        action: str,
        previous: GenerationBatchStatus,
        current: GenerationBatchStatus,
        reason: str,
        actor_id: str,
        payload: dict,
        related_batch_id: str | None = None,
    ) -> None:
        session.add(GenerationBatchManagementEvent(
            generation_batch_id=batch.id,
            related_batch_id=related_batch_id,
            action=action,
            previous_status=previous.value,
            current_status=current.value,
            reason=reason,
            actor_type="admin",
            actor_id=actor_id,
            payload_json=payload,
        ))

    @staticmethod
    def _detail_query():
        return select(GenerationBatch).options(
            selectinload(GenerationBatch.question_generation_job),
            selectinload(GenerationBatch.management_events),
        )

    def _reload_detail(self, session: Session, batch_id: str) -> GenerationBatchAdminDetail:
        session.flush()
        entity = session.scalar(self._detail_query().where(GenerationBatch.id == batch_id))
        if entity is None:
            raise GenerationBatchNotFound(batch_id)
        return self._detail(entity)

    @classmethod
    def _item(cls, entity: GenerationBatch) -> GenerationBatchAdminItem:
        job = entity.question_generation_job
        return GenerationBatchAdminItem(
            id=entity.id,
            batch_key=entity.batch_key,
            purpose=entity.purpose,
            subject=entity.subject,
            grade_band=entity.grade_band,
            topic_code=entity.topic_code,
            requested_count=entity.requested_count,
            generated_count=entity.generated_count,
            approved_count=entity.approved_count,
            quarantined_count=entity.quarantined_count,
            failed_count=entity.failed_count,
            status=GenerationBatchStatus(entity.status),
            model_version_id=entity.model_version_id,
            prompt_version_id=entity.prompt_version_id,
            job_id=job.id if job else None,
            attempt_count=job.attempt_count if job else 0,
            status_reason=job.status_reason if job else None,
            started_at=cls._optional_utc(entity.started_at),
            finished_at=cls._optional_utc(entity.finished_at),
            created_at=cls._utc(entity.created_at),
            updated_at=cls._utc(entity.updated_at),
        )

    @classmethod
    def _detail(cls, entity: GenerationBatch) -> GenerationBatchAdminDetail:
        base = cls._item(entity).model_dump()
        job = entity.question_generation_job
        return GenerationBatchAdminDetail(
            **base,
            config=entity.config_json or {},
            budget=job.budget_json if job else None,
            usage=job.usage_json if job else None,
            output=job.output_json if job else None,
            events=[
                GenerationBatchEventView(
                    id=item.id,
                    action=item.action,
                    previous_status=GenerationBatchStatus(item.previous_status),
                    current_status=GenerationBatchStatus(item.current_status),
                    reason=item.reason,
                    actor_type=item.actor_type,
                    actor_id=item.actor_id,
                    related_batch_id=item.related_batch_id,
                    payload=item.payload_json or {},
                    created_at=cls._utc(item.created_at),
                )
                for item in entity.management_events
            ],
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @staticmethod
    def _optional_utc(value: datetime | None) -> datetime | None:
        return GenerationBatchAdminRepository._utc(value) if value else None
