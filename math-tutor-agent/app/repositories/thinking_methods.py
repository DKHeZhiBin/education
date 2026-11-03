from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import create_mysql_engine, create_session_factory
from app.domain.thinking_methods import (
    PublishedThinkingMethod,
    PublishedThinkingMethodCategory,
    ThinkingMethodCategoryView,
    ThinkingMethodCategoryWrite,
    ThinkingMethodDetail,
    ThinkingMethodView,
    ThinkingMethodWrite,
)
from app.models.knowledge_content import KnowledgeAdminAudit
from app.models.thinking_method import ThinkingMethod, ThinkingMethodCategory
from app.repositories.curriculum_admin import CurriculumAdminConflict, CurriculumAdminNotFound


class ThinkingMethodRepository:
    """中文：数学思想分类与方法的读写仓储。 English: Repository for mathematical thinking categories and methods."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        """中文：初始化数据库会话工厂。 English: Initializes the database session factory."""
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())

    def close(self) -> None:
        """中文：释放数据库连接池。 English: Disposes the database connection pool."""
        self.session_factory.kw["bind"].dispose()

    def published_catalog(self) -> list[PublishedThinkingMethodCategory]:
        """中文：返回学生端可见的已发布方法目录。 English: Returns the published learner-facing method catalog."""
        with self.session_factory() as db:
            categories = list(db.scalars(select(ThinkingMethodCategory).where(ThinkingMethodCategory.status == "published").order_by(ThinkingMethodCategory.sort_order, ThinkingMethodCategory.code)))
            if not categories:
                return []
            methods = list(db.scalars(select(ThinkingMethod).where(ThinkingMethod.category_id.in_([item.id for item in categories]), ThinkingMethod.status == "published").order_by(ThinkingMethod.sort_order, ThinkingMethod.code)))
            codes = {item.id: item.code for item in methods}
            grouped: dict[int, list[PublishedThinkingMethod]] = {item.id: [] for item in categories}
            for item in methods:
                grouped[item.category_id].append(self._published_method(item, codes.get(item.parent_method_id)))
            return [PublishedThinkingMethodCategory(
                code=item.code, label=item.label, symbol=item.symbol, focus=item.focus,
                description=item.description, reminder=item.reminder, sort_order=item.sort_order,
                methods=grouped[item.id],
            ) for item in categories]

    def published_detail(self, code: str) -> ThinkingMethodDetail:
        """中文：按稳定编码读取已发布方法详情。 English: Reads a published method detail by stable code."""
        with self.session_factory() as db:
            row = db.execute(select(ThinkingMethod, ThinkingMethodCategory).join(ThinkingMethodCategory).where(
                ThinkingMethod.code == code,
                ThinkingMethod.status == "published",
                ThinkingMethodCategory.status == "published",
            )).one_or_none()
            if row is None:
                raise CurriculumAdminNotFound(f"数学方法不存在：{code}")
            item, category = row
            parent_code = db.scalar(select(ThinkingMethod.code).where(ThinkingMethod.id == item.parent_method_id)) if item.parent_method_id else None
            return ThinkingMethodDetail(**self._published_method(item, parent_code).model_dump(), category_code=category.code, category_label=category.label)

    def list_categories(self) -> list[ThinkingMethodCategoryView]:
        """中文：列出全部思想分类及其方法数量。 English: Lists all thinking categories with method counts."""
        with self.session_factory() as db:
            rows = db.execute(select(ThinkingMethodCategory, func.count(ThinkingMethod.id)).outerjoin(ThinkingMethod).group_by(ThinkingMethodCategory.id).order_by(ThinkingMethodCategory.sort_order, ThinkingMethodCategory.code)).all()
            return [self._category_view(item, count) for item, count in rows]

    def create_category(self, payload: ThinkingMethodCategoryWrite, actor_id: str) -> ThinkingMethodCategoryView:
        """中文：创建思想分类并写入审计。 English: Creates a thinking category and writes an audit record."""
        with self.session_factory.begin() as db:
            item = ThinkingMethodCategory(**payload.model_dump(exclude={"expected_version"}))
            db.add(item); db.flush()
            snapshot = self._category_dict(item)
            self._audit(db, actor_id, "create", "thinking_method_category", str(item.id), None, snapshot)
            return self._category_view(item, 0)

    def update_category(self, category_id: int, payload: ThinkingMethodCategoryWrite, actor_id: str) -> ThinkingMethodCategoryView:
        """中文：使用乐观锁更新思想分类。 English: Updates a thinking category with optimistic locking."""
        with self.session_factory.begin() as db:
            item = db.get(ThinkingMethodCategory, category_id)
            if item is None:
                raise CurriculumAdminNotFound("思想分类不存在")
            self._check_version(payload.expected_version, item.version_lock)
            before = self._category_dict(item)
            for key, value in payload.model_dump(exclude={"expected_version"}).items():
                setattr(item, key, value)
            item.version_lock += 1; db.flush()
            self._audit(db, actor_id, "update", "thinking_method_category", str(item.id), before, self._category_dict(item))
            count = db.scalar(select(func.count()).select_from(ThinkingMethod).where(ThinkingMethod.category_id == item.id)) or 0
            return self._category_view(item, count)

    def archive_category(self, category_id: int, actor_id: str) -> ThinkingMethodCategoryView:
        """中文：归档空分类，避免误删其下方法。 English: Archives an empty category without orphaning methods."""
        with self.session_factory.begin() as db:
            item = db.get(ThinkingMethodCategory, category_id)
            if item is None:
                raise CurriculumAdminNotFound("思想分类不存在")
            count = db.scalar(select(func.count()).select_from(ThinkingMethod).where(ThinkingMethod.category_id == item.id, ThinkingMethod.status != "archived")) or 0
            if count:
                raise CurriculumAdminConflict(f"分类中仍有 {count} 个未归档方法，请先移动或归档这些方法")
            before = self._category_dict(item); item.status = "archived"; item.version_lock += 1; db.flush()
            self._audit(db, actor_id, "archive", "thinking_method_category", str(item.id), before, self._category_dict(item))
            return self._category_view(item, 0)

    def list_methods(self, *, category_id: int | None = None, status: str | None = None, search: str | None = None) -> list[ThinkingMethodView]:
        """中文：按分类、状态和关键词筛选数学方法。 English: Filters mathematical methods by category, status, and keyword."""
        with self.session_factory() as db:
            query = select(ThinkingMethod, ThinkingMethodCategory).join(ThinkingMethodCategory).order_by(ThinkingMethodCategory.sort_order, ThinkingMethod.sort_order, ThinkingMethod.code)
            if category_id is not None:
                query = query.where(ThinkingMethod.category_id == category_id)
            if status:
                query = query.where(ThinkingMethod.status == status)
            if search:
                pattern = f"%{search}%"
                query = query.where(or_(ThinkingMethod.name.like(pattern), ThinkingMethod.code.like(pattern), ThinkingMethod.goal.like(pattern)))
            rows = db.execute(query).all()
            parent_ids = {item.parent_method_id for item, _ in rows if item.parent_method_id}
            parents = {item.id: item.code for item in db.scalars(select(ThinkingMethod).where(ThinkingMethod.id.in_(parent_ids)))} if parent_ids else {}
            return [self._method_view(item, category, parents.get(item.parent_method_id)) for item, category in rows]

    def create_method(self, payload: ThinkingMethodWrite, actor_id: str) -> ThinkingMethodView:
        """中文：创建数学方法并写入审计。 English: Creates a mathematical method and writes an audit record."""
        with self.session_factory.begin() as db:
            category = self._category(db, payload.category_id)
            self._validate_parent(db, payload.parent_method_id, payload.category_id)
            item = ThinkingMethod(**self._method_values(payload))
            db.add(item); db.flush()
            snapshot = self._method_dict(item)
            self._audit(db, actor_id, "create", "thinking_method", str(item.id), None, snapshot)
            parent_code = db.scalar(select(ThinkingMethod.code).where(ThinkingMethod.id == item.parent_method_id)) if item.parent_method_id else None
            return self._method_view(item, category, parent_code)

    def update_method(self, method_id: int, payload: ThinkingMethodWrite, actor_id: str) -> ThinkingMethodView:
        """中文：使用乐观锁更新数学方法。 English: Updates a mathematical method with optimistic locking."""
        with self.session_factory.begin() as db:
            item = db.get(ThinkingMethod, method_id)
            if item is None:
                raise CurriculumAdminNotFound("数学方法不存在")
            self._check_version(payload.expected_version, item.version_lock)
            category = self._category(db, payload.category_id)
            if payload.parent_method_id == item.id:
                raise CurriculumAdminConflict("方法不能把自己设为上级")
            self._validate_parent(db, payload.parent_method_id, payload.category_id)
            before = self._method_dict(item)
            for key, value in self._method_values(payload).items():
                setattr(item, key, value)
            item.version_lock += 1; db.flush()
            self._audit(db, actor_id, "update", "thinking_method", str(item.id), before, self._method_dict(item))
            parent_code = db.scalar(select(ThinkingMethod.code).where(ThinkingMethod.id == item.parent_method_id)) if item.parent_method_id else None
            return self._method_view(item, category, parent_code)

    def archive_method(self, method_id: int, actor_id: str) -> ThinkingMethodView:
        """中文：归档方法并解除其子方法的上级关系。 English: Archives a method and detaches its child methods."""
        with self.session_factory.begin() as db:
            item = db.get(ThinkingMethod, method_id)
            if item is None:
                raise CurriculumAdminNotFound("数学方法不存在")
            category = db.get(ThinkingMethodCategory, item.category_id)
            before = self._method_dict(item)
            for child in db.scalars(select(ThinkingMethod).where(ThinkingMethod.parent_method_id == item.id)):
                child.parent_method_id = None; child.version_lock += 1
            item.status = "archived"; item.version_lock += 1; db.flush()
            self._audit(db, actor_id, "archive", "thinking_method", str(item.id), before, self._method_dict(item))
            parent_code = db.scalar(select(ThinkingMethod.code).where(ThinkingMethod.id == item.parent_method_id)) if item.parent_method_id else None
            return self._method_view(item, category, parent_code)

    @staticmethod
    def _method_values(payload: ThinkingMethodWrite) -> dict[str, Any]:
        """中文：把接口字段映射到数据库 JSON 列。 English: Maps API fields to database JSON columns."""
        values = payload.model_dump(exclude={"expected_version", "grade_bands", "domain_tags", "aliases", "detail"})
        values.update(grade_bands_json=payload.grade_bands, domain_tags_json=payload.domain_tags, aliases_json=payload.aliases, detail_json=payload.detail)
        return values

    @staticmethod
    def _category(db: Session, category_id: int) -> ThinkingMethodCategory:
        """中文：读取方法分类。 English: Loads a method category."""
        item = db.get(ThinkingMethodCategory, category_id)
        if item is None:
            raise CurriculumAdminNotFound("思想分类不存在")
        return item

    @staticmethod
    def _validate_parent(db: Session, parent_id: int | None, category_id: int) -> None:
        """中文：确保上级方法存在且属于同一分类。 English: Ensures the parent method exists in the same category."""
        if parent_id is None:
            return
        parent = db.get(ThinkingMethod, parent_id)
        if parent is None:
            raise CurriculumAdminNotFound("上级方法不存在")
        if parent.category_id != category_id:
            raise CurriculumAdminConflict("上级方法必须与当前方法属于同一分类")

    @staticmethod
    def _check_version(expected: int | None, actual: int) -> None:
        """中文：执行乐观锁版本检查。 English: Performs an optimistic-lock version check."""
        if expected is not None and expected != actual:
            raise CurriculumAdminConflict("内容已被其他操作更新，请刷新后重试")

    @staticmethod
    def _audit(db: Session, actor_id: str, action: str, resource_type: str, resource_id: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
        """中文：追加知识管理审计记录。 English: Appends a knowledge-administration audit record."""
        db.add(KnowledgeAdminAudit(actor_user_id=actor_id, action=action, resource_type=resource_type, resource_id=resource_id, before_json=before, after_json=after))

    @staticmethod
    def _category_dict(item: ThinkingMethodCategory) -> dict[str, Any]:
        """中文：序列化思想分类。 English: Serializes a thinking category."""
        return {key: getattr(item, key) for key in ("id", "code", "label", "symbol", "focus", "description", "reminder", "sort_order", "status", "version_lock")}

    def _category_view(self, item: ThinkingMethodCategory, count: int) -> ThinkingMethodCategoryView:
        """中文：构造管理端思想分类视图。 English: Builds an administrator category view."""
        return ThinkingMethodCategoryView(**self._category_dict(item), method_count=count, updated_at=item.updated_at)

    @staticmethod
    def _method_dict(item: ThinkingMethod) -> dict[str, Any]:
        """中文：序列化数学方法。 English: Serializes a mathematical method."""
        return {
            "id": item.id, "code": item.code, "category_id": item.category_id, "parent_method_id": item.parent_method_id,
            "name": item.name, "kind": item.kind, "level": item.level, "goal": item.goal, "example": item.example,
            "grade_bands": item.grade_bands_json, "domain_tags": item.domain_tags_json, "aliases": item.aliases_json,
            "detail": item.detail_json, "sort_order": item.sort_order, "status": item.status, "version_lock": item.version_lock,
        }

    def _method_view(self, item: ThinkingMethod, category: ThinkingMethodCategory, parent_code: str | None) -> ThinkingMethodView:
        """中文：构造管理端数学方法视图。 English: Builds an administrator method view."""
        return ThinkingMethodView(**self._method_dict(item), category_code=category.code, category_label=category.label, parent_method_code=parent_code, updated_at=item.updated_at)

    @staticmethod
    def _published_method(item: ThinkingMethod, parent_code: str | None) -> PublishedThinkingMethod:
        """中文：构造学生端已发布方法视图。 English: Builds a learner-facing published method view."""
        return PublishedThinkingMethod(
            code=item.code, parent_method_code=parent_code, name=item.name, kind=item.kind, level=item.level,
            goal=item.goal, example=item.example, grade_bands=item.grade_bands_json, domain_tags=item.domain_tags_json,
            aliases=item.aliases_json, detail=item.detail_json, sort_order=item.sort_order,
        )
