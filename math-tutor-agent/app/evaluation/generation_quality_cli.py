from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.logging import configure_cli_logging
from app.core.config import settings
from app.domain.generation_evaluation import GenerationEvaluationRunRecord
from app.evaluation.datasets import DEFAULT_GENERATION_MANIFEST, EvaluationDatasetError
from app.evaluation.generation_quality import FixedGenerationQualityEvaluator


def load_records(path: Path) -> list[GenerationEvaluationRunRecord]:
    """中文：处理“加载·records”相关操作。
    English: Handles the load records operation.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvaluationDatasetError(
            f"Cannot read generation evaluation run {path}: {exc}"
        ) from exc
    records: list[GenerationEvaluationRunRecord] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(GenerationEvaluationRunRecord.model_validate_json(line))
        except Exception as exc:
            raise EvaluationDatasetError(
                f"Invalid generation run record at line {line_number}: {exc}"
            ) from exc
    if not records:
        raise EvaluationDatasetError("Generation evaluation run is empty")
    return records


def main() -> None:
    """中文：处理“main”相关操作。
    English: Handles the main operation.
    """
    configure_cli_logging()
    parser = argparse.ArgumentParser(
        description="Score one isolated run against the frozen generation evaluation set"
    )
    parser.add_argument("--results", required=True, help="Evaluation run JSONL path")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_GENERATION_MANIFEST),
        help="Frozen generation evaluation manifest",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON report path; the report is always printed to stdout",
    )
    args = parser.parse_args()
    report = FixedGenerationQualityEvaluator().evaluate(
        load_records(Path(args.results)),
        manifest_path=args.manifest,
        production_collection=settings.qdrant_collection,
    )
    serialized = json.dumps(
        report.model_dump(mode="json"), ensure_ascii=False, indent=2
    )
    if args.output:
        Path(args.output).write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
