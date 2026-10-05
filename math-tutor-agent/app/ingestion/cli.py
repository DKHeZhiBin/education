from __future__ import annotations

import argparse
import json

from app.core.database import create_mysql_engine, create_session_factory
from app.ingestion.pipeline import DocumentIngestionPipeline, load_manifest
from app.ingestion.repository import DocumentIngestionRepository


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare or import a versioned RAG knowledge document"
    )
    parser.add_argument("--manifest", required=True, help="Ingestion manifest JSON path")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Parse, normalize, chunk and hash without connecting to MySQL",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    prepared = DocumentIngestionPipeline().prepare(manifest, args.manifest)
    if args.validate_only:
        result = {
            "pipeline_version": prepared.pipeline_version,
            "pipeline_fingerprint": prepared.pipeline_fingerprint,
            "manifest_fingerprint": prepared.manifest_fingerprint,
            "parser_name": prepared.parser_name,
            "raw_source_hash": prepared.raw_source_hash,
            "content_checksum": prepared.content_checksum,
            "block_count": len(prepared.blocks),
            "chunk_count": len(prepared.chunks),
            "formula_count": len(prepared.formulae),
            "duplicate_chunks_removed": prepared.duplicate_chunks_removed,
        }
    else:
        session_factory = create_session_factory(create_mysql_engine())
        with session_factory.begin() as session:
            result = DocumentIngestionRepository().persist(session, prepared).model_dump()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
