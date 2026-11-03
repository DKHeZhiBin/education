from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.catalogs.managed_seed import import_managed_seed, load_managed_seed
from app.core.database import create_mysql_engine, create_session_factory
from app.core.logging import configure_cli_logging


DEFAULT_SEED = Path(__file__).parent / "catalogs" / "data" / "university_calculus_managed.v1.json"


def main() -> None:
    """中文：导入后台可维护的版本化知识目录。 English: Imports versioned administrator-maintained knowledge catalogs."""
    configure_cli_logging()
    parser = argparse.ArgumentParser(description="Import administrator-managed curriculum catalogs")
    parser.add_argument("--file", default=str(DEFAULT_SEED))
    parser.add_argument("--actor-email", default="admin.demo@example.com")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    seed = load_managed_seed(args.file)
    if args.validate_only:
        result = {"seed_code": seed.seed_code, "version": seed.version, "catalogs": len(seed.catalogs), "knowledge_points": sum(len(item.points) for item in seed.catalogs), "prerequisites": len(seed.prerequisites)}
    else:
        engine = create_mysql_engine()
        try:
            with create_session_factory(engine).begin() as session:
                result = import_managed_seed(session, seed, args.actor_email).__dict__
        finally:
            engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
