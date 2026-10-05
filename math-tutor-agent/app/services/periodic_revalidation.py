from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.agents.independent_review import IndependentReviewAgent
from app.agents.independent_solving import IndependentSolvingAgent
from app.agents.problem_condition_check import ProblemConditionCheckAgent
from app.core.config import Settings, settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.index_lifecycle import IndexMaintenanceRequest
from app.domain.periodic_revalidation import (
    RevalidationDueRunSummary,
    RevalidationPolicyInput,
    RevalidationPolicyView,
    RevalidationRunView,
    RevalidationScope,
)
from app.evaluation.leakage import EvaluationLeakageDetector
from app.models.knowledge import KnowledgeProblem
from app.models.revalidation import ContentRevalidationItem
from app.providers.llm import OpenAICompatibleProvider, llm_provider
from app.repositories.admission_gate import AdmissionGateRepository
from app.repositories.duplicate_detection import DuplicateDetectionRepository
from app.repositories.evaluation_leakage import EvaluationLeakageRepository
from app.repositories.independent_review import IndependentReviewRepository
from app.repositories.independent_solving import IndependentSolvingRepository
from app.repositories.numeric_verification import NumericVerificationRepository
from app.repositories.periodic_revalidation import PeriodicRevalidationRepository
from app.repositories.problem_condition_check import ProblemConditionCheckRepository
from app.repositories.quadratic_verification import QuadraticVerificationRepository
from app.search_index.lifecycle_service import SearchIndexLifecycleService
from app.verifiers.four_layer_duplicate import FourLayerDuplicateDetector
from app.verifiers.quadratic_numeric import QuadraticNumericVerifier
from app.verifiers.quadratic_sympy import QuadraticSympyVerifier


class PeriodicContentRevalidationService:
    """Run the existing fail-closed admission chain against approved content."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        session_factory: sessionmaker[Session] | None = None,
        provider: OpenAICompatibleProvider = llm_provider,
    ) -> None:
        self.config = config
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())
        self.provider = provider
        self.repository = PeriodicRevalidationRepository()
        self.lifecycle = SearchIndexLifecycleService(
            config, session_factory=self.session_factory
        )
        self.condition_repository = ProblemConditionCheckRepository()
        self.solving_repository = IndependentSolvingRepository()
        self.sympy_repository = QuadraticVerificationRepository()
        self.numeric_repository = NumericVerificationRepository()
        self.duplicate_repository = DuplicateDetectionRepository()
        self.leakage_repository = EvaluationLeakageRepository()
        self.review_repository = IndependentReviewRepository()
        self.admission_repository = AdmissionGateRepository()
        self.condition_agent = ProblemConditionCheckAgent(provider)
        self.solving_agent = IndependentSolvingAgent(provider)
        self.review_agent = IndependentReviewAgent(provider)
        self.sympy_verifier = QuadraticSympyVerifier()
        self.numeric_verifier = QuadraticNumericVerifier()
        self.duplicate_detector = FourLayerDuplicateDetector()
        self.leakage_detector = EvaluationLeakageDetector()

    def configure(self, request: RevalidationPolicyInput) -> RevalidationPolicyView:
        with self.session_factory.begin() as session:
            policy = self.repository.upsert_policy(session, request)
            return self.repository.view_policy(policy)

    def run_due(self, scope: RevalidationScope) -> RevalidationDueRunSummary:
        now = self._now()
        with self.session_factory.begin() as session:
            policies = self.repository.due_policies(
                session,
                now,
                policy_key=scope.policy_key,
            )
            if scope.policy_key and not policies:
                raise LookupError("enabled revalidation policy not found")
            runs = [
                self.repository.create_run(
                    session,
                    policy,
                    trigger_type="manual" if scope.force else "scheduled",
                    scheduled_for=now,
                )
                for policy in policies
                if scope.force or policy.next_run_at <= now
            ]
            run_ids = [item.id for item in runs]
        completed = 0
        failed = 0
        for run_id in run_ids:
            result = self.process_run(run_id)
            if result.status == "completed":
                completed += 1
            elif result.status in {"failed", "partial_failed"}:
                failed += 1
        return RevalidationDueRunSummary(
            selected_policy_count=len(run_ids),
            run_ids=run_ids,
            completed_count=completed,
            failed_count=failed,
        )

    def process_run(self, run_id: str) -> RevalidationRunView:
        with self.session_factory.begin() as session:
            run = self.repository.get_run(session, run_id)
            if run is None:
                raise LookupError("revalidation run not found")
            policy = self.repository.policy(session, run.policy_id)
            policy_view = self.repository.view_policy(policy)
            if run.status in {"completed", "partial_failed", "failed", "cancelled"}:
                return self.repository.view_run(run, self.repository.run_items(session, run.id))
            run.status = "running"
            run.started_at = run.started_at or self._now()
            item_ids = [
                item.id for item in self.repository.run_items(session, run.id)
                if item.status not in {"passed", "failed", "inconclusive"}
            ]

        for item_id in item_ids:
            try:
                self._process_item(item_id, policy_view)
            except Exception as error:
                self._mark_item_error(item_id, error)

        with self.session_factory.begin() as session:
            run = self.repository.get_run(session, run_id)
            if run is None:
                raise LookupError("revalidation run disappeared")
            items = self.repository.run_items(session, run.id)
            run.passed_count = sum(item.outcome == "passed" for item in items)
            run.failed_count = sum(item.outcome == "failed" for item in items)
            run.inconclusive_count = sum(item.outcome == "inconclusive" for item in items)
            if not items or run.passed_count == len(items):
                run.status = "completed"
            elif run.failed_count == len(items):
                run.status = "failed"
            else:
                run.status = "partial_failed"
            run.finished_at = self._now()
            run.summary_json = {
                "tool_chain": [
                    "quadratic_sympy",
                    "quadratic_numeric",
                    "four_layer_duplicate",
                    "evaluation_leakage",
                ],
                "ai_chain": [
                    "problem_condition_check",
                    "independent_solving",
                    "independent_pedagogical_review",
                ],
                "deterministic_failure_overridable": False,
            }
            return self.repository.view_run(run, items)

    def get_run(self, run_id: str) -> RevalidationRunView | None:
        with self.session_factory() as session:
            run = self.repository.get_run(session, run_id)
            if run is None:
                return None
            return self.repository.view_run(run, self.repository.run_items(session, run.id))

    def close(self) -> None:
        self.lifecycle.close()

    def _process_item(self, item_id: str, policy) -> None:
        problem_id = self._start_item(item_id)
        maintenance = self.lifecycle.enqueue(IndexMaintenanceRequest(
            problem_id=problem_id,
            trigger_type="revalidation",
            reason=f"periodic_cross_review:{item_id}",
        ))
        with self.session_factory.begin() as session:
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            item.maintenance_job_id = maintenance.id
            item.status = "suppressing"
        maintenance = self.lifecycle.run_job(maintenance.id)
        if maintenance.status not in {"waiting_for_approval", "completed"}:
            raise RuntimeError(f"index_suppression_{maintenance.status}")

        self._set_item_status(item_id, "validating")
        condition_context = self._load_condition_context(problem_id, policy)
        condition_report = self.condition_agent.run(
            context=condition_context.check_context,
            expected_model_name=condition_context.model_name,
            versioned_prompt=condition_context.versioned_prompt,
        )
        with self.session_factory.begin() as session:
            condition_evidence = self.condition_repository.persist_report(
                session, context=condition_context, report=condition_report
            )
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            item.condition_evidence_id = condition_evidence.id
        if condition_evidence.status.value != "passed":
            raise RuntimeError("condition_revalidation_not_passed")

        solving_context = self._load_solving_context(problem_id, policy)
        draft = self.solving_agent.run(
            context=solving_context.solver_context,
            expected_model_name=solving_context.model_name,
            versioned_prompt=solving_context.versioned_prompt,
        )
        with self.session_factory.begin() as session:
            solved = self.solving_repository.persist_solution(
                session, context=solving_context, draft=draft
            )
        solution_id = solved.solution.id
        with self.session_factory.begin() as session:
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            item.solution_id = solution_id
            item.solution_content_hash = solved.solution.content_hash
            item.solution_independence_evidence_id = solved.evidence.id
            item.status = "tool_verification"

        tool_ids = self._run_tools(item_id, problem_id, solution_id, policy)
        with self.session_factory.begin() as session:
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            item.tool_evidence_ids_json = tool_ids
            item.status = "ai_review"

        review_context = self._load_review_context(problem_id, solution_id, policy)
        review_report = self.review_agent.run(
            context=review_context.review_context,
            expected_model_name=review_context.model_name,
            versioned_prompt=review_context.versioned_prompt,
        )
        with self.session_factory.begin() as session:
            review_evidence = self.review_repository.persist_report(
                session, context=review_context, report=review_report
            )
        self._set_item_status(item_id, "admission")
        with self.session_factory.begin() as session:
            problem = session.get(KnowledgeProblem, problem_id)
            result = self.admission_repository.evaluate_and_persist(
                session,
                problem_id=problem_id,
                expected_status_version=problem.status_version,
                actor_id=f"periodic-revalidation:{item_id}",
            )
            decision = result.gate_result.decision.value
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            item.ai_review_evidence_id = review_evidence.id
            item.admission_evidence_id = result.decision_evidence.id
            item.finished_at = self._now()
            if decision == "approve":
                item.status = "passed"
                item.outcome = "passed"
            elif decision in {"revise", "quarantine"}:
                item.status = "failed"
                item.outcome = "failed"
            else:
                item.status = "inconclusive"
                item.outcome = "inconclusive"
            metadata = dict(problem.metadata_json or {})
            metadata.update({
                "last_periodic_revalidation_at": self._now().isoformat(),
                "last_periodic_revalidation_outcome": item.outcome,
                "last_periodic_revalidation_item_id": item.id,
            })
            problem.metadata_json = metadata
            maintenance_job_id = item.maintenance_job_id
        if decision == "approve" and maintenance_job_id:
            rebuilt = self.lifecycle.run_job(maintenance_job_id)
            if rebuilt.status != "completed":
                raise RuntimeError(f"index_rebuild_{rebuilt.status}")

    def _run_tools(
        self, item_id: str, problem_id: str, solution_id: str, policy
    ) -> list[str]:
        evidence_ids: list[str] = []
        with self.session_factory() as session:
            sympy_context = self.sympy_repository.load_verifier_context(
                session,
                problem_id=problem_id,
                solution_id=solution_id,
                verifier_version_id=policy.sympy_verifier_version_id,
            )
        sympy_report = self.sympy_verifier.verify(sympy_context.verification_context)
        with self.session_factory.begin() as session:
            symbolic = self.sympy_repository.persist_report(
                session, context=sympy_context, report=sympy_report
            )
        evidence_ids.extend([
            symbolic.symbolic_evidence.id,
            symbolic.constraint_evidence.id,
        ])
        self._save_tool_evidence(item_id, evidence_ids)

        with self.session_factory() as session:
            numeric_context = self.numeric_repository.load_verifier_context(
                session,
                problem_id=problem_id,
                solution_id=solution_id,
                verifier_version_id=policy.numeric_verifier_version_id,
            )
        numeric_report = self.numeric_verifier.verify(numeric_context.verification_context)
        with self.session_factory.begin() as session:
            numeric = self.numeric_repository.persist_report(
                session, context=numeric_context, report=numeric_report
            )
        evidence_ids.append(numeric.id)
        self._save_tool_evidence(item_id, evidence_ids)

        with self.session_factory() as session:
            duplicate_context = self.duplicate_repository.load_detector_context(
                session,
                problem_id=problem_id,
                solution_id=solution_id,
                verifier_version_id=policy.duplicate_verifier_version_id,
            )
        duplicate_report = self.duplicate_detector.detect(duplicate_context.detection_context)
        with self.session_factory.begin() as session:
            duplicate = self.duplicate_repository.persist_report(
                session, context=duplicate_context, report=duplicate_report
            )
        evidence_ids.append(duplicate.id)
        self._save_tool_evidence(item_id, evidence_ids)

        with self.session_factory() as session:
            leakage_context = self.leakage_repository.load_detector_context(
                session,
                problem_id=problem_id,
                verifier_version_id=policy.leakage_verifier_version_id,
            )
        leakage_report = self.leakage_detector.detect(leakage_context.leakage_context)
        with self.session_factory.begin() as session:
            leakage = self.leakage_repository.persist_report(
                session, context=leakage_context, report=leakage_report
            )
        evidence_ids.append(leakage.id)
        self._save_tool_evidence(item_id, evidence_ids)
        return evidence_ids

    def _save_tool_evidence(self, item_id: str, evidence_ids: list[str]) -> None:
        with self.session_factory.begin() as session:
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            if item is None:
                raise LookupError("revalidation item not found")
            item.tool_evidence_ids_json = list(evidence_ids)

    def _load_condition_context(self, problem_id: str, policy):
        with self.session_factory() as session:
            return self.condition_repository.load_agent_context(
                session,
                problem_id=problem_id,
                model_version_id=policy.execution_model_version_id,
                prompt_version_id=policy.condition_prompt_version_id,
            )

    def _load_solving_context(self, problem_id: str, policy):
        with self.session_factory() as session:
            return self.solving_repository.load_agent_context(
                session,
                problem_id=problem_id,
                model_version_id=policy.execution_model_version_id,
                prompt_version_id=policy.solver_prompt_version_id,
            )

    def _load_review_context(self, problem_id: str, solution_id: str, policy):
        with self.session_factory() as session:
            return self.review_repository.load_agent_context(
                session,
                problem_id=problem_id,
                solution_id=solution_id,
                model_version_id=policy.review_model_version_id,
                prompt_version_id=policy.review_prompt_version_id,
            )

    def _start_item(self, item_id: str) -> str:
        with self.session_factory.begin() as session:
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            if item is None:
                raise LookupError("revalidation item not found")
            if item.status in {"passed", "failed", "inconclusive"}:
                return item.problem_id
            problem = session.get(KnowledgeProblem, item.problem_id)
            if problem is None or problem.content_hash != item.problem_content_hash:
                raise RuntimeError("problem_changed_since_revalidation_selection")
            if problem.content_status not in {"approved", "indexed"}:
                raise RuntimeError("problem_no_longer_approved")
            item.status = "suppressing"
            item.started_at = item.started_at or self._now()
            item.error_code = None
            item.error_detail = None
            return item.problem_id

    def _set_item_status(self, item_id: str, status: str) -> None:
        with self.session_factory.begin() as session:
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            if item is None:
                raise LookupError("revalidation item not found")
            item.status = status

    def _mark_item_error(self, item_id: str, error: Exception) -> None:
        suppression_required = False
        problem_id: str | None = None
        with self.session_factory.begin() as session:
            item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
            if item is None:
                return
            item.status = "failed"
            item.outcome = "failed"
            item.error_code = type(error).__name__[:100]
            item.error_detail = str(error)[:2000]
            item.finished_at = self._now()
            problem = session.get(KnowledgeProblem, item.problem_id)
            if problem is not None:
                problem_id = problem.id
                suppression_required = (
                    problem.content_status in {"approved", "indexed"}
                    and item.maintenance_job_id is None
                )
                metadata = dict(problem.metadata_json or {})
                metadata.update({
                    "last_periodic_revalidation_at": self._now().isoformat(),
                    "last_periodic_revalidation_outcome": "failed",
                    "last_periodic_revalidation_item_id": item.id,
                })
                problem.metadata_json = metadata
        if suppression_required and problem_id:
            self._suppress_after_preflight_failure(item_id, problem_id)

    def _suppress_after_preflight_failure(self, item_id: str, problem_id: str) -> None:
        """Best-effort fail-safe for errors raised before normal index suppression."""
        try:
            maintenance = self.lifecycle.enqueue(IndexMaintenanceRequest(
                problem_id=problem_id,
                trigger_type="revalidation",
                reason=f"periodic_cross_review_preflight_failure:{item_id}",
            ))
            with self.session_factory.begin() as session:
                item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
                if item is not None:
                    item.maintenance_job_id = maintenance.id
            result = self.lifecycle.run_job(maintenance.id)
            if result.status not in {"waiting_for_approval", "completed"}:
                raise RuntimeError(f"index_suppression_{result.status}")
        except Exception as suppression_error:
            with self.session_factory.begin() as session:
                item = session.get(ContentRevalidationItem, item_id, with_for_update=True)
                if item is not None:
                    original = item.error_detail or ""
                    suffix = f"; suppression_error={suppression_error}"
                    item.error_detail = f"{original}{suffix}"[:2000]

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)


periodic_revalidation_service = PeriodicContentRevalidationService()
