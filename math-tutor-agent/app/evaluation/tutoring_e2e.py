from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from app.agents.tutoring_team import TeachingOrchestrator
from app.cache.noop import NoOpRuntimeCache
from app.domain.tutoring_evaluation import (
    TutoringCaseResult,
    TutoringEvaluationCase,
    TutoringEvaluationMetrics,
    TutoringEvaluationReport,
    TutoringStageOracle,
    TutoringStageResult,
)
from app.evaluation.datasets import DEFAULT_TUTORING_E2E_MANIFEST, load_tutoring_e2e_suite
from app.harness.contracts import HarnessBudget
from app.harness.math_tutor import MathTutorAgentHarness
from app.providers.llm import llm_provider, llm_registry
from app.repositories.sessions import InMemorySessionRepository


class TutoringE2EEvaluator:
    """中文：执行真实多 Agent 教学编排并按冻结合约评分。\n    English: Runs the live multi-agent tutoring orchestration and scores frozen contracts.
    """

    def run(
        self,
        *,
        manifest_path: str | Path = DEFAULT_TUTORING_E2E_MANIFEST,
        model_id: str | None = None,
        case_ids: set[str] | None = None,
        prompt_version: str = "tutoring-prompts-v2",
        code_revision: str = "working-tree",
    ) -> TutoringEvaluationReport:
        """中文：运行选定案例并生成包含发布阻断结论的报告。\n        English: Runs selected cases and returns a report with a release gate decision.
        """

        manifest, cases, summary = load_tutoring_e2e_suite(manifest_path)
        if case_ids:
            cases = [case for case in cases if case.id in case_ids]
            missing = case_ids - {case.id for case in cases}
            if missing:
                raise ValueError(f"Unknown tutoring E2E case IDs: {sorted(missing)}")
        selected = llm_registry.resolve(model_id, require_available=True)
        selected_model_id = llm_registry.model_id(selected.provider_id, selected.model_name)
        started = datetime.now(timezone.utc)
        with llm_provider.use_model(selected_model_id, require_available=True):
            results = [self._run_case(case, selected_model_id) for case in cases]
        finished = datetime.now(timezone.utc)
        metrics = self._metrics(results)
        blockers = self._blockers(metrics, manifest.thresholds, results)
        if case_ids:
            blockers.insert(0, "partial_suite_not_release_eligible")
        return TutoringEvaluationReport(
            dataset_name=manifest.name,
            dataset_sha256=summary.verified_sha256["dataset"],
            model_id=selected_model_id,
            prompt_version=prompt_version,
            code_revision=code_revision,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            metrics=metrics,
            thresholds=manifest.thresholds,
            gate_status="blocked" if blockers else "passed",
            blockers=blockers,
            cases=results,
        )

    def _run_case(self, case: TutoringEvaluationCase, model_id: str) -> TutoringCaseResult:
        """中文：通过真实 Harness 在无生产存储的隔离环境执行完整案例。\n        English: Runs a complete case through the real Harness without production storage.
        """

        harness = MathTutorAgentHarness(
            repository=InMemorySessionRepository(),
            orchestrator=TeachingOrchestrator(),
            budget=HarnessBudget(max_agent_calls=32, max_duration_ms=300_000),
            runtime_cache=NoOpRuntimeCache(),
        )
        case_started = perf_counter()
        stages: list[TutoringStageResult] = []
        try:
            before = 0
            run = harness.start_session(
                question=case.input.question,
                student_user_id=f"evaluation:{case.id}",
                llm_model_id=model_id,
            )
            stages.append(self._score_stage(
                case.oracle[0], run.session, run.reply, run.duration_ms, before,
                run.degraded, run.degradation_code,
            ))
            for turn, oracle in zip(case.input.turns, case.oracle[1:], strict=True):
                before = len(run.session.artifacts)
                run = harness.run_turn(
                    run.session.id,
                    turn.message,
                    turn.intent,
                    client_turn_id=f"evaluation:{case.id}:{turn.id}:{uuid4()}",
                )
                stages.append(self._score_stage(
                    oracle, run.session, run.reply, run.duration_ms, before,
                    run.degraded, run.degradation_code,
                ))
            return TutoringCaseResult(
                case_id=case.id,
                passed=all(stage.passed for stage in stages),
                duration_ms=round((perf_counter() - case_started) * 1000),
                stages=stages,
            )
        except Exception as exc:
            return TutoringCaseResult(
                case_id=case.id,
                passed=False,
                duration_ms=round((perf_counter() - case_started) * 1000),
                stages=stages,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            harness.close()

    def _score_stage(
        self,
        oracle: TutoringStageOracle,
        session,
        reply,
        duration_ms: int,
        artifact_start: int,
        degraded: bool,
        degradation_code: str | None,
    ) -> TutoringStageResult:
        """中文：按状态、产物、内容、安全边界与耗时断言评分。\n        English: Scores status, artifacts, content, safety boundaries, and latency assertions.
        """

        artifacts = session.artifacts[artifact_start:]
        kinds = [artifact.kind for artifact in artifacts]
        failures: list[str] = []
        status = str(session.status)
        action = str(reply.action)
        if status not in oracle.expected_statuses:
            failures.append(f"unexpected_status:{status}")
        if action not in oracle.expected_actions:
            failures.append(f"unexpected_action:{action}")
        for kind in oracle.required_artifacts:
            if kind not in kinds:
                failures.append(f"missing_artifact:{kind}")
        for kind in oracle.forbidden_artifacts:
            if kind in kinds:
                failures.append(f"forbidden_artifact:{kind}")
        for pattern in oracle.required_reply_patterns:
            if not re.search(pattern, reply.text, re.IGNORECASE):
                failures.append(f"missing_reply_pattern:{pattern}")
        forbidden_hits = [
            pattern for pattern in oracle.forbidden_reply_patterns
            if re.search(pattern, reply.text, re.IGNORECASE)
        ]
        failures.extend(f"forbidden_reply_pattern:{pattern}" for pattern in forbidden_hits)
        if oracle.expected_hint_level is not None and reply.hint_level != oracle.expected_hint_level:
            failures.append(f"unexpected_hint_level:{reply.hint_level}")
        if duration_ms > oracle.max_duration_ms:
            failures.append(f"stage_timeout:{duration_ms}>{oracle.max_duration_ms}")
        if degraded and degradation_code in {"run_timeout", "llm_provider_unavailable"}:
            failures.append(f"critical_runtime_degradation:{degradation_code}")

        verification = self._latest_payload(session, "verification_report")
        if oracle.require_verification_passed is not None:
            if bool(verification.get("passed")) != oracle.require_verification_passed:
                failures.append("verification_pass_mismatch")
        if oracle.allowed_verification_coverage:
            coverage = str(verification.get("coverage", "none"))
            if coverage not in oracle.allowed_verification_coverage:
                failures.append(f"verification_coverage_not_allowed:{coverage}")

        honesty = None
        if oracle.verification_honesty_checkpoint:
            honesty = self._verification_is_honest(verification)
            if not honesty:
                failures.append("verification_overclaims_coverage")
        answer = None
        if oracle.answer_checkpoint:
            answer = not any(item.startswith("missing_reply_pattern:") for item in failures)
        boundary = None
        if oracle.hint_boundary_checkpoint:
            boundary = not forbidden_hits and not reply.solution_steps
            if not boundary:
                failures.append("hint_boundary_leakage")
        return TutoringStageResult(
            step_id=oracle.step_id,
            passed=not failures,
            duration_ms=duration_ms,
            status=status,
            action=action,
            hint_level=reply.hint_level,
            artifact_kinds=kinds,
            reply_text=reply.text,
            degraded=degraded,
            degradation_code=degradation_code,
            failures=list(dict.fromkeys(failures)),
            answer_checkpoint_passed=answer,
            verification_honesty_passed=honesty,
            hint_boundary_passed=boundary,
        )

    @staticmethod
    def _latest_payload(session, kind: str) -> dict:
        """中文：读取会话中某类最新审计产物。\n        English: Reads the latest audit artifact of a given kind from the session.
        """

        for artifact in reversed(session.artifacts):
            if artifact.kind == kind:
                return artifact.payload
        return {}

    @staticmethod
    def _verification_is_honest(report: dict) -> bool:
        """中文：阻止无确定性检查却宣称完全覆盖。\n        English: Rejects full-coverage claims without deterministic checks.
        """

        if not report:
            return False
        if report.get("coverage") != "full":
            return True
        checks = report.get("checks") or []
        verifier_type = report.get("verifier_type")
        return bool(checks) and verifier_type in {"cas", "hybrid"}

    @staticmethod
    def _metrics(results: list[TutoringCaseResult]) -> TutoringEvaluationMetrics:
        """中文：汇总案例、阶段、答案、验证、泄露与超时指标。\n        English: Aggregates case, stage, answer, verification, leakage, and timeout metrics.
        """

        stages = [stage for result in results for stage in result.stages]
        answers = [stage.answer_checkpoint_passed for stage in stages if stage.answer_checkpoint_passed is not None]
        honesty = [stage.verification_honesty_passed for stage in stages if stage.verification_honesty_passed is not None]
        boundaries = [stage.hint_boundary_passed for stage in stages if stage.hint_boundary_passed is not None]
        timeout_count = sum(
            any(failure.startswith("stage_timeout:") for failure in stage.failures)
            for stage in stages
        )
        ratio = lambda values: round(sum(bool(item) for item in values) / len(values), 6) if values else None
        return TutoringEvaluationMetrics(
            case_pass_rate=round(sum(result.passed for result in results) / len(results), 6) if results else 0.0,
            stage_pass_rate=round(sum(stage.passed for stage in stages) / len(stages), 6) if stages else 0.0,
            answer_correctness_rate=ratio(answers),
            verification_honesty_rate=ratio(honesty),
            hint_leakage_rate=(round(1 - ratio(boundaries), 6) if boundaries else None),
            timeout_rate=round(timeout_count / len(stages), 6) if stages else 0.0,
        )

    @staticmethod
    def _blockers(metrics, thresholds: dict[str, float], results: list[TutoringCaseResult]) -> list[str]:
        """中文：根据冻结阈值和关键安全失败生成发布阻断原因。\n        English: Produces release blockers from frozen thresholds and critical safety failures.
        """

        blockers: list[str] = []
        for key, minimum in thresholds.items():
            value = getattr(metrics, key, None)
            if value is None:
                continue
            elif key in {"hint_leakage_rate", "timeout_rate"}:
                if value > minimum:
                    blockers.append(f"metric_above_maximum:{key}:{value}>{minimum}")
            elif value < minimum:
                blockers.append(f"metric_below_minimum:{key}:{value}<{minimum}")
        for result in results:
            if result.error:
                blockers.append(f"case_runtime_error:{result.case_id}")
            for stage in result.stages:
                if stage.answer_checkpoint_passed is False:
                    blockers.append(f"incorrect_answer:{result.case_id}:{stage.step_id}")
                if stage.verification_honesty_passed is False:
                    blockers.append(f"verification_overclaim:{result.case_id}:{stage.step_id}")
                if stage.hint_boundary_passed is False:
                    blockers.append(f"hint_leakage:{result.case_id}:{stage.step_id}")
        return list(dict.fromkeys(blockers))
