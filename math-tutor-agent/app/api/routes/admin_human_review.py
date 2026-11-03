from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies.auth import AdminUser, ReviewUser
from app.domain.human_review import (
    HumanReviewClaimRequest,
    HumanReviewQueueRequest,
    HumanReviewQueueResult,
    HumanReviewResult,
    HumanReviewSubmission,
    HumanReviewTaskPage,
    HumanReviewTaskView,
)
from app.repositories.human_review import HumanReviewConflict, HumanReviewNotFound
from app.services.human_review import human_review_service


router = APIRouter(prefix="/admin/human-reviews", tags=["admin-human-reviews"])


@router.post("/queue/refresh", response_model=HumanReviewQueueResult)
def refresh_queue(
    payload: HumanReviewQueueRequest, actor: AdminUser
) -> HumanReviewQueueResult:
    """中文：处理“刷新·queue”相关操作。
    English: Handles the refresh queue operation.
    """
    return human_review_service.enqueue(payload, actor)


@router.get("/tasks", response_model=HumanReviewTaskPage)
def list_tasks(
    actor: ReviewUser,
    statuses: Annotated[list[str] | None, Query()] = None,
    mine: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HumanReviewTaskPage:
    """中文：处理“列出·tasks”相关操作。
    English: Handles the list tasks operation.
    """
    return human_review_service.list_tasks(
        statuses=statuses, mine=mine, actor=actor, limit=limit, offset=offset
    )


@router.post("/tasks/{task_id}/claim", response_model=HumanReviewTaskView)
def claim_task(
    task_id: str, payload: HumanReviewClaimRequest, actor: ReviewUser
) -> HumanReviewTaskView:
    """中文：处理“claim·task”相关操作。
    English: Handles the claim task operation.
    """
    return _handle(lambda: human_review_service.claim(
        task_id, payload.expected_version, actor
    ))


@router.post("/tasks/{task_id}/reviews", response_model=HumanReviewResult)
def submit_review(
    task_id: str, payload: HumanReviewSubmission, actor: ReviewUser
) -> HumanReviewResult:
    """中文：处理“submit·复核”相关操作。
    English: Handles the submit review operation.
    """
    return _handle(lambda: human_review_service.submit(task_id, payload, actor))


def _handle(operation):
    """中文：处理“处理”相关操作。
    English: Handles the handle operation.
    """
    try:
        return operation()
    except HumanReviewNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except HumanReviewConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "human_review_conflict", "message": str(error)},
        ) from error
