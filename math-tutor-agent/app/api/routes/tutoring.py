from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.dependencies.auth import CurrentUser
from app.api.errors import TutoringAPIErrorResponse
from app.api.sse import stream_turn
from app.domain.content_issue import ContentIssueReportView, StudentContentIssueRequest
from app.domain.problem_image import ConfirmProblemImageOCRRequest, ProblemImageUpload
from app.domain.parent_report import ParentReportResponse
from app.domain.practice import KnowledgeExamplePracticeRequest
from app.domain.review import (
    ReviewAttemptRequest,
    ReviewAttemptResponse,
    ReviewTask,
    ReviewTaskScope,
)
from app.domain.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    LearningRecord,
    SessionSummary,
    TurnRequest,
    TurnResponse,
    TutoringSession,
)
from app.harness.contracts import HarnessTraceStep
from app.services.problem_images import problem_image_service
from app.services.reviews import review_service
from app.services.tutoring import tutoring_service

router = APIRouter(
    prefix="/tutoring",
    tags=["tutoring"],
    responses={
        status_code: {"model": TutoringAPIErrorResponse}
        for status_code in (400, 401, 403, 404, 409, 413, 415, 422, 429, 503)
    },
)


@router.post("/problem-images", response_model=ProblemImageUpload, status_code=201)
async def upload_problem_image(
    file: Annotated[UploadFile, File(...)],
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
) -> ProblemImageUpload:
    """中文：处理“upload·题目·图片”相关操作。
    English: Handles the upload problem image operation.
    """
    uploaded = await problem_image_service.upload(file, current_user)
    background_tasks.add_task(problem_image_service.recognize, uploaded.id, current_user.id)
    return uploaded


@router.get("/problem-images/{asset_id}", response_model=ProblemImageUpload)
def get_problem_image(asset_id: str, current_user: CurrentUser) -> ProblemImageUpload:
    """中文：处理“获取·题目·图片”相关操作。
    English: Handles the get problem image operation.
    """
    return problem_image_service.get(asset_id, current_user)


@router.put("/problem-images/{asset_id}/confirmation", response_model=ProblemImageUpload)
def confirm_problem_image_ocr(
    asset_id: str,
    request: ConfirmProblemImageOCRRequest,
    current_user: CurrentUser,
) -> ProblemImageUpload:
    """中文：确认并保存学生修正后的 OCR 题目和公式。
    English: Confirms and saves student-corrected OCR problem text and formulas.
    """
    return problem_image_service.confirm(asset_id, request, current_user)


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
def create_session(request: CreateSessionRequest, current_user: CurrentUser) -> CreateSessionResponse:
    """中文：处理“创建·会话”相关操作。
    English: Handles the create session operation.
    """
    return tutoring_service.create_session(request, current_user)


@router.post(
    "/knowledge-example-practice",
    response_model=CreateSessionResponse,
    status_code=201,
)
def create_knowledge_example_practice(
    request: KnowledgeExamplePracticeRequest,
    current_user: CurrentUser,
) -> CreateSessionResponse:
    """中文：从知识点例题生成相似题并创建学习会话。 English: Generates similar practice from a knowledge example and creates a learning session."""

    return tutoring_service.create_knowledge_example_practice(request, current_user)


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    current_user: CurrentUser,
    student_id: str | None = Query(default=None),
) -> list[SessionSummary]:
    """中文：处理“列出·sessions”相关操作。
    English: Handles the list sessions operation.
    """
    return tutoring_service.list_sessions(current_user, student_id)


@router.get("/sessions/{session_id}", response_model=TutoringSession)
def get_session(session_id: str, current_user: CurrentUser) -> TutoringSession:
    """中文：处理“获取·会话”相关操作。
    English: Handles the get session operation.
    """
    return tutoring_service.get_session(session_id, current_user)


@router.get("/sessions/{session_id}/trace", response_model=list[HarnessTraceStep])
def get_session_trace(session_id: str, current_user: CurrentUser) -> list[HarnessTraceStep]:
    """中文：处理“获取·会话·trace”相关操作。
    English: Handles the get session trace operation.
    """
    return tutoring_service.session_trace(session_id, current_user)


@router.post("/sessions/{session_id}/turns", response_model=TurnResponse)
def add_turn(session_id: str, request: TurnRequest, current_user: CurrentUser) -> TurnResponse:
    """中文：处理“新增·turn”相关操作。
    English: Handles the add turn operation.
    """
    return tutoring_service.add_turn(session_id, request, current_user)


@router.post(
    "/sessions/{session_id}/turns/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def stream_turn_reply(
    session_id: str,
    request: TurnRequest,
    current_user: CurrentUser,
) -> StreamingResponse:
    """中文：处理“stream·turn·reply”相关操作。
    English: Handles the stream turn reply operation.
    """
    tutoring_service.validate_turn_access(session_id, current_user)
    return StreamingResponse(
        stream_turn(session_id, request, current_user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/sessions/{session_id}/content-issues",
    response_model=ContentIssueReportView,
    status_code=202,
)
def report_content_issue(
    session_id: str,
    request: StudentContentIssueRequest,
    current_user: CurrentUser,
) -> ContentIssueReportView:
    """中文：处理“报告·内容·issue”相关操作。
    English: Handles the report content issue operation.
    """
    return tutoring_service.report_content_issue(session_id, request, current_user)


@router.get("/learning-records", response_model=list[LearningRecord])
def list_learning_records(
    current_user: CurrentUser,
    student_id: str | None = Query(default=None),
) -> list[LearningRecord]:
    """中文：处理“列出·学习·records”相关操作。
    English: Handles the list learning records operation.
    """
    return tutoring_service.list_learning_records(current_user, student_id)


@router.get("/review-tasks", response_model=list[ReviewTask])
def list_review_tasks(
    current_user: CurrentUser,
    student_id: str | None = Query(default=None),
    scope: ReviewTaskScope = Query(default="due"),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ReviewTask]:
    """中文：处理“列出·复核·tasks”相关操作。
    English: Handles the list review tasks operation.
    """
    return review_service.list_tasks(
        current_user,
        student_id=student_id,
        scope=scope,
        limit=limit,
    )


@router.post(
    "/review-tasks/{learning_record_id}/attempts",
    response_model=ReviewAttemptResponse,
    status_code=201,
)
def complete_review_task(
    learning_record_id: str,
    request: ReviewAttemptRequest,
    current_user: CurrentUser,
) -> ReviewAttemptResponse:
    """中文：处理“complete·复核·task”相关操作。
    English: Handles the complete review task operation.
    """
    return review_service.record_attempt(current_user, learning_record_id, request)


@router.get("/parent-report", response_model=ParentReportResponse)
def get_parent_report(
    current_user: CurrentUser,
    student_id: str | None = Query(default=None),
) -> ParentReportResponse:
    """中文：处理“获取·parent·报告”相关操作。
    English: Handles the get parent report operation.
    """
    return tutoring_service.parent_report(current_user, student_id)
