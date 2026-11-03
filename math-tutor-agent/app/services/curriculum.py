from __future__ import annotations

from app.catalogs.loader import load_catalog_for_graph
from app.core.product_scope import MVP_GRADE_BAND, MVP_SUBJECT_CODE
from app.domain.curriculum import CurriculumCatalogSummary, KnowledgeGraphView, KnowledgePointDetailView, KnowledgePracticeSource
from app.repositories.curriculum import CurriculumRepository, KnowledgePointNotFound, KnowledgePracticeSourceNotFound


class CurriculumService:
    """中文：定义“课程·服务”类，封装该职责相关的数据与行为。
    English: Defines the curriculum service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, repository: CurriculumRepository | None = None) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.repository = repository or CurriculumRepository()

    def list_catalogs(self, *, subject: str | None = None, grade_band: str | None = None) -> list[CurriculumCatalogSummary]:
        """中文：读取学生端可选择的已发布知识目录。 English: Reads published curriculum catalogs available to learners."""
        return self.repository.list_catalogs(subject=subject, grade_band=grade_band)

    def knowledge_graph(
        self,
        *,
        subject: str,
        grade_band: str,
        root_code: str,
    ) -> KnowledgeGraphView:
        """中文：处理“知识·graph”相关操作。
        English: Handles the knowledge graph operation.
        """
        points, prerequisites = self.repository.knowledge_graph(
            subject=subject,
            grade_band=grade_band,
            root_code=root_code,
        )
        managed = self.repository.catalog_metadata(root_code)
        if managed is None:
            legacy = load_catalog_for_graph(subject=subject, grade_band=grade_band, root_code=root_code)
            managed = (legacy.catalog_code, legacy.version, legacy.title)
        return KnowledgeGraphView(
            catalog_code=managed[0],
            catalog_version=managed[1],
            title=managed[2],
            subject=subject,
            grade_band=grade_band,
            root_code=root_code,
            knowledge_points=points,
            prerequisites=prerequisites,
        )

    def knowledge_point_detail(self, code: str) -> KnowledgePointDetailView:
        """中文：读取知识点下已发布的教学内容。 English: Reads published teaching content for a knowledge point."""
        detail = self.repository.knowledge_point_detail(code)
        if detail.grade_band != MVP_GRADE_BAND:
            raise KnowledgePointNotFound(code)
        return detail

    def knowledge_practice_source(
        self,
        knowledge_point_code: str,
        content_key: str,
    ) -> KnowledgePracticeSource:
        """中文：读取相似题生成所需的已发布例题与框架。 English: Reads the published example and framework required for similar-practice generation."""

        source = self.repository.knowledge_practice_source(
            knowledge_point_code,
            content_key,
        )
        if source.subject != MVP_SUBJECT_CODE or source.grade_band != MVP_GRADE_BAND:
            raise KnowledgePracticeSourceNotFound(
                f"{knowledge_point_code}:{content_key}"
            )
        return source


curriculum_service = CurriculumService()
