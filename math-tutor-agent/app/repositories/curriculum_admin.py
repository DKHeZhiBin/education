from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import create_mysql_engine, create_session_factory
from app.core.product_scope import MVP_GRADE_BAND, MVP_SUBJECT_CODE
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
from app.models.knowledge_content import KnowledgeAdminAudit, KnowledgeCatalog, KnowledgePointContent
from app.models.learning import KnowledgePoint, KnowledgePointPrerequisite


class CurriculumAdminNotFound(LookupError):
    """中文：管理对象不存在。 English: Raised when an administrator-managed resource is missing."""


class CurriculumAdminConflict(RuntimeError):
    """中文：版本冲突或目录关系冲突。 English: Raised for optimistic-lock or relationship conflicts."""


class CurriculumAdminRepository:
    """中文：知识目录、关系和教学内容的管理仓储。 English: Repository for managed catalogs, relations, and teaching content."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        """中文：初始化数据库会话工厂。 English: Initializes the database session factory."""
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())

    def close(self) -> None:
        """中文：释放数据库连接池。 English: Disposes the database connection pool."""
        self.session_factory.kw["bind"].dispose()

    def dashboard(self) -> KnowledgeDashboard:
        """中文：汇总管理首页统计。 English: Aggregates administration dashboard statistics."""
        with self.session_factory() as db:
            scope = (
                KnowledgePoint.subject == MVP_SUBJECT_CODE,
                KnowledgePoint.grade_band == MVP_GRADE_BAND,
            )
            catalogs = db.scalar(select(func.count()).select_from(KnowledgeCatalog).where(
                KnowledgeCatalog.subject == MVP_SUBJECT_CODE,
                KnowledgeCatalog.grade_band == MVP_GRADE_BAND,
            )) or 0
            points = db.scalar(select(func.count()).select_from(KnowledgePoint).where(*scope)) or 0
            active = db.scalar(select(func.count()).select_from(KnowledgePoint).where(*scope, KnowledgePoint.active.is_(True))) or 0
            relations = db.scalar(select(func.count()).select_from(KnowledgePointPrerequisite).join(
                KnowledgePoint,
                KnowledgePoint.id == KnowledgePointPrerequisite.knowledge_point_id,
            ).where(*scope)) or 0
            content_rows = db.execute(select(
                KnowledgePointContent.content_type,
                KnowledgePointContent.status,
                func.count(),
            ).join(KnowledgePoint, KnowledgePoint.id == KnowledgePointContent.knowledge_point_id).where(
                *scope
            ).group_by(KnowledgePointContent.content_type, KnowledgePointContent.status)).all()
        by_type: Counter[str] = Counter()
        draft = published = 0
        for content_type, status, count in content_rows:
            by_type[content_type] += count
            draft += count if status == "draft" else 0
            published += count if status == "published" else 0
        return KnowledgeDashboard(catalogs=catalogs, knowledge_points=points, active_points=active, relations=relations, contents_by_type=dict(by_type), draft_contents=draft, published_contents=published)

    def list_catalogs(self) -> list[CatalogView]:
        """中文：列出全部知识目录。 English: Lists all knowledge catalogs."""
        with self.session_factory() as db:
            rows = db.execute(select(KnowledgeCatalog, func.count(KnowledgePoint.id)).outerjoin(KnowledgePoint, KnowledgePoint.catalog_id == KnowledgeCatalog.id).where(
                KnowledgeCatalog.subject == MVP_SUBJECT_CODE,
                KnowledgeCatalog.grade_band == MVP_GRADE_BAND,
            ).group_by(KnowledgeCatalog.id).order_by(KnowledgeCatalog.sort_order, KnowledgeCatalog.code)).all()
            return [self._catalog_view(item, count) for item, count in rows]

    def create_catalog(self, payload: CatalogWrite, actor_id: str) -> CatalogView:
        """中文：新建知识目录并写入审计。 English: Creates a catalog and writes an audit record."""
        with self.session_factory.begin() as db:
            item = KnowledgeCatalog(**payload.model_dump(exclude={"expected_version"}))
            db.add(item); db.flush()
            self._audit(db, actor_id, "create", "catalog", str(item.id), None, self._catalog_dict(item))
            return self._catalog_view(item, 0)

    def update_catalog(self, catalog_id: int, payload: CatalogWrite, actor_id: str) -> CatalogView:
        """中文：使用乐观锁更新知识目录。 English: Updates a catalog with optimistic locking."""
        with self.session_factory.begin() as db:
            item = db.get(KnowledgeCatalog, catalog_id)
            if item is None: raise CurriculumAdminNotFound("知识目录不存在")
            self._check_version(payload.expected_version, item.version_lock)
            before = self._catalog_dict(item)
            for key, value in payload.model_dump(exclude={"expected_version"}).items(): setattr(item, key, value)
            item.version_lock += 1; db.flush()
            self._audit(db, actor_id, "update", "catalog", str(item.id), before, self._catalog_dict(item))
            count = db.scalar(select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.catalog_id == item.id)) or 0
            return self._catalog_view(item, count)

    def delete_catalog(self, catalog_id: int, actor_id: str) -> None:
        """中文：删除没有知识点的空目录。 English: Deletes an empty catalog that has no knowledge points."""
        with self.session_factory.begin() as db:
            item = db.get(KnowledgeCatalog, catalog_id)
            if item is None:
                raise CurriculumAdminNotFound("知识目录不存在")
            point_count = db.scalar(select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.catalog_id == catalog_id)) or 0
            if point_count:
                raise CurriculumAdminConflict(f"目录中仍有 {point_count} 个知识点，请先移动或删除这些知识点")
            before = self._catalog_dict(item)
            db.delete(item)
            self._audit(db, actor_id, "delete", "catalog", str(catalog_id), before, None)

    def list_points(self, *, catalog_id: int | None = None, search: str | None = None, include_inactive: bool = True) -> list[KnowledgePointAdminView]:
        """中文：按目录和关键词列出知识点。 English: Lists knowledge points by catalog and search term."""
        with self.session_factory() as db:
            query = select(KnowledgePoint).where(
                KnowledgePoint.subject == MVP_SUBJECT_CODE,
                KnowledgePoint.grade_band == MVP_GRADE_BAND,
            ).order_by(KnowledgePoint.sort_order, KnowledgePoint.code)
            if catalog_id is not None: query = query.where(KnowledgePoint.catalog_id == catalog_id)
            if not include_inactive: query = query.where(KnowledgePoint.active.is_(True))
            if search: query = query.where(KnowledgePoint.name.like(f"%{search}%") | KnowledgePoint.code.like(f"%{search}%"))
            points = list(db.scalars(query))
            parent_ids = {point.parent_id for point in points if point.parent_id is not None}
            parents = {item.id: item.code for item in db.scalars(select(KnowledgePoint).where(KnowledgePoint.id.in_(parent_ids)))} if parent_ids else {}
            counts = {(point_id, content_type): count for point_id, content_type, count in db.execute(select(KnowledgePointContent.knowledge_point_id, KnowledgePointContent.content_type, func.count()).where(KnowledgePointContent.status != "archived").group_by(KnowledgePointContent.knowledge_point_id, KnowledgePointContent.content_type)).all()}
            return [self._point_view(point, parents.get(point.parent_id), counts) for point in points]

    def create_point(self, payload: KnowledgePointWrite, actor_id: str) -> KnowledgePointAdminView:
        """中文：创建可由管理端维护的知识点。 English: Creates an administrator-maintained knowledge point."""
        with self.session_factory.begin() as db:
            parent = self._point_by_code(db, payload.parent_code) if payload.parent_code else None
            item = KnowledgePoint(**payload.model_dump(exclude={"parent_code", "expected_version"}), parent_id=parent.id if parent else None)
            db.add(item); db.flush()
            after = self._point_dict(item, parent.code if parent else None)
            self._audit(db, actor_id, "create", "knowledge_point", str(item.id), None, after)
            return self._point_view(item, parent.code if parent else None, {})

    def update_point(self, point_id: int, payload: KnowledgePointWrite, actor_id: str) -> KnowledgePointAdminView:
        """中文：使用乐观锁更新知识点。 English: Updates a knowledge point with optimistic locking."""
        with self.session_factory.begin() as db:
            item = db.get(KnowledgePoint, point_id)
            if item is None: raise CurriculumAdminNotFound("知识点不存在")
            self._check_version(payload.expected_version, item.version_lock)
            parent = self._point_by_code(db, payload.parent_code) if payload.parent_code else None
            if parent and parent.id == item.id: raise CurriculumAdminConflict("知识点不能把自己设为父节点")
            before = self._point_dict(item, item.parent.code if item.parent else None)
            for key, value in payload.model_dump(exclude={"parent_code", "expected_version"}).items(): setattr(item, key, value)
            item.parent_id = parent.id if parent else None; item.version_lock += 1; db.flush()
            after = self._point_dict(item, parent.code if parent else None)
            self._audit(db, actor_id, "update", "knowledge_point", str(item.id), before, after)
            return self._point_view(item, parent.code if parent else None, {})

    def delete_point(self, point_id: int, actor_id: str) -> None:
        """中文：安全删除知识点并清理图关系、归档内容。 English: Safely deletes a point by removing graph edges and archiving its content."""
        with self.session_factory.begin() as db:
            item = db.get(KnowledgePoint, point_id)
            if item is None:
                raise CurriculumAdminNotFound("知识点不存在")
            child_count = db.scalar(select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.parent_id == point_id, KnowledgePoint.active.is_(True))) or 0
            if child_count:
                raise CurriculumAdminConflict(f"该知识点仍有 {child_count} 个子知识点，请先移动或删除子节点")
            before = self._point_dict(item, item.parent.code if item.parent else None)
            db.execute(delete(KnowledgePointPrerequisite).where(
                (KnowledgePointPrerequisite.knowledge_point_id == point_id)
                | (KnowledgePointPrerequisite.prerequisite_id == point_id)
            ))
            db.execute(update(KnowledgePointContent).where(
                KnowledgePointContent.knowledge_point_id == point_id,
                KnowledgePointContent.status != "archived",
            ).values(status="archived", updated_by_user_id=actor_id, version_lock=KnowledgePointContent.version_lock + 1))
            item.active = False
            item.version_lock += 1
            self._audit(db, actor_id, "delete", "knowledge_point", str(point_id), before, {**before, "active": False, "version_lock": item.version_lock})

    def delete_points(self, point_ids: list[int], actor_id: str) -> BulkKnowledgePointDeleteResult:
        """中文：在一个事务中批量安全删除知识点。 English: Safely deletes knowledge points in bulk within one transaction."""
        unique_ids = sorted(set(point_ids))
        with self.session_factory.begin() as db:
            items = list(db.scalars(select(KnowledgePoint).where(KnowledgePoint.id.in_(unique_ids)).with_for_update()))
            found_ids = {item.id for item in items}
            missing = [point_id for point_id in unique_ids if point_id not in found_ids]
            if missing:
                raise CurriculumAdminNotFound(f"部分知识点不存在：{', '.join(map(str, missing))}")
            external_children = list(db.scalars(select(KnowledgePoint).where(
                KnowledgePoint.parent_id.in_(unique_ids),
                KnowledgePoint.active.is_(True),
                KnowledgePoint.id.not_in(unique_ids),
            )))
            if external_children:
                names = "、".join(item.name for item in external_children[:5])
                raise CurriculumAdminConflict(f"所选知识点仍有未选中的子节点：{names}；请一起选择或先移动这些子节点")

            parent_ids = {item.parent_id for item in items if item.parent_id and item.parent_id not in found_ids}
            parent_codes = {parent.id: parent.code for parent in db.scalars(select(KnowledgePoint).where(KnowledgePoint.id.in_(parent_ids)))} if parent_ids else {}
            before_snapshots = {item.id: self._point_dict(item, parent_codes.get(item.parent_id)) for item in items}
            db.execute(delete(KnowledgePointPrerequisite).where(
                KnowledgePointPrerequisite.knowledge_point_id.in_(unique_ids)
                | KnowledgePointPrerequisite.prerequisite_id.in_(unique_ids)
            ))
            db.execute(update(KnowledgePointContent).where(
                KnowledgePointContent.knowledge_point_id.in_(unique_ids),
                KnowledgePointContent.status != "archived",
            ).values(status="archived", updated_by_user_id=actor_id, version_lock=KnowledgePointContent.version_lock + 1))
            for item in items:
                item.active = False
                item.version_lock += 1
                before = before_snapshots[item.id]
                self._audit(db, actor_id, "bulk_delete", "knowledge_point", str(item.id), before, {**before, "active": False, "version_lock": item.version_lock})
            return BulkKnowledgePointDeleteResult(deleted_count=len(items), deleted_ids=unique_ids)

    def list_relations(self, catalog_id: int | None = None) -> list[PrerequisiteAdminView]:
        """中文：列出先修关系。 English: Lists prerequisite relationships."""
        with self.session_factory() as db:
            query = select(KnowledgePointPrerequisite)
            relations = list(db.scalars(query))
            ids = {value for item in relations for value in (item.knowledge_point_id, item.prerequisite_id)}
            points = {item.id: item for item in db.scalars(select(KnowledgePoint).where(KnowledgePoint.id.in_(ids)))} if ids else {}
            relations = [item for item in relations if all(
                point is not None
                and point.subject == MVP_SUBJECT_CODE
                and point.grade_band == MVP_GRADE_BAND
                for point in (points.get(item.knowledge_point_id), points.get(item.prerequisite_id))
            )]
            if catalog_id is not None: relations = [item for item in relations if points.get(item.knowledge_point_id) and points[item.knowledge_point_id].catalog_id == catalog_id]
            return [PrerequisiteAdminView(knowledge_code=points[item.knowledge_point_id].code, prerequisite_code=points[item.prerequisite_id].code, knowledge_name=points[item.knowledge_point_id].name, prerequisite_name=points[item.prerequisite_id].name, strength=item.strength, required_level=item.required_level, rationale=item.rationale) for item in relations]

    def upsert_relation(self, payload: PrerequisiteWrite, actor_id: str) -> PrerequisiteAdminView:
        """中文：新增或更新先修关系并阻止循环。 English: Upserts a prerequisite relation and prevents cycles."""
        with self.session_factory.begin() as db:
            knowledge = self._point_by_code(db, payload.knowledge_code); prerequisite = self._point_by_code(db, payload.prerequisite_code)
            self._ensure_no_cycle(db, prerequisite.id, knowledge.id)
            item = db.get(KnowledgePointPrerequisite, (knowledge.id, prerequisite.id))
            before = None if item is None else {"strength": item.strength, "required_level": item.required_level, "rationale": item.rationale}
            if item is None:
                item = KnowledgePointPrerequisite(knowledge_point_id=knowledge.id, prerequisite_id=prerequisite.id)
                db.add(item)
            item.strength = payload.strength; item.required_level = payload.required_level; item.rationale = payload.rationale
            after = payload.model_dump(); self._audit(db, actor_id, "upsert", "prerequisite", f"{knowledge.id}:{prerequisite.id}", before, after)
            return PrerequisiteAdminView(**after, knowledge_name=knowledge.name, prerequisite_name=prerequisite.name)

    def delete_relation(self, knowledge_code: str, prerequisite_code: str, actor_id: str) -> None:
        """中文：删除指定先修关系。 English: Deletes a prerequisite relationship."""
        with self.session_factory.begin() as db:
            knowledge = self._point_by_code(db, knowledge_code); prerequisite = self._point_by_code(db, prerequisite_code)
            item = db.get(KnowledgePointPrerequisite, (knowledge.id, prerequisite.id))
            if item is None: raise CurriculumAdminNotFound("先修关系不存在")
            before = {"knowledge_code": knowledge_code, "prerequisite_code": prerequisite_code, "strength": item.strength, "required_level": item.required_level, "rationale": item.rationale}
            db.delete(item); self._audit(db, actor_id, "delete", "prerequisite", f"{knowledge.id}:{prerequisite.id}", before, None)

    def list_contents(self, *, point_id: int | None = None, content_type: str | None = None, status: str | None = None) -> list[KnowledgeContentView]:
        """中文：筛选知识内容条目。 English: Filters knowledge content items."""
        with self.session_factory() as db:
            query = select(KnowledgePointContent).order_by(KnowledgePointContent.knowledge_point_id, KnowledgePointContent.content_type, KnowledgePointContent.sort_order)
            if point_id is not None: query = query.where(KnowledgePointContent.knowledge_point_id == point_id)
            if content_type: query = query.where(KnowledgePointContent.content_type == content_type)
            if status: query = query.where(KnowledgePointContent.status == status)
            items = list(db.scalars(query)); point_ids = {item.knowledge_point_id for item in items}
            points = {item.id: item for item in db.scalars(select(KnowledgePoint).where(KnowledgePoint.id.in_(point_ids)))} if point_ids else {}
            return [
                self._content_view(item, points[item.knowledge_point_id])
                for item in items
                if points[item.knowledge_point_id].subject == MVP_SUBJECT_CODE
                and points[item.knowledge_point_id].grade_band == MVP_GRADE_BAND
            ]

    def create_content(self, point_id: int, payload: KnowledgeContentWrite, actor_id: str) -> KnowledgeContentView:
        """中文：创建知识内容条目。 English: Creates a knowledge content item."""
        with self.session_factory.begin() as db:
            point = db.get(KnowledgePoint, point_id)
            if point is None: raise CurriculumAdminNotFound("知识点不存在")
            values = payload.model_dump(exclude={"expected_version"})
            item = KnowledgePointContent(knowledge_point_id=point.id, created_by_user_id=actor_id, updated_by_user_id=actor_id, **values)
            db.add(item); db.flush(); after = self._content_dict(item)
            self._audit(db, actor_id, "create", "knowledge_content", item.id, None, after)
            return self._content_view(item, point)

    def update_content(self, content_id: str, payload: KnowledgeContentWrite, actor_id: str) -> KnowledgeContentView:
        """中文：使用乐观锁更新知识内容。 English: Updates knowledge content with optimistic locking."""
        with self.session_factory.begin() as db:
            item = db.get(KnowledgePointContent, content_id)
            if item is None: raise CurriculumAdminNotFound("知识内容不存在")
            self._check_version(payload.expected_version, item.version_lock); before = self._content_dict(item)
            values = payload.model_dump(exclude={"expected_version"})
            for key, value in values.items(): setattr(item, key, value)
            item.updated_by_user_id = actor_id; item.version_lock += 1; db.flush()
            self._audit(db, actor_id, "update", "knowledge_content", item.id, before, self._content_dict(item))
            point = db.get(KnowledgePoint, item.knowledge_point_id)
            return self._content_view(item, point)

    def archive_content(self, content_id: str, actor_id: str) -> KnowledgeContentView:
        """中文：归档内容而不物理删除。 English: Archives content without physically deleting it."""
        with self.session_factory.begin() as db:
            item = db.get(KnowledgePointContent, content_id)
            if item is None: raise CurriculumAdminNotFound("知识内容不存在")
            before = self._content_dict(item); item.status = "archived"; item.updated_by_user_id = actor_id; item.version_lock += 1; db.flush()
            self._audit(db, actor_id, "archive", "knowledge_content", item.id, before, self._content_dict(item))
            return self._content_view(item, db.get(KnowledgePoint, item.knowledge_point_id))

    @staticmethod
    def _check_version(expected: int | None, actual: int) -> None:
        """中文：检查客户端版本是否仍为最新。 English: Checks whether the client version is still current."""
        if expected is not None and expected != actual: raise CurriculumAdminConflict(f"版本冲突：期望 {expected}，当前 {actual}")

    @staticmethod
    def _point_by_code(db: Session, code: str | None) -> KnowledgePoint:
        """中文：按编码读取知识点。 English: Loads a knowledge point by code."""
        item = db.scalar(select(KnowledgePoint).where(
            KnowledgePoint.code == code,
            KnowledgePoint.subject == MVP_SUBJECT_CODE,
            KnowledgePoint.grade_band == MVP_GRADE_BAND,
        ))
        if item is None: raise CurriculumAdminNotFound(f"知识点不存在：{code}")
        return item

    @staticmethod
    def _ensure_no_cycle(db: Session, prerequisite_id: int, knowledge_id: int) -> None:
        """中文：确保新增关系不会形成环。 English: Ensures a new relationship cannot create a cycle."""
        edges = list(db.scalars(select(KnowledgePointPrerequisite)))
        adjacency: dict[int, set[int]] = {}
        for edge in edges: adjacency.setdefault(edge.prerequisite_id, set()).add(edge.knowledge_point_id)
        stack = [knowledge_id]; visited: set[int] = set()
        while stack:
            current = stack.pop()
            if current == prerequisite_id: raise CurriculumAdminConflict("该关系会形成循环依赖")
            if current not in visited: visited.add(current); stack.extend(adjacency.get(current, ()))

    @staticmethod
    def _audit(db: Session, actor_id: str, action: str, resource_type: str, resource_id: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
        """中文：追加不可变管理审计。 English: Appends an immutable administration audit record."""
        db.add(KnowledgeAdminAudit(actor_user_id=actor_id, action=action, resource_type=resource_type, resource_id=resource_id, before_json=before, after_json=after))

    @staticmethod
    def _catalog_dict(item: KnowledgeCatalog) -> dict[str, Any]:
        """中文：序列化目录审计快照。 English: Serializes a catalog audit snapshot."""
        return {key: getattr(item, key) for key in ("id", "code", "version", "title", "subject", "grade_band", "topic", "sort_order", "status", "version_lock")}

    def _catalog_view(self, item: KnowledgeCatalog, count: int) -> CatalogView:
        """中文：构造目录响应对象。 English: Builds a catalog response object."""
        return CatalogView(**self._catalog_dict(item), knowledge_point_count=count, updated_at=item.updated_at)

    @staticmethod
    def _point_dict(item: KnowledgePoint, parent_code: str | None) -> dict[str, Any]:
        """中文：序列化知识点审计快照。 English: Serializes a knowledge-point audit snapshot."""
        return {"id": item.id, "catalog_id": item.catalog_id, "subject": item.subject, "grade_band": item.grade_band, "code": item.code, "name": item.name, "description": item.description, "category": item.category, "parent_code": parent_code, "sort_order": item.sort_order, "active": item.active, "version_lock": item.version_lock}

    def _point_view(self, item: KnowledgePoint, parent_code: str | None, counts: dict[tuple[int, str], int]) -> KnowledgePointAdminView:
        """中文：构造知识点管理视图。 English: Builds a knowledge-point administration view."""
        content_counts = {kind: counts.get((item.id, kind), 0) for kind in ("definition", "property", "theorem", "formula", "problem_type")}
        return KnowledgePointAdminView(**self._point_dict(item, parent_code), content_counts=content_counts)

    @staticmethod
    def _content_dict(item: KnowledgePointContent) -> dict[str, Any]:
        """中文：序列化内容审计快照。 English: Serializes a content audit snapshot."""
        return {key: getattr(item, key) for key in ("id", "knowledge_point_id", "content_type", "content_key", "title", "summary", "body_markdown", "formula_latex", "structured_json", "solution_framework_json", "status", "sort_order", "version_lock")}

    def _content_view(self, item: KnowledgePointContent, point: KnowledgePoint) -> KnowledgeContentView:
        """中文：构造知识内容管理视图。 English: Builds a knowledge-content administration view."""
        return KnowledgeContentView(**self._content_dict(item), knowledge_point_code=point.code, knowledge_point_name=point.name, created_at=item.created_at, updated_at=item.updated_at)
