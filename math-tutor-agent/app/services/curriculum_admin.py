from __future__ import annotations


from app.domain.curriculum_admin import (
    CatalogView,
    CatalogWrite,
    KnowledgeContentView,
    KnowledgeContentWrite,
    KnowledgeDashboard,
    BulkKnowledgePointDeleteResult,
    KnowledgePointAdminView,
    KnowledgePointWrite,
    PrerequisiteAdminView,
    PrerequisiteWrite,
)
from app.repositories.curriculum_admin import CurriculumAdminRepository


class CurriculumAdminService:
    """中文：组织知识目录管理用例。 English: Coordinates knowledge administration use cases."""

    def __init__(self, repository: CurriculumAdminRepository | None = None) -> None:
        """中文：注入知识管理仓储。 English: Injects the knowledge administration repository."""
        self.repository = repository or CurriculumAdminRepository()

    def close(self) -> None:
        """中文：释放服务持有的资源。 English: Releases resources owned by the service."""
        self.repository.close()

    def dashboard(self) -> KnowledgeDashboard:
        """中文：返回管理概览。 English: Returns the administration overview."""
        return self.repository.dashboard()

    def list_catalogs(self) -> list[CatalogView]:
        """中文：返回知识目录。 English: Returns knowledge catalogs."""
        return self.repository.list_catalogs()

    def create_catalog(self, payload: CatalogWrite, actor_id: str) -> CatalogView:
        """中文：创建知识目录。 English: Creates a knowledge catalog."""
        return self.repository.create_catalog(payload, actor_id)

    def update_catalog(self, catalog_id: int, payload: CatalogWrite, actor_id: str) -> CatalogView:
        """中文：更新知识目录。 English: Updates a knowledge catalog."""
        return self.repository.update_catalog(catalog_id, payload, actor_id)

    def delete_catalog(self, catalog_id: int, actor_id: str) -> None:
        """中文：删除空知识目录。 English: Deletes an empty knowledge catalog."""
        self.repository.delete_catalog(catalog_id, actor_id)

    def list_points(self, catalog_id: int | None, search: str | None, include_inactive: bool) -> list[KnowledgePointAdminView]:
        """中文：筛选知识点。 English: Filters knowledge points."""
        return self.repository.list_points(
            catalog_id=catalog_id, search=search, include_inactive=include_inactive
        )

    def create_point(self, payload: KnowledgePointWrite, actor_id: str) -> KnowledgePointAdminView:
        """中文：创建知识点。 English: Creates a knowledge point."""
        return self.repository.create_point(payload, actor_id)

    def update_point(self, point_id: int, payload: KnowledgePointWrite, actor_id: str) -> KnowledgePointAdminView:
        """中文：更新知识点。 English: Updates a knowledge point."""
        return self.repository.update_point(point_id, payload, actor_id)

    def delete_point(self, point_id: int, actor_id: str) -> None:
        """中文：安全删除知识点。 English: Safely deletes a knowledge point."""
        self.repository.delete_point(point_id, actor_id)

    def delete_points(self, point_ids: list[int], actor_id: str) -> BulkKnowledgePointDeleteResult:
        """中文：批量安全删除知识点。 English: Safely deletes knowledge points in bulk."""
        return self.repository.delete_points(point_ids, actor_id)

    def list_relations(self, catalog_id: int | None) -> list[PrerequisiteAdminView]:
        """中文：列出先修关系。 English: Lists prerequisite relationships."""
        return self.repository.list_relations(catalog_id)

    def upsert_relation(self, payload: PrerequisiteWrite, actor_id: str) -> PrerequisiteAdminView:
        """中文：保存先修关系。 English: Saves a prerequisite relationship."""
        return self.repository.upsert_relation(payload, actor_id)

    def delete_relation(self, knowledge_code: str, prerequisite_code: str, actor_id: str) -> None:
        """中文：删除先修关系。 English: Deletes a prerequisite relationship."""
        self.repository.delete_relation(knowledge_code, prerequisite_code, actor_id)

    def list_contents(self, point_id: int | None, content_type: str | None, status: str | None) -> list[KnowledgeContentView]:
        """中文：筛选知识内容。 English: Filters knowledge content."""
        return self.repository.list_contents(point_id=point_id, content_type=content_type, status=status)

    def create_content(self, point_id: int, payload: KnowledgeContentWrite, actor_id: str) -> KnowledgeContentView:
        """中文：创建知识内容。 English: Creates knowledge content."""
        return self.repository.create_content(point_id, payload, actor_id)

    def update_content(self, content_id: str, payload: KnowledgeContentWrite, actor_id: str) -> KnowledgeContentView:
        """中文：更新知识内容。 English: Updates knowledge content."""
        return self.repository.update_content(content_id, payload, actor_id)

    def archive_content(self, content_id: str, actor_id: str) -> KnowledgeContentView:
        """中文：归档知识内容。 English: Archives knowledge content."""
        return self.repository.archive_content(content_id, actor_id)


curriculum_admin_service = CurriculumAdminService()
