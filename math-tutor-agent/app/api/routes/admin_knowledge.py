from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies.auth import AdminUser
from app.domain.knowledge import ProblemContentStatus
from app.domain.knowledge_admin import (
    PersistedProblemTransition,
    ProblemAdminDetail,
    ProblemAdminPage,
    ProblemStatusChangeRequest,
    ProblemStatusCount,
)
from app.domain.problem_lifecycle import InvalidProblemTransition
from app.domain.teaching_content import (
    ErrorPatternLinkView,
    HintBlueprintUpsert,
    HintBlueprintView,
    ProblemErrorPatternUpsert,
    ProblemTeachingMap,
    SolutionStepView,
)
from app.repositories.knowledge import (
    KnowledgeProblemNotFound,
    KnowledgeProblemVersionConflict,
)
from app.services.knowledge_admin import knowledge_admin_service
from app.repositories.teaching_content import (
    TeachingContentConflict,
    TeachingContentNotFound,
)


router = APIRouter(prefix="/admin/knowledge", tags=["admin-knowledge"])


@router.get("/problems/status-summary", response_model=list[ProblemStatusCount])
def problem_status_summary(_: AdminUser) -> list[ProblemStatusCount]:
    return knowledge_admin_service.status_summary()


@router.get("/problems", response_model=ProblemAdminPage)
def list_problems(
    _: AdminUser,
    statuses: Annotated[list[ProblemContentStatus] | None, Query()] = None,
    subject: str | None = None,
    grade_band: str | None = None,
    grade_code: str | None = None,
    problem_type: str | None = None,
    content_type: str | None = None,
    curriculum_version_id: str | None = None,
    knowledge_point_code: str | None = None,
    difficulty_source: str | None = None,
    generation_batch_id: str | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProblemAdminPage:
    return knowledge_admin_service.list_problems(
        statuses=statuses,
        subject=subject,
        grade_band=grade_band,
        grade_code=grade_code,
        problem_type=problem_type,
        content_type=content_type,
        curriculum_version_id=curriculum_version_id,
        knowledge_point_code=knowledge_point_code,
        difficulty_source=difficulty_source,
        generation_batch_id=generation_batch_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/problems/{problem_id}", response_model=ProblemAdminDetail)
def get_problem(problem_id: str, _: AdminUser) -> ProblemAdminDetail:
    problem = knowledge_admin_service.get_problem(problem_id)
    if problem is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    return problem


@router.post(
    "/problems/{problem_id}/transitions",
    response_model=PersistedProblemTransition,
)
def transition_problem(
    problem_id: str,
    payload: ProblemStatusChangeRequest,
    actor: AdminUser,
) -> PersistedProblemTransition:
    try:
        return knowledge_admin_service.transition_problem(problem_id, payload, actor)
    except KnowledgeProblemNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在"
        ) from error
    except KnowledgeProblemVersionConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "status_version_conflict",
                "expected_status_version": error.expected,
                "actual_status_version": error.actual,
            },
        ) from error
    except InvalidProblemTransition as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": error.code,
                "message": str(error),
                "missing_requirements": list(error.missing_requirements),
                "suggested_status": (
                    error.suggested_status.value if error.suggested_status else None
                ),
            },
        ) from error


@router.post(
    "/problems/{problem_id}/solutions/{solution_id}/steps/sync",
    response_model=list[SolutionStepView],
)
def sync_solution_steps(
    problem_id: str,
    solution_id: str,
    _: AdminUser,
) -> list[SolutionStepView]:
    try:
        return knowledge_admin_service.sync_solution_steps(problem_id, solution_id)
    except TeachingContentNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except TeachingContentConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/problems/{problem_id}/error-pattern-links",
    response_model=ErrorPatternLinkView,
)
def upsert_error_pattern_link(
    problem_id: str,
    payload: ProblemErrorPatternUpsert,
    _: AdminUser,
) -> ErrorPatternLinkView:
    try:
        return knowledge_admin_service.upsert_error_pattern_link(problem_id, payload)
    except TeachingContentNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except TeachingContentConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/problems/{problem_id}/hints",
    response_model=HintBlueprintView,
)
def upsert_hint(
    problem_id: str,
    payload: HintBlueprintUpsert,
    _: AdminUser,
) -> HintBlueprintView:
    try:
        return knowledge_admin_service.upsert_hint(problem_id, payload)
    except TeachingContentNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except TeachingContentConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get(
    "/problems/{problem_id}/teaching-map",
    response_model=ProblemTeachingMap,
)
def get_problem_teaching_map(
    problem_id: str,
    _: AdminUser,
) -> ProblemTeachingMap:
    try:
        return knowledge_admin_service.get_problem_teaching_map(problem_id)
    except TeachingContentNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
