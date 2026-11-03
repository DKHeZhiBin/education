from __future__ import annotations

from app.core.config import Settings, settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.auth import AuthenticatedUser
from app.domain.human_review import (
    HumanReviewQueueRequest,
    HumanReviewQueueResult,
    HumanReviewResult,
    HumanReviewSubmission,
    HumanReviewTaskPage,
    HumanReviewTaskView,
)
from app.domain.index_lifecycle import IndexMaintenanceRequest
from app.repositories.human_review import HumanReviewRepository, HumanReviewStale
from app.search_index.lifecycle_service import SearchIndexLifecycleService


class HumanReviewService:
    """中文：定义“human·复核·服务”类，封装该职责相关的数据与行为。
    English: Defines the human review service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, config: Settings = settings) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.session_factory = create_session_factory(create_mysql_engine())
        self.repository = HumanReviewRepository(self.session_factory)
        self.lifecycle = SearchIndexLifecycleService(
            config, session_factory=self.session_factory
        )

    def enqueue(
        self, request: HumanReviewQueueRequest, actor: AuthenticatedUser
    ) -> HumanReviewQueueResult:
        """中文：处理“enqueue”相关操作。
        English: Handles the enqueue operation.
        """
        return self.repository.enqueue(request, actor_id=actor.id)

    def list_tasks(
        self,
        *,
        statuses: list[str] | None,
        mine: bool,
        actor: AuthenticatedUser,
        limit: int,
        offset: int,
    ) -> HumanReviewTaskPage:
        """中文：处理“列出·tasks”相关操作。
        English: Handles the list tasks operation.
        """
        return self.repository.list_tasks(
            statuses=statuses,
            assignee_id=actor.id if mine else None,
            limit=limit,
            offset=offset,
        )

    def claim(
        self, task_id: str, expected_version: int, actor: AuthenticatedUser
    ) -> HumanReviewTaskView:
        """中文：处理“claim”相关操作。
        English: Handles the claim operation.
        """
        try:
            return self.repository.claim(
                task_id, reviewer_id=actor.id, expected_version=expected_version
            )
        except HumanReviewStale:
            self.repository.mark_stale(task_id)
            raise

    def submit(
        self, task_id: str, request: HumanReviewSubmission, actor: AuthenticatedUser
    ) -> HumanReviewResult:
        """中文：处理“submit”相关操作。
        English: Handles the submit operation.
        """
        try:
            review_id, task, evidence_id = self.repository.submit(
                task_id, reviewer_id=actor.id, request=request
            )
        except HumanReviewStale:
            self.repository.mark_stale(task_id)
            raise
        maintenance_job_id = None
        if request.decision in {"revision_required", "quarantine"} and (
            task.problem_status in {"approved", "indexed"}
        ):
            job = self.lifecycle.enqueue(IndexMaintenanceRequest(
                problem_id=task.problem_id,
                trigger_type="revalidation",
                reason=f"qualified_human_review:{review_id}:{request.decision}",
            ))
            maintenance_job_id = job.id
            self.lifecycle.run_job(job.id)
        return HumanReviewResult(
            review_id=review_id,
            task=task,
            evidence_id=evidence_id,
            decision=request.decision,
            production_suppression_job_id=maintenance_job_id,
        )

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.lifecycle.close()


human_review_service = HumanReviewService()
