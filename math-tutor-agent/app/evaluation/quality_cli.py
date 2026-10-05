from __future__ import annotations

import argparse
import json
from datetime import datetime

from app.domain.generation_quality import GenerationQualityScope
from app.services.generation_quality import generation_quality_service


def _datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected an ISO-8601 datetime, for example 2026-10-01T00:00:00Z"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate generation quality metrics from MySQL audit evidence"
    )
    parser.add_argument("--batch-id")
    parser.add_argument("--topic-code")
    parser.add_argument(
        "--batch-purpose",
        default="question_variation",
        help="Generation batch purpose; use an empty string to include every purpose",
    )
    parser.add_argument("--created-from", type=_datetime)
    parser.add_argument("--created-to", type=_datetime)
    args = parser.parse_args()
    report = generation_quality_service.report(GenerationQualityScope(
        batch_id=args.batch_id,
        topic_code=args.topic_code,
        batch_purpose=args.batch_purpose or None,
        created_from=args.created_from,
        created_to=args.created_to,
    ))
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
