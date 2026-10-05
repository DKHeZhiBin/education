from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.cache.knowledge_retrieval import KnowledgeIndexVersion
from app.core.config import Settings, settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.index_lifecycle import (
    IndexMaintenanceJobView,
    IndexMaintenanceRequest,
    IndexMaintenanceRunSummary,
)
from app.search_index.lifecycle_repository import SearchIndexLifecycleRepository
from app.search_index.service import ProductionIndexService
from app.vector_store.qdrant import QdrantVectorStore


class SearchIndexLifecycleService:
    def __init__(
        self,
        config: Settings = settings,
        *,
        session_factory: sessionmaker[Session] | None = None,
        production_service: ProductionIndexService | None = None,
    ) -> None:
        self.config = config
        self.session_factory = session_factory or create_session_factory(
            create_mysql_engine()
        )
        self.production_service = production_service
        self.vector_store = (
            production_service.vector_store if production_service else None
        )
        self.repository = SearchIndexLifecycleRepository()
        self.cache_version = (
            production_service.cache_version
            if production_service is not None
            else KnowledgeIndexVersion(
                config,
                session_factory=self.session_factory,
            )
        )

    def enqueue(
        self,
        request: IndexMaintenanceRequest,
    ) -> IndexMaintenanceJobView:
        with self.session_factory.begin() as session:
            job = self.repository.enqueue(
                session,
                request,
                index_version=self.config.production_index_version,
            )
            generation = self.cache_version.bump(
                session,
                reason=f"index_suppressed:{job.id}",
            )
            view = self.repository.view(job)
        self.cache_version.publish(generation, f"index_suppressed:{job.id}")
        return view

    def get(self, job_id: str) -> IndexMaintenanceJobView | None:
        with self.session_factory() as session:
            job = self.repository.get(session, job_id)
            return self.repository.view(job) if job else None

    def run(self, *, limit: int = 25) -> IndexMaintenanceRunSummary:
        if limit <= 0:
            raise ValueError("maintenance limit must be greater than zero")
        with self.session_factory() as session:
            recovery_before = self._recovery_before()
            job_ids = self.repository.work_ids(
                session,
                limit=limit,
                max_attempts=self.config.production_index_maintenance_max_attempts,
                recovery_before=recovery_before,
            )
        completed = 0
        waiting = 0
        failed: list[str] = []
        for job_id in job_ids:
            try:
                outcome = self._process(job_id)
                if outcome == "completed":
                    completed += 1
                elif outcome == "waiting_for_approval":
                    waiting += 1
            except Exception as error:
                failed.append(job_id)
                with self.session_factory.begin() as session:
                    self.repository.mark_failed(
                        session,
                        job_id,
                        self._error_code(error),
                    )
        return IndexMaintenanceRunSummary(
            selected_count=len(job_ids),
            completed_count=completed,
            waiting_count=waiting,
            failed_job_ids=failed,
        )

    def run_job(self, job_id: str) -> IndexMaintenanceJobView:
        """Process one known outbox job immediately; failures remain retryable."""
        try:
            self._process(job_id)
        except Exception as error:
            with self.session_factory.begin() as session:
                self.repository.mark_failed(
                    session,
                    job_id,
                    self._error_code(error),
                )
        job = self.get(job_id)
        if job is None:
            raise LookupError("index maintenance job not found")
        return job

    def close(self) -> None:
        if self.production_service is not None:
            self.production_service.close()
        elif self.vector_store is not None:
            self.vector_store.close()

    def _process(self, job_id: str) -> str:
        recovery_before = self._recovery_before()
        with self.session_factory.begin() as session:
            claimed, point_ids = self.repository.start_deletion(
                session,
                job_id,
                recovery_before=recovery_before,
            )
        if not claimed:
            return "in_progress"
        if point_ids is not None:
            self._vector_store().delete_points(point_ids)
            with self.session_factory.begin() as session:
                outcome = self.repository.finish_deletion(session, job_id)
                generation = self.cache_version.bump(
                    session,
                    reason=f"index_deleted:{job_id}",
                )
            self.cache_version.publish(generation, f"index_deleted:{job_id}")
            if outcome == "completed":
                return outcome

        with self.session_factory.begin() as session:
            claimed, rebuild_problem_id = self.repository.prepare_rebuild(
                session,
                job_id,
                recovery_before=recovery_before,
            )
        if not claimed:
            return "in_progress"
        if rebuild_problem_id is None:
            with self.session_factory() as session:
                job = self.repository.get(session, job_id)
                return (
                    "completed"
                    if job is not None and job.status == "completed"
                    else "waiting_for_approval"
                )
        self._production_service().sync_problem(rebuild_problem_id)
        with self.session_factory.begin() as session:
            self.repository.finish_rebuild(session, job_id)
        return "completed"

    def _vector_store(self) -> QdrantVectorStore:
        if self.vector_store is None:
            self.vector_store = QdrantVectorStore(
                self.config,
                timeout_seconds=self.config.production_index_timeout_seconds,
            )
        return self.vector_store

    def _production_service(self) -> ProductionIndexService:
        if self.production_service is None:
            self.production_service = ProductionIndexService(
                self.config,
                session_factory=self.session_factory,
                vector_store=self._vector_store(),
            )
        return self.production_service

    def _recovery_before(self) -> datetime:
        return (
            datetime.now(timezone.utc)
            - timedelta(
                seconds=self.config.production_index_maintenance_lease_seconds
            )
        ).replace(tzinfo=None)

    @staticmethod
    def _error_code(error: Exception) -> str:
        if isinstance(error, LookupError):
            return "maintenance_entity_missing"
        return type(error).__name__.lower()[:100]
