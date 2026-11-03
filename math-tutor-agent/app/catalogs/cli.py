import argparse
import json

from app.core.logging import configure_cli_logging
from app.catalogs.loader import catalog_paths, import_catalog, load_catalog
from app.core.database import create_mysql_engine, create_session_factory


def main() -> None:
    """中文：处理“main”相关操作。
    English: Handles the main operation.
    """
    configure_cli_logging()
    parser = argparse.ArgumentParser(description="Import a versioned curriculum catalog")
    parser.add_argument("--file", help="Catalog JSON path; omit to import every bundled catalog")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate and summarize the catalog without connecting to MySQL",
    )
    args = parser.parse_args()

    catalogs = [load_catalog(args.file)] if args.file else [
        load_catalog(path) for path in catalog_paths()
    ]
    summaries = []
    if args.validate_only:
        summaries = [{
            "catalog_code": catalog.catalog_code,
            "version": catalog.version,
            "knowledge_points": len(catalog.knowledge_points),
            "capability_points": len(catalog.capability_points),
            "knowledge_prerequisites": len(catalog.knowledge_prerequisites),
            "capability_prerequisites": len(catalog.capability_prerequisites),
            "capability_knowledge_requirements": len(
                catalog.capability_knowledge_requirements
            ),
        } for catalog in catalogs]
    else:
        session_factory = create_session_factory(create_mysql_engine())
        with session_factory.begin() as session:
            summaries = [import_catalog(session, catalog).__dict__ for catalog in catalogs]
    summary = summaries[0] if len(summaries) == 1 else {"catalogs": summaries}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
