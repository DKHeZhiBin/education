from app.domain.thinking_methods import (
    PublishedThinkingMethodCategory,
    ThinkingMethodCategoryView,
    ThinkingMethodCategoryWrite,
    ThinkingMethodDetail,
    ThinkingMethodView,
    ThinkingMethodWrite,
)
from app.repositories.thinking_methods import ThinkingMethodRepository


class ThinkingMethodService:
    """中文：组织数学思想与方法的学生端和管理端用例。 English: Coordinates learner and administrator thinking-method use cases."""

    def __init__(self, repository: ThinkingMethodRepository | None = None) -> None:
        """中文：注入数学方法仓储。 English: Injects the thinking-method repository."""
        self.repository = repository or ThinkingMethodRepository()

    def close(self) -> None:
        """中文：释放服务资源。 English: Releases service resources."""
        self.repository.close()

    def published_catalog(self) -> list[PublishedThinkingMethodCategory]:
        """中文：读取学生端方法总目录。 English: Reads the learner-facing method catalog."""
        return self.repository.published_catalog()

    def published_detail(self, code: str) -> ThinkingMethodDetail:
        """中文：读取学生端方法详情。 English: Reads a learner-facing method detail."""
        return self.repository.published_detail(code)

    def list_categories(self) -> list[ThinkingMethodCategoryView]:
        """中文：列出管理端思想分类。 English: Lists administrator thinking categories."""
        return self.repository.list_categories()

    def create_category(self, payload: ThinkingMethodCategoryWrite, actor_id: str) -> ThinkingMethodCategoryView:
        """中文：创建思想分类。 English: Creates a thinking category."""
        return self.repository.create_category(payload, actor_id)

    def update_category(self, category_id: int, payload: ThinkingMethodCategoryWrite, actor_id: str) -> ThinkingMethodCategoryView:
        """中文：更新思想分类。 English: Updates a thinking category."""
        return self.repository.update_category(category_id, payload, actor_id)

    def archive_category(self, category_id: int, actor_id: str) -> ThinkingMethodCategoryView:
        """中文：归档思想分类。 English: Archives a thinking category."""
        return self.repository.archive_category(category_id, actor_id)

    def list_methods(self, category_id: int | None, status: str | None, search: str | None) -> list[ThinkingMethodView]:
        """中文：筛选管理端数学方法。 English: Filters administrator mathematical methods."""
        return self.repository.list_methods(category_id=category_id, status=status, search=search)

    def create_method(self, payload: ThinkingMethodWrite, actor_id: str) -> ThinkingMethodView:
        """中文：创建数学方法。 English: Creates a mathematical method."""
        return self.repository.create_method(payload, actor_id)

    def update_method(self, method_id: int, payload: ThinkingMethodWrite, actor_id: str) -> ThinkingMethodView:
        """中文：更新数学方法。 English: Updates a mathematical method."""
        return self.repository.update_method(method_id, payload, actor_id)

    def archive_method(self, method_id: int, actor_id: str) -> ThinkingMethodView:
        """中文：归档数学方法。 English: Archives a mathematical method."""
        return self.repository.archive_method(method_id, actor_id)


thinking_method_service = ThinkingMethodService()
