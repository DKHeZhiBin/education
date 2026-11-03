from __future__ import annotations

from app.domain.auth import AuthenticatedUser
from app.domain.generation import GenerationBatchStatus
from app.domain.generation_admin import (
    BatchActionRequest,
    BatchRetryRequest,
    BatchWithdrawalRequest,
    BatchWithdrawalResult,
    GenerationBatchActionResult,
    GenerationBatchAdminDetail,
    GenerationBatchAdminPage,
    GenerationBatchRetryResult,
)
from app.repositories.generation_admin import GenerationBatchAdminRepository


class GenerationAdminService:
    """中文：定义“生成·admin·服务”类，封装该职责相关的数据与行为。
    English: Defines the generation admin service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, repository: GenerationBatchAdminRepository) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.repository = repository

    def list_batches(
        self,
        *,
        statuses: list[GenerationBatchStatus] | None,
        limit: int,
        offset: int,
    ) -> GenerationBatchAdminPage:
        """中文：处理“列出·batches”相关操作。
        English: Handles the list batches operation.
        """
        return self.repository.list_batches(statuses=statuses, limit=limit, offset=offset)

    def get_batch(self, batch_id: str) -> GenerationBatchAdminDetail | None:
        """中文：处理“获取·批次”相关操作。
        English: Handles the get batch operation.
        """
        return self.repository.get_batch(batch_id)

    def pause(
        self, batch_id: str, payload: BatchActionRequest, actor: AuthenticatedUser
    ) -> GenerationBatchActionResult:
        """中文：处理“pause”相关操作。
        English: Handles the pause operation.
        """
        return self.repository.pause(batch_id, reason=payload.reason, actor_id=actor.id)

    def resume(
        self, batch_id: str, payload: BatchActionRequest, actor: AuthenticatedUser
    ) -> GenerationBatchActionResult:
        """中文：处理“resume”相关操作。
        English: Handles the resume operation.
        """
        return self.repository.resume(batch_id, reason=payload.reason, actor_id=actor.id)

    def cancel(
        self, batch_id: str, payload: BatchActionRequest, actor: AuthenticatedUser
    ) -> GenerationBatchActionResult:
        """中文：处理“cancel”相关操作。
        English: Handles the cancel operation.
        """
        return self.repository.cancel(batch_id, reason=payload.reason, actor_id=actor.id)

    def retry(
        self, batch_id: str, payload: BatchRetryRequest, actor: AuthenticatedUser
    ) -> GenerationBatchRetryResult:
        """中文：处理“重试”相关操作。
        English: Handles the retry operation.
        """
        return self.repository.retry(
            batch_id,
            idempotency_key=payload.idempotency_key,
            reason=payload.reason,
            actor_id=actor.id,
        )

    def withdraw_approved(
        self, batch_id: str, payload: BatchWithdrawalRequest, actor: AuthenticatedUser
    ) -> BatchWithdrawalResult:
        """中文：处理“withdraw·approved”相关操作。
        English: Handles the withdraw approved operation.
        """
        return self.repository.withdraw_approved(
            batch_id,
            reason=payload.reason,
            include_indexed=payload.include_indexed,
            indexed_content_removed=payload.indexed_content_removed,
            actor_id=actor.id,
        )


generation_admin_service = GenerationAdminService(GenerationBatchAdminRepository())

