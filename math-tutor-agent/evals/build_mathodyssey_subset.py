"""Build the pinned, evaluation-only MathOdyssey high-difficulty subset."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


SOURCE_COMMIT = "fe9e83df06111728e1b06ddaee0a60837c07d6c9"
SOURCE_URL = "https://github.com/protagolabs/odyssey-math"
SOURCE_FILE_URL = (
    "https://raw.githubusercontent.com/protagolabs/odyssey-math/"
    f"{SOURCE_COMMIT}/final-odyssey-math-with-levels.jsonl"
)
SELECTED_IDS = (
    "Problem_2",
    "Problem_29",
    "Problem_32",
    "Problem_34",
    "Problem_45",
    "Problem_46",
    "Problem_51",
    "Problem_94",
    "Problem_101",
    "Problem_107",
    "Problem_108",
    "Problem_125",
    "Problem_126",
    "Problem_135",
    "Problem_136",
    "Problem_137",
)

# These records passed the upstream committee process but were excluded during
# local integrity screening because the published English text is unsuitable
# for a deterministic evaluation run. This screening does not claim a second
# local mathematical review of the selected solutions.
EXCLUDED_AFTER_INTEGRITY_SCREENING = {
    "Problem_44": "The statement switches from coefficient a to undefined alpha.",
    "Problem_47": "The counted integer variable and its domain are not fully specified.",
    "Problem_113": "The statement uses n^2 after fixing a 2023 by 2023 board without defining n.",
    "Problem_129": "The optimization target is ambiguous in the published English wording.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/data/high_difficulty_v1.jsonl"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evals/data/high_difficulty_v1.manifest.json"),
    )
    return parser.parse_args()


def load_source(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            outer = json.loads(line)
            source_id, payload = next(iter(outer.items()))
            records[source_id] = payload
    return records


def build_case(source_id: str, payload: dict) -> dict:
    if payload.get("level") != "high school competition":
        raise ValueError(f"{source_id} is not a high school competition item")
    for field in ("question", "answer", "reasoning", "label"):
        if not payload.get(field):
            raise ValueError(f"{source_id} is missing {field}")
    return {
        "id": f"mathodyssey_{source_id.lower()}",
        "schema_version": "1.0",
        "evaluation_only": True,
        "source": {
            "dataset": "MathOdyssey / GAIC Math 2024",
            "upstream_id": source_id,
            "repository_url": SOURCE_URL,
            "source_file_url": SOURCE_FILE_URL,
            "source_commit": SOURCE_COMMIT,
            "license": "CC BY-SA 4.0 with upstream evaluation-only terms",
            "usage": "evaluation_only",
        },
        "human_review": {
            "status": "source_committee_reviewed",
            "reviewer_group": "GAIC Math 2024 problem setter committee",
            "review_scope": [
                "problem_generation",
                "review",
                "formatting",
                "testing",
                "revision",
            ],
            "evidence_url": SOURCE_URL,
            "local_content_unchanged": True,
            "local_reviewer": None,
        },
        "taxonomy": {
            "level": payload["level"],
            "source_label": payload["label"],
            "difficulty": "high",
            "language": "en",
        },
        "problem": payload["question"],
        "reference_answer": payload["answer"],
        "reference_solution": payload["reasoning"],
        "evaluation_contract": {
            "required_artifacts": [
                "problem_spec",
                "solution_plan",
                "verification_report",
            ],
            "answer_evaluation": "mathematical_equivalence_or_exact_normalized_text",
            "require_condition_coverage": True,
            "require_key_breakthrough": True,
            "require_verification_evidence": True,
            "allow_training": False,
        },
    }


def main() -> None:
    args = parse_args()
    source_records = load_source(args.source)
    missing = [source_id for source_id in SELECTED_IDS if source_id not in source_records]
    if missing:
        raise ValueError(f"Missing selected source ids: {', '.join(missing)}")
    cases = [build_case(source_id, source_records[source_id]) for source_id in SELECTED_IDS]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = "".join(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n"
        for case in cases
    )
    args.output.write_text(serialized, encoding="utf-8")
    labels = Counter(case["taxonomy"]["source_label"] for case in cases)
    manifest = {
        "schema_version": "1.0",
        "name": "high_difficulty_v1",
        "evaluation_only": True,
        "case_count": len(cases),
        "source_commit": SOURCE_COMMIT,
        "source_file_url": SOURCE_FILE_URL,
        "selected_upstream_ids": list(SELECTED_IDS),
        "label_counts": dict(sorted(labels.items())),
        "dataset_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "review_status": "source_committee_reviewed",
        "local_integrity_screening": "completed",
        "excluded_after_integrity_screening": EXCLUDED_AFTER_INTEGRITY_SCREENING,
        "local_translation_status": "not_translated",
    }
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
