import argparse
import json

from app.catalogs.loader import DEFAULT_CATALOG_PATH, import_catalog, load_catalog
from app.core.database import create_mysql_engine, create_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a versioned curriculum catalog")
    parser.add_argument("--file", default=str(DEFAULT_CATALOG_PATH), help="Catalog JSON path")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate and summarize the catalog without connecting to MySQL",
    )
    args = parser.parse_args()

    catalog = load_catalog(args.file)
    if args.validate_only:
        summary = {
            "catalog_code": catalog.catalog_code,
            "version": catalog.version,
            "knowledge_points": len(catalog.knowledge_points),
            "capability_points": len(catalog.capability_points),
            "knowledge_prerequisites": len(catalog.knowledge_prerequisites),
            "capability_prerequisites": len(catalog.capability_prerequisites),
            "capability_knowledge_requirements": len(
                catalog.capability_knowledge_requirements
            ),
        }
    else:
        session_factory = create_session_factory(create_mysql_engine())
        with session_factory.begin() as session:
            summary = import_catalog(session, catalog).__dict__
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
