from __future__ import annotations

from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.knowledge import KnowledgeQuery, RetrievedTeachingContext
from app.domain.search_index import (
    KeywordSearchQuery,
    RankedTeachingCandidate,
)
from app.providers.embeddings import EmbeddingProviderError
from app.providers.qdrant_knowledge import QdrantKnowledgeRetriever
from app.retrieval.teaching_context import (
    allowed_entity_types,
    build_teaching_context,
)
from app.retrieval.structural_reranker import StructuralCandidateReranker
from app.search_index.repository import ProductionIndexRepository


class HybridKnowledgeRetriever:
    """Fuse Qdrant and MySQL FULLTEXT ranks through weighted RRF."""

    name = "hybrid"
    available = True

    def __init__(
        self,
        config: Settings = settings,
        *,
        vector_retriever: QdrantKnowledgeRetriever | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.config = config
        self.vector_retriever = vector_retriever or QdrantKnowledgeRetriever(config)
        self.session_factory = session_factory or create_session_factory(
            create_mysql_engine()
        )
        self.repository = ProductionIndexRepository()
        self.reranker = StructuralCandidateReranker(config)

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext:
        started = perf_counter()
        candidate_limit = min(
            100,
            query.top_k * self.config.qdrant_oversampling_factor,
        )
        limitations: list[str] = []
        try:
            vector_candidates = self.vector_retriever.search_candidates(
                query,
                limit=candidate_limit,
            )
        except EmbeddingProviderError:
            vector_candidates = []
            limitations.append("embedding_unavailable")
        except Exception:
            vector_candidates = []
            limitations.append("qdrant_query_failed")

        try:
            with self.session_factory() as session:
                keyword_hits = self.repository.keyword_search(
                    session,
                    self._keyword_query(query, candidate_limit),
                )
        except Exception:
            keyword_hits = []
            limitations.append("mysql_keyword_query_failed")

        keyword_candidates = [
            RankedTeachingCandidate(
                entity_type=hit.entity_type,
                entity_id=hit.entity_id,
                payload=hit.payload,
                score=0,
                keyword_rank=rank,
            )
            for rank, hit in enumerate(keyword_hits, start=1)
        ]
        fused = self._fuse(vector_candidates, keyword_candidates)
        reranked = self.reranker.rerank(query, fused)
        return build_teaching_context(
            provider=self.name,
            query=query,
            candidates=reranked,
            started=started,
            max_context_chars=self.config.rag_max_context_chars,
            candidate_count=len(vector_candidates) + len(keyword_candidates),
            limitations=limitations,
        )

    def check_readiness(self) -> tuple[bool, str]:
        vector_ok, vector_detail = self.vector_retriever.check_readiness()
        if not vector_ok:
            return False, f"vector_{vector_detail}"
        try:
            with self.session_factory() as session:
                session.execute(select(1)).scalar_one()
        except Exception:
            return False, "mysql_connection_failed"
        return True, "mysql_keyword_qdrant_and_embedding_ready"

    def close(self) -> None:
        self.vector_retriever.close()

    def _fuse(
        self,
        vector_candidates: list[RankedTeachingCandidate],
        keyword_candidates: list[RankedTeachingCandidate],
    ) -> list[RankedTeachingCandidate]:
        entries: dict[tuple[str, str], dict] = {}
        for candidate in vector_candidates:
            identity = (candidate.entity_type, candidate.entity_id)
            entries[identity] = {
                "payload": candidate.payload,
                "vector_rank": candidate.vector_rank,
                "keyword_rank": None,
            }
        for candidate in keyword_candidates:
            identity = (candidate.entity_type, candidate.entity_id)
            entry = entries.setdefault(identity, {
                "payload": candidate.payload,
                "vector_rank": None,
                "keyword_rank": None,
            })
            entry["keyword_rank"] = candidate.keyword_rank

        rrf_k = self.config.rag_hybrid_rrf_k
        vector_weight = self.config.rag_hybrid_vector_weight
        keyword_weight = self.config.rag_hybrid_keyword_weight
        maximum = (vector_weight + keyword_weight) / (rrf_k + 1)
        fused: list[RankedTeachingCandidate] = []
        for (entity_type, entity_id), entry in entries.items():
            raw_score = 0.0
            if entry["vector_rank"] is not None:
                raw_score += vector_weight / (rrf_k + entry["vector_rank"])
            if entry["keyword_rank"] is not None:
                raw_score += keyword_weight / (rrf_k + entry["keyword_rank"])
            fused.append(RankedTeachingCandidate(
                entity_type=entity_type,
                entity_id=entity_id,
                payload=entry["payload"],
                score=min(raw_score / maximum, 1.0),
                vector_rank=entry["vector_rank"],
                keyword_rank=entry["keyword_rank"],
            ))
        return sorted(
            fused,
            key=lambda item: (
                -item.score,
                item.vector_rank or 10_000,
                item.keyword_rank or 10_000,
                item.entity_type,
                item.entity_id,
            ),
        )

    @staticmethod
    def _keyword_query(
        query: KnowledgeQuery,
        limit: int,
    ) -> KeywordSearchQuery:
        filters = query.filters
        return KeywordSearchQuery(
            text=query.text,
            subject=filters.subject,
            grade_band=filters.grade_band,
            grade=filters.grade,
            grade_codes=filters.grade_codes,
            knowledge_point_codes=filters.knowledge_points,
            problem_types=filters.problem_types,
            content_types=filters.content_types,
            difficulty=(
                int(filters.difficulty)
                if filters.difficulty and str(filters.difficulty).isdigit()
                else None
            ),
            difficulty_sources=filters.difficulty_sources,
            curriculum_version=filters.curriculum_version,
            curriculum_version_id=filters.curriculum_version_id,
            language=filters.language,
            disclosure_level_lte=(
                query.hint_level if query.purpose == "hint_teaching" else None
            ),
            hint_level=(
                query.hint_level if query.purpose == "hint_teaching" else None
            ),
            entity_types=allowed_entity_types(query),
            limit=limit,
        )


def build_hybrid_retriever(
    config: Settings = settings,
) -> HybridKnowledgeRetriever:
    return HybridKnowledgeRetriever(config)
