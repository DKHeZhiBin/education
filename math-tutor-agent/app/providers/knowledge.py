from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from app.core.config import Settings, settings
from app.domain.knowledge import KnowledgeQuery, RetrievedTeachingContext


@runtime_checkable
class TextbookKnowledgeRetriever(Protocol):
    """中文：定义“textbook·知识·retriever”类，封装该职责相关的数据与行为。
    English: Defines the textbook knowledge retriever class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Public textbook RAG boundary; it must never read student-owned records.
    """

    @property
    def name(self) -> str:
        """中文：处理“name”相关操作。
        English: Handles the name operation.
        """
        ...

    @property
    def available(self) -> bool:
        """中文：处理“available”相关操作。
        English: Handles the available operation.
        """
        ...

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext:
        """中文：处理“检索”相关操作。
        English: Handles the retrieve operation.
        """
        ...

    def check_readiness(self) -> tuple[bool, str]:
        """中文：处理“检查·就绪状态”相关操作。
        English: Handles the check readiness operation.
        """
        ...

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        ...


class DisabledKnowledgeRetriever:
    """中文：定义“disabled·知识·retriever”类，封装该职责相关的数据与行为。
    English: Defines the disabled knowledge retriever class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    No-op implementation used when RAG is disabled by configuration.
    """

    name = "disabled"
    available = False

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext:
        """中文：处理“检索”相关操作。
        English: Handles the retrieve operation.
        """
        return RetrievedTeachingContext(
            status="disabled",
            provider=self.name,
            query=query,
            limitations=["RAG is disabled by configuration."],
        )

    def check_readiness(self) -> tuple[bool, str]:
        """中文：处理“检查·就绪状态”相关操作。
        English: Handles the check readiness operation.
        """
        return True, "disabled_by_configuration"

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        return None


KnowledgeRetriever = TextbookKnowledgeRetriever


KnowledgeRetrieverFactory = Callable[[Settings], TextbookKnowledgeRetriever]
_PROVIDER_FACTORIES: dict[str, KnowledgeRetrieverFactory] = {}


def register_knowledge_retriever(
    name: str,
    factory: KnowledgeRetrieverFactory,
) -> None:
    """中文：处理“register·知识·retriever”相关操作。
    English: Handles the register knowledge retriever operation.

    原有说明 / Existing notes:
    Register a concrete adapter without changing Harness or Agent code.
    """

    normalized = name.strip().lower()
    if not normalized or normalized == "disabled":
        raise ValueError("Knowledge retriever provider name is invalid")
    _PROVIDER_FACTORIES[normalized] = factory


def build_knowledge_retriever(config: Settings = settings) -> KnowledgeRetriever:
    """中文：处理“构建·知识·retriever”相关操作。
    English: Handles the build knowledge retriever operation.
    """
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
    if not isinstance(retriever, TextbookKnowledgeRetriever):
        raise TypeError(f"RAG provider {provider_name} does not satisfy KnowledgeRetriever")
    if config.rag_cache_enabled and config.redis_enabled:
        from app.cache.knowledge_retrieval import CachedKnowledgeRetriever

        retriever = CachedKnowledgeRetriever(retriever, config)
    return retriever


knowledge_retriever = build_knowledge_retriever()
