from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies.auth import CurrentUser
from app.core.product_scope import MVP_DEFAULT_ROOT_CODE, MVP_GRADE_BAND, MVP_SUBJECT_CODE
from app.domain.curriculum import CurriculumCatalogSummary, KnowledgeGraphView, KnowledgePointDetailView
from app.repositories.curriculum import KnowledgePointNotFound
from app.services.curriculum import curriculum_service


router = APIRouter(prefix="/curriculum", tags=["curriculum"])


@router.get("/catalogs", response_model=list[CurriculumCatalogSummary])
def list_curriculum_catalogs(
    _: CurrentUser,
) -> list[CurriculumCatalogSummary]:
    """中文：列出学生端可用的已发布知识目录。 English: Lists published curriculum catalogs available to learners."""
    return curriculum_service.list_catalogs(
        subject=MVP_SUBJECT_CODE, grade_band=MVP_GRADE_BAND
    )


@router.get("/knowledge-graph", response_model=KnowledgeGraphView)
def get_knowledge_graph(
    _: CurrentUser,
    root_code: str = Query(default=MVP_DEFAULT_ROOT_CODE, min_length=1, max_length=80),
) -> KnowledgeGraphView:
    """中文：处理“获取·知识·graph”相关操作。
    English: Handles the get knowledge graph operation.
    """
    try:
        return curriculum_service.knowledge_graph(
            subject=MVP_SUBJECT_CODE,
            grade_band=MVP_GRADE_BAND,
            root_code=root_code,
        )
    except KnowledgePointNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"知识点目录根节点不存在：{error.args[0]}",
        ) from error


@router.get("/knowledge-points/{code}", response_model=KnowledgePointDetailView)
def get_knowledge_point_detail(code: str, _: CurrentUser) -> KnowledgePointDetailView:
    """中文：读取知识点及已发布的定义、性质、定理、公式和题型。 English: Reads a point and its published definitions, properties, theorems, formulas, and problem types."""
    try:
        return curriculum_service.knowledge_point_detail(code)
    except KnowledgePointNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"知识点不存在：{code}") from error
