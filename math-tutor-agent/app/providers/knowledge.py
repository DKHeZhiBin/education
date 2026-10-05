from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from app.core.config import Settings, settings
from app.domain.knowledge import KnowledgeQuery, RetrievedTeachingContext


@runtime_checkable
class KnowledgeRetriever(Protocol):
    """RAG boundary returning validated structure rather than raw document text."""

    @property
    def name(self) -> str: ...

    @property
    def available(self) -> bool: ...

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext: ...

    def check_readiness(self) -> tuple[bool, str]: ...

    def close(self) -> None: ...


class DisabledKnowledgeRetriever:
    """No-op implementation used when RAG is disabled by configuration."""

    name = "disabled"
    available = False

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext:
        return RetrievedTeachingContext(
            status="disabled",
            provider=self.name,
            query=query,
            limitations=["RAG is disabled by configuration."],
        )

    def check_readiness(self) -> tuple[bool, str]:
        return True, "disabled_by_configuration"

    def close(self) -> None:
        return None


KnowledgeRetrieverFactory = Callable[[Settings], KnowledgeRetriever]
_PROVIDER_FACTORIES: dict[str, KnowledgeRetrieverFactory] = {}


def register_knowledge_retriever(
    name: str,
    factory: KnowledgeRetrieverFactory,
) -> None:
    """Register a concrete adapter without changing Harness or Agent code."""

    normalized = name.strip().lower()
    if not normalized or normalized == "disabled":
        raise ValueError("Knowledge retriever provider name is invalid")
    _PROVIDER_FACTORIES[normalized] = factory


def build_knowledge_retriever(config: Settings = settings) -> KnowledgeRetriever:
    if not config.rag_enabled:
        return DisabledKnowledgeRetriever()

    provider_name = config.rag_provider.strip().lower()
    factory = _PROVIDER_FACTORIES.get(provider_name)
    if factory is None and provider_name == "qdrant":
        from app.providers.qdrant_knowledge import build_qdrant_retriever

        factory = build_qdrant_retriever
    if factory is None and provider_name == "hybrid":
        from app.providers.hybrid_knowledge import build_hybrid_retriever

        factory = build_hybrid_retriever
    if factory is None:
        configured = provider_name or "<empty>"
        raise ValueError(
            f"RAG_ENABLED=true but RAG_PROVIDER={configured} is not registered"
        )
    retriever = factory(config)
    if not isinstance(retriever, KnowledgeRetriever):
        raise TypeError(f"RAG provider {provider_name} does not satisfy KnowledgeRetriever")
    if config.rag_cache_enabled and config.redis_enabled:
        from app.cache.knowledge_retrieval import CachedKnowledgeRetriever

        retriever = CachedKnowledgeRetriever(retriever, config)
    return retriever


knowledge_retriever = build_knowledge_retriever()
