from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.knowledge import KnowledgeContentType, ProblemDifficultyFactor


SupportedMediaType = Literal["text/plain", "text/markdown", "text/html"]
SupportedDocumentType = Literal[
    "curriculum",
    "textbook",
    "chapter",
    "lesson",
    "theorem",
    "example",
    "problem_set",
    "solution_manual",
    "teaching_note",
]


class ChunkingConfig(BaseModel):
    target_tokens: int = Field(default=420, ge=100, le=1200)
    max_tokens: int = Field(default=560, ge=150, le=1600)
    overlap_tokens: int = Field(default=60, ge=0, le=240)

    @model_validator(mode="after")
    def validate_limits(self) -> ChunkingConfig:
        if self.target_tokens > self.max_tokens:
            raise ValueError("target_tokens cannot exceed max_tokens")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")
        return self


class DocumentIngestionManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    input_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_reference_id: str | None = Field(default=None, min_length=1)
    source_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_external_id: str | None = Field(default=None, min_length=1, max_length=255)
    document_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=500)
    version_label: str = Field(min_length=1, max_length=100)
    document_type: SupportedDocumentType
    media_type: SupportedMediaType | None = None
    language: str = Field(default="zh-CN", min_length=2, max_length=16)
    subject: str = Field(default="math", min_length=1, max_length=32)
    grade_band: str | None = Field(default=None, max_length=32)
    grade_codes: list[str] = Field(default_factory=list)
    curriculum_version_id: str | None = None
    knowledge_point_codes: list[str] = Field(default_factory=list)
    problem_types: list[str] = Field(default_factory=list)
    difficulty_factors: list[ProblemDifficultyFactor] = Field(default_factory=list)
    content_types: list[KnowledgeContentType] = Field(default_factory=list)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)

    @model_validator(mode="after")
    def validate_source_locator(self) -> DocumentIngestionManifest:
        locators = (
            self.source_reference_id,
            self.source_fingerprint,
            self.source_external_id,
        )
        if sum(value is not None for value in locators) != 1:
            raise ValueError(
                "exactly one source_reference_id, source_fingerprint or "
                "source_external_id is required"
            )
        if len(self.knowledge_point_codes) != len(set(self.knowledge_point_codes)):
            raise ValueError("knowledge_point_codes must be unique")
        if len(self.grade_codes) != len(set(self.grade_codes)):
            raise ValueError("grade_codes must be unique")
        if self.grade_codes and self.grade_band is None:
            raise ValueError("grade_codes require grade_band")
        if len(self.problem_types) != len(set(self.problem_types)):
            raise ValueError("problem_types must be unique")
        if len(self.content_types) != len(set(self.content_types)):
            raise ValueError("content_types must be unique")
        factor_codes = {
            code
            for factor in self.difficulty_factors
            for code in factor.related_knowledge_codes
        }
        missing_from_tags = sorted(factor_codes - set(self.knowledge_point_codes))
        if missing_from_tags:
            raise ValueError(
                "difficulty factor knowledge codes must be included in "
                "knowledge_point_codes: " + ", ".join(missing_from_tags)
            )
        return self

    def resolve_input_path(self, manifest_path: str | Path) -> Path:
        candidate = Path(self.input_path)
        if candidate.is_absolute():
            return candidate
        return Path(manifest_path).resolve().parent / candidate


class ParsedBlock(BaseModel):
    text: str = Field(min_length=1)
    heading_path: list[str] = Field(default_factory=list)
    locator: str | None = Field(default=None, max_length=255)
    content_type: KnowledgeContentType = KnowledgeContentType.TEXT


class FormulaRecord(BaseModel):
    original: str
    normalized: str
    block_ordinal: int = Field(ge=0)


class ChunkFormula(BaseModel):
    normalized: str
    originals: list[str] = Field(default_factory=list)


class PreparedChunk(BaseModel):
    ordinal: int = Field(ge=0)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    token_count: int = Field(ge=1)
    heading_path: list[str] = Field(default_factory=list)
    locator: str | None = Field(default=None, max_length=255)
    content_type: KnowledgeContentType = KnowledgeContentType.TEXT
    knowledge_point_codes: list[str] = Field(default_factory=list)
    formulae: list[ChunkFormula] = Field(default_factory=list)


class PreparedDocument(BaseModel):
    manifest: DocumentIngestionManifest
    parser_name: str
    pipeline_version: str
    pipeline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_content: str = Field(min_length=1)
    blocks: list[ParsedBlock] = Field(min_length=1)
    chunks: list[PreparedChunk] = Field(min_length=1)
    formulae: list[FormulaRecord] = Field(default_factory=list)
    duplicate_chunks_removed: int = Field(ge=0)


class IngestionResult(BaseModel):
    outcome: Literal["created", "created_duplicate_content", "duplicate_version"]
    document_id: str
    version_label: str
    content_checksum: str
    chunk_count: int = Field(ge=0)
    duplicate_of_version: str | None = None
