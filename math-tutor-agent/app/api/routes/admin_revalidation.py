from fastapi import APIRouter, HTTPException, status

from app.api.dependencies.auth import AdminUser
from app.domain.periodic_revalidation import (
    RevalidationDueRunSummary,
    RevalidationPolicyInput,
    RevalidationPolicyView,
    RevalidationRunView,
    RevalidationScope,
)
from app.repositories.periodic_revalidation import PeriodicRevalidationReferenceInvalid
from app.services.periodic_revalidation import periodic_revalidation_service


router = APIRouter(prefix="/admin/revalidation", tags=["admin-revalidation"])


@router.put("/policies/{policy_key}", response_model=RevalidationPolicyView)
def configure_policy(
    policy_key: str,
    payload: RevalidationPolicyInput,
    _: AdminUser,
) -> RevalidationPolicyView:
    """中文：处理“configure·策略”相关操作。
    English: Handles the configure policy operation.
    """
    if payload.policy_key != policy_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="路径中的 policy_key 必须与请求体一致",
        )
    try:
        return periodic_revalidation_service.configure(payload)
    except PeriodicRevalidationReferenceInvalid as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_revalidation_reference", "message": str(error)},
        ) from error


@router.post("/runs/run-due", response_model=RevalidationDueRunSummary)
def run_due(payload: RevalidationScope, _: AdminUser) -> RevalidationDueRunSummary:
    """中文：处理“执行·due”相关操作。
    English: Handles the run due operation.
    """
    try:
        return periodic_revalidation_service.run_due(payload)
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.post("/runs/{run_id}/process", response_model=RevalidationRunView)
def process_run(run_id: str, _: AdminUser) -> RevalidationRunView:
    """中文：处理“处理·执行”相关操作。
    English: Handles the process run operation.
    """
    try:
        return periodic_revalidation_service.process_run(run_id)
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.get("/runs/{run_id}", response_model=RevalidationRunView)
def get_run(run_id: str, _: AdminUser) -> RevalidationRunView:
    """中文：处理“获取·执行”相关操作。
    English: Handles the get run operation.
    """
    result = periodic_revalidation_service.get_run(run_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="复核批次不存在"
        )
    return result
