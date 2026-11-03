from fastapi import HTTPException, status

from app.api.errors import tutoring_error
from app.agents.similar_practice import SimilarPracticeGenerationError
from app.domain.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    LearningRecord,
    SessionSummary,
    TurnRequest,
    TurnResponse,
    TutoringSession,
)
from app.domain.auth import AuthenticatedUser
from app.domain.practice import KnowledgeExamplePracticeRequest
from app.domain.parent_report import (
    ParentKnowledgeSummary,
    ParentReportOverview,
    ParentReportResponse,
    ParentReportSampleScope,
)
from app.domain.content_issue import (
    ContentIssueReportView,
    StudentContentIssueRequest,
)
from app.harness.contracts import (
    HarnessBudgetExceeded,
    HarnessCoordinationUnavailable,
    HarnessSessionBusy,
    HarnessSessionConflict,
    HarnessSessionNotFound,
    HarnessPracticeUnavailable,
    HarnessTraceStep,
)
from app.harness.factory import build_math_tutor_harness
from app.services.auth import auth_service
from app.services.content_integrity import (
    ContentIssueReferenceInvalid,
    content_integrity_service,
)
from app.providers.llm import LLMModelNotFound, LLMModelUnavailable
from app.providers.llm import llm_registry
from app.repositories.curriculum import KnowledgePracticeSourceNotFound
from app.services.curriculum import curriculum_service


class TutoringService:
    """中文：定义“tutoring·服务”类，封装该职责相关的数据与行为。
    English: Defines the tutoring service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.harness = build_math_tutor_harness()

    def create_session(
        self,
        request: CreateSessionRequest,
        actor: AuthenticatedUser,
    ) -> CreateSessionResponse:
        """中文：处理“创建·会话”相关操作。
        English: Handles the create session operation.
        """
        auth_service.require_role(actor, "student")
        try:
            question = (
                content_integrity_service.canonical_problem_statement(request.problem_id)
                if request.problem_id
                else request.question
            )
        except ContentIssueReferenceInvalid as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error(
                    "problem_unavailable",
                    "题目不存在或当前不可用于学习。",
                ),
            ) from error
        result = self._run(lambda: self.harness.start_session(
            question=question,
            student_user_id=actor.id,
            knowledge_problem_id=request.problem_id,
            llm_model_id=request.llm_model_id,
        ))
        return CreateSessionResponse(
            session=result.session,
            reply=result.reply,
            run_id=result.run_id,
            trace=[step.model_dump() for step in result.trace],
            duration_ms=result.duration_ms,
            degraded=result.degraded,
            degradation_code=result.degradation_code,
            degradation_reason=result.degradation_reason,
        )

    def create_knowledge_example_practice(
        self,
        request: KnowledgeExamplePracticeRequest,
        actor: AuthenticatedUser,
    ) -> CreateSessionResponse:
        """中文：从知识点中的已发布例题生成相似题并建立独立学习会话。 English: Generates similar practice from a published knowledge example and starts an independent session."""

        auth_service.require_role(actor, "student")
        try:
            source = curriculum_service.knowledge_practice_source(
                request.knowledge_point_code,
                request.content_key,
            )
        except KnowledgePracticeSourceNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error(
                    "knowledge_example_unavailable",
                    "这条例题不存在、尚未发布或不能用于相似题生成。",
                ),
            ) from error

        def generate_and_start():
            if self.harness.practice_agent is None:
                raise HarnessPracticeUnavailable("相似题生成器未配置")
            selected = llm_registry.resolve(
                request.llm_model_id,
                require_available=True,
            )
            profile = request.difficulty_profile()
            try:
                generated = self.harness.practice_agent.run_from_knowledge_example(
                    source,
                    difficulty=profile.level,
                    provider=selected,
                    structure_level=profile.structure_level,
                    reasoning_level=profile.reasoning_level,
                    teaching_goal=profile.teaching_goal,
                    candidate_count=profile.candidate_count,
                    quality_threshold=profile.quality_threshold,
                    numeric_difficulty=profile.numeric_difficulty,
                )
            except SimilarPracticeGenerationError as error:
                raise HarnessPracticeUnavailable(str(error)) from error
            selected_model_id = llm_registry.model_id(
                selected.provider_id,
                selected.model_name,
            )
            practice_context = {
                "origin": "runtime_generated",
                "visibility": "session_only",
                "source_knowledge_point_code": source.knowledge_point_code,
                "source_content_key": source.content_key,
                "difficulty": generated.difficulty,
                "difficulty_level": profile.level,
                "candidate_count": profile.candidate_count,
                "quality_threshold": profile.quality_threshold,
                "knowledge_point_codes": generated.knowledge_point_codes,
                "generator": generated.generator,
                "constraint_check": "passed",
                "client_request_id": request.client_request_id,
                "first_step_prompt": generated.first_step_prompt,
                "structure_level": generated.structure_level,
                "reasoning_level": generated.reasoning_level,
                "teaching_goal": generated.teaching_goal,
                "variation_summary": generated.variation_summary,
                "new_reasoning_step": generated.new_reasoning_step,
                "structure_type": generated.structure_type,
                "relation_form": generated.relation_form,
                "function_family": generated.function_family,
                "key_strategy": generated.key_strategy,
                "verification_summary": generated.verification_summary,
                "source_type": generated.source_type,
                "mother_analysis": (
                    generated.mother_analysis.model_dump(mode="json")
                    if generated.mother_analysis is not None
                    else None
                ),
                "variation_plan": (
                    generated.variation_plan.model_dump(mode="json")
                    if generated.variation_plan is not None
                    else None
                ),
                "mother_mpr": (
                    generated.mother_mpr.model_dump(mode="json")
                    if generated.mother_mpr is not None
                    else None
                ),
                "candidate_mpr": (
                    generated.candidate_mpr.model_dump(mode="json")
                    if generated.candidate_mpr is not None
                    else None
                ),
                "mpr_relation": (
                    generated.mpr_relation.model_dump(mode="json")
                    if generated.mpr_relation is not None
                    else None
                ),
            }
            return self.harness.start_session(
                question=generated.question,
                student_user_id=actor.id,
                llm_model_id=selected_model_id,
                practice_context=practice_context,
            )

        result = self._run(generate_and_start)
        return CreateSessionResponse(
            session=result.session,
            reply=result.reply,
            run_id=result.run_id,
            trace=[step.model_dump() for step in result.trace],
            duration_ms=result.duration_ms,
            degraded=result.degraded,
            degradation_code=result.degradation_code,
            degradation_reason=result.degradation_reason,
        )

    def get_session(self, session_id: str, actor: AuthenticatedUser) -> TutoringSession:
        """中文：处理“获取·会话”相关操作。
        English: Handles the get session operation.
        """
        try:
            session = self.harness.get_session(session_id)
            self._authorize_session(actor, session)
            return session
        except HarnessSessionNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error(
                    "session_not_found",
                    "学习会话不存在或已过期。",
                ),
            ) from error

    def add_turn(
        self,
        session_id: str,
        request: TurnRequest,
        actor: AuthenticatedUser,
    ) -> TurnResponse:
        """中文：处理“新增·turn”相关操作。
        English: Handles the add turn operation.
        """
        auth_service.require_role(actor, "student")
        session = self.get_session(session_id, actor)
        self._authorize_session(actor, session, require_owner=True)
        result = self._run(lambda: self.harness.run_turn(
            session_id,
            request.message,
            request.intent,
            client_turn_id=request.client_turn_id,
        ))
        return TurnResponse(
            session=result.session,
            reply=result.reply,
            run_id=result.run_id,
            trace=[step.model_dump() for step in result.trace],
            duration_ms=result.duration_ms,
            degraded=result.degraded,
            degradation_code=result.degradation_code,
            degradation_reason=result.degradation_reason,
        )

    def validate_turn_access(self, session_id: str, actor: AuthenticatedUser) -> None:
        """中文：处理“验证·turn·access”相关操作。
        English: Handles the validate turn access operation.

        原有说明 / Existing notes:
        Fail with the normal REST status before an SSE response has started.
        """
        auth_service.require_role(actor, "student")
        session = self.get_session(session_id, actor)
        self._authorize_session(actor, session, require_owner=True)

    def list_sessions(
        self,
        actor: AuthenticatedUser,
        student_id: str | None = None,
    ) -> list[SessionSummary]:
        """中文：处理“列出·sessions”相关操作。
        English: Handles the list sessions operation.
        """
        target_student_id = self._student_scope(actor, student_id)
        return [
            SessionSummary(
                id=item.id,
                question=item.question,
                status=item.status,
                llm_model_id=item.llm_model_id,
                updated_at=item.updated_at,
            )
            for item in self.harness.list_sessions(target_student_id)
        ]

    def list_learning_records(
        self,
        actor: AuthenticatedUser,
        student_id: str | None = None,
    ) -> list[LearningRecord]:
        """中文：处理“列出·学习·records”相关操作。
        English: Handles the list learning records operation.
        """
        return self.harness.list_learning_records(self._student_scope(actor, student_id))

    def session_trace(
        self,
        session_id: str,
        actor: AuthenticatedUser,
    ) -> list[HarnessTraceStep]:
        """中文：处理“会话·trace”相关操作。
        English: Handles the session trace operation.
        """
        try:
            self._authorize_session(actor, self.harness.get_session(session_id))
            return self.harness.trace_for_session(session_id)
        except HarnessSessionNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error(
                    "session_not_found",
                    "学习会话不存在或已过期。",
                ),
            ) from error

    def report_content_issue(
        self,
        session_id: str,
        request: StudentContentIssueRequest,
        actor: AuthenticatedUser,
    ) -> ContentIssueReportView:
        """中文：处理“报告·内容·issue”相关操作。
        English: Handles the report content issue operation.
        """
        auth_service.require_role(actor, "student")
        tutoring_session = self.get_session(session_id, actor)
        self._authorize_session(actor, tutoring_session, require_owner=True)
        try:
            return content_integrity_service.report_student_issue(
                tutoring_session,
                reporter_user_id=actor.id,
                request=request,
            ).report
        except ContentIssueReferenceInvalid as error:
            raise HTTPException(
                status_code=422,
                detail=tutoring_error(
                    "invalid_content_issue_reference",
                    str(error),
                ),
            ) from error

    def parent_report(
        self,
        actor: AuthenticatedUser,
        student_id: str | None = None,
    ) -> ParentReportResponse:
        """中文：处理“parent·报告”相关操作。
        English: Handles the parent report operation.
        """
        records = self.list_learning_records(actor, student_id)
        records = sorted(records, key=lambda item: (item.date, item.id))
        knowledge_summary = self._parent_knowledge_summary(records)
        tags = [item.name for item in knowledge_summary]
        weak_points = sorted({record.error_reason for record in records if record.error_reason})
        subjects = sorted({record.subject for record in records})
        grades = sorted({record.grade for record in records})
        sample_count = len(records)
        return ParentReportResponse(
            sample_scope=ParentReportSampleScope(
                status="available" if sample_count else "no_samples",
                completed_record_count=sample_count,
                knowledge_evidence_count=sum(
                    len(record.knowledge_points) for record in records
                ),
                first_record_date=records[0].date if records else None,
                last_record_date=records[-1].date if records else None,
                subjects=subjects,
                grades=grades,
            ),
            overview=ParentReportOverview(
                completed_questions=sample_count,
                subjects=subjects,
                mistakes_to_review=sum(record.mastery != "已掌握" for record in records),
            ),
            knowledge_points=tags,
            knowledge_summary=knowledge_summary,
            weak_points=weak_points,
            recommendations=self._parent_recommendations(knowledge_summary),
            records=records,
            note=(
                "报告仅基于已完成会话写入的真实学习记录；当前样本不足以推断长期能力。"
                if sample_count < 3
                else "报告仅基于已完成会话写入的真实学习记录，结论范围见样本说明。"
            ),
        )

    @staticmethod
    def _parent_knowledge_summary(records: list[LearningRecord]) -> list[ParentKnowledgeSummary]:
        """中文：处理“parent·知识·summary”相关操作。
        English: Handles the parent knowledge summary operation.
        """
        aggregates: dict[str, dict] = {}
        for record in records:
            for point in record.knowledge_points:
                key = point.code or point.name
                current = aggregates.get(key)
                if current is None:
                    current = {
                        "code": point.code or f"record:{point.name}",
                        "name": point.name,
                        "evidence_count": 0,
                        "mistake_count": 0,
                        "effective_attempt_count": 0,
                        "highest_hint_level": 0,
                        "mastered_evidence_count": 0,
                        "latest_mastery": point.mastery,
                        "latest_record_date": record.date,
                    }
                    aggregates[key] = current
                current["evidence_count"] += 1
                current["mistake_count"] += int(point.mistake_detected)
                current["effective_attempt_count"] += point.effective_attempt_count
                current["highest_hint_level"] = max(
                    current["highest_hint_level"], point.hint_level
                )
                current["mastered_evidence_count"] += int(point.mastery == "已掌握")
                if record.date >= current["latest_record_date"]:
                    current["latest_mastery"] = point.mastery
                    current["latest_record_date"] = record.date
        return sorted(
            (ParentKnowledgeSummary.model_validate(item) for item in aggregates.values()),
            key=lambda item: (-item.mistake_count, item.name, item.code),
        )

    @staticmethod
    def _parent_recommendations(
        summaries: list[ParentKnowledgeSummary],
    ) -> list[str]:
        """中文：处理“parent·recommendations”相关操作。
        English: Handles the parent recommendations operation.
        """
        candidates = [
            item for item in summaries
            if item.mistake_count > 0 or item.latest_mastery != "已掌握"
        ]
        return [
            (
                f"复习“{item.name}”：现有 {item.evidence_count} 条学习证据，"
                f"其中 {item.mistake_count} 条记录到错误，最近状态为“{item.latest_mastery}”。"
            )
            for item in candidates[:3]
        ]

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.harness.close()

    @staticmethod
    def _authorize_session(
        actor: AuthenticatedUser,
        session: TutoringSession,
        require_owner: bool = False,
    ) -> None:
        """中文：处理“授权·会话”相关操作。
        English: Handles the authorize session operation.
        """
        allowed = actor.id == session.student_user_id if require_owner else auth_service.can_read_student(
            actor,
            session.student_user_id,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error(
                    "session_not_found",
                    "学习会话不存在或已过期。",
                ),
            )

    @staticmethod
    def _student_scope(actor: AuthenticatedUser, student_id: str | None) -> str:
        """中文：处理“学生·范围”相关操作。
        English: Handles the student scope operation.
        """
        if actor.role == "student":
            if student_id is not None and student_id != actor.id:
                raise HTTPException(
                    status_code=403,
                    detail=tutoring_error(
                        "student_scope_forbidden",
                        "无权访问其他学生的数据。",
                    ),
                )
            return actor.id
        if student_id is None:
            raise HTTPException(
                status_code=422,
                detail=tutoring_error(
                    "student_id_required",
                    "家长或管理员查询时必须指定学生。",
                ),
            )
        if not auth_service.can_read_student(actor, student_id):
            raise HTTPException(
                status_code=403,
                detail=tutoring_error(
                    "student_access_not_granted",
                    "尚未获得该学生的数据访问授权。",
                ),
            )
        return student_id

    @staticmethod
    def _run(operation):
        """中文：处理“执行”相关操作。
        English: Handles the run operation.
        """
        try:
            return operation()
        except HarnessSessionNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error(
                    "session_not_found",
                    "学习会话不存在或已过期。",
                ),
            ) from error
        except HarnessBudgetExceeded as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=tutoring_error(
                    "agent_budget_exceeded",
                    "本轮教学处理超出运行预算，请稍后重试。",
                    retryable=True,
                ),
                headers={"Retry-After": "2"},
            ) from error
        except HarnessSessionBusy as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=tutoring_error(
                    "session_busy",
                    "上一条消息仍在处理中，正在为你同步最新会话。",
                    retryable=True,
                    retry_after_seconds=1,
                ),
                headers={"Retry-After": "1"},
            ) from error
        except HarnessSessionConflict as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=tutoring_error(
                    "session_version_conflict",
                    "学习会话已在其他请求中更新，正在重新获取最新进度。",
                    retryable=True,
                    retry_after_seconds=1,
                ),
                headers={"Retry-After": "1"},
            ) from error
        except HarnessCoordinationUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=tutoring_error(
                    "session_coordination_unavailable",
                    "会话协调服务暂时不可用，请稍后重试同一请求。",
                    retryable=True,
                    retry_after_seconds=2,
                ),
                headers={"Retry-After": "2"},
            ) from error
        except HarnessPracticeUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=tutoring_error(
                    "similar_problem_constraints_unsatisfied",
                    f"当前学习范围内暂时无法生成合适的相似题：{error}",
                    retryable=False,
                ),
            ) from error
        except (LLMModelNotFound, LLMModelUnavailable) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=tutoring_error(
                    "llm_model_unavailable",
                    str(error),
                    retryable=False,
                ),
            ) from error


tutoring_service = TutoringService()
