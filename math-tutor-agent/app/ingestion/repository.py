from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.schemas import IngestionResult, PreparedDocument
from app.models.knowledge import (
    CurriculumVersion,
    DocumentChunk,
    KnowledgeDocument,
    SourceReference,
)
from app.models.learning import KnowledgePoint


class IngestionSourceNotFound(LookupError):
    pass


class DocumentVersionConflict(RuntimeError):
    pass


class DocumentIngestionRepository:
    """Persist one prepared document inside the caller's database transaction."""

    def persist(self, session: Session, prepared: PreparedDocument) -> IngestionResult:
        manifest = prepared.manifest
        source = self._resolve_source(session, prepared)
        self._validate_references(session, prepared)
        version_document = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_reference_id == source.id,
                KnowledgeDocument.document_key == manifest.document_key,
                KnowledgeDocument.version_label == manifest.version_label,
            )
        )
        if version_document is not None:
            if version_document.content_checksum != prepared.content_checksum:
                raise DocumentVersionConflict(
                    f"version {manifest.version_label!r} already points to different content"
                )
            return self._duplicate_result("duplicate_version", version_document)

        duplicate_content = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_reference_id == source.id,
                KnowledgeDocument.document_key == manifest.document_key,
                KnowledgeDocument.content_checksum == prepared.content_checksum,
            )
        )

        previous = session.scalar(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.source_reference_id == source.id,
                KnowledgeDocument.document_key == manifest.document_key,
            )
            .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
            .limit(1)
        )
        document = KnowledgeDocument(
            source_reference_id=source.id,
            curriculum_version_id=manifest.curriculum_version_id,
            document_type=manifest.document_type,
            document_key=manifest.document_key,
            title=manifest.title,
            version_label=manifest.version_label,
            language=manifest.language,
            subject=manifest.subject,
            grade_band=manifest.grade_band,
            grade_codes_json=manifest.grade_codes,
            content_checksum=prepared.content_checksum,
            review_status="unreviewed",
            lifecycle_status="draft",
            ingestion_status="parsed",
            knowledge_point_codes_json=manifest.knowledge_point_codes,
            problem_types_json=manifest.problem_types,
            difficulty_factors_json=[
                item.model_dump(mode="json") for item in manifest.difficulty_factors
            ],
            content_types_json=(
                [item.value for item in manifest.content_types]
                or sorted({item.content_type.value for item in prepared.chunks})
            ),
            metadata_json={
                "pipeline_version": prepared.pipeline_version,
                "pipeline_fingerprint": prepared.pipeline_fingerprint,
                "manifest_fingerprint": prepared.manifest_fingerprint,
                "parser_name": prepared.parser_name,
                "raw_source_sha256": prepared.raw_source_hash,
                "normalized_content_sha256": prepared.content_checksum,
                "formula_normalizer": "latex_conservative_v1",
                "cleaning_profile": "unicode_nfc_text_v1",
                "chunking": manifest.chunking.model_dump(),
                "block_count": len(prepared.blocks),
                "chunk_count": len(prepared.chunks),
                "formula_count": len(prepared.formulae),
                "duplicate_chunks_removed": prepared.duplicate_chunks_removed,
                "duplicate_content_of_document_id": (
                    duplicate_content.id if duplicate_content is not None else None
                ),
                "duplicate_content_of_version": (
                    duplicate_content.version_label
                    if duplicate_content is not None
                    else None
                ),
                "supersedes_document_id": previous.id if previous else None,
                "supersedes_version_label": previous.version_label if previous else None,
            },
        )
        session.add(document)
        session.flush()
        existing_chunks = list(session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.content_hash.in_(
                [chunk.content_hash for chunk in prepared.chunks]
            ))
            .order_by(DocumentChunk.created_at, DocumentChunk.id)
        ))
        duplicate_chunk_ids = {
            chunk.content_hash: chunk.id for chunk in existing_chunks
        }
        for chunk in prepared.chunks:
            session.add(DocumentChunk(
                document_id=document.id,
                curriculum_version_id=manifest.curriculum_version_id,
                ordinal=chunk.ordinal,
                content=chunk.content,
                content_hash=chunk.content_hash,
                token_count=chunk.token_count,
                heading_path_json=chunk.heading_path,
                locator=chunk.locator,
                content_type=chunk.content_type.value,
                grade_band=manifest.grade_band,
                grade_codes_json=manifest.grade_codes,
                knowledge_point_codes_json=(
                    chunk.knowledge_point_codes or manifest.knowledge_point_codes
                ),
                problem_types_json=manifest.problem_types,
                difficulty_factors_json=[
                    item.model_dump(mode="json") for item in manifest.difficulty_factors
                ],
                metadata_json={
                    "formulae": [formula.model_dump() for formula in chunk.formulae],
                    "pipeline_version": prepared.pipeline_version,
                    "duplicate_of_chunk_id": duplicate_chunk_ids.get(chunk.content_hash),
                },
                enabled=True,
            ))
        session.flush()
        return IngestionResult(
            outcome=(
                "created_duplicate_content"
                if duplicate_content is not None
                else "created"
            ),
            document_id=document.id,
            version_label=document.version_label,
            content_checksum=document.content_checksum,
            chunk_count=len(prepared.chunks),
            duplicate_of_version=(
                duplicate_content.version_label
                if duplicate_content is not None
                else None
            ),
        )

    @staticmethod
    def _resolve_source(session: Session, prepared: PreparedDocument) -> SourceReference:
        manifest = prepared.manifest
        if manifest.source_reference_id:
            clause = SourceReference.id == manifest.source_reference_id
        elif manifest.source_fingerprint:
            clause = SourceReference.fingerprint == manifest.source_fingerprint
        else:
            clause = SourceReference.external_id == manifest.source_external_id
        sources = list(session.scalars(select(SourceReference).where(clause).limit(2)))
        if not sources:
            raise IngestionSourceNotFound("manifest source reference does not exist")
        if len(sources) > 1:
            raise IngestionSourceNotFound(
                "manifest source locator is ambiguous; use source_reference_id or fingerprint"
            )
        return sources[0]

    @staticmethod
    def _validate_references(session: Session, prepared: PreparedDocument) -> None:
        manifest = prepared.manifest
        if manifest.curriculum_version_id:
            curriculum = session.get(CurriculumVersion, manifest.curriculum_version_id)
            if curriculum is None:
                raise IngestionSourceNotFound("manifest curriculum version does not exist")
            if curriculum.subject != manifest.subject or (
                manifest.grade_band is not None
                and curriculum.grade_band != manifest.grade_band
            ):
                raise IngestionSourceNotFound(
                    "manifest curriculum version does not match subject and grade band"
                )
        referenced_codes = set(manifest.knowledge_point_codes)
        for factor in manifest.difficulty_factors:
            referenced_codes.update(factor.related_knowledge_codes)
        if referenced_codes:
            known_codes = set(session.scalars(
                select(KnowledgePoint.code).where(
                    KnowledgePoint.code.in_(referenced_codes)
                )
            ))
            missing = sorted(referenced_codes - known_codes)
            if missing:
                raise IngestionSourceNotFound(
                    "manifest references unknown knowledge points: " + ", ".join(missing)
                )

    @staticmethod
    def _duplicate_result(
        outcome: str, document: KnowledgeDocument
    ) -> IngestionResult:
        return IngestionResult(
            outcome=outcome,
            document_id=document.id,
            version_label=document.version_label,
            content_checksum=document.content_checksum,
            chunk_count=len(document.chunks),
        )
