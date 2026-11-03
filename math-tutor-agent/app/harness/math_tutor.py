from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

from app.agents.tutoring_team import TeachingOrchestrator
from app.agents.similar_practice import (
    ConstrainedSimilarPracticeAgent,
    SimilarPracticeGenerationError,
)
from app.cache.base import RuntimeCache, RuntimeCoordinationUnavailable, SessionLockBusy
from app.core.product_scope import MVP_GRADE_LABEL, MVP_SUBJECT_LABEL
from app.domain.schemas import LearningRecord, TutoringSession
from app.domain.tutoring import TutoringStatus
from app.harness.contracts import (
    HarnessBudget,
    HarnessBudgetExceeded,
    HarnessCoordinationUnavailable,
    HarnessRunResult,
    HarnessSessionBusy,
    HarnessSessionConflict,
    HarnessSessionNotFound,
    HarnessPracticeUnavailable,
    HarnessTraceStep,
)
from app.providers.llm import llm_provider, llm_registry
from app.repositories.base import SessionRepository
from app.repositories.base import SessionVersionConflict

if TYPE_CHECKING:
    from app.services.content_integrity import ContentIntegrityService


logger = logging.getLogger(__name__)


class MathTutorAgentHarness:
    """中文：定义“math·tutor·智能体·harness”类，封装该职责相关的数据与行为。
    English: Defines the math tutor agent harness class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Single runtime entry point for every adapter that invokes the tutoring team.
    """

    def __init__(
        self,
        repository: SessionRepository,
        orchestrator: TeachingOrchestrator,
        budget: HarnessBudget,
        runtime_cache: RuntimeCache,
        content_integrity: ContentIntegrityService | None = None,
        practice_agent: ConstrainedSimilarPracticeAgent | None = None,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.repository = repository
        self.orchestrator = orchestrator
        self.budget = budget
        self.runtime_cache = runtime_cache
        self.content_integrity = content_integrity
        self.practice_agent = practice_agent

    def start_session(
        self,
        question: str,
        student_user_id: str,
        knowledge_problem_id: str | None = None,
        llm_model_id: str | None = None,
        practice_context: dict | None = None,
    ) -> HarnessRunResult:
        """中文：处理“启动·会话”相关操作。
        English: Handles the start session operation.
        """
        run_id = str(uuid4())
        started = perf_counter()
        self._reserve_calls(4 + 2 * self.orchestrator.max_revision_attempts)
        selected = llm_registry.resolve(
            llm_model_id,
            require_available=llm_model_id is not None,
        )
        selected_model_id = llm_registry.model_id(
            selected.provider_id, selected.model_name
        )
        with llm_provider.use_model(
            selected_model_id,
            require_available=llm_model_id is not None,
        ):
            session, reply = self.orchestrator.create_session(
                question=question,
                subject=MVP_SUBJECT_LABEL,
                grade=MVP_GRADE_LABEL,
                run_id=run_id,
                student_user_id=student_user_id,
                knowledge_problem_id=knowledge_problem_id,
                llm_model_id=selected_model_id,
            )
        if practice_context is not None:
            from app.domain.schemas import AgentArtifact

            if session.status != TutoringStatus.CLARIFYING:
                reply.text = (
                    f"已按你的学习范围生成相似题：{question}\n\n"
                    f"{practice_context['first_step_prompt']}"
                )
                if session.messages and session.messages[-1].role == "assistant":
                    session.messages[-1].content = reply.text
            session.artifacts.append(AgentArtifact(
                run_id=run_id,
                schema_version="1.0",
                agent="constrained_similar_practice",
                kind="practice_constraints",
                payload={key: value for key, value in practice_context.items() if key != "first_step_prompt"},
                confidence=1.0,
            ))
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
        """中文：处理“执行·turn”相关操作。
        English: Handles the run turn operation.
        """
        if intent == "practice" or any(token in message for token in ("相似题", "练习一下")):
            return self.start_practice_session(
                session_id,
                message,
                client_turn_id=client_turn_id,
            )
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
                with llm_provider.use_model(
                    session.llm_model_id,
                    require_available=False,
                ):
                    reply = self.orchestrator.handle_turn(
                        session, message, intent, run_id=run_id
                    )
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

    def start_practice_session(
        self,
        source_session_id: str,
        request_text: str,
        *,
        client_turn_id: str | None = None,
    ) -> HarnessRunResult:
        """中文：处理“启动·练习·会话”相关操作。
        English: Handles the start practice session operation.
        """
        if self.practice_agent is None:
            raise HarnessPracticeUnavailable("相似题生成器未配置")
        try:
            with self.runtime_cache.lock_session(source_session_id):
                if client_turn_id:
                    cached = self.runtime_cache.get_run_result(source_session_id, client_turn_id)
                    if cached is not None:
                        return cached
                source = self.get_session(source_session_id)
                generated = self.practice_agent.run(source, request_text)
                context = generated.public_context(source_session_id)
                context["first_step_prompt"] = generated.first_step_prompt
                result = self.start_session(
                    question=generated.question,
                    student_user_id=source.student_user_id,
                    llm_model_id=source.llm_model_id,
                    practice_context=context,
                )
                if client_turn_id:
                    self.runtime_cache.set_run_result(source_session_id, client_turn_id, result)
                return result
        except SimilarPracticeGenerationError as error:
            raise HarnessPracticeUnavailable(str(error)) from error
        except ValueError as error:
            raise HarnessPracticeUnavailable(str(error)) from error
        except RuntimeCoordinationUnavailable as error:
            raise HarnessCoordinationUnavailable(source_session_id) from error
        except SessionLockBusy as error:
            raise HarnessSessionBusy(source_session_id) from error

    def get_session(self, session_id: str) -> TutoringSession:
        """中文：处理“获取·会话”相关操作。
        English: Handles the get session operation.
        """
        session = self.runtime_cache.get_session(session_id)
        if session is None:
            session = self.repository.get(session_id)
            if session is not None:
                self.runtime_cache.set_session(session)
        if session is None:
            raise HarnessSessionNotFound(session_id)
        return session

    def list_sessions(self, student_user_id: str) -> list[TutoringSession]:
        """中文：处理“列出·sessions”相关操作。
        English: Handles the list sessions operation.
        """
        return self.repository.list(student_user_id)

    def list_learning_records(self, student_user_id: str) -> list[LearningRecord]:
        """中文：处理“列出·学习·records”相关操作。
        English: Handles the list learning records operation.
        """
        return [
            session.record
            for session in self.repository.list(student_user_id)
            if session.status == TutoringStatus.COMPLETED and session.record is not None
        ]

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.orchestrator.close()
        self.runtime_cache.close()
        self.repository.close()
        if self.content_integrity is not None:
            self.content_integrity.close()

    def trace_for_session(self, session_id: str) -> list[HarnessTraceStep]:
        """中文：处理“trace·for·会话”相关操作。
        English: Handles the trace for session operation.
        """
        session = self.get_session(session_id)
        return [self._trace_step(artifact) for artifact in session.artifacts]

    def _reserve_calls(self, required: int) -> None:
        """中文：处理“reserve·calls”相关操作。
        English: Handles the reserve calls operation.
        """
        if required > self.budget.max_agent_calls:
            raise HarnessBudgetExceeded(
                f"Run requires {required} agent calls, budget allows {self.budget.max_agent_calls}"
            )

    def _result(self, run_id: str, session: TutoringSession, reply, started: float) -> HarnessRunResult:
        """中文：处理“结果”相关操作。
        English: Handles the result operation.
        """
        duration_ms = round((perf_counter() - started) * 1000)
        trace = [self._trace_step(item) for item in session.artifacts if item.run_id == run_id]
        timed_out = duration_ms > self.budget.max_duration_ms
        selected_provider = llm_registry.resolve(
            session.llm_model_id,
            require_available=False,
        )
        provider_missing = not selected_provider.available and any(
            item.kind == "verification_report" and not item.payload.get("passed") for item in session.artifacts if item.run_id == run_id
        )
        retrieval_degraded = any(
            item.kind in {"retrieved_textbook_context", "retrieved_teaching_context"}
            and (
                item.status == "failed"
                or item.payload.get("status") == "degraded"
            )
            for item in session.artifacts
            if item.run_id == run_id
        )
        if timed_out:
            degradation_code = "run_timeout"
            reason = "运行超过时间预算"
        elif provider_missing:
            degradation_code = "llm_provider_unavailable"
            reason = "模型未配置，已使用安全降级"
        elif retrieval_degraded:
            degradation_code = "knowledge_retrieval_degraded"
            reason = "知识检索不可用，已回退到原教学链路"
        else:
            degradation_code = None
            reason = None
        result = HarnessRunResult(
            run_id=run_id,
            session=session,
            reply=reply,
            trace=trace,
            duration_ms=duration_ms,
            degraded=bool(reason),
            degradation_code=degradation_code,
            degradation_reason=reason,
        )
        logger.info(
            "Tutoring agent run completed",
            extra={
                "event": "agent.run.completed",
                "run_id": run_id,
                "session_id": session.id,
                "session_status": session.status.value,
                "duration_ms": duration_ms,
                "artifact_kinds": [step.artifact_kind for step in trace],
                "degraded": result.degraded,
                "degradation_code": result.degradation_code,
            },
        )
        return result

    @staticmethod
    def _trace_step(artifact) -> HarnessTraceStep:
        """中文：处理“trace·step”相关操作。
        English: Handles the trace step operation.
        """
        return HarnessTraceStep(
            run_id=artifact.run_id,
            agent=artifact.agent,
            artifact_kind=artifact.kind,
            status=artifact.status,
            confidence=artifact.confidence,
            duration_ms=artifact.duration_ms,
        )
