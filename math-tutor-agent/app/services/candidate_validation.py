from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.independent_review import IndependentReviewAgent
from app.agents.independent_solving import IndependentSolvingAgent
from app.agents.problem_condition_check import ProblemConditionCheckAgent
from app.core.database import create_mysql_engine, create_session_factory
from app.core.config import settings
from app.domain.candidate_validation import (
    CandidateValidationBatchResult,
    CandidateValidationResult,
    CandidateValidationStage,
    CandidateValidationStep,
)
from app.domain.knowledge import ProblemContentStatus
from app.evaluation.leakage import EvaluationLeakageDetector
from app.models.generation import GenerationBatch
from app.models.knowledge import KnowledgeProblem
from app.providers.llm import LLMProvider, RoutingLLMProvider, llm_provider
from app.repositories.admission_gate import AdmissionGateRepository
from app.repositories.duplicate_detection import DuplicateDetectionRepository
from app.repositories.evaluation_leakage import EvaluationLeakageRepository
from app.repositories.independent_review import IndependentReviewRepository
from app.repositories.independent_solving import IndependentSolvingRepository
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.numeric_verification import NumericVerificationRepository
from app.repositories.problem_condition_check import ProblemConditionCheckRepository
from app.repositories.quadratic_verification import QuadraticVerificationRepository
from app.services.validation_versions import (
    CandidateValidationVersions,
    ValidationVersionRegistry,
    validation_version_registry,
)
from app.search_index.service import ProductionIndexService
from app.verifiers.four_layer_duplicate import FourLayerDuplicateDetector
from app.verifiers.quadratic_numeric import QuadraticNumericVerifier
from app.verifiers.quadratic_sympy import QuadraticSympyVerifier


class CandidateValidationService:
    """中文：定义“候选内容·验证·服务”类，封装该职责相关的数据与行为。
    English: Defines the candidate validation service class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Fail-closed validation chain for newly generated candidate problems.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        provider: LLMProvider = llm_provider,
        version_registry: ValidationVersionRegistry = validation_version_registry,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())
        self.provider = provider
        self.version_registry = version_registry
        self.knowledge_repository = KnowledgeRepository(session_factory=self.session_factory)
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

    def validate_batch(
        self,
        generation_batch_id: str,
        *,
        verifier_profile: str,
    ) -> CandidateValidationBatchResult:
        """中文：处理“验证·批次”相关操作。
        English: Handles the validate batch operation.
        """
        with self.session_factory.begin() as session:
            batch = session.get(GenerationBatch, generation_batch_id)
            if batch is None:
                raise LookupError("generation batch not found")
            if batch.model_version_id is None:
                raise ValueError("generation batch has no model version")
            versions = self.version_registry.ensure(
                session,
                model_version_id=batch.model_version_id,
                profile=verifier_profile,
            )
            problem_ids = list(session.scalars(
                select(KnowledgeProblem.id)
                .where(
                    KnowledgeProblem.generation_batch_id == generation_batch_id,
                    KnowledgeProblem.content_status.in_([
                        "candidate", "revision_required", "validating",
                    ]),
                )
                .order_by(KnowledgeProblem.created_at, KnowledgeProblem.id)
            ))

        results = [
            self.validate_problem(problem_id, versions=versions)
            for problem_id in problem_ids
        ]
        failed = sum(result.error_code is not None for result in results)
        return CandidateValidationBatchResult(
            generation_batch_id=generation_batch_id,
            verifier_profile=verifier_profile,
            total_count=len(results),
            completed_count=len(results) - failed,
            failed_count=failed,
            model_calls=sum(result.model_calls for result in results),
            results=results,
        )

    def validate_problem(
        self,
        problem_id: str,
        *,
        versions: CandidateValidationVersions,
    ) -> CandidateValidationResult:
        """中文：处理“验证·题目”相关操作。
        English: Handles the validate problem operation.
        """
        initial = self._problem(problem_id)
        steps: list[CandidateValidationStep] = []
        model_calls = 0
        solution_id: str | None = None
        try:
            if initial.content_status != "validating":
                self.knowledge_repository.transition_problem(
                    problem_id=problem_id,
                    target_status=ProblemContentStatus.VALIDATING,
                    expected_status_version=initial.status_version,
                    actor_type="job",
                    actor_id=f"candidate-validation:{initial.generation_batch_id}",
                )

            condition_context = self._condition_context(problem_id, versions)
            condition_report = self._model_call(
                condition_context.provider_id,
                condition_context.model_name,
                lambda: self.condition_agent.run(
                    context=condition_context.check_context,
                    expected_model_name=condition_context.model_name,
                    versioned_prompt=condition_context.versioned_prompt,
                ),
            )
            model_calls += 1
            with self.session_factory.begin() as session:
                condition = self.condition_repository.persist_report(
                    session, context=condition_context, report=condition_report
                )
            steps.append(CandidateValidationStep(
                stage=CandidateValidationStage.CONDITION_CHECK,
                status=condition.status.value,
                evidence_ids=[condition.id],
                detail=condition.summary,
            ))
            if condition.status.value != "passed":
                return self._finish_with_gate(
                    problem_id, initial, steps, model_calls, solution_id
                )

            solving_context = self._solving_context(problem_id, versions)
            draft = self._model_call(
                solving_context.provider_id,
                solving_context.model_name,
                lambda: self.solving_agent.run(
                    context=solving_context.solver_context,
                    expected_model_name=solving_context.model_name,
                    versioned_prompt=solving_context.versioned_prompt,
                ),
            )
            model_calls += 1
            with self.session_factory.begin() as session:
                solved = self.solving_repository.persist_solution(
                    session, context=solving_context, draft=draft
                )
            solution_id = solved.solution.id
            steps.append(CandidateValidationStep(
                stage=CandidateValidationStage.INDEPENDENT_SOLVING,
                status=solved.evidence.status.value,
                evidence_ids=[solved.evidence.id],
            ))

            steps.extend(self._run_tools(problem_id, solution_id, versions))

            review_context = self._review_context(problem_id, solution_id, versions)
            review_report = self._model_call(
                review_context.provider_id,
                review_context.model_name,
                lambda: self.review_agent.run(
                    context=review_context.review_context,
                    expected_model_name=review_context.model_name,
                    versioned_prompt=review_context.versioned_prompt,
                ),
            )
            model_calls += 1
            with self.session_factory.begin() as session:
                review = self.review_repository.persist_report(
                    session, context=review_context, report=review_report
                )
            steps.append(CandidateValidationStep(
                stage=CandidateValidationStage.INDEPENDENT_REVIEW,
                status=review.status.value,
                evidence_ids=[review.id],
                detail=review.summary,
            ))
            return self._finish_with_gate(
                problem_id, initial, steps, model_calls, solution_id
            )
        except Exception as error:
            try:
                result = self._finish_with_gate(
                    problem_id, initial, steps, model_calls, solution_id
                )
                return result.model_copy(update={
                    "error_code": type(error).__name__,
                    "error_detail": str(error)[:2000],
                })
            except Exception as gate_error:
                current = self._problem(problem_id)
                return CandidateValidationResult(
                    problem_id=problem_id,
                    initial_status=ProblemContentStatus(initial.content_status),
                    final_status=ProblemContentStatus(current.content_status),
                    solution_id=solution_id,
                    steps=steps,
                    model_calls=model_calls,
                    error_code=type(error).__name__,
                    error_detail=f"{error}; admission_error={gate_error}"[:2000],
                )

    def _run_tools(self, problem_id, solution_id, versions):
        """中文：处理“执行·tools”相关操作。
        English: Handles the run tools operation.
        """
        steps: list[CandidateValidationStep] = []
        with self.session_factory() as session:
            context = self.sympy_repository.load_verifier_context(
                session, problem_id=problem_id, solution_id=solution_id,
                verifier_version_id=versions.sympy_verifier_version_id,
            )
        report = self.sympy_verifier.verify(context.verification_context)
        with self.session_factory.begin() as session:
            persisted = self.sympy_repository.persist_report(
                session, context=context, report=report
            )
        steps.append(CandidateValidationStep(
            stage=CandidateValidationStage.SYMBOLIC_VERIFICATION,
            status=persisted.symbolic_evidence.status.value,
            evidence_ids=[
                persisted.symbolic_evidence.id, persisted.constraint_evidence.id,
            ],
        ))

        with self.session_factory() as session:
            context = self.numeric_repository.load_verifier_context(
                session, problem_id=problem_id, solution_id=solution_id,
                verifier_version_id=versions.numeric_verifier_version_id,
            )
        report = self.numeric_verifier.verify(context.verification_context)
        with self.session_factory.begin() as session:
            persisted_numeric = self.numeric_repository.persist_report(
                session, context=context, report=report
            )
        steps.append(CandidateValidationStep(
            stage=CandidateValidationStage.NUMERIC_VERIFICATION,
            status=persisted_numeric.status.value,
            evidence_ids=[persisted_numeric.id],
        ))

        with self.session_factory() as session:
            context = self.duplicate_repository.load_detector_context(
                session, problem_id=problem_id, solution_id=solution_id,
                verifier_version_id=versions.duplicate_verifier_version_id,
            )
        report = self.duplicate_detector.detect(context.detection_context)
        with self.session_factory.begin() as session:
            duplicate = self.duplicate_repository.persist_report(
                session, context=context, report=report
            )
        steps.append(CandidateValidationStep(
            stage=CandidateValidationStage.DUPLICATE_DETECTION,
            status=duplicate.status.value,
            evidence_ids=[duplicate.id],
        ))

        with self.session_factory() as session:
            context = self.leakage_repository.load_detector_context(
                session, problem_id=problem_id,
                verifier_version_id=versions.leakage_verifier_version_id,
            )
        report = self.leakage_detector.detect(context.leakage_context)
        with self.session_factory.begin() as session:
            leakage = self.leakage_repository.persist_report(
                session, context=context, report=report
            )
        steps.append(CandidateValidationStep(
            stage=CandidateValidationStage.LEAKAGE_DETECTION,
            status=leakage.status.value,
            evidence_ids=[leakage.id],
        ))
        return steps

    def _finish_with_gate(
        self, problem_id, initial, steps, model_calls, solution_id
    ) -> CandidateValidationResult:
        """中文：处理“finish·with·准入门”相关操作。
        English: Handles the finish with gate operation.
        """
        decision = None
        with self.session_factory.begin() as session:
            problem = session.get(KnowledgeProblem, problem_id)
            gate = self.admission_repository.evaluate_and_persist(
                session,
                problem_id=problem_id,
                expected_status_version=problem.status_version,
                actor_id=f"candidate-validation:{problem.generation_batch_id}",
            )
            final_status = gate.transition.current_status if gate.transition else ProblemContentStatus(problem.content_status)
            steps.append(CandidateValidationStep(
                stage=CandidateValidationStage.ADMISSION,
                status=gate.gate_result.decision.value,
                evidence_ids=[gate.decision_evidence.id],
                detail=gate.gate_result.reason,
            ))
            decision = gate.gate_result.decision.value
        if decision == "approve":
            steps.append(self._sync_approved_problem(problem_id))
            final_status = ProblemContentStatus(self._problem(problem_id).content_status)
        return CandidateValidationResult(
            problem_id=problem_id,
            initial_status=ProblemContentStatus(initial.content_status),
            final_status=final_status,
            solution_id=solution_id,
            steps=steps,
            model_calls=model_calls,
        )

    def _sync_approved_problem(self, problem_id: str) -> CandidateValidationStep:
        """中文：处理“同步·approved·题目”相关操作。
        English: Handles the sync approved problem operation.
        """
        if not settings.embedding_base_url.strip() or not settings.embedding_model.strip():
            return CandidateValidationStep(
                stage=CandidateValidationStage.INDEX_SYNC,
                status="not_configured",
                detail="内容已批准；Embedding Provider 未配置，尚未进入生产索引。",
            )
        service: ProductionIndexService | None = None
        try:
            service = ProductionIndexService(
                settings, session_factory=self.session_factory
            )
            projection_count = service.sync_problem(problem_id)
            return CandidateValidationStep(
                stage=CandidateValidationStage.INDEX_SYNC,
                status="passed",
                detail=f"关键词索引与 Qdrant 已激活 {projection_count} 条投影。",
            )
        except Exception as error:
            return CandidateValidationStep(
                stage=CandidateValidationStage.INDEX_SYNC,
                status="failed",
                detail=str(error)[:1000],
            )
        finally:
            if service is not None:
                service.close()

    def _condition_context(self, problem_id, versions):
        """中文：处理“condition·context”相关操作。
        English: Handles the condition context operation.
        """
        with self.session_factory() as session:
            return self.condition_repository.load_agent_context(
                session, problem_id=problem_id,
                model_version_id=versions.model_version_id,
                prompt_version_id=versions.condition_prompt_version_id,
            )

    def _solving_context(self, problem_id, versions):
        """中文：处理“solving·context”相关操作。
        English: Handles the solving context operation.
        """
        with self.session_factory() as session:
            return self.solving_repository.load_agent_context(
                session, problem_id=problem_id,
                model_version_id=versions.model_version_id,
                prompt_version_id=versions.solver_prompt_version_id,
            )

    def _review_context(self, problem_id, solution_id, versions):
        """中文：处理“复核·context”相关操作。
        English: Handles the review context operation.
        """
        with self.session_factory() as session:
            return self.review_repository.load_agent_context(
                session, problem_id=problem_id, solution_id=solution_id,
                model_version_id=versions.model_version_id,
                prompt_version_id=versions.review_prompt_version_id,
            )

    def _model_call(self, provider_id, model_name, operation):
        """中文：处理“模型·call”相关操作。
        English: Handles the model call operation.
        """
        if isinstance(self.provider, RoutingLLMProvider):
            with self.provider.use_provider_model(provider_id, model_name):
                return operation()
        return operation()

    def _problem(self, problem_id: str) -> KnowledgeProblem:
        """中文：处理“题目”相关操作。
        English: Handles the problem operation.
        """
        with self.session_factory() as session:
            problem = session.get(KnowledgeProblem, problem_id)
            if problem is None:
                raise LookupError("candidate problem not found")
            session.expunge(problem)
            return problem


candidate_validation_service = CandidateValidationService()
