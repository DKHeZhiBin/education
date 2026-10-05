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
        raise argparse.ArgumentTypeError("expected an ISO-8601 datetime") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Block production release when erroneous automatic admission is unsafe"
    )
    parser.add_argument("--batch-id")
    parser.add_argument("--topic-code", default="MS.QE")
    parser.add_argument("--batch-purpose", default="question_variation")
    parser.add_argument("--created-from", type=_datetime)
    parser.add_argument("--created-to", type=_datetime)
    args = parser.parse_args()
    result = generation_quality_service.release_gate(GenerationQualityScope(
        batch_id=args.batch_id,
        topic_code=args.topic_code,
        batch_purpose=args.batch_purpose or None,
        created_from=args.created_from,
        created_to=args.created_to,
    ))
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if result.status == "blocked":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
