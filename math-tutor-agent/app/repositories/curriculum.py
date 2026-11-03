from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import create_mysql_engine, create_session_factory
from app.core.product_scope import MVP_GRADE_BAND, MVP_SUBJECT_CODE
from app.domain.curriculum import (
    CurriculumCatalogSummary,
    KnowledgePointDetailView,
    KnowledgePointView,
    KnowledgePracticeSource,
    KnowledgePrerequisiteView,
    PublishedKnowledgeContent,
    RelatedKnowledgePoint,
)
from app.models.knowledge_content import KnowledgeCatalog, KnowledgePointContent
from app.models.learning import KnowledgePoint, KnowledgePointPrerequisite


class KnowledgePointNotFound(LookupError):
    """中文：定义“知识·point·not·found”类，封装该职责相关的数据与行为。
    English: Defines the knowledge point not found class and encapsulates data and behavior for that responsibility.
    """
    pass


class KnowledgePracticeSourceNotFound(LookupError):
    """中文：知识点下没有可用于相似题生成的已发布题型。 English: No published problem type can seed similar practice."""

    pass


class CurriculumRepository:
    """中文：定义“课程·仓储”类，封装该职责相关的数据与行为。
    English: Defines the curriculum repository class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())

    def list_catalogs(self, *, subject: str | None = None, grade_band: str | None = None) -> list[CurriculumCatalogSummary]:
        """中文：列出拥有启用根节点的已发布知识目录。 English: Lists published catalogs that have an active root point."""
        with self.session_factory() as db:
            query = (
                select(KnowledgeCatalog, KnowledgePoint.code)
                .join(
                    KnowledgePoint,
                    (KnowledgePoint.catalog_id == KnowledgeCatalog.id)
                    & (KnowledgePoint.code == KnowledgeCatalog.code)
                    & KnowledgePoint.active.is_(True),
                )
                .where(KnowledgeCatalog.status == "published")
                .order_by(KnowledgeCatalog.sort_order, KnowledgeCatalog.code)
            )
            if subject:
                query = query.where(KnowledgeCatalog.subject == subject)
            if grade_band:
                query = query.where(KnowledgeCatalog.grade_band == grade_band)
            rows = db.execute(query).all()
            return [CurriculumCatalogSummary(
                code=catalog.code,
                version=catalog.version,
                title=catalog.title,
                subject=catalog.subject,
                grade_band=catalog.grade_band,
                topic=catalog.topic,
                root_code=root_code,
            ) for catalog, root_code in rows]

    def knowledge_graph(
        self,
        *,
        subject: str,
        grade_band: str,
        root_code: str,
    ) -> tuple[list[KnowledgePointView], list[KnowledgePrerequisiteView]]:
        """中文：处理“知识·graph”相关操作。
        English: Handles the knowledge graph operation.
        """
        with self.session_factory() as db:
            points = list(
                db.scalars(
                    select(KnowledgePoint).where(
                        KnowledgePoint.subject == subject,
                        KnowledgePoint.grade_band == grade_band,
                        KnowledgePoint.active.is_(True),
                    )
                )
            )
            relations = list(db.scalars(select(KnowledgePointPrerequisite)))

        points_by_id = {point.id: point for point in points}
        points_by_code = {point.code: point for point in points}
        root = points_by_code.get(root_code)
        if root is None:
            raise KnowledgePointNotFound(root_code)

        topic_ids = {root.id}
        changed = True
        while changed:
            changed = False
            for point in points:
                if point.parent_id in topic_ids and point.id not in topic_ids:
                    topic_ids.add(point.id)
                    changed = True

        included_ids = set(topic_ids)
        changed = True
        while changed:
            changed = False
            for relation in relations:
                if (
                    relation.knowledge_point_id in included_ids
                    and relation.prerequisite_id in points_by_id
                    and relation.prerequisite_id not in included_ids
                ):
                    included_ids.add(relation.prerequisite_id)
                    changed = True

        selected_points = sorted(
            (points_by_id[point_id] for point_id in included_ids),
            key=lambda point: (point.sort_order, point.code),
        )
        point_views = [
            KnowledgePointView(
                code=point.code,
                name=point.name,
                description=point.description,
                category=point.category,
                parent_code=(
                    points_by_id[point.parent_id].code
                    if point.parent_id in points_by_id
                    else None
                ),
                sort_order=point.sort_order,
                graph_role="topic" if point.id in topic_ids else "prerequisite",
            )
            for point in selected_points
        ]

        relation_views = [
            KnowledgePrerequisiteView(
                knowledge_code=points_by_id[relation.knowledge_point_id].code,
                prerequisite_code=points_by_id[relation.prerequisite_id].code,
                strength=relation.strength,
                required_level=relation.required_level,
                rationale=relation.rationale,
            )
            for relation in relations
            if relation.knowledge_point_id in included_ids
            and relation.prerequisite_id in included_ids
        ]
        relation_views.sort(key=lambda item: (item.knowledge_code, item.prerequisite_code))
        return point_views, relation_views

    def catalog_metadata(self, root_code: str) -> tuple[str, str, str] | None:
        """中文：读取根节点关联的受管目录信息。 English: Reads managed catalog metadata associated with a root node."""
        with self.session_factory() as db:
            row = db.execute(
                select(KnowledgeCatalog.code, KnowledgeCatalog.version, KnowledgeCatalog.title)
                .join(KnowledgePoint, KnowledgePoint.catalog_id == KnowledgeCatalog.id)
                .where(KnowledgePoint.code == root_code)
            ).one_or_none()
            return tuple(row) if row else None

    def knowledge_point_detail(self, code: str) -> KnowledgePointDetailView:
        """中文：返回知识点及其已发布内容。 English: Returns a knowledge point and its published content."""
        with self.session_factory() as db:
            point = db.scalar(select(KnowledgePoint).where(
                KnowledgePoint.code == code,
                KnowledgePoint.active.is_(True),
                KnowledgePoint.subject == MVP_SUBJECT_CODE,
                KnowledgePoint.grade_band == MVP_GRADE_BAND,
            ))
            if point is None:
                raise KnowledgePointNotFound(code)
            catalog = db.get(KnowledgeCatalog, point.catalog_id) if point.catalog_id else None
            parent = db.get(KnowledgePoint, point.parent_id) if point.parent_id else None
            items = list(db.scalars(
                select(KnowledgePointContent)
                .where(KnowledgePointContent.knowledge_point_id == point.id, KnowledgePointContent.status == "published")
                .order_by(KnowledgePointContent.content_type, KnowledgePointContent.sort_order, KnowledgePointContent.content_key)
            ))
            contents = [PublishedKnowledgeContent(
                content_type=item.content_type,
                content_key=item.content_key,
                title=item.title,
                summary=item.summary,
                body_markdown=item.body_markdown,
                formula_latex=item.formula_latex,
                structured_json=item.structured_json,
                solution_framework_json=item.solution_framework_json,
                sort_order=item.sort_order,
            ) for item in items]
            prerequisite_relations = list(db.scalars(
                select(KnowledgePointPrerequisite).where(
                    KnowledgePointPrerequisite.knowledge_point_id == point.id
                )
            ))
            dependent_relations = list(db.scalars(
                select(KnowledgePointPrerequisite).where(
                    KnowledgePointPrerequisite.prerequisite_id == point.id
                )
            ))
            related_ids = {
                relation.prerequisite_id for relation in prerequisite_relations
            } | {
                relation.knowledge_point_id for relation in dependent_relations
            }
            related_points = {
                item.id: item
                for item in db.scalars(
                    select(KnowledgePoint).where(
                        KnowledgePoint.id.in_(related_ids),
                        KnowledgePoint.active.is_(True),
                    )
                )
            } if related_ids else {}
            prerequisites = [RelatedKnowledgePoint(
                code=related_points[relation.prerequisite_id].code,
                name=related_points[relation.prerequisite_id].name,
                strength=relation.strength,
                required_level=relation.required_level,
                rationale=relation.rationale,
            ) for relation in prerequisite_relations if relation.prerequisite_id in related_points]
            dependents = [RelatedKnowledgePoint(
                code=related_points[relation.knowledge_point_id].code,
                name=related_points[relation.knowledge_point_id].name,
                strength=relation.strength,
                required_level=relation.required_level,
                rationale=relation.rationale,
            ) for relation in dependent_relations if relation.knowledge_point_id in related_points]
            root_code = catalog.code if catalog else point.code
            if catalog is None:
                current = point
                while current.parent_id is not None:
                    current = db.get(KnowledgePoint, current.parent_id)
                    if current is None:
                        break
                if current is not None:
                    root_code = current.code
            return KnowledgePointDetailView(
                code=point.code,
                name=point.name,
                description=point.description,
                category=point.category,
                grade_band=point.grade_band,
                parent_code=parent.code if parent else None,
                catalog_code=catalog.code if catalog else None,
                catalog_version=catalog.version if catalog else None,
                catalog_title=catalog.title if catalog else None,
                root_code=root_code,
                contents=contents,
                prerequisites=prerequisites,
                dependents=dependents,
            )

    def knowledge_practice_source(
        self,
        knowledge_point_code: str,
        content_key: str,
    ) -> KnowledgePracticeSource:
        """中文：读取可用于生成相似练习的已发布题型内容。 English: Reads a published problem type that can seed similar practice."""

        with self.session_factory() as db:
            row = db.execute(
                select(KnowledgePoint, KnowledgePointContent)
                .join(
                    KnowledgePointContent,
                    KnowledgePointContent.knowledge_point_id == KnowledgePoint.id,
                )
                .where(
                    KnowledgePoint.code == knowledge_point_code,
                    KnowledgePoint.active.is_(True),
                    KnowledgePoint.subject == MVP_SUBJECT_CODE,
                    KnowledgePoint.grade_band == MVP_GRADE_BAND,
                    KnowledgePointContent.content_key == content_key,
                    KnowledgePointContent.content_type == "problem_type",
                    KnowledgePointContent.status == "published",
                )
            ).one_or_none()
            if row is None:
                raise KnowledgePracticeSourceNotFound(
                    f"{knowledge_point_code}:{content_key}"
                )
            point, content = row
            return KnowledgePracticeSource(
                knowledge_point_code=point.code,
                knowledge_point_name=point.name,
                subject=point.subject,
                grade_band=point.grade_band,
                content_key=content.content_key,
                title=content.title,
                summary=content.summary,
                body_markdown=content.body_markdown,
                formula_latex=content.formula_latex,
                structured_json=content.structured_json,
                solution_framework_json=content.solution_framework_json,
            )
