from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies.auth import AdminUser
from app.domain.generation import GenerationBatchStatus
from app.domain.generation_quality import (
    GenerationQualityReport,
    GenerationQualityScope,
    ProductionReleaseGate,
)
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
from app.domain.problem_lifecycle import InvalidProblemTransition
from app.repositories.generation_admin import (
    GenerationBatchActionConflict,
    GenerationBatchNotFound,
)
from app.repositories.question_generation import (
    QuestionGenerationIdempotencyConflict,
    QuestionGenerationReferenceInvalid,
    QuestionGenerationVersionNotFound,
)
from app.services.generation_admin import generation_admin_service
from app.services.generation_quality import generation_quality_service


router = APIRouter(prefix="/admin/generation", tags=["admin-generation"])


@router.get("/quality-report", response_model=GenerationQualityReport)
def generation_quality_report(
    _: AdminUser,
    batch_id: str | None = None,
    topic_code: str | None = None,
    batch_purpose: str | None = "question_variation",
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> GenerationQualityReport:
    return generation_quality_service.report(GenerationQualityScope(
        batch_id=batch_id,
        topic_code=topic_code,
        batch_purpose=batch_purpose,
        created_from=created_from,
        created_to=created_to,
    ))


@router.get("/release-gate", response_model=ProductionReleaseGate)
def generation_release_gate(
    _: AdminUser,
    batch_id: str | None = None,
    topic_code: str | None = "MS.QE",
    batch_purpose: str | None = "question_variation",
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> ProductionReleaseGate:
    return generation_quality_service.release_gate(GenerationQualityScope(
        batch_id=batch_id,
        topic_code=topic_code,
        batch_purpose=batch_purpose,
        created_from=created_from,
        created_to=created_to,
    ))


@router.get("/batches", response_model=GenerationBatchAdminPage)
def list_batches(
    _: AdminUser,
    statuses: Annotated[list[GenerationBatchStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GenerationBatchAdminPage:
    return generation_admin_service.list_batches(
        statuses=statuses, limit=limit, offset=offset
    )


@router.get("/batches/{batch_id}", response_model=GenerationBatchAdminDetail)
def get_batch(batch_id: str, _: AdminUser) -> GenerationBatchAdminDetail:
    result = generation_admin_service.get_batch(batch_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成批次不存在")
    return result


@router.post("/batches/{batch_id}/pause", response_model=GenerationBatchActionResult)
def pause_batch(
    batch_id: str, payload: BatchActionRequest, actor: AdminUser
) -> GenerationBatchActionResult:
    return _run_action(lambda: generation_admin_service.pause(batch_id, payload, actor))


@router.post("/batches/{batch_id}/resume", response_model=GenerationBatchActionResult)
def resume_batch(
    batch_id: str, payload: BatchActionRequest, actor: AdminUser
) -> GenerationBatchActionResult:
    return _run_action(lambda: generation_admin_service.resume(batch_id, payload, actor))


@router.post("/batches/{batch_id}/cancel", response_model=GenerationBatchActionResult)
def cancel_batch(
    batch_id: str, payload: BatchActionRequest, actor: AdminUser
) -> GenerationBatchActionResult:
    return _run_action(lambda: generation_admin_service.cancel(batch_id, payload, actor))


@router.post("/batches/{batch_id}/retry", response_model=GenerationBatchRetryResult)
def retry_batch(
    batch_id: str, payload: BatchRetryRequest, actor: AdminUser
) -> GenerationBatchRetryResult:
    return _run_action(lambda: generation_admin_service.retry(batch_id, payload, actor))


@router.post(
    "/batches/{batch_id}/withdraw-approved",
    response_model=BatchWithdrawalResult,
)
def withdraw_approved(
    batch_id: str, payload: BatchWithdrawalRequest, actor: AdminUser
) -> BatchWithdrawalResult:
    return _run_action(
        lambda: generation_admin_service.withdraw_approved(batch_id, payload, actor)
    )


def _run_action(operation):
    try:
        return operation()
    except GenerationBatchNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="生成批次不存在"
        ) from error
    except GenerationBatchActionConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": error.code, "message": str(error)},
        ) from error
    except InvalidProblemTransition as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": error.code,
                "message": str(error),
                "missing_requirements": list(error.missing_requirements),
            },
        ) from error
    except QuestionGenerationIdempotencyConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "idempotency_conflict", "message": str(error)},
        ) from error
    except (QuestionGenerationReferenceInvalid, QuestionGenerationVersionNotFound) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "retry_precondition_failed", "message": str(error)},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_batch_transition", "message": str(error)},
        ) from error
