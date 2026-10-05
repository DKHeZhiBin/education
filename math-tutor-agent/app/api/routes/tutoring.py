from fastapi import APIRouter, Query

from app.api.dependencies.auth import CurrentUser

from app.domain.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    LearningRecord,
    SessionSummary,
    TurnRequest,
    TurnResponse,
    TutoringSession,
)
from app.domain.content_issue import ContentIssueReportView, StudentContentIssueRequest
from app.services.tutoring import tutoring_service
from app.harness.contracts import HarnessTraceStep

router = APIRouter(prefix="/tutoring", tags=["tutoring"])


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
def create_session(request: CreateSessionRequest, current_user: CurrentUser) -> CreateSessionResponse:
    return tutoring_service.create_session(request, current_user)


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    current_user: CurrentUser,
    student_id: str | None = Query(default=None),
) -> list[SessionSummary]:
    return tutoring_service.list_sessions(current_user, student_id)


@router.get("/sessions/{session_id}", response_model=TutoringSession)
def get_session(session_id: str, current_user: CurrentUser) -> TutoringSession:
    return tutoring_service.get_session(session_id, current_user)


@router.get("/sessions/{session_id}/trace", response_model=list[HarnessTraceStep])
def get_session_trace(session_id: str, current_user: CurrentUser) -> list[HarnessTraceStep]:
    return tutoring_service.session_trace(session_id, current_user)


@router.post("/sessions/{session_id}/turns", response_model=TurnResponse)
def add_turn(session_id: str, request: TurnRequest, current_user: CurrentUser) -> TurnResponse:
    return tutoring_service.add_turn(session_id, request, current_user)


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
    return tutoring_service.report_content_issue(session_id, request, current_user)


@router.get("/learning-records", response_model=list[LearningRecord])
def list_learning_records(
    current_user: CurrentUser,
    student_id: str | None = Query(default=None),
) -> list[LearningRecord]:
    return tutoring_service.list_learning_records(current_user, student_id)


@router.get("/parent-report")
def get_parent_report(
    current_user: CurrentUser,
    student_id: str | None = Query(default=None),
) -> dict:
    return tutoring_service.parent_report(current_user, student_id)
