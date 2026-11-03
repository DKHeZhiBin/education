from __future__ import annotations

from app.domain.auth import AuthenticatedUser
from app.domain.knowledge import ProblemContentStatus
from app.domain.knowledge_admin import (
    PersistedProblemTransition,
    ProblemAdminDetail,
    ProblemAdminPage,
    ProblemStatusChangeRequest,
    ProblemStatusCount,
    ProblemRetirementRequest,
    ProblemRetirementResult,
)
from app.domain.index_lifecycle import IndexMaintenanceRequest
from app.domain.teaching_content import (
    ErrorPatternLinkView,
    HintBlueprintUpsert,
    HintBlueprintView,
    ProblemErrorPatternUpsert,
    ProblemTeachingMap,
    SolutionStepView,
)
from app.repositories.knowledge import KnowledgeProblemNotFound, KnowledgeRepository
from app.repositories.teaching_content import TeachingContentRepository
from app.search_index.lifecycle_service import SearchIndexLifecycleService


class KnowledgeAdminService:
    """中文：定义“知识·admin·服务”类，封装该职责相关的数据与行为。
    English: Defines the knowledge admin service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(
        self,
        repository: KnowledgeRepository,
        teaching_repository: TeachingContentRepository | None = None,
        lifecycle_service: SearchIndexLifecycleService | None = None,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.repository = repository
        self.teaching_repository = teaching_repository or TeachingContentRepository(
            repository.session_factory
        )
        self.lifecycle_service = lifecycle_service or SearchIndexLifecycleService(
            session_factory=repository.session_factory
        )

    def status_summary(self) -> list[ProblemStatusCount]:
        """中文：处理“状态·summary”相关操作。
        English: Handles the status summary operation.
        """
        return self.repository.status_summary()

    def list_problems(
        self,
        *,
        statuses: list[ProblemContentStatus] | None = None,
        subject: str | None = None,
        grade_band: str | None = None,
        grade_code: str | None = None,
        problem_type: str | None = None,
        content_type: str | None = None,
        curriculum_version_id: str | None = None,
        knowledge_point_code: str | None = None,
        difficulty_source: str | None = None,
        generation_batch_id: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ProblemAdminPage:
        """中文：处理“列出·problems”相关操作。
        English: Handles the list problems operation.
        """
        return self.repository.list_problems(
            statuses=statuses,
            subject=subject,
            grade_band=grade_band,
            grade_code=grade_code,
            problem_type=problem_type,
            content_type=content_type,
            curriculum_version_id=curriculum_version_id,
            knowledge_point_code=knowledge_point_code,
            difficulty_source=difficulty_source,
            generation_batch_id=generation_batch_id,
            search=search,
            limit=limit,
            offset=offset,
        )

    def get_problem(self, problem_id: str) -> ProblemAdminDetail | None:
        """中文：处理“获取·题目”相关操作。
        English: Handles the get problem operation.
        """
        return self.repository.get_problem(problem_id)

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.lifecycle_service.close()

    def transition_problem(
        self,
        problem_id: str,
        payload: ProblemStatusChangeRequest,
        actor: AuthenticatedUser,
    ) -> PersistedProblemTransition:
        """中文：处理“transition·题目”相关操作。
        English: Handles the transition problem operation.
        """
        return self.repository.transition_problem(
            problem_id=problem_id,
            target_status=payload.target_status,
            expected_status_version=payload.expected_status_version,
            actor_type="admin",
            actor_id=actor.id,
            reason=payload.reason,
            index_is_active=payload.index_is_active,
        )

    def retire_problem(
        self,
        problem_id: str,
        payload: ProblemRetirementRequest,
        actor: AuthenticatedUser,
    ) -> ProblemRetirementResult:
        """中文：处理“退役·题目”相关操作。
        English: Handles the retire problem operation.
        """
        before = self.repository.get_problem(problem_id)
        if before is None:
            raise KnowledgeProblemNotFound(problem_id)
        job = self.lifecycle_service.enqueue(IndexMaintenanceRequest(
            problem_id=problem_id,
            trigger_type="retired",
            reason=payload.reason,
            expected_status_version=payload.expected_status_version,
        ))
        completed = self.lifecycle_service.run_job(job.id, actor_id=actor.id)
        if completed.status != "completed":
            raise ProblemRetirementFailed(completed)
        after = self.repository.get_problem(problem_id)
        if after is None or after.content_status != ProblemContentStatus.RETIRED:
            raise ProblemRetirementFailed(completed)
        knowledge_version = self.lifecycle_service.cache_version.current()
        return ProblemRetirementResult(
            problem_id=problem_id,
            previous_status=before.content_status,
            current_status=ProblemContentStatus.RETIRED,
            status_version=after.status_version,
            maintenance_job=completed,
            knowledge_version=knowledge_version,
        )

    def sync_solution_steps(
        self,
        problem_id: str,
        solution_id: str,
    ) -> list[SolutionStepView]:
        """中文：处理“同步·解答·steps”相关操作。
        English: Handles the sync solution steps operation.
        """
        return self.teaching_repository.sync_steps(problem_id, solution_id)

    def upsert_error_pattern_link(
        self,
        problem_id: str,
        payload: ProblemErrorPatternUpsert,
    ) -> ErrorPatternLinkView:
        """中文：处理“upsert·error·pattern·link”相关操作。
        English: Handles the upsert error pattern link operation.
        """
        return self.teaching_repository.upsert_error_pattern_link(problem_id, payload)

    def upsert_hint(
        self,
        problem_id: str,
        payload: HintBlueprintUpsert,
    ) -> HintBlueprintView:
        """中文：处理“upsert·提示”相关操作。
        English: Handles the upsert hint operation.
        """
        return self.teaching_repository.upsert_hint(problem_id, payload)

    def get_problem_teaching_map(self, problem_id: str) -> ProblemTeachingMap:
        """中文：处理“获取·题目·教学·map”相关操作。
        English: Handles the get problem teaching map operation.
        """
        return self.teaching_repository.get_problem_teaching_map(problem_id)


knowledge_admin_service = KnowledgeAdminService(KnowledgeRepository())


class ProblemRetirementFailed(RuntimeError):
    """中文：定义“题目·retirement·failed”类，封装该职责相关的数据与行为。
    English: Defines the problem retirement failed class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, job) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.job = job
        super().__init__(f"problem retirement job ended with status {job.status}")
