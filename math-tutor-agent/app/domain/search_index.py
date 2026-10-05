from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.vector_store import QdrantTeachingPayload


class SearchProjection(BaseModel):
    point_id: UUID
    problem_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    payload: QdrantTeachingPayload


class KeywordSearchQuery(BaseModel):
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
    search_document_id: str
    entity_type: str
    entity_id: str
    score: float = Field(ge=0)
    payload: QdrantTeachingPayload


class RankedTeachingCandidate(BaseModel):
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
    outcome: Literal["completed", "partial_failed", "no_candidates"]
    approved_problem_count: int = 0
    approved_document_count: int = 0
    indexed_problem_count: int = 0
    indexed_document_count: int = 0
    projection_count: int = 0
    failed_owner_ids: list[str] = Field(default_factory=list)


class ProductionIndexStatus(BaseModel):
    approved_problems: int = 0
    indexed_problems: int = 0
    approved_documents: int = 0
    indexed_documents: int = 0
    staging_documents: int = 0
    active_documents: int = 0
    failed_documents: int = 0
    pending_vectors: int = 0
    synced_vectors: int = 0
