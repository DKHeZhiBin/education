from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.human_review import (
    HumanReviewQueueRequest,
    HumanReviewQueueResult,
    HumanReviewSubmission,
    HumanReviewTaskPage,
    HumanReviewTaskView,
)
from app.domain.knowledge import ProblemContentStatus
from app.domain.problem_lifecycle import ProblemContentStateMachine, ProblemTransitionRequest
from app.models.generation import AdmissionEvidence
from app.models.human_review import HumanContentReview, HumanReviewTask
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution, ProblemStatusTransition
from app.repositories.admission_gate import AdmissionGateRepository


class HumanReviewConflict(RuntimeError):
    """中文：定义“human·复核·conflict”类，封装该职责相关的数据与行为。
    English: Defines the human review conflict class and encapsulates data and behavior for that responsibility.
    """
    pass


class HumanReviewNotFound(LookupError):
    """中文：定义“human·复核·not·found”类，封装该职责相关的数据与行为。
    English: Defines the human review not found class and encapsulates data and behavior for that responsibility.
    """
    pass


class HumanReviewStale(HumanReviewConflict):
    """中文：定义“human·复核·stale”类，封装该职责相关的数据与行为。
    English: Defines the human review stale class and encapsulates data and behavior for that responsibility.
    """
    pass


class HumanReviewRepository:
    """中文：定义“human·复核·仓储”类，封装该职责相关的数据与行为。
    English: Defines the human review repository class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.session_factory = session_factory
        self.state_machine = ProblemContentStateMachine()
        self.admission_repository = AdmissionGateRepository(state_machine=self.state_machine)

    def enqueue(
        self, request: HumanReviewQueueRequest, *, actor_id: str
    ) -> HumanReviewQueueResult:
        """中文：处理“enqueue”相关操作。
        English: Handles the enqueue operation.
        """
        with self.session_factory.begin() as session:
            filters = []
            if request.problem_ids:
                filters.append(KnowledgeProblem.id.in_(request.problem_ids))
            eligibility = []
            if request.include_quarantined:
                eligibility.append(KnowledgeProblem.content_status == "quarantined")
            if request.include_high_value:
                eligibility.extend([
                    KnowledgeProblem.difficulty >= request.minimum_difficulty,
                    func.json_unquote(
                        func.json_extract(KnowledgeProblem.metadata_json, "$.high_value")
                    ) == "true",
                    func.json_unquote(
                        func.json_extract(KnowledgeProblem.metadata_json, "$.trusted_mother")
                    ) == "true",
                ])
            if not eligibility:
                return HumanReviewQueueResult(selected_count=0, created_count=0)
            filters.append(or_(*eligibility))
            problems = list(session.scalars(
                select(KnowledgeProblem)
                .where(
                    *filters,
                    KnowledgeProblem.content_status.in_([
                        "quarantined", "approved", "indexed",
                    ]),
                )
                .order_by(KnowledgeProblem.difficulty.desc(), KnowledgeProblem.updated_at)
                .limit(request.limit)
                .with_for_update(skip_locked=True)
            ))
            created_ids: list[str] = []
            for problem in problems:
                existing = session.scalar(select(HumanReviewTask.id).where(
                    HumanReviewTask.problem_id == problem.id,
                    HumanReviewTask.problem_content_hash == problem.content_hash,
                    HumanReviewTask.status.in_(["queued", "claimed"]),
                ))
                if existing:
                    continue
                solution = self._preferred_solution(session, problem.id)
                factors, score = self._value(problem)
                reason = (
                    "manual"
                    if request.problem_ids
                    else (
                        "quarantined"
                        if problem.content_status == "quarantined"
                        else "high_value"
                    )
                )
                task = HumanReviewTask(
                    problem_id=problem.id,
                    solution_id=solution.id if solution else None,
                    problem_content_hash=problem.content_hash,
                    solution_content_hash=solution.content_hash if solution else None,
                    problem_status_version=problem.status_version,
                    selection_reason=reason,
                    priority=request.priority,
                    value_score=score,
                    value_factors_json=factors,
                    review_requirements_json=request.review_requirements,
                    created_by_user_id=actor_id,
                )
                session.add(task)
                session.flush()
                created_ids.append(task.id)
            return HumanReviewQueueResult(
                selected_count=len(problems),
                created_count=len(created_ids),
                task_ids=created_ids,
            )

    def list_tasks(
        self, *, statuses: list[str] | None, assignee_id: str | None, limit: int, offset: int
    ) -> HumanReviewTaskPage:
        """中文：处理“列出·tasks”相关操作。
        English: Handles the list tasks operation.
        """
        with self.session_factory() as session:
            filters = []
            if statuses:
                filters.append(HumanReviewTask.status.in_(statuses))
            if assignee_id:
                filters.append(HumanReviewTask.assigned_to_user_id == assignee_id)
            total = session.scalar(select(func.count(HumanReviewTask.id)).where(*filters)) or 0
            rows = list(session.scalars(
                select(HumanReviewTask)
                .where(*filters)
                .order_by(HumanReviewTask.priority.desc(), HumanReviewTask.created_at)
                .limit(limit).offset(offset)
            ))
            return HumanReviewTaskPage(
                items=[self._view(session, row) for row in rows],
                total=total, limit=limit, offset=offset,
            )

    def claim(self, task_id: str, *, reviewer_id: str, expected_version: int) -> HumanReviewTaskView:
        """中文：处理“claim”相关操作。
        English: Handles the claim operation.
        """
        with self.session_factory.begin() as session:
            task = self._locked_task(session, task_id)
            if task.version != expected_version:
                raise HumanReviewConflict("review task version conflict")
            if task.status == "claimed" and task.assigned_to_user_id == reviewer_id:
                return self._view(session, task)
            if task.status != "queued":
                raise HumanReviewConflict("review task is not claimable")
            self._ensure_snapshot(session, task)
            task.status = "claimed"
            task.assigned_to_user_id = reviewer_id
            task.claimed_at = self._now()
            task.version += 1
            session.flush()
            return self._view(session, task)

    def submit(
        self, task_id: str, *, reviewer_id: str, request: HumanReviewSubmission
    ) -> tuple[str, HumanReviewTaskView, str]:
        """中文：处理“submit”相关操作。
        English: Handles the submit operation.
        """
        with self.session_factory.begin() as session:
            task = self._locked_task(session, task_id)
            if task.version != request.expected_version:
                raise HumanReviewConflict("review task version conflict")
            if task.status != "claimed" or task.assigned_to_user_id != reviewer_id:
                raise HumanReviewConflict("review task is not assigned to this reviewer")
            problem, solution = self._ensure_snapshot(session, task)
            if request.decision == "approve" and solution is None:
                raise HumanReviewConflict("approval requires a versioned solution snapshot")
            submitted_at = self._now()
            review = HumanContentReview(
                task_id=task.id,
                problem_id=problem.id,
                solution_id=solution.id if solution else None,
                reviewer_user_id=reviewer_id,
                problem_content_hash=problem.content_hash,
                solution_content_hash=solution.content_hash if solution else None,
                decision=request.decision,
                coverage_level=request.coverage_level,
                checklist_json=request.checklist,
                issues_json=request.issues,
                summary=request.summary.strip(),
                submitted_at=submitted_at,
            )
            session.add(review)
            session.flush()
            evidence = self._create_evidence(
                session, problem, solution, review, request, submitted_at
            )
            review.evidence_id = evidence.id
            task.status = "completed"
            task.completed_at = submitted_at
            task.version += 1
            problem.review_status = (
                "human_passed"
                if request.decision == "approve"
                else "human_attention"
            )
            if request.decision == "approve" and problem.content_status == "quarantined":
                self._return_to_rule_gate(session, problem, reviewer_id)
            session.flush()
            return review.id, self._view(session, task), evidence.id

    def mark_stale(self, task_id: str) -> None:
        """中文：处理“mark·stale”相关操作。
        English: Handles the mark stale operation.
        """
        with self.session_factory.begin() as session:
            task = self._locked_task(session, task_id)
            if task.status not in {"completed", "cancelled", "stale"}:
                task.status = "stale"
                task.version += 1

    @staticmethod
    def _create_evidence(session, problem, solution, review, request, submitted_at):
        """中文：处理“创建·evidence”相关操作。
        English: Handles the create evidence operation.
        """
        if problem.generation_batch_id is None:
            raise HumanReviewConflict("human review evidence requires a generation batch")
        payload = {
            "schema_version": "1.0",
            "review_task_id": review.task_id,
            "review_id": review.id,
            "reviewer_kind": "qualified_human",
            "reviewer_id": review.reviewer_user_id,
            "reviewed_at": submitted_at.isoformat(),
            "problem_content_hash": problem.content_hash,
            "problem_status_version": problem.status_version,
            "solution_content_hash": solution.content_hash if solution else None,
            "decision": request.decision,
            "coverage_level": request.coverage_level,
            "checklist": request.checklist,
            "issues": request.issues,
        }
        digest = HumanReviewRepository._hash(payload)
        evidence = AdmissionEvidence(
            generation_batch_id=problem.generation_batch_id,
            problem_id=problem.id,
            solution_id=solution.id if solution else None,
            evidence_type="qualified_human_review",
            producer_type="system",
            status=("passed" if request.decision == "approve" else
                    "inconclusive" if request.decision == "inconclusive" else "failed"),
            is_blocking=request.decision != "approve",
            summary=request.summary.strip()[:1000],
            payload_json=payload,
            evidence_hash=digest,
        )
        session.add(evidence)
        session.flush()
        return evidence

    def _return_to_rule_gate(self, session, problem, reviewer_id: str) -> None:
        """中文：处理“return·to·rule·准入门”相关操作。
        English: Handles the return to rule gate operation.
        """
        transition = self.state_machine.transition(ProblemTransitionRequest(
            problem_id=problem.id,
            generation_batch_id=problem.generation_batch_id,
            current_status=ProblemContentStatus(problem.content_status),
            target_status=ProblemContentStatus.VALIDATING,
            current_status_reason=problem.status_reason,
            revision_attempts=problem.revision_attempts,
            index_is_active=False,
        ))
        changed_at = self._now()
        next_version = problem.status_version + 1
        session.add(ProblemStatusTransition(
            problem_id=problem.id,
            from_status=transition.previous_status.value,
            to_status=transition.current_status.value,
            reason=None,
            revision_attempts=transition.revision_attempts,
            status_version=next_version,
            checked_requirements_json=[
                "qualified_human_review",
                *transition.checked_requirements,
            ],
            actor_type="system",
            actor_id=reviewer_id,
            created_at=changed_at,
        ))
        problem.content_status = transition.current_status.value
        problem.status_reason = None
        problem.status_version = next_version
        problem.status_changed_at = changed_at
        session.flush()
        self.admission_repository.evaluate_and_persist(
            session,
            problem_id=problem.id,
            expected_status_version=problem.status_version,
            actor_id=f"qualified-human-reviewer:{reviewer_id}",
        )

    def _ensure_snapshot(self, session, task):
        """中文：处理“ensure·snapshot”相关操作。
        English: Handles the ensure snapshot operation.
        """
        problem = session.get(KnowledgeProblem, task.problem_id, with_for_update=True)
        if problem is None:
            raise HumanReviewNotFound("problem not found")
        if problem.content_hash != task.problem_content_hash:
            raise HumanReviewStale("problem changed after review task creation")
        solution = session.get(KnowledgeSolution, task.solution_id) if task.solution_id else None
        if task.solution_id and (
            solution is None or solution.content_hash != task.solution_content_hash
        ):
            raise HumanReviewStale("solution changed after review task creation")
        return problem, solution

    @staticmethod
    def _preferred_solution(session, problem_id):
        """中文：处理“preferred·解答”相关操作。
        English: Handles the preferred solution operation.
        """
        return session.scalar(
            select(KnowledgeSolution).where(KnowledgeSolution.problem_id == problem_id)
            .order_by(KnowledgeSolution.is_preferred.desc(), KnowledgeSolution.updated_at.desc())
            .limit(1)
        )

    @staticmethod
    def _value(problem):
        """中文：处理“value”相关操作。
        English: Handles the value operation.
        """
        factors: list[str] = []
        score = 0
        metadata = problem.metadata_json or {}
        if problem.content_status == "quarantined":
            factors.append("quarantined")
            score += 45
        if problem.difficulty >= 4:
            factors.append("high_difficulty")
            score += 25
        if metadata.get("trusted_mother") is True:
            factors.append("trusted_mother")
            score += 20
        if metadata.get("high_value") is True:
            factors.append("explicit_high_value")
            score += 30
        return factors, min(score, 100)

    @staticmethod
    def _locked_task(session, task_id):
        """中文：处理“locked·task”相关操作。
        English: Handles the locked task operation.
        """
        task = session.scalar(select(HumanReviewTask).where(
            HumanReviewTask.id == task_id
        ).with_for_update())
        if task is None:
            raise HumanReviewNotFound("human review task not found")
        return task

    @staticmethod
    def _view(session, task):
        """中文：处理“view”相关操作。
        English: Handles the view operation.
        """
        problem = session.get(KnowledgeProblem, task.problem_id)
        return HumanReviewTaskView(
            id=task.id, problem_id=task.problem_id, solution_id=task.solution_id,
            statement=problem.statement if problem else "", problem_content_hash=task.problem_content_hash,
            solution_content_hash=task.solution_content_hash,
            problem_status=problem.content_status if problem else "missing",
            problem_status_version=task.problem_status_version,
            selection_reason=task.selection_reason, priority=task.priority,
            value_score=task.value_score, value_factors=task.value_factors_json,
            review_requirements=task.review_requirements_json, status=task.status,
            version=task.version, created_by_user_id=task.created_by_user_id,
            assigned_to_user_id=task.assigned_to_user_id, claimed_at=task.claimed_at,
            completed_at=task.completed_at, created_at=task.created_at, updated_at=task.updated_at,
        )

    @staticmethod
    def _hash(payload):
        """中文：处理“hash”相关操作。
        English: Handles the hash operation.
        """
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _now():
        """中文：处理“now”相关操作。
        English: Handles the now operation.
        """
        return datetime.now(timezone.utc).replace(tzinfo=None)
