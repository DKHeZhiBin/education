from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies.auth import AdminUser
from app.domain.thinking_methods import (
    ThinkingMethodCategoryView,
    ThinkingMethodCategoryWrite,
    ThinkingMethodView,
    ThinkingMethodWrite,
)
from app.repositories.curriculum_admin import CurriculumAdminConflict, CurriculumAdminNotFound
from app.services.thinking_methods import thinking_method_service


router = APIRouter(prefix="/admin/thinking-methods", tags=["admin-thinking-methods"])


def _translate_error(error: Exception) -> HTTPException:
    """中文：把数学方法管理错误转换为稳定 HTTP 状态。 English: Converts thinking-method administration errors to stable HTTP statuses."""
    if isinstance(error, CurriculumAdminNotFound):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, IntegrityError):
        return HTTPException(status_code=409, detail="编码已经存在或关联对象无效")
    return HTTPException(status_code=409, detail=str(error))


@router.get("/categories", response_model=list[ThinkingMethodCategoryView])
def list_categories(_: AdminUser) -> list[ThinkingMethodCategoryView]:
    """中文：列出数学思想分类。 English: Lists mathematical thinking categories."""
    return thinking_method_service.list_categories()


@router.post("/categories", response_model=ThinkingMethodCategoryView, status_code=status.HTTP_201_CREATED)
def create_category(payload: ThinkingMethodCategoryWrite, actor: AdminUser) -> ThinkingMethodCategoryView:
    """中文：创建数学思想分类。 English: Creates a mathematical thinking category."""
    try:
        return thinking_method_service.create_category(payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_error(error) from error


@router.put("/categories/{category_id}", response_model=ThinkingMethodCategoryView)
def update_category(category_id: int, payload: ThinkingMethodCategoryWrite, actor: AdminUser) -> ThinkingMethodCategoryView:
    """中文：更新数学思想分类。 English: Updates a mathematical thinking category."""
    try:
        return thinking_method_service.update_category(category_id, payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_error(error) from error


@router.delete("/categories/{category_id}", response_model=ThinkingMethodCategoryView)
def archive_category(category_id: int, actor: AdminUser) -> ThinkingMethodCategoryView:
    """中文：归档没有活跃方法的思想分类。 English: Archives a thinking category without active methods."""
    try:
        return thinking_method_service.archive_category(category_id, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_error(error) from error


@router.get("/methods", response_model=list[ThinkingMethodView])
def list_methods(
    _: AdminUser,
    category_id: int | None = None,
    method_status: str | None = Query(default=None, alias="status"),
    search: str | None = None,
) -> list[ThinkingMethodView]:
    """中文：筛选数学方法。 English: Filters mathematical methods."""
    return thinking_method_service.list_methods(category_id, method_status, search)


@router.post("/methods", response_model=ThinkingMethodView, status_code=status.HTTP_201_CREATED)
def create_method(payload: ThinkingMethodWrite, actor: AdminUser) -> ThinkingMethodView:
    """中文：创建数学方法。 English: Creates a mathematical method."""
    try:
        return thinking_method_service.create_method(payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_error(error) from error


@router.put("/methods/{method_id}", response_model=ThinkingMethodView)
def update_method(method_id: int, payload: ThinkingMethodWrite, actor: AdminUser) -> ThinkingMethodView:
    """中文：更新数学方法。 English: Updates a mathematical method."""
    try:
        return thinking_method_service.update_method(method_id, payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_error(error) from error


@router.delete("/methods/{method_id}", response_model=ThinkingMethodView)
def archive_method(method_id: int, actor: AdminUser) -> ThinkingMethodView:
    """中文：归档数学方法。 English: Archives a mathematical method."""
    try:
        return thinking_method_service.archive_method(method_id, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_error(error) from error
