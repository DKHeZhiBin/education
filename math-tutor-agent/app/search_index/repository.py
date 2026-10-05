from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import exists, func, or_, select
from sqlalchemy.dialects.mysql import match
from sqlalchemy.orm import Session, selectinload
from pydantic import ValidationError

from app.domain.generation import (
    AdmissionEvidence as DomainAdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)
from app.domain.knowledge import ProblemContentStatus
from app.domain.problem_lifecycle import ProblemContentStateMachine, ProblemTransitionRequest
from app.domain.search_index import (
    KeywordSearchHit,
    KeywordSearchQuery,
    ProductionIndexStatus,
    SearchProjection,
)
from app.models.generation import AdmissionEvidence
from app.models.knowledge import (
    DocumentChunk,
    KnowledgeDocument,
    KnowledgeProblem,
    ProblemStatusTransition,
)
from app.models.search_index import KnowledgeSearchDocument
from app.models.teaching import HintBlueprint, ProblemErrorPattern


class ProductionIndexRepository:
    def __init__(self) -> None:
        self.state_machine = ProblemContentStateMachine()

    @staticmethod
    def active_candidate_identities(
        session: Session,
        identities: list[tuple[str, str]],
    ) -> set[tuple[str, str]]:
        if not identities:
            return set()
        entity_types = {item[0] for item in identities}
        entity_ids = {item[1] for item in identities}
        rows = session.execute(
            select(
                KnowledgeSearchDocument.entity_type,
                KnowledgeSearchDocument.entity_id,
            ).where(
                KnowledgeSearchDocument.entity_type.in_(entity_types),
                KnowledgeSearchDocument.entity_id.in_(entity_ids),
                KnowledgeSearchDocument.index_status == "active",
                KnowledgeSearchDocument.content_status.in_(["approved", "indexed"]),
            )
        ).all()
        requested = set(identities)
        return {(row.entity_type, row.entity_id) for row in rows} & requested

    @staticmethod
    def approved_problem_ids(session: Session, limit: int) -> list[str]:
        return list(session.scalars(
            select(KnowledgeProblem.id)
            .where(KnowledgeProblem.content_status == "approved")
            .order_by(KnowledgeProblem.status_changed_at, KnowledgeProblem.id)
            .limit(limit)
        ))

    @staticmethod
    def approved_document_ids(
        session: Session,
        limit: int,
        *,
        index_version: str,
        embedding_model: str,
    ) -> list[str]:
        active_projection_exists = exists(
            select(KnowledgeSearchDocument.id).where(
                KnowledgeSearchDocument.document_id == KnowledgeDocument.id,
                KnowledgeSearchDocument.problem_id.is_(None),
                KnowledgeSearchDocument.index_status == "active",
                KnowledgeSearchDocument.index_version == index_version,
                KnowledgeSearchDocument.embedding_model == embedding_model,
            )
        )
        return list(session.scalars(
            select(KnowledgeDocument.id)
            .where(
                KnowledgeDocument.review_status == "approved",
                KnowledgeDocument.lifecycle_status == "active",
                ~active_projection_exists,
            )
            .order_by(KnowledgeDocument.updated_at, KnowledgeDocument.id)
            .limit(limit)
        ))

    @staticmethod
    def load_problem(session: Session, problem_id: str) -> KnowledgeProblem:
        problem = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == problem_id)
            .options(
                selectinload(KnowledgeProblem.source_reference),
                selectinload(KnowledgeProblem.document),
                selectinload(KnowledgeProblem.source_chunk),
                selectinload(KnowledgeProblem.curriculum_version),
                selectinload(KnowledgeProblem.solutions),
                selectinload(KnowledgeProblem.admission_evidence)
                .selectinload(AdmissionEvidence.verifier_version),
                selectinload(KnowledgeProblem.error_pattern_links)
                .selectinload(ProblemErrorPattern.error_pattern),
                selectinload(KnowledgeProblem.error_pattern_links)
                .selectinload(ProblemErrorPattern.solution_step),
                selectinload(KnowledgeProblem.hint_blueprints)
                .selectinload(HintBlueprint.solution_step),
                selectinload(KnowledgeProblem.hint_blueprints)
                .selectinload(HintBlueprint.problem_error_pattern)
                .selectinload(ProblemErrorPattern.error_pattern),
            )
            .with_for_update()
        )
        if problem is None or problem.content_status != "approved":
            raise LookupError("approved problem is no longer available")
        return problem

    @staticmethod
    def load_document(session: Session, document_id: str) -> KnowledgeDocument:
        document = session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .options(
                selectinload(KnowledgeDocument.source_reference),
                selectinload(KnowledgeDocument.curriculum_version),
                selectinload(KnowledgeDocument.chunks)
                .selectinload(DocumentChunk.curriculum_version),
            )
            .with_for_update()
        )
        if (
            document is None
            or document.review_status != "approved"
            or document.lifecycle_status != "active"
        ):
            raise LookupError("approved document is no longer available")
        return document

    @staticmethod
    def stage(session: Session, projections: list[SearchProjection]) -> None:
        for projection in projections:
            payload = projection.payload
            row = session.scalar(
                select(KnowledgeSearchDocument).where(
                    KnowledgeSearchDocument.entity_type == payload.entity_type,
                    KnowledgeSearchDocument.entity_id == payload.entity_id,
                ).with_for_update()
            )
            if row is None:
                row = KnowledgeSearchDocument(
                    entity_type=payload.entity_type,
                    entity_id=payload.entity_id,
                    point_id=str(projection.point_id),
                )
                session.add(row)
            row.problem_id = projection.problem_id
            row.document_id = projection.document_id
            row.chunk_id = projection.chunk_id
            row.source_content_hash = payload.source_content_hash
            row.index_version = payload.index_version
            row.embedding_model = payload.embedding_model
            row.content_status = "approved"
            row.index_status = "staging"
            row.vector_status = "pending"
            row.subject = payload.subject
            row.language = payload.language
            row.grade_band = payload.grade_band
            row.curriculum_version_id = payload.curriculum_version_id
            row.generation_batch_id = payload.generation_batch_id
            row.verification_level = payload.verification_level
            row.verification_coverage_json = (
                payload.verification_coverage.model_dump(mode="json")
                if payload.verification_coverage else None
            )
            row.verifier_version_ids_json = payload.verifier_version_ids
            row.verifier_versions_json = [
                item.model_dump(mode="json") for item in payload.verifier_versions
            ]
            row.grade_codes_json = payload.grade_codes
            row.knowledge_point_codes_json = payload.knowledge_point_codes
            row.problem_types_json = payload.problem_types
            row.content_types_json = payload.content_types
            row.difficulty_sources_json = payload.difficulty_sources
            row.search_text = payload.search_text
            row.payload_json = payload.model_dump(mode="json")
            row.attempt_count = (row.attempt_count or 0) + 1
            row.last_error_code = None
        session.flush()

    @staticmethod
    def mark_vector_staged(session: Session, point_ids: list[str]) -> None:
        rows = list(session.scalars(
            select(KnowledgeSearchDocument)
            .where(KnowledgeSearchDocument.point_id.in_(point_ids))
            .with_for_update()
        ))
        for row in rows:
            row.vector_status = "staged"
            row.last_error_code = None

    def activate_problem(
        self,
        session: Session,
        *,
        problem_id: str,
        point_ids: list[str],
        index_version: str,
        embedding_model: str,
    ) -> None:
        problem = session.get(KnowledgeProblem, problem_id, with_for_update=True)
        if problem is None or problem.content_status != "approved":
            raise LookupError("problem changed before index activation")
        self._activate_rows(session, point_ids)
        evidence = self._index_evidence(
            session,
            problem=problem,
            point_ids=point_ids,
            index_version=index_version,
            embedding_model=embedding_model,
        )
        transition = self.state_machine.transition(ProblemTransitionRequest(
            problem_id=problem.id,
            generation_batch_id=problem.generation_batch_id,
            current_status=ProblemContentStatus.APPROVED,
            target_status=ProblemContentStatus.INDEXED,
            revision_attempts=problem.revision_attempts,
            index_is_active=True,
            evidence=[evidence],
        ))
        changed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        next_version = problem.status_version + 1
        session.add(ProblemStatusTransition(
            problem_id=problem.id,
            from_status="approved",
            to_status="indexed",
            reason=None,
            revision_attempts=problem.revision_attempts,
            status_version=next_version,
            checked_requirements_json=[
                "production_index_sync",
                *transition.checked_requirements,
            ],
            actor_type="system",
            actor_id=None,
            created_at=changed_at,
        ))
        problem.content_status = "indexed"
        problem.status_reason = None
        problem.status_version = next_version
        problem.status_changed_at = changed_at

    def activate_document(
        self,
        session: Session,
        *,
        document_id: str,
        point_ids: list[str],
    ) -> None:
        document = session.get(KnowledgeDocument, document_id, with_for_update=True)
        if (
            document is None
            or document.review_status != "approved"
            or document.lifecycle_status != "active"
        ):
            raise LookupError("document changed before index activation")
        self._activate_rows(session, point_ids)
        document.ingestion_status = "indexed"

    @staticmethod
    def mark_failed(
        session: Session,
        *,
        problem_id: str | None = None,
        document_id: str | None = None,
        error_code: str,
    ) -> None:
        conditions = []
        if problem_id:
            conditions.append(KnowledgeSearchDocument.problem_id == problem_id)
        if document_id:
            conditions.extend([
                KnowledgeSearchDocument.document_id == document_id,
                KnowledgeSearchDocument.problem_id.is_(None),
            ])
        if not conditions:
            return
        rows = list(session.scalars(
            select(KnowledgeSearchDocument).where(*conditions).with_for_update()
        ))
        for row in rows:
            row.index_status = "failed"
            row.vector_status = "failed"
            row.last_error_code = error_code[:100]

    @staticmethod
    def keyword_search(
        session: Session,
        query: KeywordSearchQuery,
    ) -> list[KeywordSearchHit]:
        score = match(KnowledgeSearchDocument.search_text, against=query.text).in_natural_language_mode()
        filters = [
            KnowledgeSearchDocument.index_status == "active",
            KnowledgeSearchDocument.content_status.in_(["approved", "indexed"]),
            KnowledgeSearchDocument.subject == query.subject,
            KnowledgeSearchDocument.language == query.language,
            score > 0,
        ]
        if query.grade_band:
            filters.append(KnowledgeSearchDocument.grade_band == query.grade_band)
        if query.entity_types:
            filters.append(KnowledgeSearchDocument.entity_type.in_(query.entity_types))
        if query.curriculum_version_id:
            filters.append(
                KnowledgeSearchDocument.curriculum_version_id
                == query.curriculum_version_id
            )
        if query.curriculum_version:
            filters.append(
                func.json_unquote(func.json_extract(
                    KnowledgeSearchDocument.payload_json,
                    "$.curriculum_version",
                )) == query.curriculum_version
            )
        if query.difficulty is not None:
            filters.append(
                func.json_extract(
                    KnowledgeSearchDocument.payload_json,
                    "$.difficulty",
                ) == query.difficulty
            )
        if query.disclosure_level_lte is not None:
            filters.append(
                func.json_extract(
                    KnowledgeSearchDocument.payload_json,
                    "$.disclosure_level",
                ) <= query.disclosure_level_lte
            )
        if query.hint_level is not None:
            filters.append(
                or_(
                    KnowledgeSearchDocument.entity_type != "hint",
                    func.json_extract(
                        KnowledgeSearchDocument.payload_json,
                        "$.hint_level",
                    ) == query.hint_level,
                )
            )
        filters.extend(
            ProductionIndexRepository._json_contains_all(
                KnowledgeSearchDocument.knowledge_point_codes_json,
                query.knowledge_point_codes,
            )
        )
        if query.grade:
            filters.extend(
                ProductionIndexRepository._json_contains_all(
                    KnowledgeSearchDocument.grade_codes_json,
                    [query.grade],
                )
            )
        for column, values in (
            (KnowledgeSearchDocument.grade_codes_json, query.grade_codes),
            (KnowledgeSearchDocument.problem_types_json, query.problem_types),
            (KnowledgeSearchDocument.content_types_json, query.content_types),
            (
                KnowledgeSearchDocument.difficulty_sources_json,
                query.difficulty_sources,
            ),
        ):
            condition = ProductionIndexRepository._json_contains_any(column, values)
            if condition is not None:
                filters.append(condition)
        rows = session.execute(
            select(KnowledgeSearchDocument, score.label("score"))
            .where(*filters)
            .order_by(score.desc(), KnowledgeSearchDocument.updated_at.desc())
            .limit(query.limit)
        ).all()
        hits: list[KeywordSearchHit] = []
        for row, rank in rows:
            try:
                hits.append(KeywordSearchHit(
                    search_document_id=row.id,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    score=float(rank),
                    payload=row.payload_json,
                ))
            except (ValidationError, TypeError, ValueError):
                continue
        return hits

    @staticmethod
    def _json_contains_all(column, values: list[str]) -> list:
        return [
            func.json_contains(column, json.dumps(value, ensure_ascii=False)) == 1
            for value in values
        ]

    @staticmethod
    def _json_contains_any(column, values: list[str]):
        if not values:
            return None
        return or_(*[
            func.json_contains(column, json.dumps(value, ensure_ascii=False)) == 1
            for value in values
        ])

    @staticmethod
    def status(session: Session) -> ProductionIndexStatus:
        def count(model, *conditions) -> int:
            return int(session.scalar(select(func.count(model.id)).where(*conditions)) or 0)

        return ProductionIndexStatus(
            approved_problems=count(
                KnowledgeProblem, KnowledgeProblem.content_status == "approved"
            ),
            indexed_problems=count(
                KnowledgeProblem, KnowledgeProblem.content_status == "indexed"
            ),
            approved_documents=count(
                KnowledgeDocument,
                KnowledgeDocument.review_status == "approved",
                KnowledgeDocument.lifecycle_status == "active",
                KnowledgeDocument.ingestion_status != "indexed",
            ),
            indexed_documents=count(
                KnowledgeDocument, KnowledgeDocument.ingestion_status == "indexed"
            ),
            staging_documents=count(
                KnowledgeSearchDocument, KnowledgeSearchDocument.index_status == "staging"
            ),
            active_documents=count(
                KnowledgeSearchDocument, KnowledgeSearchDocument.index_status == "active"
            ),
            failed_documents=count(
                KnowledgeSearchDocument, KnowledgeSearchDocument.index_status == "failed"
            ),
            pending_vectors=count(
                KnowledgeSearchDocument,
                KnowledgeSearchDocument.vector_status.in_(["pending", "staged"]),
            ),
            synced_vectors=count(
                KnowledgeSearchDocument, KnowledgeSearchDocument.vector_status == "synced"
            ),
        )

    @staticmethod
    def _activate_rows(session: Session, point_ids: list[str]) -> None:
        rows = list(session.scalars(
            select(KnowledgeSearchDocument)
            .where(KnowledgeSearchDocument.point_id.in_(point_ids))
            .with_for_update()
        ))
        if len(rows) != len(point_ids):
            raise RuntimeError("staged search projection set is incomplete")
        synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
        for row in rows:
            payload = dict(row.payload_json)
            payload["index_status"] = "active"
            payload["content_status"] = "indexed"
            row.payload_json = payload
            row.content_status = "indexed"
            row.index_status = "active"
            row.vector_status = "synced"
            row.last_error_code = None
            row.vector_synced_at = synced_at

    @staticmethod
    def _index_evidence(
        session: Session,
        *,
        problem: KnowledgeProblem,
        point_ids: list[str],
        index_version: str,
        embedding_model: str,
    ) -> DomainAdmissionEvidence:
        if problem.generation_batch_id is None:
            raise RuntimeError("approved problem is missing generation_batch_id")
        payload = {
            "index_version": index_version,
            "embedding_model": embedding_model,
            "point_ids": sorted(point_ids),
            "keyword_index": "knowledge_search_documents.ngram",
            "vector_index": "qdrant",
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        evidence_hash = sha256(serialized.encode("utf-8")).hexdigest()
        entity = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "index_sync",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if entity is None:
            entity = AdmissionEvidence(
                generation_batch_id=problem.generation_batch_id,
                problem_id=problem.id,
                solution_id=None,
                evidence_type="index_sync",
                producer_type="system",
                status="passed",
                is_blocking=False,
                summary="keyword and Qdrant production indexes activated",
                payload_json=payload,
                evidence_hash=evidence_hash,
            )
            session.add(entity)
            session.flush()
        return DomainAdmissionEvidence(
            id=entity.id,
            generation_batch_id=entity.generation_batch_id,
            problem_id=entity.problem_id,
            solution_id=None,
            evidence_type="index_sync",
            producer_type=EvidenceProducerType.SYSTEM,
            status=AdmissionEvidenceStatus.PASSED,
            is_blocking=False,
            summary=entity.summary,
            payload=entity.payload_json,
            evidence_hash=entity.evidence_hash,
            created_at=(
                entity.created_at.replace(tzinfo=timezone.utc)
                if entity.created_at.tzinfo is None else entity.created_at
            ),
        )
