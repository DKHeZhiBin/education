from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from app.ingestion.chunking import chunk_blocks
from app.ingestion.normalization import normalize_blocks
from app.ingestion.parsers import parser_for
from app.ingestion.schemas import DocumentIngestionManifest, PreparedDocument


PIPELINE_VERSION = "document-ingestion-v1"
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_CHUNKS = 10_000
EXTENSION_MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
}


class DocumentIngestionError(ValueError):
    pass


class DocumentIngestionPipeline:
    def prepare(
        self,
        manifest: DocumentIngestionManifest,
        manifest_path: str | Path,
    ) -> PreparedDocument:
        input_path = manifest.resolve_input_path(manifest_path)
        raw = input_path.read_bytes()
        if not raw:
            raise DocumentIngestionError("source document is empty")
        if len(raw) > MAX_SOURCE_BYTES:
            raise DocumentIngestionError("source document exceeds the 20 MiB limit")
        raw_hash = sha256(raw).hexdigest()
        if raw_hash != manifest.source_sha256:
            raise DocumentIngestionError(
                f"source checksum mismatch: expected {manifest.source_sha256}, got {raw_hash}"
            )
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DocumentIngestionError("source document must be UTF-8") from error

        media_type = manifest.media_type or EXTENSION_MEDIA_TYPES.get(input_path.suffix.lower())
        if media_type is None:
            raise DocumentIngestionError(
                "media_type is required for files without a supported extension"
            )
        parser = parser_for(media_type)
        parsed = parser.parse(content)
        normalized = normalize_blocks(parsed)
        if not normalized.blocks:
            raise DocumentIngestionError("document has no usable blocks after cleaning")

        normalized_content = "\n\n".join(
            json.dumps(
                {
                    "heading_path": block.heading_path,
                    "content_type": block.content_type,
                    "text": block.text,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for block in normalized.blocks
        )
        content_checksum = sha256(normalized_content.encode("utf-8")).hexdigest()
        chunks, duplicate_count = chunk_blocks(
            normalized.blocks,
            manifest.chunking,
            manifest.knowledge_point_codes,
            normalized.formulae,
        )
        if not chunks:
            raise DocumentIngestionError("document has no chunks after deduplication")
        if len(chunks) > MAX_CHUNKS:
            raise DocumentIngestionError(
                f"document produces more than the {MAX_CHUNKS} chunk limit"
            )
        manifest_payload = json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return PreparedDocument(
            manifest=manifest,
            parser_name=parser.name,
            pipeline_version=PIPELINE_VERSION,
            pipeline_fingerprint=_pipeline_fingerprint(),
            manifest_fingerprint=sha256(manifest_payload.encode("utf-8")).hexdigest(),
            raw_source_hash=raw_hash,
            content_checksum=content_checksum,
            normalized_content=normalized_content,
            blocks=normalized.blocks,
            chunks=chunks,
            formulae=normalized.formulae,
            duplicate_chunks_removed=duplicate_count,
        )


def load_manifest(path: str | Path) -> DocumentIngestionManifest:
    with Path(path).open(encoding="utf-8") as manifest_file:
        return DocumentIngestionManifest.model_validate(json.load(manifest_file))


def _pipeline_fingerprint() -> str:
    package_dir = Path(__file__).parent
    implementation = b"".join(
        (package_dir / filename).read_bytes()
        for filename in (
            "schemas.py",
            "parsers.py",
            "normalization.py",
            "chunking.py",
            "pipeline.py",
        )
    )
    return sha256(implementation).hexdigest()
