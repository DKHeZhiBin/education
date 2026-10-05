from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.domain.retrieval_evaluation import RetrievalEvaluationRunRecord
from app.evaluation.datasets import DEFAULT_RETRIEVAL_MANIFEST, EvaluationDatasetError
from app.evaluation.retrieval_quality import RetrievalQualityEvaluator


def _load_records(path: Path) -> list[RetrievalEvaluationRunRecord]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvaluationDatasetError(f"Cannot read retrieval run {path}: {exc}") from exc
    records: list[RetrievalEvaluationRunRecord] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(RetrievalEvaluationRunRecord.model_validate_json(line))
        except Exception as exc:
            raise EvaluationDatasetError(
                f"Invalid retrieval run record at line {line_number}: {exc}"
            ) from exc
    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate retrieval, reranking, evidence and citation quality"
    )
    parser.add_argument("--results", required=True, help="Evaluation run JSONL path")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_RETRIEVAL_MANIFEST),
        help="Frozen RAG evaluation manifest",
    )
    parser.add_argument(
        "--production-collection",
        default=settings.qdrant_collection,
        help="Production collection used for isolation validation",
    )
    args = parser.parse_args()
    report = RetrievalQualityEvaluator().evaluate(
        _load_records(Path(args.results)),
        manifest_path=args.manifest,
        production_collection=args.production_collection,
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
