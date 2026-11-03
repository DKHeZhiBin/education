import argparse
import json

from app.core.logging import configure_cli_logging
from app.harness.factory import build_math_tutor_harness


def main() -> None:
    """中文：处理“main”相关操作。
    English: Handles the main operation.
    """
    configure_cli_logging()
    parser = argparse.ArgumentParser(description="Run the Math Tutor Agent Harness")
    parser.add_argument("question", help="The math question to start with")
    parser.add_argument("--student-id", required=True, help="Existing authenticated student user ID")
    args = parser.parse_args()

    harness = build_math_tutor_harness()
    try:
        result = harness.start_session(
            args.question,
            student_user_id=args.student_id,
        )
        print(json.dumps({
            "run_id": result.run_id,
            "session_id": result.session.id,
            "reply": result.reply.model_dump(mode="json"),
            "trace": [step.model_dump(mode="json") for step in result.trace],
            "duration_ms": result.duration_ms,
            "degraded": result.degraded,
            "degradation_reason": result.degradation_reason,
        }, ensure_ascii=False, indent=2))
    finally:
        harness.close()


if __name__ == "__main__":
    main()
