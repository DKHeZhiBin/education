from fastapi import APIRouter, HTTPException, status

from app.api.dependencies.auth import CurrentUser
from app.domain.thinking_methods import PublishedThinkingMethodCategory, ThinkingMethodDetail
from app.repositories.curriculum_admin import CurriculumAdminNotFound
from app.services.thinking_methods import thinking_method_service


router = APIRouter(prefix="/curriculum/thinking-methods", tags=["thinking-methods"])


@router.get("", response_model=list[PublishedThinkingMethodCategory])
def list_thinking_methods(_: CurrentUser) -> list[PublishedThinkingMethodCategory]:
    """中文：读取已发布的数学思想与方法总目录。 English: Reads the published mathematical thinking and methods catalog."""
    return thinking_method_service.published_catalog()


@router.get("/{method_code}", response_model=ThinkingMethodDetail)
def get_thinking_method(method_code: str, _: CurrentUser) -> ThinkingMethodDetail:
    """中文：按稳定编码读取一个已发布方法。 English: Reads one published method by stable code."""
    try:
        return thinking_method_service.published_detail(method_code)
    except CurriculumAdminNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
