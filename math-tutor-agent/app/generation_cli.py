from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.logging import configure_cli_logging
from app.domain.question_generation import QuestionGenerationJobInput
from app.core.database import create_mysql_engine, create_session_factory
from app.services.candidate_validation import candidate_validation_service
from app.services.question_generation import question_generation_service
from app.services.validation_versions import validation_version_registry


def main() -> None:
    """中文：处理“main”相关操作。
    English: Handles the main operation.
    """
    configure_cli_logging()
    parser = argparse.ArgumentParser(
        description="Generate candidate variations from trusted mother problems"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser("create", help="Register and execute a generation batch")
    create.add_argument("--file", required=True, help="QuestionGenerationJobInput JSON")
    run = subparsers.add_parser("run", help="Resume one registered job")
    run.add_argument("job_id")
    show = subparsers.add_parser("show", help="Show job output and candidate positions")
    show.add_argument("job_id")
    validate = subparsers.add_parser("validate", help="Validate all candidates in a batch")
    validate.add_argument("batch_id")
    validate.add_argument("--profile", default="quadratic-v1")
    validate_problem = subparsers.add_parser(
        "validate-problem", help="Validate one candidate with an explicit model version"
    )
    validate_problem.add_argument("problem_id")
    validate_problem.add_argument("model_version_id")
    bootstrap = subparsers.add_parser(
        "bootstrap-validation", help="Register the default prompts and verifiers"
    )
    bootstrap.add_argument("model_version_id")
    args = parser.parse_args()

    if args.action == "create":
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        result = question_generation_service.create_and_run(
            QuestionGenerationJobInput.model_validate(payload)
        )
    elif args.action == "run":
        result = question_generation_service.run(args.job_id)
    elif args.action == "show":
        result = question_generation_service.get(args.job_id)
    elif args.action == "validate":
        result = candidate_validation_service.validate_batch(
            args.batch_id, verifier_profile=args.profile
        )
    elif args.action == "validate-problem":
        session_factory = create_session_factory(create_mysql_engine())
        with session_factory.begin() as session:
            versions = validation_version_registry.ensure(
                session,
                model_version_id=args.model_version_id,
                profile="quadratic-v1",
            )
        result = candidate_validation_service.validate_problem(
            args.problem_id, versions=versions
        )
    else:
        session_factory = create_session_factory(create_mysql_engine())
        with session_factory.begin() as session:
            generation_prompt = validation_version_registry.generation_prompt(session)
            versions = validation_version_registry.ensure(
                session,
                model_version_id=args.model_version_id,
                profile="quadratic-v1",
            )
        result = {
            "profile": "quadratic-v1",
            "generation_prompt_version_id": generation_prompt.id,
            **versions.__dict__,
        }
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
