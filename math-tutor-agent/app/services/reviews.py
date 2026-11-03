from __future__ import annotations

from fastapi import HTTPException, status

from app.api.errors import tutoring_error
from app.domain.auth import AuthenticatedUser
from app.domain.review import (
    ReviewAttemptRequest,
    ReviewAttemptResponse,
    ReviewTask,
    ReviewTaskScope,
)
from app.repositories.reviews import (
    ReviewRepository,
    ReviewSessionInvalid,
    ReviewTaskNotFound,
)
from app.services.auth import auth_service


class ReviewService:
    """中文：定义“复核·服务”类，封装该职责相关的数据与行为。
    English: Defines the review service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, repository: ReviewRepository | None = None) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.repository = repository or ReviewRepository()

    def list_tasks(
        self,
        actor: AuthenticatedUser,
        *,
        student_id: str | None,
        scope: ReviewTaskScope,
        limit: int,
    ) -> list[ReviewTask]:
        """中文：处理“列出·tasks”相关操作。
        English: Handles the list tasks operation.
        """
        target_student_id = self._student_scope(actor, student_id)
        return self.repository.list_tasks(
            target_student_id,
            scope=scope,
            limit=limit,
        )

    def record_attempt(
        self,
        actor: AuthenticatedUser,
        learning_record_id: str,
        request: ReviewAttemptRequest,
    ) -> ReviewAttemptResponse:
        """中文：处理“记录·attempt”相关操作。
        English: Handles the record attempt operation.
        """
        auth_service.require_role(actor, "student")
        try:
            recorded = self.repository.record_attempt(
                actor.id,
                learning_record_id,
                request,
            )
        except ReviewTaskNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=tutoring_error(
                    "review_task_not_found",
                    "复习任务不存在或不属于当前学生。",
                ),
            ) from error
        except ReviewSessionInvalid as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=tutoring_error(
                    "review_session_invalid",
                    "关联的复习会话不存在或不属于当前学生。",
                ),
            ) from error
        return ReviewAttemptResponse(
            attempt_id=recorded.attempt_id,
            task=recorded.task,
            interval_days=recorded.interval_days,
            rationale=recorded.rationale,
        )

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.repository.close()

    @staticmethod
    def _student_scope(actor: AuthenticatedUser, student_id: str | None) -> str:
        """中文：处理“学生·范围”相关操作。
        English: Handles the student scope operation.
        """
        if actor.role == "student":
            if student_id is not None and student_id != actor.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=tutoring_error(
                        "student_scope_forbidden",
                        "无权访问其他学生的复习任务。",
                    ),
                )
            return actor.id
        if student_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=tutoring_error(
                    "student_id_required",
                    "家长或管理员查询复习任务时必须指定学生。",
                ),
            )
        if not auth_service.can_read_student(actor, student_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=tutoring_error(
                    "student_access_not_granted",
                    "尚未获得该学生的数据访问授权。",
                ),
            )
        return student_id


review_service = ReviewService()
