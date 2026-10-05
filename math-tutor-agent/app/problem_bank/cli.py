import argparse
import json

from app.core.database import create_mysql_engine, create_session_factory
from app.problem_bank.loader import (
    DEFAULT_SEED_PATH,
    import_trusted_seed,
    load_trusted_seed,
    validate_trusted_seed,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate or import trusted quadratic mother problems"
    )
    parser.add_argument("--file", default=str(DEFAULT_SEED_PATH), help="Seed JSON path")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate rights metadata, leakage and SymPy answers without MySQL",
    )
    args = parser.parse_args()

    dataset = load_trusted_seed(args.file)
    if args.validate_only:
        validation, _ = validate_trusted_seed(dataset)
        summary = validation.__dict__
    else:
        session_factory = create_session_factory(create_mysql_engine())
        with session_factory.begin() as session:
            summary = import_trusted_seed(session, dataset).__dict__
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
