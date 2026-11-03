from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.managed_curriculum_seed import ManagedCurriculumSeed
from app.models.identity import User
from app.models.knowledge_content import KnowledgeAdminAudit, KnowledgeCatalog
from app.models.learning import KnowledgePoint, KnowledgePointPrerequisite


@dataclass(frozen=True)
class ManagedSeedImportSummary:
    """中文：后台目录种子导入结果。 English: Result of importing a managed curriculum seed."""

    seed_code: str
    version: str
    catalogs: int
    knowledge_points: int
    prerequisites: int


def load_managed_seed(path: str | Path) -> ManagedCurriculumSeed:
    """中文：读取并校验版本化目录种子。 English: Loads and validates a versioned catalog seed."""
    with Path(path).open(encoding="utf-8") as source:
        return ManagedCurriculumSeed.model_validate(json.load(source))


def import_managed_seed(session: Session, seed: ManagedCurriculumSeed, actor_email: str) -> ManagedSeedImportSummary:
    """中文：幂等导入目录、知识点和跨目录先修关系。 English: Idempotently imports catalogs, points, and cross-catalog prerequisites."""
    actor = session.scalar(select(User).where(User.email == actor_email, User.role == "admin"))
    if actor is None:
        raise LookupError(f"administrator not found: {actor_email}")

    catalog_by_code: dict[str, KnowledgeCatalog] = {}
    for item in seed.catalogs:
        catalog = session.scalar(select(KnowledgeCatalog).where(KnowledgeCatalog.code == item.code, KnowledgeCatalog.version == seed.version))
        if catalog is None:
            catalog = KnowledgeCatalog(code=item.code, version=seed.version)
            session.add(catalog)
        catalog.title = item.title
        catalog.subject = seed.subject
        catalog.grade_band = seed.grade_band
        catalog.topic = item.topic
        catalog.sort_order = item.sort_order
        catalog.status = item.status
        catalog_by_code[item.code] = catalog
    session.flush()

    seed_points = [(catalog, point) for catalog in seed.catalogs for point in catalog.points]
    codes = [point.code for _, point in seed_points]
    point_by_code = {point.code: point for point in session.scalars(select(KnowledgePoint).where(KnowledgePoint.code.in_(codes)))}
    for catalog_item, item in seed_points:
        point = point_by_code.get(item.code)
        if point is None:
            point = KnowledgePoint(code=item.code)
            session.add(point)
            point_by_code[item.code] = point
        point.catalog_id = catalog_by_code[catalog_item.code].id
        point.subject = seed.subject
        point.grade_band = seed.grade_band
        point.name = item.name
        point.description = item.description
        point.category = item.category
        point.sort_order = item.sort_order
        point.active = True
    session.flush()

    for _, item in seed_points:
        point_by_code[item.code].parent_id = point_by_code[item.parent_code].id if item.parent_code else None

    imported_ids = [point_by_code[code].id for code in codes]
    session.execute(delete(KnowledgePointPrerequisite).where(KnowledgePointPrerequisite.knowledge_point_id.in_(imported_ids)))
    for relation in seed.prerequisites:
        session.add(KnowledgePointPrerequisite(
            knowledge_point_id=point_by_code[relation.knowledge_code].id,
            prerequisite_id=point_by_code[relation.prerequisite_code].id,
            strength=relation.strength,
            required_level=relation.required_level,
            rationale=relation.rationale,
        ))

    session.add(KnowledgeAdminAudit(
        actor_user_id=actor.id,
        action="seed_import",
        resource_type="curriculum_seed",
        resource_id=f"{seed.seed_code}:{seed.version}",
        before_json=None,
        after_json={"catalogs": len(seed.catalogs), "knowledge_points": len(seed_points), "prerequisites": len(seed.prerequisites)},
    ))
    session.flush()
    return ManagedSeedImportSummary(seed.seed_code, seed.version, len(seed.catalogs), len(seed_points), len(seed.prerequisites))
