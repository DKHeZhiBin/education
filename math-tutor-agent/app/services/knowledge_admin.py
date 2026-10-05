from __future__ import annotations

from app.domain.auth import AuthenticatedUser
from app.domain.knowledge import ProblemContentStatus
from app.domain.knowledge_admin import (
    PersistedProblemTransition,
    ProblemAdminDetail,
    ProblemAdminPage,
    ProblemStatusChangeRequest,
    ProblemStatusCount,
)
from app.domain.teaching_content import (
    ErrorPatternLinkView,
    HintBlueprintUpsert,
    HintBlueprintView,
    ProblemErrorPatternUpsert,
    ProblemTeachingMap,
    SolutionStepView,
)
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.teaching_content import TeachingContentRepository


class KnowledgeAdminService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        teaching_repository: TeachingContentRepository | None = None,
    ) -> None:
        self.repository = repository
        self.teaching_repository = teaching_repository or TeachingContentRepository(
            repository.session_factory
        )

    def status_summary(self) -> list[ProblemStatusCount]:
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
        return self.repository.get_problem(problem_id)

    def transition_problem(
        self,
        problem_id: str,
        payload: ProblemStatusChangeRequest,
        actor: AuthenticatedUser,
    ) -> PersistedProblemTransition:
        return self.repository.transition_problem(
            problem_id=problem_id,
            target_status=payload.target_status,
            expected_status_version=payload.expected_status_version,
            actor_type="admin",
            actor_id=actor.id,
            reason=payload.reason,
            index_is_active=payload.index_is_active,
        )

    def sync_solution_steps(
        self,
        problem_id: str,
        solution_id: str,
    ) -> list[SolutionStepView]:
        return self.teaching_repository.sync_steps(problem_id, solution_id)

    def upsert_error_pattern_link(
        self,
        problem_id: str,
        payload: ProblemErrorPatternUpsert,
    ) -> ErrorPatternLinkView:
        return self.teaching_repository.upsert_error_pattern_link(problem_id, payload)

    def upsert_hint(
        self,
        problem_id: str,
        payload: HintBlueprintUpsert,
    ) -> HintBlueprintView:
        return self.teaching_repository.upsert_hint(problem_id, payload)

    def get_problem_teaching_map(self, problem_id: str) -> ProblemTeachingMap:
        return self.teaching_repository.get_problem_teaching_map(problem_id)


knowledge_admin_service = KnowledgeAdminService(KnowledgeRepository())
