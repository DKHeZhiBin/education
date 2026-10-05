# RAG source registry

`source_registry_v1.json` is the allowlist and denylist for knowledge ingestion.

- Missing sources are blocked until reviewed.
- An allowlisted source still requires a pinned version, license snapshot, file checksum and file-level exclusions before ingestion.
- Curriculum standards marked `metadata_and_taxonomy_only` must not be chunked or embedded.
- Evaluation-only data and authenticated teacher resources must not enter the knowledge index.
- Policy details and attribution rules are documented in `docs/RAG_SOURCES.md`.

This directory contains source decisions and metadata only. It must not contain downloaded textbooks or restricted answer guides.

`evidence/` stores small, manually reviewed license fact records and official evidence URLs. It does not mirror textbook content. Importers hash these records so a database batch can be traced to the rights evidence used at import time.

Approved local snapshots enter the database through `math-tutor-ingest` and a pinned JSON manifest. The deterministic parsing, normalization, chunking, hash, deduplication and version rules are documented in `docs/DOCUMENT_INGESTION.md`.
