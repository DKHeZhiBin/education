from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, Field

from app.core.config import settings
from app.domain.evaluation import (
    GenerationEvaluationCase,
    RetrievalEvaluationDocument,
    RetrievalEvaluationQuery,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = PROJECT_ROOT / "evals/data"
DEFAULT_GENERATION_MANIFEST = DATA_DIRECTORY / "question_generation_quadratic_v1.manifest.json"
DEFAULT_RETRIEVAL_MANIFEST = DATA_DIRECTORY / "rag_retrieval_quadratic_v1.manifest.json"


class EvaluationDatasetError(ValueError):
    """Raised when a frozen evaluation artifact violates its manifest or isolation contract."""


class GenerationEvaluationManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    name: str
    evaluation_only: Literal[True]
    immutable: Literal[True]
    production_index_forbidden: Literal[True]
    topic_code: Literal["MS.QE"]
    scope: str
    source: Literal["project-authored"]
    split: Literal["generation_holdout"]
    dataset_file: str
    case_count: int = Field(gt=0)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_ids: list[str] = Field(min_length=1)
    freeze_policy: str


class RetrievalEvaluationManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    name: str
    evaluation_only: Literal[True]
    immutable: Literal[True]
    production_index_forbidden: Literal[True]
    topic_code: Literal["MS.QE"]
    scope: str
    source: Literal["project-authored"]
    index_namespace: str = Field(min_length=1, max_length=100)
    corpus_file: str
    query_file: str
    document_count: int = Field(gt=0)
    query_count: int = Field(gt=0)
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_ids: list[str] = Field(min_length=1)
    query_ids: list[str] = Field(min_length=1)
    freeze_policy: str


class EvaluationDatasetSummary(BaseModel):
    name: str
    dataset_type: Literal["question_generation", "rag_retrieval"]
    evaluation_only: Literal[True] = True
    immutable: Literal[True] = True
    artifact_counts: dict[str, int]
    verified_sha256: dict[str, str]
    index_namespace: str | None = None
    production_collection: str
    production_isolated: Literal[True] = True


ModelT = TypeVar("ModelT", bound=BaseModel)


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationDatasetError(f"Cannot read evaluation manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationDatasetError(f"Evaluation manifest must be an object: {path}")
    return value


def _artifact_path(manifest_path: Path, filename: str) -> Path:
    if Path(filename).name != filename:
        raise EvaluationDatasetError("Evaluation artifact filename must not contain a path")
    path = (manifest_path.parent / filename).resolve()
    if path.parent != manifest_path.parent.resolve():
        raise EvaluationDatasetError("Evaluation artifact escaped the manifest directory")
    return path


def _sha256(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EvaluationDatasetError(f"Cannot read evaluation artifact {path}: {exc}") from exc


def _load_jsonl(path: Path, model_type: type[ModelT]) -> list[ModelT]:
    records: list[ModelT] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvaluationDatasetError(f"Cannot read evaluation artifact {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(model_type.model_validate_json(line))
        except Exception as exc:
            raise EvaluationDatasetError(
                f"Invalid record in {path.name} at line {line_number}: {exc}"
            ) from exc
    if not records:
        raise EvaluationDatasetError(f"Evaluation artifact is empty: {path}")
    return records


def _verify_ids(actual: list[str], expected: list[str], label: str) -> None:
    if len(actual) != len(set(actual)):
        raise EvaluationDatasetError(f"Duplicate {label} IDs are not allowed")
    if actual != expected:
        raise EvaluationDatasetError(
            f"Frozen {label} ID order does not match its manifest"
        )


def load_generation_evaluation_suite(
    manifest_path: str | Path = DEFAULT_GENERATION_MANIFEST,
    *,
    production_collection: str = settings.qdrant_collection,
) -> tuple[GenerationEvaluationManifest, list[GenerationEvaluationCase], EvaluationDatasetSummary]:
    path = Path(manifest_path).resolve()
    manifest = GenerationEvaluationManifest.model_validate(_load_json(path))
    dataset_path = _artifact_path(path, manifest.dataset_file)
    actual_hash = _sha256(dataset_path)
    if actual_hash != manifest.dataset_sha256:
        raise EvaluationDatasetError("Generation evaluation dataset SHA-256 mismatch")
    cases = _load_jsonl(dataset_path, GenerationEvaluationCase)
    if len(cases) != manifest.case_count:
        raise EvaluationDatasetError("Generation evaluation case count mismatch")
    _verify_ids([case.id for case in cases], manifest.case_ids, "generation case")
    if any(case.input.topic_code != manifest.topic_code for case in cases):
        raise EvaluationDatasetError("Generation case topic escaped the manifest scope")
    return manifest, cases, EvaluationDatasetSummary(
        name=manifest.name,
        dataset_type="question_generation",
        artifact_counts={"cases": len(cases)},
        verified_sha256={"dataset": actual_hash},
        production_collection=production_collection,
    )


def load_retrieval_evaluation_suite(
    manifest_path: str | Path = DEFAULT_RETRIEVAL_MANIFEST,
    *,
    production_collection: str = settings.qdrant_collection,
) -> tuple[
    RetrievalEvaluationManifest,
    list[RetrievalEvaluationDocument],
    list[RetrievalEvaluationQuery],
    EvaluationDatasetSummary,
]:
    path = Path(manifest_path).resolve()
    manifest = RetrievalEvaluationManifest.model_validate(_load_json(path))
    if manifest.index_namespace == production_collection:
        raise EvaluationDatasetError(
            "RAG evaluation namespace must differ from the production Qdrant collection"
        )
    corpus_path = _artifact_path(path, manifest.corpus_file)
    query_path = _artifact_path(path, manifest.query_file)
    corpus_hash = _sha256(corpus_path)
    query_hash = _sha256(query_path)
    if corpus_hash != manifest.corpus_sha256:
        raise EvaluationDatasetError("RAG evaluation corpus SHA-256 mismatch")
    if query_hash != manifest.query_sha256:
        raise EvaluationDatasetError("RAG evaluation query SHA-256 mismatch")

    documents = _load_jsonl(corpus_path, RetrievalEvaluationDocument)
    queries = _load_jsonl(query_path, RetrievalEvaluationQuery)
    if len(documents) != manifest.document_count:
        raise EvaluationDatasetError("RAG evaluation document count mismatch")
    if len(queries) != manifest.query_count:
        raise EvaluationDatasetError("RAG evaluation query count mismatch")
    _verify_ids([document.id for document in documents], manifest.document_ids, "document")
    _verify_ids([query.id for query in queries], manifest.query_ids, "query")

    document_ids = {document.id for document in documents}
    for document in documents:
        if document.index_namespace != manifest.index_namespace:
            raise EvaluationDatasetError(f"Document {document.id} uses the wrong namespace")
    for query in queries:
        if query.index_namespace != manifest.index_namespace:
            raise EvaluationDatasetError(f"Query {query.id} uses the wrong namespace")
        relevant = set(query.relevant_document_ids)
        required = set(query.required_document_ids)
        forbidden = set(query.forbidden_document_ids)
        referenced = relevant | required | forbidden
        missing = referenced - document_ids
        if missing:
            raise EvaluationDatasetError(
                f"Query {query.id} references unknown documents: {sorted(missing)}"
            )
        if not required <= relevant:
            raise EvaluationDatasetError(
                f"Query {query.id} required documents must also be relevant"
            )
        if relevant & forbidden:
            raise EvaluationDatasetError(
                f"Query {query.id} marks a document as both relevant and forbidden"
            )
        if query.hint_level is not None and query.purpose != "hint_teaching":
            raise EvaluationDatasetError(
                f"Query {query.id} has a hint level outside hint teaching"
            )

    return manifest, documents, queries, EvaluationDatasetSummary(
        name=manifest.name,
        dataset_type="rag_retrieval",
        artifact_counts={"documents": len(documents), "queries": len(queries)},
        verified_sha256={"corpus": corpus_hash, "queries": query_hash},
        index_namespace=manifest.index_namespace,
        production_collection=production_collection,
    )


def validate_all_evaluation_suites(
    *, production_collection: str = settings.qdrant_collection
) -> list[EvaluationDatasetSummary]:
    _, _, generation_summary = load_generation_evaluation_suite(
        production_collection=production_collection
    )
    _, _, _, retrieval_summary = load_retrieval_evaluation_suite(
        production_collection=production_collection
    )
    return [generation_summary, retrieval_summary]
