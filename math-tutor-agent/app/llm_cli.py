from __future__ import annotations

import argparse
import json
from hashlib import sha256

from sqlalchemy import select

from app.core.logging import configure_cli_logging
from app.core.database import create_mysql_engine, create_session_factory
from app.models.generation import ModelVersion
from app.providers.llm import llm_registry


def main() -> None:
    """中文：处理“main”相关操作。
    English: Handles the main operation.
    """
    configure_cli_logging()
    parser = argparse.ArgumentParser(description="Manage configured LLM providers")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("list", help="List the allowlisted model catalog")
    check = subparsers.add_parser("check", help="Check one provider endpoint")
    check.add_argument("model_id")
    probe = subparsers.add_parser("probe", help="Send one minimal structured-output call")
    probe.add_argument("model_id")
    tutor_smoke = subparsers.add_parser(
        "tutor-smoke",
        help="Run one complete tutoring-session start through the Agent Harness",
    )
    tutor_smoke.add_argument("model_id")
    tutor_smoke.add_argument(
        "--question",
        default="求 x→0 时 (e^x-1-x)/x^2 的极限。",
    )
    subparsers.add_parser(
        "sync-model-versions",
        help="Register configured models for generation and review audit records",
    )
    args = parser.parse_args()

    if args.action == "list":
        result = {
            "default_model_id": llm_registry.default_model_id,
            "models": [item.__dict__ for item in llm_registry.list_models()],
        }
    elif args.action == "check":
        provider = llm_registry.resolve(args.model_id)
        ready, detail = provider.check_readiness()
        result = {"model_id": args.model_id, "ready": ready, "detail": detail}
    elif args.action == "probe":
        provider = llm_registry.resolve(args.model_id)
        response = provider.complete_json(
            "Return JSON only. Reply with an object containing ok=true and provider.",
            f"Test the configured {provider.provider_id} model and return JSON.",
        )
        result = {
            "model_id": args.model_id,
            "ok": isinstance(response, dict) and response.get("ok") is True,
            "response": response,
        }
    elif args.action == "tutor-smoke":
        result = _run_tutor_smoke(args.model_id, args.question)
    else:
        result = _sync_model_versions()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _sync_model_versions() -> dict:
    """中文：处理“同步·模型·versions”相关操作。
    English: Handles the sync model versions operation.
    """
    session_factory = create_session_factory(create_mysql_engine())
    synced: list[dict[str, str]] = []
    with session_factory.begin() as session:
        for option in llm_registry.list_models():
            if not option.available:
                continue
            provider = llm_registry.resolve(option.id)
            entity = session.scalar(select(ModelVersion).where(
                ModelVersion.provider == option.provider,
                ModelVersion.model_name == option.model,
                ModelVersion.version_label == "runtime-config-v1",
            ))
            fingerprint = sha256(
                json.dumps({
                    "api_family": "openai_chat_completions",
                    "provider": option.provider,
                    "model": option.model,
                    "base_url": getattr(provider, "base_url", ""),
                    "max_output_tokens": getattr(provider, "max_output_tokens", None),
                }, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if entity is None:
                entity = ModelVersion(
                    provider=option.provider,
                    model_name=option.model,
                    version_label="runtime-config-v1",
                    api_family="openai_chat_completions",
                    config_fingerprint=fingerprint,
                    capabilities_json=["json_output", "structured_agents"],
                    metadata_json={
                        "public_model_id": option.id,
                        "managed_by": "math-tutor-llm",
                    },
                    active=True,
                )
                session.add(entity)
                session.flush()
            else:
                entity.config_fingerprint = fingerprint
                entity.active = True
            synced.append({"model_id": option.id, "model_version_id": entity.id})
    return {"synced": synced, "count": len(synced)}


def _run_tutor_smoke(model_id: str, question: str) -> dict:
    """中文：处理“执行·tutor·smoke”相关操作。
    English: Handles the run tutor smoke operation.
    """
    from app.agents.tutoring_team import TeachingOrchestrator
    from app.cache.noop import NoOpRuntimeCache
    from app.harness.contracts import HarnessBudget
    from app.harness.math_tutor import MathTutorAgentHarness
    from app.repositories.sessions import InMemorySessionRepository

    harness = MathTutorAgentHarness(
        repository=InMemorySessionRepository(),
        orchestrator=TeachingOrchestrator(),
        budget=HarnessBudget(max_agent_calls=8, max_duration_ms=120_000),
        runtime_cache=NoOpRuntimeCache(),
    )
    try:
        run = harness.start_session(
            question=question,
            student_user_id="llm-smoke-student",
            llm_model_id=model_id,
        )
        return {
            "model_id": run.session.llm_model_id,
            "session_id": run.session.id,
            "status": run.session.status.value,
            "reply": run.reply.model_dump(mode="json"),
            "duration_ms": run.duration_ms,
            "degraded": run.degraded,
            "degradation_reason": run.degradation_reason,
            "trace": [item.model_dump(mode="json") for item in run.trace],
        }
    finally:
        harness.close()


if __name__ == "__main__":
    main()
