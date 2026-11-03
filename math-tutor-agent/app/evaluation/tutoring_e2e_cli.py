from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.logging import configure_cli_logging
from app.evaluation.datasets import DEFAULT_TUTORING_E2E_MANIFEST
from app.evaluation.tutoring_e2e import TutoringE2EEvaluator


def main() -> None:
    """中文：运行教学端到端评估并按门槛返回进程状态。\n    English: Runs tutoring E2E evaluation and returns a gate-aware process status.
    """

    configure_cli_logging()
    parser = argparse.ArgumentParser(description="Run frozen multi-agent tutoring E2E evaluation")
    parser.add_argument("--manifest", default=str(DEFAULT_TUTORING_E2E_MANIFEST))
    parser.add_argument("--model")
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--prompt-version", default="tutoring-prompts-v2")
    parser.add_argument("--code-revision", default="working-tree")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = TutoringE2EEvaluator().run(
        manifest_path=args.manifest,
        model_id=args.model,
        case_ids=set(args.case_ids or []),
        prompt_version=args.prompt_version,
        code_revision=args.code_revision,
    )
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if report.gate_status == "blocked":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
