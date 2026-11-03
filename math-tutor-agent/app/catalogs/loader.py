from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.curriculum import CurriculumCatalog
from app.models.learning import (
    CapabilityKnowledgeRequirement,
    CapabilityPoint,
    CapabilityPointPrerequisite,
    KnowledgePoint,
    KnowledgePointPrerequisite,
)


DEFAULT_CATALOG_PATH = (
    Path(__file__).parent / "data" / "middle_school_quadratic_equations.v1.json"
)
CATALOG_DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class CatalogImportSummary:
    """中文：定义“catalog·import·summary”类，封装该职责相关的数据与行为。
    English: Defines the catalog import summary class and encapsulates data and behavior for that responsibility.
    """
    catalog_code: str
    version: str
    knowledge_points: int
    capability_points: int
    knowledge_prerequisites: int
    capability_prerequisites: int
    capability_knowledge_requirements: int


def load_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> CurriculumCatalog:
    """中文：处理“加载·catalog”相关操作。
    English: Handles the load catalog operation.
    """
    with Path(path).open(encoding="utf-8") as catalog_file:
        return CurriculumCatalog.model_validate(json.load(catalog_file))


def catalog_paths() -> list[Path]:
    """中文：返回所有内置且版本化的课程目录文件。
    English: Returns all bundled versioned curriculum catalog files.
    """
    paths: list[Path] = []
    for path in sorted(CATALOG_DATA_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as catalog_file:
            payload = json.load(catalog_file)
        # 管理端批量种子与领域目录共用 data 目录，但两者有不同的数据契约。
        # Managed admin seeds share this directory with domain catalogs, but use a different contract.
        if "seed_code" in payload and isinstance(payload.get("catalogs"), list):
            continue
        paths.append(path)
    return paths


def load_catalog_for_graph(
    *,
    subject: str,
    grade_band: str,
    root_code: str,
) -> CurriculumCatalog:
    """中文：根据学科、学段和根节点选择对应目录元数据。
    English: Selects catalog metadata for a subject, grade band, and graph root.
    """
    for path in catalog_paths():
        catalog = load_catalog(path)
        if catalog.subject != subject or catalog.grade_band != grade_band:
            continue
        if any(point.code == root_code for point in catalog.knowledge_points):
            return catalog
    return load_catalog()


def import_catalog(session: Session, catalog: CurriculumCatalog) -> CatalogImportSummary:
    """中文：处理“import·catalog”相关操作。
    English: Handles the import catalog operation.

    原有说明 / Existing notes:
    Idempotently synchronize one versioned curriculum catalog into MySQL.
    """

    knowledge_by_code = {
        item.code: item
        for item in session.scalars(
            select(KnowledgePoint).where(
                KnowledgePoint.code.in_([point.code for point in catalog.knowledge_points])
            )
        )
    }
    for item in catalog.knowledge_points:
        point = knowledge_by_code.get(item.code)
        if point is None:
            point = KnowledgePoint(code=item.code)
            session.add(point)
            knowledge_by_code[item.code] = point
        point.subject = catalog.subject
        point.grade_band = catalog.grade_band
        point.name = item.name
        point.description = item.description
        point.category = item.category
        point.sort_order = item.sort_order
        point.active = True
    session.flush()
    for item in catalog.knowledge_points:
        knowledge_by_code[item.code].parent_id = (
            knowledge_by_code[item.parent_code].id if item.parent_code else None
        )

    capability_by_code = {
        item.code: item
        for item in session.scalars(
            select(CapabilityPoint).where(
                CapabilityPoint.code.in_([point.code for point in catalog.capability_points])
            )
        )
    }
    for item in catalog.capability_points:
        point = capability_by_code.get(item.code)
        if point is None:
            point = CapabilityPoint(code=item.code)
            session.add(point)
            capability_by_code[item.code] = point
        point.subject = catalog.subject
        point.grade_band = catalog.grade_band
        point.name = item.name
        point.description = item.description
        point.category = item.category
        point.sort_order = item.sort_order
        point.active = True
    session.flush()
    for item in catalog.capability_points:
        capability_by_code[item.code].parent_id = (
            capability_by_code[item.parent_code].id if item.parent_code else None
        )

    knowledge_ids = [point.id for point in knowledge_by_code.values()]
    capability_ids = [point.id for point in capability_by_code.values()]
    session.execute(
        delete(KnowledgePointPrerequisite).where(
            KnowledgePointPrerequisite.knowledge_point_id.in_(knowledge_ids)
        )
    )
    session.execute(
        delete(CapabilityPointPrerequisite).where(
            CapabilityPointPrerequisite.capability_point_id.in_(capability_ids)
        )
    )
    session.execute(
        delete(CapabilityKnowledgeRequirement).where(
            CapabilityKnowledgeRequirement.capability_point_id.in_(capability_ids)
        )
    )

    for item in catalog.knowledge_prerequisites:
        session.add(
            KnowledgePointPrerequisite(
                knowledge_point_id=knowledge_by_code[item.knowledge_code].id,
                prerequisite_id=knowledge_by_code[item.prerequisite_code].id,
                strength=item.strength,
                required_level=item.required_level,
                rationale=item.rationale,
            )
        )
    for item in catalog.capability_prerequisites:
        session.add(
            CapabilityPointPrerequisite(
                capability_point_id=capability_by_code[item.capability_code].id,
                prerequisite_id=capability_by_code[item.prerequisite_code].id,
                strength=item.strength,
                rationale=item.rationale,
            )
        )
    for item in catalog.capability_knowledge_requirements:
        session.add(
            CapabilityKnowledgeRequirement(
                capability_point_id=capability_by_code[item.capability_code].id,
                knowledge_point_id=knowledge_by_code[item.knowledge_code].id,
                role=item.role,
                required_level=item.required_level,
            )
        )
    session.flush()

    return CatalogImportSummary(
        catalog_code=catalog.catalog_code,
        version=catalog.version,
        knowledge_points=len(catalog.knowledge_points),
        capability_points=len(catalog.capability_points),
        knowledge_prerequisites=len(catalog.knowledge_prerequisites),
        capability_prerequisites=len(catalog.capability_prerequisites),
        capability_knowledge_requirements=len(catalog.capability_knowledge_requirements),
    )
