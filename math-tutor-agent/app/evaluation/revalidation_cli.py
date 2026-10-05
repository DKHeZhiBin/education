from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.domain.periodic_revalidation import RevalidationPolicyInput, RevalidationScope
from app.services.periodic_revalidation import periodic_revalidation_service


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schedule and run approved-content AI cross review and tool revalidation"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    configure = subparsers.add_parser("configure", help="Create or update one policy")
    configure.add_argument("--file", required=True, help="Policy JSON path")
    due = subparsers.add_parser("run-due", help="Run every policy currently due")
    due.add_argument("--policy-key")
    due.add_argument("--force", action="store_true")
    process = subparsers.add_parser("process", help="Resume one existing run")
    process.add_argument("run_id")
    status = subparsers.add_parser("status", help="Show one run and its items")
    status.add_argument("run_id")
    args = parser.parse_args()

    try:
        if args.action == "configure":
            payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
            result = periodic_revalidation_service.configure(
                RevalidationPolicyInput.model_validate(payload)
            ).model_dump(mode="json")
        elif args.action == "run-due":
            result = periodic_revalidation_service.run_due(RevalidationScope(
                policy_key=args.policy_key,
                force=args.force,
            )).model_dump(mode="json")
        elif args.action == "process":
            result = periodic_revalidation_service.process_run(
                args.run_id
            ).model_dump(mode="json")
        else:
            item = periodic_revalidation_service.get_run(args.run_id)
            if item is None:
                raise SystemExit("revalidation run not found")
            result = item.model_dump(mode="json")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        periodic_revalidation_service.close()


if __name__ == "__main__":
    main()
