from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.cache.knowledge_retrieval import KnowledgeIndexVersion
from app.core.config import Settings, settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.search_index import IndexSyncSummary
from app.domain.vector_store import VectorPoint
from app.providers.embeddings import EmbeddingProvider, build_embedding_provider
from app.search_index.projector import ProductionIndexProjector
from app.search_index.repository import ProductionIndexRepository
from app.vector_store.qdrant import QdrantVectorStore


class ProductionIndexService:
    """Idempotently publishes approved MySQL content to keyword and Qdrant indexes."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        session_factory: sessionmaker[Session] | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: QdrantVectorStore | None = None,
        cache_version: KnowledgeIndexVersion | None = None,
    ) -> None:
        if embedding_provider is None:
            if not config.embedding_base_url.strip():
                raise ValueError(
                    "EMBEDDING_BASE_URL is required for production indexing"
                )
            if not config.embedding_model.strip():
                raise ValueError(
                    "EMBEDDING_MODEL is required for production indexing"
                )
        self.config = config
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())
        self.embedding_provider = embedding_provider or build_embedding_provider(config)
        self.vector_store = vector_store or QdrantVectorStore(
            config,
            timeout_seconds=config.production_index_timeout_seconds,
        )
        self.repository = ProductionIndexRepository()
        self.cache_version = cache_version or KnowledgeIndexVersion(
            config,
            session_factory=self.session_factory,
        )
        self.projector = ProductionIndexProjector(
            embedding_model=self.embedding_provider.model_name,
            index_version=config.production_index_version,
        )

    def sync(self, *, limit: int | None = None) -> IndexSyncSummary:
        sync_limit = self.config.production_index_sync_limit if limit is None else limit
        if sync_limit <= 0:
            raise ValueError("index sync limit must be greater than zero")
        self.vector_store.ensure_collection()
        with self.session_factory() as session:
            problem_ids = self.repository.approved_problem_ids(session, sync_limit)
            document_ids = self.repository.approved_document_ids(
                session,
                sync_limit,
                index_version=self.config.production_index_version,
                embedding_model=self.embedding_provider.model_name,
            )

        indexed_problems = 0
        indexed_documents = 0
        projection_count = 0
        failures: list[str] = []
        for problem_id in problem_ids:
            try:
                projection_count += self._sync_owner(
                    owner_id=problem_id,
                    load=self.repository.load_problem,
                    project=self.projector.project_problem,
                    activate=lambda session, point_ids: self.repository.activate_problem(
                        session,
                        problem_id=problem_id,
                        point_ids=point_ids,
                        index_version=self.config.production_index_version,
                        embedding_model=self.embedding_provider.model_name,
                    ),
                )
                indexed_problems += 1
            except Exception as error:
                failures.append(problem_id)
                self._mark_failed(
                    error_code=self._error_code(error), problem_id=problem_id
                )

        for document_id in document_ids:
            try:
                projection_count += self._sync_owner(
                    owner_id=document_id,
                    load=self.repository.load_document,
                    project=self.projector.project_document,
                    activate=lambda session, point_ids: self.repository.activate_document(
                        session, document_id=document_id, point_ids=point_ids
                    ),
                )
                indexed_documents += 1
            except Exception as error:
                failures.append(document_id)
                self._mark_failed(
                    error_code=self._error_code(error), document_id=document_id
                )

        if not problem_ids and not document_ids:
            outcome = "no_candidates"
        elif failures:
            outcome = "partial_failed"
        else:
            outcome = "completed"
        return IndexSyncSummary(
            outcome=outcome,
            approved_problem_count=len(problem_ids),
            approved_document_count=len(document_ids),
            indexed_problem_count=indexed_problems,
            indexed_document_count=indexed_documents,
            projection_count=projection_count,
            failed_owner_ids=failures,
        )

    def sync_problem(self, problem_id: str) -> int:
        """Publish one reapproved problem during an index rebuild job."""
        self.vector_store.ensure_collection()
        return self._sync_owner(
            owner_id=problem_id,
            load=self.repository.load_problem,
            project=self.projector.project_problem,
            activate=lambda session, point_ids: self.repository.activate_problem(
                session,
                problem_id=problem_id,
                point_ids=point_ids,
                index_version=self.config.production_index_version,
                embedding_model=self.embedding_provider.model_name,
            ),
        )

    def close(self) -> None:
        self.embedding_provider.close()
        self.vector_store.close()

    def _sync_owner(
        self,
        *,
        owner_id: str,
        load: Callable,
        project: Callable,
        activate: Callable[[Session, list[str]], None],
    ) -> int:
        with self.session_factory.begin() as session:
            owner = load(session, owner_id)
            projections = project(owner)
            if not projections:
                raise RuntimeError("empty_projection")
            self.repository.stage(session, projections)

        staging_points: list[VectorPoint] = []
        batch_size = self.config.production_embedding_batch_size
        for offset in range(0, len(projections), batch_size):
            projection_batch = projections[offset:offset + batch_size]
            vectors = self.embedding_provider.embed_documents([
                projection.payload.search_text for projection in projection_batch
            ])
            point_batch = [
                VectorPoint(
                    id=projection.point_id,
                    vector=vector,
                    payload=projection.payload,
                )
                for projection, vector in zip(
                    projection_batch, vectors, strict=True
                )
            ]
            self.vector_store.upsert(point_batch)
            staging_points.extend(point_batch)
        point_ids = [str(point.id) for point in staging_points]
        with self.session_factory.begin() as session:
            self.repository.mark_vector_staged(session, point_ids)

        active_points = [
            point.model_copy(update={
                "payload": point.payload.model_copy(update={
                    "index_status": "active",
                    "content_status": "indexed",
                })
            })
            for point in staging_points
        ]
        for offset in range(0, len(active_points), batch_size):
            self.vector_store.upsert(active_points[offset:offset + batch_size])
        with self.session_factory.begin() as session:
            activate(session, point_ids)
            generation = self.cache_version.bump(
                session,
                reason=f"index_activated:{owner_id}",
            )
        self.cache_version.publish(generation, f"index_activated:{owner_id}")
        return len(projections)

    def _mark_failed(self, *, error_code: str, **owner: str) -> None:
        with self.session_factory.begin() as session:
            self.repository.mark_failed(session, error_code=error_code, **owner)

    @staticmethod
    def _error_code(error: Exception) -> str:
        if isinstance(error, LookupError):
            return "owner_no_longer_approved"
        message = str(error).strip()
        if message in {
            "empty_projection",
            "EMBEDDING_BASE_URL is required for production indexing",
            "EMBEDDING_MODEL is required for production indexing",
        }:
            return message.lower().replace(" ", "_")[:100]
        return type(error).__name__.lower()[:100]
