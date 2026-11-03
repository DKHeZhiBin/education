from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies.auth import AdminUser
from app.domain.curriculum_admin import (
    CatalogView,
    CatalogWrite,
    KnowledgeContentView,
    KnowledgeContentWrite,
    KnowledgeDashboard,
    BulkKnowledgePointDelete,
    BulkKnowledgePointDeleteResult,
    KnowledgePointAdminView,
    KnowledgePointWrite,
    PrerequisiteAdminView,
    PrerequisiteWrite,
)
from app.repositories.curriculum_admin import CurriculumAdminConflict, CurriculumAdminNotFound
from app.services.curriculum_admin import curriculum_admin_service


router = APIRouter(prefix="/admin/curriculum", tags=["admin-curriculum"])


def _translate_admin_error(error: Exception) -> HTTPException:
    """中文：把仓储错误转换为稳定的 HTTP 状态。 English: Converts repository errors into stable HTTP statuses."""
    if isinstance(error, CurriculumAdminNotFound):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, IntegrityError):
        return HTTPException(status_code=409, detail="编码、版本或内容键已经存在")
    return HTTPException(status_code=409, detail=str(error))


@router.get("/dashboard", response_model=KnowledgeDashboard)
def dashboard(_: AdminUser) -> KnowledgeDashboard:
    """中文：读取知识管理统计。 English: Reads knowledge administration statistics."""
    return curriculum_admin_service.dashboard()


@router.get("/catalogs", response_model=list[CatalogView])
def list_catalogs(_: AdminUser) -> list[CatalogView]:
    """中文：列出知识目录。 English: Lists knowledge catalogs."""
    return curriculum_admin_service.list_catalogs()


@router.post("/catalogs", response_model=CatalogView, status_code=status.HTTP_201_CREATED)
def create_catalog(payload: CatalogWrite, actor: AdminUser) -> CatalogView:
    """中文：创建知识目录。 English: Creates a knowledge catalog."""
    try:
        return curriculum_admin_service.create_catalog(payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error


@router.put("/catalogs/{catalog_id}", response_model=CatalogView)
def update_catalog(catalog_id: int, payload: CatalogWrite, actor: AdminUser) -> CatalogView:
    """中文：更新知识目录。 English: Updates a knowledge catalog."""
    try:
        return curriculum_admin_service.update_catalog(catalog_id, payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error


@router.delete("/catalogs/{catalog_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_catalog(catalog_id: int, actor: AdminUser) -> Response:
    """中文：删除不包含知识点的目录。 English: Deletes a catalog that contains no knowledge points."""
    try:
        curriculum_admin_service.delete_catalog(catalog_id, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/points", response_model=list[KnowledgePointAdminView])
def list_points(
    actor: AdminUser,
    catalog_id: int | None = None,
    search: str | None = None,
    include_inactive: bool = True,
) -> list[KnowledgePointAdminView]:
    """中文：按目录与关键字筛选知识点。 English: Filters knowledge points by catalog and keyword."""
    del actor
    return curriculum_admin_service.list_points(catalog_id, search, include_inactive)


@router.post("/points", response_model=KnowledgePointAdminView, status_code=status.HTTP_201_CREATED)
def create_point(payload: KnowledgePointWrite, actor: AdminUser) -> KnowledgePointAdminView:
    """中文：创建知识星图节点。 English: Creates a knowledge-planet node."""
    try:
        return curriculum_admin_service.create_point(payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error


@router.put("/points/{point_id}", response_model=KnowledgePointAdminView)
def update_point(point_id: int, payload: KnowledgePointWrite, actor: AdminUser) -> KnowledgePointAdminView:
    """中文：更新知识星图节点。 English: Updates a knowledge-planet node."""
    try:
        return curriculum_admin_service.update_point(point_id, payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error


@router.delete("/points/{point_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_point(point_id: int, actor: AdminUser) -> Response:
    """中文：安全删除知识点、图关系及其未归档内容。 English: Safely deletes a point, its graph edges, and active content."""
    try:
        curriculum_admin_service.delete_point(point_id, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/points/bulk-delete", response_model=BulkKnowledgePointDeleteResult)
def bulk_delete_points(payload: BulkKnowledgePointDelete, actor: AdminUser) -> BulkKnowledgePointDeleteResult:
    """中文：在单个事务中批量安全删除知识点。 English: Safely deletes knowledge points in bulk within one transaction."""
    try:
        return curriculum_admin_service.delete_points(payload.point_ids, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error


@router.get("/relations", response_model=list[PrerequisiteAdminView])
def list_relations(actor: AdminUser, catalog_id: int | None = None) -> list[PrerequisiteAdminView]:
    """中文：列出知识点先修关系。 English: Lists knowledge-point prerequisite relationships."""
    del actor
    return curriculum_admin_service.list_relations(catalog_id)


@router.put("/relations", response_model=PrerequisiteAdminView)
def upsert_relation(payload: PrerequisiteWrite, actor: AdminUser) -> PrerequisiteAdminView:
    """中文：新增或更新先修关系。 English: Creates or updates a prerequisite relationship."""
    try:
        return curriculum_admin_service.upsert_relation(payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error


@router.delete("/relations", status_code=status.HTTP_204_NO_CONTENT)
def delete_relation(
    actor: AdminUser,
    knowledge_code: str = Query(min_length=1),
    prerequisite_code: str = Query(min_length=1),
) -> Response:
    """中文：删除先修关系。 English: Deletes a prerequisite relationship."""
    try:
        curriculum_admin_service.delete_relation(knowledge_code, prerequisite_code, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/contents", response_model=list[KnowledgeContentView])
def list_contents(
    actor: AdminUser,
    point_id: int | None = None,
    content_type: str | None = None,
    content_status: str | None = Query(default=None, alias="status"),
) -> list[KnowledgeContentView]:
    """中文：筛选定义、性质、定理、公式和题型。 English: Filters definitions, properties, theorems, formulas, and problem types."""
    del actor
    return curriculum_admin_service.list_contents(point_id, content_type, content_status)


@router.post("/points/{point_id}/contents", response_model=KnowledgeContentView, status_code=status.HTTP_201_CREATED)
def create_content(point_id: int, payload: KnowledgeContentWrite, actor: AdminUser) -> KnowledgeContentView:
    """中文：给知识点新增内容。 English: Adds content to a knowledge point."""
    try:
        return curriculum_admin_service.create_content(point_id, payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error


@router.put("/contents/{content_id}", response_model=KnowledgeContentView)
def update_content(content_id: str, payload: KnowledgeContentWrite, actor: AdminUser) -> KnowledgeContentView:
    """中文：更新知识内容。 English: Updates knowledge content."""
    try:
        return curriculum_admin_service.update_content(content_id, payload, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error


@router.delete("/contents/{content_id}", response_model=KnowledgeContentView)
def archive_content(content_id: str, actor: AdminUser) -> KnowledgeContentView:
    """中文：归档知识内容并保留审计历史。 English: Archives knowledge content while retaining its audit history."""
    try:
        return curriculum_admin_service.archive_content(content_id, actor.id)
    except (CurriculumAdminNotFound, CurriculumAdminConflict, IntegrityError) as error:
        raise _translate_admin_error(error) from error
