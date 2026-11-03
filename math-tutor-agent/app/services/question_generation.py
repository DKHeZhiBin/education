from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.question_variation import QuestionVariationAgent, QuestionVariationError
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.generation import GenerationBatchStatus
from app.domain.knowledge import ProblemContentStatus
from app.domain.question_generation import (
    CandidateGenerationOutcome,
    QuestionGenerationCandidateResult,
    QuestionGenerationBudget,
    QuestionGenerationJobInput,
    QuestionGenerationJobOutput,
    QuestionGenerationStopReason,
    QuestionGenerationUsage,
    candidate_key,
)
from app.models.generation import GenerationBatch, QuestionGenerationJob
from app.models.knowledge import KnowledgeProblem
from app.providers.llm import LLMProvider, RoutingLLMProvider, llm_provider
from app.repositories.question_generation import QuestionGenerationJobRepository
from app.services.candidate_validation import (
    CandidateValidationService,
    candidate_validation_service,
)


class QuestionGenerationJobNotFound(LookupError):
    """中文：定义“问题·生成·任务·not·found”类，封装该职责相关的数据与行为。
    English: Defines the question generation job not found class and encapsulates data and behavior for that responsibility.
    """
    pass


class QuestionGenerationExecutionConflict(RuntimeError):
    """中文：定义“问题·生成·execution·conflict”类，封装该职责相关的数据与行为。
    English: Defines the question generation execution conflict class and encapsulates data and behavior for that responsibility.
    """
    pass


class QuestionGenerationService:
    """中文：定义“问题·生成·服务”类，封装该职责相关的数据与行为。
    English: Defines the question generation service class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Execute a resumable, budgeted batch of mother-problem variations.
    """

    TERMINAL = {"completed", "partial_failed", "failed", "cancelled"}

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        provider: LLMProvider = llm_provider,
        validation_service: CandidateValidationService = candidate_validation_service,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())
        self.repository = QuestionGenerationJobRepository()
        self.provider = provider
        self.agent = QuestionVariationAgent(provider)
        self.validation_service = validation_service

    def create_and_run(
        self, request: QuestionGenerationJobInput
    ) -> QuestionGenerationJobOutput:
        """中文：处理“创建·and·执行”相关操作。
        English: Handles the create and run operation.
        """
        with self.session_factory.begin() as session:
            registration = self.repository.register(session, request)
            job_id = registration.job.id
            should_run = registration.created or registration.batch.status == "pending"
        if not should_run:
            return self.get(job_id)
        return self.run(job_id)

    def run(self, job_id: str) -> QuestionGenerationJobOutput:
        """中文：处理“执行”相关操作。
        English: Handles the run operation.
        """
        initial = self._start_or_resume(job_id)
        if initial.status in {
            GenerationBatchStatus.COMPLETED,
            GenerationBatchStatus.PARTIAL_FAILED,
            GenerationBatchStatus.FAILED,
            GenerationBatchStatus.CANCELLED,
        }:
            return initial

        with self.session_factory() as session:
            context = self.repository.load_agent_context(session, job_id)
            job = session.get(QuestionGenerationJob, job_id)
            budget = job.budget_json
        candidates = list(initial.candidates)
        usage = initial.usage
        errors = list(initial.errors)
        completed_ordinals = {item.ordinal for item in candidates}
        attempt_started = monotonic()
        attempt_base_duration_ms = usage.duration_ms
        configured_budget = QuestionGenerationBudget.model_validate(budget)

        for ordinal in range(context.generation_input.requested_count):
            if ordinal in completed_ordinals:
                continue
            live_status = self._batch_status(job_id)
            if live_status == "paused":
                return self._save_nonterminal(
                    job_id, GenerationBatchStatus.PAUSED, candidates, usage,
                    errors, initial.started_at, attempt_started,
                    attempt_base_duration_ms,
                )
            if live_status == "cancelled":
                errors.append("cancelled:generation batch was cancelled")
                candidates.extend(self._skipped_positions(
                    context, completed_ordinals | {item.ordinal for item in candidates},
                    "cancelled", "generation batch was cancelled",
                ))
                return self._finish(
                    job_id, GenerationBatchStatus.CANCELLED,
                    QuestionGenerationStopReason.CANCELLED,
                    candidates, usage, errors, initial.started_at, attempt_started,
                    attempt_base_duration_ms,
                )
            if not usage.can_reserve(
                configured_budget, model_calls=1, candidates=1
            ):
                candidates.extend(self._skipped_positions(
                    context, completed_ordinals | {item.ordinal for item in candidates},
                    "budget_exhausted", "generation budget was exhausted",
                ))
                return self._finish_by_outcomes(
                    job_id, QuestionGenerationStopReason.BUDGET_EXHAUSTED,
                    candidates, usage, errors, initial.started_at, attempt_started,
                    attempt_base_duration_ms,
                )

            mother = context.mothers[ordinal % len(context.mothers)]
            identity = candidate_key(context.idempotency_key_hash, ordinal)
            call_started = monotonic()
            call_counted = False
            try:
                if isinstance(self.provider, RoutingLLMProvider):
                    with self.provider.use_provider_model(
                        context.provider_id, context.model_name
                    ):
                        draft = self.agent.run(
                            mother=mother,
                            generation_input=context.generation_input,
                            candidate_key=identity,
                            ordinal=ordinal,
                            expected_model_name=context.model_name,
                            versioned_prompt=context.versioned_prompt,
                        )
                else:
                    draft = self.agent.run(
                        mother=mother,
                        generation_input=context.generation_input,
                        candidate_key=identity,
                        ordinal=ordinal,
                        expected_model_name=context.model_name,
                        versioned_prompt=context.versioned_prompt,
                    )
                call_ms = max(0, int((monotonic() - call_started) * 1000))
                usage = self._increment_usage(usage, call_ms)
                call_counted = True
                with self.session_factory.begin() as session:
                    result = self.repository.persist_candidate(
                        session,
                        job_id=job_id,
                        ordinal=ordinal,
                        mother_problem_id=mother.id,
                        draft=draft,
                        allow_paused_inflight=True,
                    )
                    candidates.append(result)
                    _, locked_batch = self._job_and_batch(session, job_id, lock=True)
                    progress_status = (
                        GenerationBatchStatus.PAUSED
                        if locked_batch.status == "paused"
                        else GenerationBatchStatus.RUNNING
                    )
                    self._persist_progress(
                        session, job_id, progress_status,
                        candidates, usage, errors, initial.started_at,
                    )
                if progress_status == GenerationBatchStatus.PAUSED:
                    return self._save_nonterminal(
                        job_id, GenerationBatchStatus.PAUSED, candidates, usage,
                        errors, initial.started_at, attempt_started,
                        attempt_base_duration_ms,
                    )
            except QuestionVariationError as error:
                call_ms = max(0, int((monotonic() - call_started) * 1000))
                usage = self._increment_usage(usage, call_ms)
                failure = self._failure(ordinal, identity, mother.id, error.code, str(error))
                candidates.append(failure)
                errors.append(f"{ordinal}:{error.code}:{error}"[:1000])
                live_status = self._batch_status(job_id)
                if live_status == "cancelled":
                    errors.append("cancelled:generation batch was cancelled")
                    candidates.extend(self._skipped_positions(
                        context, {item.ordinal for item in candidates},
                        "cancelled", "generation batch was cancelled",
                    ))
                    return self._finish(
                        job_id, GenerationBatchStatus.CANCELLED,
                        QuestionGenerationStopReason.CANCELLED,
                        candidates, usage, errors, initial.started_at, attempt_started,
                        attempt_base_duration_ms,
                    )
                if live_status == "paused":
                    return self._save_nonterminal(
                        job_id, GenerationBatchStatus.PAUSED, candidates, usage,
                        errors, initial.started_at, attempt_started,
                        attempt_base_duration_ms,
                    )
                self._save_progress(
                    job_id, candidates, usage, errors, initial.started_at
                )
                if error.code == "provider_unavailable":
                    candidates.extend(self._skipped_positions(
                        context, {item.ordinal for item in candidates},
                        "provider_unavailable", "LLM provider is unavailable",
                    ))
                    return self._finish_by_outcomes(
                        job_id, QuestionGenerationStopReason.PROVIDER_UNAVAILABLE,
                        candidates, usage, errors, initial.started_at, attempt_started,
                        attempt_base_duration_ms,
                    )
            except Exception as error:
                if not call_counted:
                    call_ms = max(0, int((monotonic() - call_started) * 1000))
                    usage = self._increment_usage(usage, call_ms)
                live_status = self._batch_status(job_id)
                if live_status == "cancelled":
                    errors.append("cancelled:generation batch was cancelled")
                    candidates.append(self._failure(
                        ordinal,
                        identity,
                        mother.id,
                        "cancelled_before_persistence",
                        "generation completed but cancellation prevented persistence",
                    ))
                    candidates.extend(self._skipped_positions(
                        context, {item.ordinal for item in candidates},
                        "cancelled", "generation batch was cancelled",
                    ))
                    return self._finish(
                        job_id, GenerationBatchStatus.CANCELLED,
                        QuestionGenerationStopReason.CANCELLED,
                        candidates, usage, errors, initial.started_at, attempt_started,
                        attempt_base_duration_ms,
                    )
                if live_status == "paused":
                    usage = usage.model_copy(update={
                        "candidates_attempted": max(
                            0, usage.candidates_attempted - 1
                        ),
                    })
                    return self._save_nonterminal(
                        job_id, GenerationBatchStatus.PAUSED, candidates, usage,
                        errors, initial.started_at, attempt_started,
                        attempt_base_duration_ms,
                    )
                failure = self._failure(
                    ordinal, identity, mother.id, "candidate_persistence_failed", str(error)
                )
                candidates.append(failure)
                errors.append(f"{ordinal}:candidate_persistence_failed:{error}"[:1000])
                self._save_progress(
                    job_id, candidates, usage, errors, initial.started_at
                )

        stop_reason = self._stop_reason_for(candidates)
        return self._finish_by_outcomes(
            job_id, stop_reason, candidates, usage, errors,
            initial.started_at, attempt_started, attempt_base_duration_ms,
        )

    def get(self, job_id: str) -> QuestionGenerationJobOutput:
        """中文：处理“获取”相关操作。
        English: Handles the get operation.
        """
        with self.session_factory() as session:
            job, batch = self._job_and_batch(session, job_id)
            return self._output(job, batch)

    def _start_or_resume(self, job_id: str) -> QuestionGenerationJobOutput:
        """中文：处理“启动·or·resume”相关操作。
        English: Handles the start or resume operation.
        """
        with self.session_factory.begin() as session:
            job, batch = self._job_and_batch(session, job_id, lock=True)
            if batch.status in self.TERMINAL:
                return self._output(job, batch)
            starts_attempt = batch.status in {"pending", "paused"}
            if starts_attempt:
                budget = job.budget_json
                maximum_attempts = int(budget.get("max_execution_attempts", 1))
                if job.attempt_count >= maximum_attempts:
                    raise QuestionGenerationExecutionConflict(
                        "generation job execution attempt limit is exhausted"
                    )
            now = self._now()
            batch.status = "running"
            batch.started_at = batch.started_at or now
            batch.finished_at = None
            if starts_attempt:
                job.attempt_count += 1
            job.status_reason = None
            job.last_error_code = None
            if job.output_json is None:
                job.output_json = QuestionGenerationJobOutput(
                    job_id=job.id,
                    generation_batch_id=batch.id,
                    status=GenerationBatchStatus.RUNNING,
                    usage=QuestionGenerationUsage.model_validate(job.usage_json),
                    started_at=batch.started_at,
                ).model_dump(mode="json")
            return self._output(job, batch)

    def _save_progress(self, job_id, candidates, usage, errors, started_at):
        """中文：处理“保存·progress”相关操作。
        English: Handles the save progress operation.
        """
        with self.session_factory.begin() as session:
            self._persist_progress(
                session, job_id, GenerationBatchStatus.RUNNING,
                candidates, usage, errors, started_at,
            )

    def _save_nonterminal(
        self, job_id, status, candidates, usage, errors, started_at, attempt_started,
        attempt_base_duration_ms,
    ):
        """中文：处理“保存·nonterminal”相关操作。
        English: Handles the save nonterminal operation.
        """
        usage = self._with_attempt_duration(
            usage, attempt_started, attempt_base_duration_ms
        )
        with self.session_factory.begin() as session:
            self._persist_progress(
                session, job_id, status, candidates, usage, errors, started_at
            )
            job, batch = self._job_and_batch(session, job_id)
            return self._output(job, batch)

    def _finish_by_outcomes(
        self, job_id, stop_reason, candidates, usage, errors, started_at,
        attempt_started, attempt_base_duration_ms,
    ):
        """中文：处理“finish·by·outcomes”相关操作。
        English: Handles the finish by outcomes operation.
        """
        created = sum(
            item.outcome == CandidateGenerationOutcome.CANDIDATE_CREATED
            for item in candidates
        )
        status = (
            GenerationBatchStatus.COMPLETED
            if created == len(candidates)
            else GenerationBatchStatus.PARTIAL_FAILED
            if created > 0
            else GenerationBatchStatus.FAILED
        )
        output = self._finish(
            job_id, status, stop_reason, candidates, usage, errors,
            started_at, attempt_started, attempt_base_duration_ms,
        )
        with self.session_factory() as session:
            job, _ = self._job_and_batch(session, job_id)
            generation_input = job.input_json
        if (
            generation_input.get("auto_validate", True)
            and created > 0
            and status in {
                GenerationBatchStatus.COMPLETED,
                GenerationBatchStatus.PARTIAL_FAILED,
            }
        ):
            validation = self.validation_service.validate_batch(
                output.generation_batch_id,
                verifier_profile=generation_input["verifier_profile"],
            )
            return self._attach_validation(job_id, validation)
        return output

    def _attach_validation(self, job_id, validation):
        """中文：处理“attach·验证”相关操作。
        English: Handles the attach validation operation.
        """
        with self.session_factory.begin() as session:
            job, batch = self._job_and_batch(session, job_id, lock=True)
            output = QuestionGenerationJobOutput.model_validate(job.output_json)
            statuses = dict(session.execute(
                select(KnowledgeProblem.id, KnowledgeProblem.content_status).where(
                    KnowledgeProblem.generation_batch_id == batch.id
                )
            ).all())
            candidates = [
                item.model_copy(update={
                    "content_status": ProblemContentStatus(statuses[item.problem_id])
                })
                if item.problem_id in statuses else item
                for item in output.candidates
            ]
            usage = output.usage.model_copy(update={
                "model_calls": output.usage.model_calls + validation.model_calls,
            })
            output = output.model_copy(update={
                "candidates": candidates,
                "usage": usage,
                "validation": validation,
            })
            job.usage_json = usage.model_dump(mode="json")
            job.output_json = output.model_dump(mode="json")
            session.flush()
            return output

    def _finish(
        self, job_id, status, stop_reason, candidates, usage, errors,
        started_at, attempt_started, attempt_base_duration_ms,
    ):
        """中文：处理“finish”相关操作。
        English: Handles the finish operation.
        """
        usage = self._with_attempt_duration(
            usage, attempt_started, attempt_base_duration_ms
        )
        with self.session_factory.begin() as session:
            self._persist_progress(
                session, job_id, status, candidates, usage, errors,
                started_at, stop_reason=stop_reason, finished_at=self._now(),
            )
            job, batch = self._job_and_batch(session, job_id)
            return self._output(job, batch)

    def _persist_progress(
        self, session, job_id, status, candidates, usage, errors, started_at,
        *, stop_reason=None, finished_at=None,
    ):
        """中文：处理“persist·progress”相关操作。
        English: Handles the persist progress operation.
        """
        job, batch = self._job_and_batch(session, job_id, lock=True)
        output = QuestionGenerationJobOutput(
            job_id=job.id,
            generation_batch_id=batch.id,
            status=status,
            stop_reason=stop_reason,
            candidates=sorted(candidates, key=lambda item: item.ordinal),
            usage=usage,
            started_at=started_at,
            finished_at=finished_at,
            errors=errors[-100:],
        )
        job.usage_json = usage.model_dump(mode="json")
        job.output_json = output.model_dump(mode="json")
        job.last_error_code = errors[-1].split(":", 2)[1] if errors else None
        job.status_reason = errors[-1] if errors else None
        batch.status = status.value
        batch.failed_count = sum(
            item.outcome != CandidateGenerationOutcome.CANDIDATE_CREATED
            for item in candidates
        )
        if finished_at is not None:
            batch.finished_at = finished_at
        session.flush()

    def _batch_status(self, job_id: str) -> str:
        """中文：处理“批次·状态”相关操作。
        English: Handles the batch status operation.
        """
        with self.session_factory() as session:
            _, batch = self._job_and_batch(session, job_id)
            return batch.status

    @staticmethod
    def _job_and_batch(session, job_id, lock=False):
        """中文：处理“任务·and·批次”相关操作。
        English: Handles the job and batch operation.
        """
        query = select(QuestionGenerationJob).where(QuestionGenerationJob.id == job_id)
        if lock:
            query = query.with_for_update()
        job = session.scalar(query)
        if job is None:
            raise QuestionGenerationJobNotFound("question generation job not found")
        batch = session.get(GenerationBatch, job.generation_batch_id, with_for_update=lock)
        if batch is None:
            raise QuestionGenerationJobNotFound("generation batch not found")
        return job, batch

    @staticmethod
    def _output(job, batch):
        """中文：处理“output”相关操作。
        English: Handles the output operation.
        """
        if job.output_json is not None:
            return QuestionGenerationJobOutput.model_validate(job.output_json)
        return QuestionGenerationJobOutput(
            job_id=job.id,
            generation_batch_id=batch.id,
            status=GenerationBatchStatus(batch.status),
            usage=QuestionGenerationUsage.model_validate(job.usage_json),
            started_at=batch.started_at,
        )

    @staticmethod
    def _increment_usage(usage: QuestionGenerationUsage, duration_ms: int):
        """中文：处理“increment·usage”相关操作。
        English: Handles the increment usage operation.
        """
        return usage.model_copy(update={
            "model_calls": usage.model_calls + 1,
            "duration_ms": usage.duration_ms + duration_ms,
            "candidates_attempted": usage.candidates_attempted + 1,
        })

    @staticmethod
    def _with_attempt_duration(usage, attempt_started, attempt_base_duration_ms):
        """中文：处理“with·attempt·duration”相关操作。
        English: Handles the with attempt duration operation.
        """
        elapsed = max(0, int((monotonic() - attempt_started) * 1000))
        return usage.model_copy(update={
            "duration_ms": max(
                usage.duration_ms,
                attempt_base_duration_ms + elapsed,
            ),
        })

    @staticmethod
    def _stop_reason_for(candidates):
        """中文：处理“停止·reason·for”相关操作。
        English: Handles the stop reason for operation.
        """
        if all(
            item.outcome == CandidateGenerationOutcome.CANDIDATE_CREATED
            for item in candidates
        ):
            return QuestionGenerationStopReason.COMPLETED
        if any(
            item.failure_code == "candidate_persistence_failed"
            for item in candidates
        ):
            return QuestionGenerationStopReason.PERSISTENCE_FAILED
        return QuestionGenerationStopReason.INVALID_MODEL_OUTPUT

    @staticmethod
    def _failure(ordinal, identity, mother_id, code, message):
        """中文：处理“failure”相关操作。
        English: Handles the failure operation.
        """
        return QuestionGenerationCandidateResult(
            ordinal=ordinal,
            candidate_key=identity,
            mother_problem_id=mother_id,
            outcome=CandidateGenerationOutcome.GENERATION_FAILED,
            failure_code=code[:64],
            failure_message=(message or code)[:1000],
        )

    @staticmethod
    def _skipped_positions(context, accounted, code, message):
        """中文：处理“skipped·positions”相关操作。
        English: Handles the skipped positions operation.
        """
        results = []
        for ordinal in range(context.generation_input.requested_count):
            if ordinal in accounted:
                continue
            mother = context.mothers[ordinal % len(context.mothers)]
            results.append(QuestionGenerationCandidateResult(
                ordinal=ordinal,
                candidate_key=candidate_key(context.idempotency_key_hash, ordinal),
                mother_problem_id=mother.id,
                outcome=CandidateGenerationOutcome.SKIPPED,
                failure_code=code,
                failure_message=message,
            ))
        return results

    @staticmethod
    def _now():
        """中文：处理“now”相关操作。
        English: Handles the now operation.
        """
        return datetime.now(timezone.utc).replace(tzinfo=None)


question_generation_service = QuestionGenerationService()
