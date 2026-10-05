from __future__ import annotations

from hashlib import sha256
import json
import logging
from typing import Protocol

from pydantic import ValidationError
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.cache.keys import RedisKeys
from app.core.config import Settings, settings
from app.core.database import create_mysql_engine, create_session_factory
from app.core.redis import get_redis_client
from app.domain.knowledge import KnowledgeQuery, RetrievedTeachingContext
from app.models.base import utc_now
from app.models.search_index import KnowledgeIndexState


logger = logging.getLogger(__name__)


class RetrieverLike(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def available(self) -> bool: ...

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext: ...

    def check_readiness(self) -> tuple[bool, str]: ...

    def close(self) -> None: ...


class KnowledgeIndexVersion:
    """Durable MySQL generation used to invalidate all retrieval cache keys."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        client: Redis | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.config = config
        self.client = client or get_redis_client()
        self.keys = RedisKeys(config.redis_key_prefix)
        self.session_factory = session_factory or create_session_factory(
            create_mysql_engine()
        )
        self.scope = "rag:" + sha256(
            f"{config.qdrant_collection}:{config.production_index_version}".encode(
                "utf-8"
            )
        ).hexdigest()
        self.key = self.keys.rag_index_generation(
            config.qdrant_collection,
            config.production_index_version,
        )

    def current(self) -> str | None:
        try:
            with self.session_factory.begin() as session:
                state = session.get(KnowledgeIndexState, self.scope)
                if state is None:
                    state = KnowledgeIndexState(
                        scope=self.scope,
                        generation=1,
                        reason="initialized",
                        updated_at=utc_now(),
                    )
                    session.add(state)
                    session.flush()
                generation = state.generation
            version = self._token(generation)
            self._mirror(generation)
            return version
        except Exception:
            logger.warning(
                "Unable to read durable RAG index generation; bypassing cache",
                exc_info=True,
            )
            return None

    def bump(self, session: Session, reason: str) -> int:
        state = session.execute(
            select(KnowledgeIndexState)
            .where(KnowledgeIndexState.scope == self.scope)
            .with_for_update()
        ).scalar_one_or_none()
        if state is None:
            state = KnowledgeIndexState(
                scope=self.scope,
                generation=1,
                reason=reason[:100],
                updated_at=utc_now(),
            )
            session.add(state)
        else:
            state.generation += 1
            state.reason = reason[:100]
            state.updated_at = utc_now()
        session.flush()
        return state.generation

    def publish(self, generation: int, reason: str) -> str:
        self._mirror(generation)
        version = self._token(generation)
        logger.info(
            "RAG retrieval cache generation advanced",
            extra={"knowledge_version": version, "reason": reason},
        )
        return version

    def _mirror(self, generation: int) -> None:
        if not self.config.redis_enabled or not self.config.rag_cache_enabled:
            return
        try:
            self.client.set(self.key, str(generation))
        except RedisError:
            logger.warning(
                "Unable to mirror RAG index generation to Redis",
                exc_info=True,
            )

    def _token(self, generation: int) -> str:
        return f"{self.config.production_index_version}.{generation}"


class CachedKnowledgeRetriever:
    """Fail-open Redis cache around a provider-neutral knowledge retriever."""

    def __init__(
        self,
        delegate: RetrieverLike,
        config: Settings = settings,
        *,
        client: Redis | None = None,
        version: KnowledgeIndexVersion | None = None,
    ) -> None:
        self.delegate = delegate
        self.config = config
        self.client = client or get_redis_client()
        self.version = version or KnowledgeIndexVersion(config, client=self.client)
        self.keys = RedisKeys(config.redis_key_prefix)

    @property
    def name(self) -> str:
        return self.delegate.name

    @property
    def available(self) -> bool:
        return self.delegate.available

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext:
        knowledge_version = self.version.current()
        if knowledge_version is None:
            return self.delegate.retrieve(query)

        key = self.keys.rag_query(
            self.name,
            self.config.rag_cache_schema_version,
            knowledge_version,
            self._query_digest(query),
        )
        cached = self._read(key, query, knowledge_version)
        if cached is not None:
            return cached

        context = self.delegate.retrieve(query)
        context = context.model_copy(update={
            "diagnostics": context.diagnostics.model_copy(update={
                "cache_hit": False,
                "knowledge_version": knowledge_version,
            })
        })
        if context.status in {"success", "no_results"}:
            ttl = (
                self.config.rag_cache_ttl_seconds
                if context.status == "success"
                else self.config.rag_cache_no_results_ttl_seconds
            )
            self._write(key, ttl, context)
        return context

    def check_readiness(self) -> tuple[bool, str]:
        return self.delegate.check_readiness()

    def close(self) -> None:
        self.delegate.close()

    def _read(
        self,
        key: str,
        query: KnowledgeQuery,
        knowledge_version: str,
    ) -> RetrievedTeachingContext | None:
        try:
            payload = self.client.get(key)
        except RedisError:
            logger.warning("Redis RAG cache read failed", exc_info=True)
            return None
        if not payload:
            return None
        try:
            context = RetrievedTeachingContext.model_validate_json(payload)
        except (ValidationError, ValueError, TypeError):
            logger.warning("Ignoring invalid Redis RAG cache payload")
            try:
                self.client.delete(key)
            except RedisError:
                logger.warning("Unable to delete invalid RAG cache payload", exc_info=True)
            return None
        if context.query != query:
            logger.warning("Ignoring Redis RAG cache query mismatch")
            return None
        return context.model_copy(update={
            "diagnostics": context.diagnostics.model_copy(update={
                "cache_hit": True,
                "knowledge_version": knowledge_version,
                "latency_ms": 0,
            })
        })

    def _write(
        self,
        key: str,
        ttl_seconds: int,
        context: RetrievedTeachingContext,
    ) -> None:
        try:
            self.client.setex(key, ttl_seconds, context.model_dump_json())
        except RedisError:
            logger.warning("Redis RAG cache write failed", exc_info=True)

    @staticmethod
    def _query_digest(query: KnowledgeQuery) -> str:
        canonical = json.dumps(
            query.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()
