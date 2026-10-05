from fastapi import HTTPException, status

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
    HarnessTraceStep,
)
from app.harness.factory import build_math_tutor_harness
from app.services.auth import auth_service
from app.services.content_integrity import (
    ContentIssueReferenceInvalid,
    content_integrity_service,
)


class TutoringService:
    def __init__(self) -> None:
        self.harness = build_math_tutor_harness()

    def create_session(
        self,
        request: CreateSessionRequest,
        actor: AuthenticatedUser,
    ) -> CreateSessionResponse:
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
                detail="题目不存在或当前不可用于学习",
            ) from error
        result = self._run(lambda: self.harness.start_session(
            question=question,
            subject=request.subject,
            grade=request.grade,
            student_user_id=actor.id,
            knowledge_problem_id=request.problem_id,
        ))
        return CreateSessionResponse(
            session=result.session,
            reply=result.reply,
            run_id=result.run_id,
            trace=[step.model_dump() for step in result.trace],
            duration_ms=result.duration_ms,
            degraded=result.degraded,
            degradation_reason=result.degradation_reason,
        )

    def get_session(self, session_id: str, actor: AuthenticatedUser) -> TutoringSession:
        try:
            session = self.harness.get_session(session_id)
            self._authorize_session(actor, session)
            return session
        except HarnessSessionNotFound as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习会话不存在或已过期") from error

    def add_turn(
        self,
        session_id: str,
        request: TurnRequest,
        actor: AuthenticatedUser,
    ) -> TurnResponse:
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
            degradation_reason=result.degradation_reason,
        )

    def list_sessions(
        self,
        actor: AuthenticatedUser,
        student_id: str | None = None,
    ) -> list[SessionSummary]:
        target_student_id = self._student_scope(actor, student_id)
        return [
            SessionSummary(id=item.id, question=item.question, status=item.status, updated_at=item.updated_at)
            for item in self.harness.list_sessions(target_student_id)
        ]

    def list_learning_records(
        self,
        actor: AuthenticatedUser,
        student_id: str | None = None,
    ) -> list[LearningRecord]:
        return self.harness.list_learning_records(self._student_scope(actor, student_id))

    def session_trace(
        self,
        session_id: str,
        actor: AuthenticatedUser,
    ) -> list[HarnessTraceStep]:
        try:
            self._authorize_session(actor, self.harness.get_session(session_id))
            return self.harness.trace_for_session(session_id)
        except HarnessSessionNotFound as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习会话不存在或已过期") from error

    def report_content_issue(
        self,
        session_id: str,
        request: StudentContentIssueRequest,
        actor: AuthenticatedUser,
    ) -> ContentIssueReportView:
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
            raise HTTPException(status_code=422, detail=str(error)) from error

    def parent_report(
        self,
        actor: AuthenticatedUser,
        student_id: str | None = None,
    ) -> dict:
        records = self.list_learning_records(actor, student_id)
        tags = sorted({tag for record in records for tag in record.knowledge_tags})
        weak_points = sorted({record.error_reason for record in records if record.error_reason})
        return {
            "overview": {
                "completed_questions": len(records),
                "subjects": sorted({record.subject for record in records}),
                "mistakes_to_review": sum(record.mastery != "已掌握" for record in records),
            },
            "knowledge_points": tags,
            "weak_points": weak_points,
            "recommendations": [
                f"围绕“{tag}”每天完成 2 道同类题，连续练习 5 天。" for tag in tags[:3]
            ],
            "records": records,
            "note": "报告仅基于真实完成的学习记录生成；样本不足时不推断长期能力。",
        }

    def close(self) -> None:
        self.harness.close()

    @staticmethod
    def _authorize_session(
        actor: AuthenticatedUser,
        session: TutoringSession,
        require_owner: bool = False,
    ) -> None:
        allowed = actor.id == session.student_user_id if require_owner else auth_service.can_read_student(
            actor,
            session.student_user_id,
        )
        if not allowed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习会话不存在或已过期")

    @staticmethod
    def _student_scope(actor: AuthenticatedUser, student_id: str | None) -> str:
        if actor.role == "student":
            if student_id is not None and student_id != actor.id:
                raise HTTPException(status_code=403, detail="无权访问其他学生的数据")
            return actor.id
        if student_id is None:
            raise HTTPException(status_code=422, detail="家长或管理员查询时必须指定 student_id")
        if not auth_service.can_read_student(actor, student_id):
            raise HTTPException(status_code=403, detail="尚未获得该学生的数据访问授权")
        return student_id

    @staticmethod
    def _run(operation):
        try:
            return operation()
        except HarnessSessionNotFound as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习会话不存在或已过期") from error
        except HarnessBudgetExceeded as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent 运行预算不足") from error
        except HarnessSessionBusy as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该学习会话正在处理上一条消息，请稍后重试",
            ) from error
        except HarnessSessionConflict as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="学习会话已在其他请求中更新，请重新加载后再提交",
            ) from error
        except HarnessCoordinationUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="会话协调服务暂时不可用，请稍后重试同一请求",
                headers={"Retry-After": "2"},
            ) from error


tutoring_service = TutoringService()
