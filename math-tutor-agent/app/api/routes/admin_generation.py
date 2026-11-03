from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies.auth import AdminUser
from app.core.product_scope import MVP_DEFAULT_ROOT_CODE
from app.domain.generation import GenerationBatchStatus
from app.domain.candidate_validation import CandidateValidationBatchResult
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
from app.domain.question_generation import (
    QuestionGenerationJobInput,
    QuestionGenerationJobOutput,
)
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
from app.services.candidate_validation import candidate_validation_service
from app.services.generation_quality import generation_quality_service
from app.services.question_generation import (
    QuestionGenerationExecutionConflict,
    QuestionGenerationJobNotFound,
    question_generation_service,
)


router = APIRouter(prefix="/admin/generation", tags=["admin-generation"])


@router.post("/jobs", response_model=QuestionGenerationJobOutput)
def create_generation_job(
    payload: QuestionGenerationJobInput, _: AdminUser
) -> QuestionGenerationJobOutput:
    """中文：处理“创建·生成·任务”相关操作。
    English: Handles the create generation job operation.
    """
    return _run_action(lambda: question_generation_service.create_and_run(payload))


@router.post("/jobs/{job_id}/run", response_model=QuestionGenerationJobOutput)
def run_generation_job(job_id: str, _: AdminUser) -> QuestionGenerationJobOutput:
    """中文：处理“执行·生成·任务”相关操作。
    English: Handles the run generation job operation.
    """
    return _run_action(lambda: question_generation_service.run(job_id))


@router.get("/jobs/{job_id}", response_model=QuestionGenerationJobOutput)
def get_generation_job(job_id: str, _: AdminUser) -> QuestionGenerationJobOutput:
    """中文：处理“获取·生成·任务”相关操作。
    English: Handles the get generation job operation.
    """
    return _run_action(lambda: question_generation_service.get(job_id))


@router.post(
    "/batches/{batch_id}/validate",
    response_model=CandidateValidationBatchResult,
)
def validate_candidates(
    batch_id: str,
    _: AdminUser,
    verifier_profile: str = "quadratic-v1",
) -> CandidateValidationBatchResult:
    """中文：处理“验证·candidates”相关操作。
    English: Handles the validate candidates operation.
    """
    return _run_action(lambda: candidate_validation_service.validate_batch(
        batch_id,
        verifier_profile=verifier_profile,
    ))


@router.get("/quality-report", response_model=GenerationQualityReport)
def generation_quality_report(
    _: AdminUser,
    batch_id: str | None = None,
    topic_code: str | None = None,
    batch_purpose: str | None = "question_variation",
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> GenerationQualityReport:
    """中文：处理“生成·质量·报告”相关操作。
    English: Handles the generation quality report operation.
    """
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
    topic_code: str | None = MVP_DEFAULT_ROOT_CODE,
    batch_purpose: str | None = "question_variation",
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> ProductionReleaseGate:
    """中文：处理“生成·release·准入门”相关操作。
    English: Handles the generation release gate operation.
    """
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
    """中文：处理“列出·batches”相关操作。
    English: Handles the list batches operation.
    """
    return generation_admin_service.list_batches(
        statuses=statuses, limit=limit, offset=offset
    )


@router.get("/batches/{batch_id}", response_model=GenerationBatchAdminDetail)
def get_batch(batch_id: str, _: AdminUser) -> GenerationBatchAdminDetail:
    """中文：处理“获取·批次”相关操作。
    English: Handles the get batch operation.
    """
    result = generation_admin_service.get_batch(batch_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成批次不存在")
    return result


@router.post("/batches/{batch_id}/pause", response_model=GenerationBatchActionResult)
def pause_batch(
    batch_id: str, payload: BatchActionRequest, actor: AdminUser
) -> GenerationBatchActionResult:
    """中文：处理“pause·批次”相关操作。
    English: Handles the pause batch operation.
    """
    return _run_action(lambda: generation_admin_service.pause(batch_id, payload, actor))


@router.post("/batches/{batch_id}/resume", response_model=GenerationBatchActionResult)
def resume_batch(
    batch_id: str, payload: BatchActionRequest, actor: AdminUser
) -> GenerationBatchActionResult:
    """中文：处理“resume·批次”相关操作。
    English: Handles the resume batch operation.
    """
    return _run_action(lambda: generation_admin_service.resume(batch_id, payload, actor))


@router.post("/batches/{batch_id}/cancel", response_model=GenerationBatchActionResult)
def cancel_batch(
    batch_id: str, payload: BatchActionRequest, actor: AdminUser
) -> GenerationBatchActionResult:
    """中文：处理“cancel·批次”相关操作。
    English: Handles the cancel batch operation.
    """
    return _run_action(lambda: generation_admin_service.cancel(batch_id, payload, actor))


@router.post("/batches/{batch_id}/retry", response_model=GenerationBatchRetryResult)
def retry_batch(
    batch_id: str, payload: BatchRetryRequest, actor: AdminUser
) -> GenerationBatchRetryResult:
    """中文：处理“重试·批次”相关操作。
    English: Handles the retry batch operation.
    """
    return _run_action(lambda: generation_admin_service.retry(batch_id, payload, actor))


@router.post(
    "/batches/{batch_id}/withdraw-approved",
    response_model=BatchWithdrawalResult,
)
def withdraw_approved(
    batch_id: str, payload: BatchWithdrawalRequest, actor: AdminUser
) -> BatchWithdrawalResult:
    """中文：处理“withdraw·approved”相关操作。
    English: Handles the withdraw approved operation.
    """
    return _run_action(
        lambda: generation_admin_service.withdraw_approved(batch_id, payload, actor)
    )


def _run_action(operation):
    """中文：处理“执行·action”相关操作。
    English: Handles the run action operation.
    """
    try:
        return operation()
    except GenerationBatchNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="生成批次不存在"
        ) from error
    except QuestionGenerationJobNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="生成任务不存在"
        ) from error
    except QuestionGenerationExecutionConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "generation_execution_conflict", "message": str(error)},
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
