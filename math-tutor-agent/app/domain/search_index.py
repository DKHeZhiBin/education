from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.vector_store import QdrantTeachingPayload


class SearchProjection(BaseModel):
    """中文：定义“搜索·projection”类，封装该职责相关的数据与行为。
    English: Defines the search projection class and encapsulates data and behavior for that responsibility.
    """
    point_id: UUID
    problem_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    payload: QdrantTeachingPayload


class KeywordSearchQuery(BaseModel):
    """中文：定义“keyword·搜索·query”类，封装该职责相关的数据与行为。
    English: Defines the keyword search query class and encapsulates data and behavior for that responsibility.
    """
    text: str = Field(min_length=1, max_length=4000)
    subject: str = "math"
    grade_band: str | None = None
    grade: str | None = Field(default=None, max_length=32)
    grade_codes: list[str] = Field(default_factory=list, max_length=12)
    knowledge_point_codes: list[str] = Field(default_factory=list, max_length=20)
    problem_types: list[str] = Field(default_factory=list, max_length=12)
    content_types: list[str] = Field(default_factory=list, max_length=12)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    difficulty_sources: list[str] = Field(default_factory=list, max_length=12)
    curriculum_version: str | None = Field(default=None, max_length=100)
    curriculum_version_id: str | None = None
    language: str = Field(default="zh-CN", min_length=2, max_length=16)
    disclosure_level_lte: int | None = Field(default=None, ge=1, le=4)
    hint_level: int | None = Field(default=None, ge=1, le=4)
    entity_types: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=10, ge=1, le=50)


class KeywordSearchHit(BaseModel):
    """中文：定义“keyword·搜索·hit”类，封装该职责相关的数据与行为。
    English: Defines the keyword search hit class and encapsulates data and behavior for that responsibility.
    """
    search_document_id: str
    entity_type: str
    entity_id: str
    score: float = Field(ge=0)
    payload: QdrantTeachingPayload


class RankedTeachingCandidate(BaseModel):
    """中文：定义“ranked·教学·候选内容”类，封装该职责相关的数据与行为。
    English: Defines the ranked teaching candidate class and encapsulates data and behavior for that responsibility.
    """
    entity_type: str
    entity_id: str
    payload: QdrantTeachingPayload
    score: float = Field(ge=0, le=1)
    fusion_score: float | None = Field(default=None, ge=0, le=1)
    condition_score: float | None = Field(default=None, ge=0, le=1)
    target_score: float | None = Field(default=None, ge=0, le=1)
    solution_structure_score: float | None = Field(default=None, ge=0, le=1)
    vector_rank: int | None = Field(default=None, ge=1)
    keyword_rank: int | None = Field(default=None, ge=1)


class IndexSyncSummary(BaseModel):
    """中文：定义“索引·同步·summary”类，封装该职责相关的数据与行为。
    English: Defines the index sync summary class and encapsulates data and behavior for that responsibility.
    """
    outcome: Literal["completed", "partial_failed", "no_candidates"]
    approved_problem_count: int = 0
    approved_document_count: int = 0
    indexed_problem_count: int = 0
    indexed_document_count: int = 0
    projection_count: int = 0
    failed_owner_ids: list[str] = Field(default_factory=list)


class ProductionIndexStatus(BaseModel):
    """中文：定义“production·索引·状态”类，封装该职责相关的数据与行为。
    English: Defines the production index status class and encapsulates data and behavior for that responsibility.
    """
    approved_problems: int = 0
    indexed_problems: int = 0
    approved_documents: int = 0
    indexed_documents: int = 0
    staging_documents: int = 0
    active_documents: int = 0
    failed_documents: int = 0
    pending_vectors: int = 0
    synced_vectors: int = 0
