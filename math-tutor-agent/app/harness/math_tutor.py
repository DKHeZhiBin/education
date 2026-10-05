from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

from app.agents.tutoring_team import TeachingOrchestrator
from app.cache.base import RuntimeCache, RuntimeCoordinationUnavailable, SessionLockBusy
from app.domain.schemas import LearningRecord, TutoringSession
from app.harness.contracts import (
    HarnessBudget,
    HarnessBudgetExceeded,
    HarnessCoordinationUnavailable,
    HarnessRunResult,
    HarnessSessionBusy,
    HarnessSessionConflict,
    HarnessSessionNotFound,
    HarnessTraceStep,
)
from app.providers.llm import llm_provider
from app.repositories.base import SessionRepository
from app.repositories.base import SessionVersionConflict

if TYPE_CHECKING:
    from app.services.content_integrity import ContentIntegrityService


class MathTutorAgentHarness:
    """Single runtime entry point for every adapter that invokes the tutoring team."""

    def __init__(
        self,
        repository: SessionRepository,
        orchestrator: TeachingOrchestrator,
        budget: HarnessBudget,
        runtime_cache: RuntimeCache,
        content_integrity: ContentIntegrityService | None = None,
    ) -> None:
        self.repository = repository
        self.orchestrator = orchestrator
        self.budget = budget
        self.runtime_cache = runtime_cache
        self.content_integrity = content_integrity

    def start_session(
        self,
        question: str,
        subject: str,
        grade: str,
        student_user_id: str,
        knowledge_problem_id: str | None = None,
    ) -> HarnessRunResult:
        run_id = str(uuid4())
        started = perf_counter()
        self._reserve_calls(4 + 2 * self.orchestrator.max_revision_attempts)
        session, reply = self.orchestrator.create_session(
            question=question,
            subject=subject,
            grade=grade,
            run_id=run_id,
            student_user_id=student_user_id,
            knowledge_problem_id=knowledge_problem_id,
        )
        self.repository.save(session)
        if self.content_integrity is not None:
            self.content_integrity.process_runtime_signals(session, run_id)
        self.runtime_cache.set_session(session)
        return self._result(run_id, session, reply, started)

    def run_turn(
        self,
        session_id: str,
        message: str,
        intent: str,
        client_turn_id: str | None = None,
    ) -> HarnessRunResult:
        try:
            with self.runtime_cache.lock_session(session_id):
                if client_turn_id:
                    cached = self.runtime_cache.get_run_result(session_id, client_turn_id)
                    if cached is not None:
                        return cached

                session = self.get_session(session_id)
                run_id = str(uuid4())
                started = perf_counter()
                required_calls = (
                    4 + 2 * self.orchestrator.max_revision_attempts
                    if session.status.value == "clarifying"
                    else 3 if intent == "complete" else 2
                )
                self._reserve_calls(required_calls)
                previous_message_count = len(session.messages)
                reply = self.orchestrator.handle_turn(session, message, intent, run_id=run_id)
                for new_message in session.messages[previous_message_count:]:
                    if new_message.role == "student":
                        new_message.intent = intent
                        new_message.client_turn_id = client_turn_id
                        break
                self.repository.save(session)
                if self.content_integrity is not None:
                    self.content_integrity.process_runtime_signals(session, run_id)
                self.runtime_cache.set_session(session)
                result = self._result(run_id, session, reply, started)
                if client_turn_id:
                    self.runtime_cache.set_run_result(session_id, client_turn_id, result)
                return result
        except RuntimeCoordinationUnavailable as error:
            raise HarnessCoordinationUnavailable(session_id) from error
        except SessionVersionConflict as error:
            self.runtime_cache.delete_session(session_id)
            raise HarnessSessionConflict(session_id) from error
        except SessionLockBusy as error:
            raise HarnessSessionBusy(session_id) from error

    def get_session(self, session_id: str) -> TutoringSession:
        session = self.runtime_cache.get_session(session_id)
        if session is None:
            session = self.repository.get(session_id)
            if session is not None:
                self.runtime_cache.set_session(session)
        if session is None:
            raise HarnessSessionNotFound(session_id)
        return session

    def list_sessions(self, student_user_id: str) -> list[TutoringSession]:
        return self.repository.list(student_user_id)

    def list_learning_records(self, student_user_id: str) -> list[LearningRecord]:
        return [
            session.record
            for session in self.repository.list(student_user_id)
            if session.record is not None
        ]

    def close(self) -> None:
        self.orchestrator.close()
        self.runtime_cache.close()
        self.repository.close()
        if self.content_integrity is not None:
            self.content_integrity.close()

    def trace_for_session(self, session_id: str) -> list[HarnessTraceStep]:
        session = self.get_session(session_id)
        return [self._trace_step(artifact) for artifact in session.artifacts]

    def _reserve_calls(self, required: int) -> None:
        if required > self.budget.max_agent_calls:
            raise HarnessBudgetExceeded(
                f"Run requires {required} agent calls, budget allows {self.budget.max_agent_calls}"
            )

    def _result(self, run_id: str, session: TutoringSession, reply, started: float) -> HarnessRunResult:
        duration_ms = round((perf_counter() - started) * 1000)
        trace = [self._trace_step(item) for item in session.artifacts if item.run_id == run_id]
        timed_out = duration_ms > self.budget.max_duration_ms
        provider_missing = not llm_provider.available and any(
            item.kind == "verification_report" and not item.payload.get("passed") for item in session.artifacts if item.run_id == run_id
        )
        retrieval_degraded = any(
            item.kind == "retrieved_teaching_context"
            and (
                item.status == "failed"
                or item.payload.get("status") == "degraded"
            )
            for item in session.artifacts
            if item.run_id == run_id
        )
        reason = (
            "运行超过时间预算"
            if timed_out
            else "模型未配置，已使用安全降级"
            if provider_missing
            else "知识检索不可用，已回退到原教学链路"
            if retrieval_degraded
            else None
        )
        return HarnessRunResult(
            run_id=run_id,
            session=session,
            reply=reply,
            trace=trace,
            duration_ms=duration_ms,
            degraded=bool(reason),
            degradation_reason=reason,
        )

    @staticmethod
    def _trace_step(artifact) -> HarnessTraceStep:
        return HarnessTraceStep(
            run_id=artifact.run_id,
            agent=artifact.agent,
            artifact_kind=artifact.kind,
            status=artifact.status,
            confidence=artifact.confidence,
            duration_ms=artifact.duration_ms,
        )
