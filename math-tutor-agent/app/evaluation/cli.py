from __future__ import annotations

import argparse
import json

from app.core.config import settings
from app.evaluation.datasets import validate_all_evaluation_suites


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate frozen evaluation data and production-index isolation"
    )
    parser.add_argument(
        "--production-collection",
        default=settings.qdrant_collection,
        help="Production Qdrant collection that evaluation namespaces must not match",
    )
    args = parser.parse_args()
    summaries = validate_all_evaluation_suites(
        production_collection=args.production_collection
    )
    print(
        json.dumps(
            {"status": "valid", "suites": [item.model_dump() for item in summaries]},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
