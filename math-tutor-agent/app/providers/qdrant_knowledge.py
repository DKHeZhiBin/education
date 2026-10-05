from __future__ import annotations

from time import perf_counter
from pydantic import ValidationError
from qdrant_client import models
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.knowledge import (
    KnowledgeQuery,
    RetrievalDiagnostics,
    RetrievedTeachingContext,
)
from app.domain.search_index import RankedTeachingCandidate
from app.domain.vector_store import QdrantTeachingPayload
from app.providers.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    build_embedding_provider,
)
from app.retrieval.teaching_context import (
    allowed_entity_types,
    build_teaching_context,
)
from app.vector_store.qdrant import QdrantVectorStore
from app.search_index.repository import ProductionIndexRepository


class QdrantKnowledgeRetriever:
    name = "qdrant"
    available = True

    def __init__(
        self,
        config: Settings = settings,
        embedding_provider: EmbeddingProvider | None = None,
        store: QdrantVectorStore | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.config = config
        self.embedding_provider = embedding_provider or build_embedding_provider(config)
        self.store = store or QdrantVectorStore(config)
        self.session_factory = session_factory or create_session_factory(
            create_mysql_engine()
        )
        self.index_repository = ProductionIndexRepository()

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext:
        started = perf_counter()
        try:
            candidates = self.search_candidates(query)
        except EmbeddingProviderError:
            return self._failure(query, started, "embedding_unavailable")
        except Exception:
            return self._failure(query, started, "qdrant_query_failed")
        return build_teaching_context(
            provider=self.name,
            query=query,
            candidates=candidates,
            started=started,
            max_context_chars=self.config.rag_max_context_chars,
        )

    def search_candidates(
        self,
        query: KnowledgeQuery,
        *,
        limit: int | None = None,
    ) -> list[RankedTeachingCandidate]:
        vector = self.embedding_provider.embed_query(query.text)
        points = self.store.client.query_points(
            collection_name=self.config.qdrant_collection,
            query=vector,
            using=self.config.qdrant_vector_name,
            query_filter=self._filter(query),
            score_threshold=self.config.qdrant_score_threshold,
            limit=(
                min(100, query.top_k * self.config.qdrant_oversampling_factor)
                if limit is None else min(100, limit)
            ),
            with_payload=True,
            with_vectors=False,
        ).points
        candidates: list[RankedTeachingCandidate] = []
        for rank, point in enumerate(points, start=1):
            if not isinstance(point.payload, dict):
                continue
            try:
                payload = QdrantTeachingPayload.model_validate(point.payload)
                candidates.append(RankedTeachingCandidate(
                    entity_type=payload.entity_type,
                    entity_id=payload.entity_id,
                    payload=payload,
                    score=max(0.0, min(float(point.score), 1.0)),
                    vector_rank=rank,
                ))
            except (ValidationError, TypeError, ValueError):
                continue
        with self.session_factory() as session:
            active = self.index_repository.active_candidate_identities(
                session,
                [(item.entity_type, item.entity_id) for item in candidates],
            )
        return [
            item
            for item in candidates
            if (item.entity_type, item.entity_id) in active
        ]

    def _filter(self, query: KnowledgeQuery) -> models.Filter:
        entity_types = allowed_entity_types(query)
        filters = query.filters
        must: list[models.Condition] = [
            models.FieldCondition(
                key="index_status", match=models.MatchValue(value="active")
            ),
            models.FieldCondition(
                key="content_status",
                match=models.MatchAny(any=["approved", "indexed"]),
            ),
            models.FieldCondition(
                key="evaluation_only", match=models.MatchValue(value=False)
            ),
            models.FieldCondition(
                key="entity_type", match=models.MatchAny(any=entity_types)
            ),
            models.FieldCondition(
                key="embedding_model",
                match=models.MatchValue(value=self.embedding_provider.model_name),
            ),
            models.FieldCondition(
                key="subject", match=models.MatchValue(value=filters.subject)
            ),
            models.FieldCondition(
                key="language", match=models.MatchValue(value=filters.language)
            ),
        ]
        self._add_value(must, "grade_band", filters.grade_band)
        self._add_value(must, "curriculum_version", filters.curriculum_version)
        self._add_value(must, "curriculum_version_id", filters.curriculum_version_id)
        if filters.grade:
            must.append(models.FieldCondition(
                key="grade_codes", match=models.MatchValue(value=filters.grade)
            ))
        if filters.grade_codes:
            must.append(models.FieldCondition(
                key="grade_codes", match=models.MatchAny(any=filters.grade_codes)
            ))
        for value in filters.knowledge_points:
            must.append(models.FieldCondition(
                key="knowledge_point_codes", match=models.MatchValue(value=value)
            ))
        if filters.problem_types:
            must.append(models.FieldCondition(
                key="problem_types", match=models.MatchAny(any=filters.problem_types)
            ))
        if filters.content_types:
            must.append(models.FieldCondition(
                key="content_types", match=models.MatchAny(any=filters.content_types)
            ))
        if filters.difficulty_sources:
            must.append(models.FieldCondition(
                key="difficulty_sources",
                match=models.MatchAny(any=filters.difficulty_sources),
            ))
        if filters.difficulty and str(filters.difficulty).isdigit():
            must.append(models.FieldCondition(
                key="difficulty",
                match=models.MatchValue(value=int(filters.difficulty)),
            ))
        if query.purpose == "hint_teaching" and query.hint_level is not None:
            must.append(models.FieldCondition(
                key="disclosure_level",
                range=models.Range(lte=query.hint_level),
            ))
        return models.Filter(must=must)

    def check_readiness(self) -> tuple[bool, str]:
        embedding_ok, embedding_detail = self.embedding_provider.check_readiness()
        if not embedding_ok:
            return False, f"embedding_{embedding_detail}"
        qdrant_ok, qdrant_detail = self.store.check_readiness()
        if not qdrant_ok:
            return False, f"qdrant_{qdrant_detail}"
        try:
            with self.session_factory() as session:
                session.execute(select(1)).scalar_one()
        except Exception:
            return False, "mysql_active_projection_check_failed"
        return True, "qdrant_embedding_and_mysql_projection_ready"

    def close(self) -> None:
        self.embedding_provider.close()
        self.store.close()

    def _failure(
        self,
        query: KnowledgeQuery,
        started: float,
        limitation: str,
    ) -> RetrievedTeachingContext:
        return RetrievedTeachingContext(
            status="degraded",
            provider=self.name,
            query=query,
            limitations=[limitation],
            diagnostics=RetrievalDiagnostics(
                latency_ms=round((perf_counter() - started) * 1000)
            ),
            max_context_chars=self.config.rag_max_context_chars,
        )

    @staticmethod
    def _add_value(
        conditions: list[models.Condition],
        key: str,
        value: str | None,
    ) -> None:
        if value:
            conditions.append(models.FieldCondition(
                key=key, match=models.MatchValue(value=value)
            ))


def build_qdrant_retriever(config: Settings = settings) -> QdrantKnowledgeRetriever:
    return QdrantKnowledgeRetriever(config)
