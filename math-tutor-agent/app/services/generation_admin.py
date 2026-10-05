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
    def __init__(self, repository: GenerationBatchAdminRepository) -> None:
        self.repository = repository

    def list_batches(
        self,
        *,
        statuses: list[GenerationBatchStatus] | None,
        limit: int,
        offset: int,
    ) -> GenerationBatchAdminPage:
        return self.repository.list_batches(statuses=statuses, limit=limit, offset=offset)

    def get_batch(self, batch_id: str) -> GenerationBatchAdminDetail | None:
        return self.repository.get_batch(batch_id)

    def pause(
        self, batch_id: str, payload: BatchActionRequest, actor: AuthenticatedUser
    ) -> GenerationBatchActionResult:
        return self.repository.pause(batch_id, reason=payload.reason, actor_id=actor.id)

    def resume(
        self, batch_id: str, payload: BatchActionRequest, actor: AuthenticatedUser
    ) -> GenerationBatchActionResult:
        return self.repository.resume(batch_id, reason=payload.reason, actor_id=actor.id)

    def cancel(
        self, batch_id: str, payload: BatchActionRequest, actor: AuthenticatedUser
    ) -> GenerationBatchActionResult:
        return self.repository.cancel(batch_id, reason=payload.reason, actor_id=actor.id)

    def retry(
        self, batch_id: str, payload: BatchRetryRequest, actor: AuthenticatedUser
    ) -> GenerationBatchRetryResult:
        return self.repository.retry(
            batch_id,
            idempotency_key=payload.idempotency_key,
            reason=payload.reason,
            actor_id=actor.id,
        )

    def withdraw_approved(
        self, batch_id: str, payload: BatchWithdrawalRequest, actor: AuthenticatedUser
    ) -> BatchWithdrawalResult:
        return self.repository.withdraw_approved(
            batch_id,
            reason=payload.reason,
            include_indexed=payload.include_indexed,
            indexed_content_removed=payload.indexed_content_removed,
            actor_id=actor.id,
        )


generation_admin_service = GenerationAdminService(GenerationBatchAdminRepository())

