from __future__ import annotations

import argparse
import json

from app.core.config import settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.index_lifecycle import IndexMaintenanceRequest
from app.search_index.lifecycle_service import SearchIndexLifecycleService
from app.search_index.repository import ProductionIndexRepository
from app.search_index.service import ProductionIndexService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage the MySQL keyword and Qdrant production indexes"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    sync_parser = subparsers.add_parser("sync", help="Publish approved content")
    sync_parser.add_argument("--limit", type=int, default=None)
    subparsers.add_parser("status", help="Show production index counts")
    retire_parser = subparsers.add_parser(
        "retire", help="Remove an indexed problem permanently"
    )
    retire_parser.add_argument("problem_id")
    retire_parser.add_argument("--reason", required=True)
    revalidate_parser = subparsers.add_parser(
        "revalidate", help="Remove an index and wait for reapproval"
    )
    revalidate_parser.add_argument("problem_id")
    revalidate_parser.add_argument("--reason", required=True)
    replace_parser = subparsers.add_parser(
        "replace-version", help="Retire an old problem and index its replacement"
    )
    replace_parser.add_argument("problem_id")
    replace_parser.add_argument("replacement_problem_id")
    replace_parser.add_argument("--reason", required=True)
    maintain_parser = subparsers.add_parser(
        "maintain", help="Run queued index removals and rebuilds"
    )
    maintain_parser.add_argument("--limit", type=int, default=25)
    job_parser = subparsers.add_parser(
        "maintenance-status", help="Show one index maintenance job"
    )
    job_parser.add_argument("job_id")
    args = parser.parse_args()

    if args.action == "status":
        factory = create_session_factory(create_mysql_engine())
        with factory() as session:
            result = ProductionIndexRepository.status(session).model_dump(mode="json")
    elif args.action == "sync":
        service = ProductionIndexService(settings)
        try:
            result = service.sync(limit=args.limit).model_dump(mode="json")
        finally:
            service.close()
    else:
        service = SearchIndexLifecycleService(settings)
        try:
            if args.action == "maintain":
                result = service.run(limit=args.limit).model_dump(mode="json")
            elif args.action == "maintenance-status":
                job = service.get(args.job_id)
                if job is None:
                    raise SystemExit("index maintenance job not found")
                result = job.model_dump(mode="json")
            else:
                trigger = {
                    "retire": "retired",
                    "revalidate": "revalidation",
                    "replace-version": "version_update",
                }[args.action]
                request = IndexMaintenanceRequest(
                    problem_id=args.problem_id,
                    replacement_problem_id=getattr(
                        args,
                        "replacement_problem_id",
                        None,
                    ),
                    trigger_type=trigger,
                    reason=args.reason,
                )
                result = service.enqueue(request).model_dump(mode="json")
        finally:
            service.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
