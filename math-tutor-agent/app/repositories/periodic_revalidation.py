from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.periodic_revalidation import (
    RevalidationItemView,
    RevalidationPolicyInput,
    RevalidationPolicyView,
    RevalidationRunView,
)
from app.models.generation import ModelVersion, PromptVersion, VerifierVersion
from app.models.knowledge import KnowledgeProblem
from app.models.revalidation import (
    ContentRevalidationItem,
    ContentRevalidationPolicy,
    ContentRevalidationRun,
)


class PeriodicRevalidationReferenceInvalid(ValueError):
    pass


class PeriodicRevalidationRepository:
    PROMPT_PURPOSES = {
        "condition_prompt_version_id": "problem_condition_check",
        "solver_prompt_version_id": "independent_problem_solving",
        "review_prompt_version_id": "independent_pedagogical_review",
    }
    VERIFIER_KEYS = {
        "sympy_verifier_version_id": "quadratic_sympy",
        "numeric_verifier_version_id": "quadratic_numeric",
        "duplicate_verifier_version_id": "four_layer_duplicate",
        "leakage_verifier_version_id": "evaluation_leakage",
    }

    def upsert_policy(
        self, session: Session, request: RevalidationPolicyInput
    ) -> ContentRevalidationPolicy:
        self._validate_versions(session, request)
        policy = session.scalar(select(ContentRevalidationPolicy).where(
            ContentRevalidationPolicy.policy_key == request.policy_key
        ))
        values = request.model_dump(exclude={"config"})
        if policy is None:
            policy = ContentRevalidationPolicy(**values, config_json=request.config)
            session.add(policy)
        else:
            for key, value in values.items():
                setattr(policy, key, value)
            policy.config_json = request.config
        session.flush()
        return policy

    def due_policies(
        self, session: Session, now: datetime, policy_key: str | None = None
    ) -> list[ContentRevalidationPolicy]:
        filters = [ContentRevalidationPolicy.enabled.is_(True)]
        if policy_key:
            filters.append(ContentRevalidationPolicy.policy_key == policy_key)
        else:
            filters.append(ContentRevalidationPolicy.next_run_at <= now)
        return list(session.scalars(
            select(ContentRevalidationPolicy)
            .where(*filters)
            .order_by(ContentRevalidationPolicy.next_run_at, ContentRevalidationPolicy.id)
            .with_for_update(skip_locked=True)
        ))

    def create_run(
        self,
        session: Session,
        policy: ContentRevalidationPolicy,
        *,
        trigger_type: str,
        scheduled_for: datetime,
    ) -> ContentRevalidationRun:
        run_key = f"{policy.policy_key}:{trigger_type}:{scheduled_for.isoformat()}"
        existing = session.scalar(select(ContentRevalidationRun).where(
            ContentRevalidationRun.run_key == run_key
        ))
        if existing is not None:
            return existing
        run = ContentRevalidationRun(
            policy_id=policy.id,
            run_key=run_key,
            trigger_type=trigger_type,
            status="pending",
            scheduled_for=scheduled_for,
        )
        session.add(run)
        session.flush()
        candidates = self._candidates(session, policy, scheduled_for)
        for problem in candidates:
            session.add(ContentRevalidationItem(
                run_id=run.id,
                problem_id=problem.id,
                problem_content_hash=problem.content_hash,
                status="queued",
            ))
        run.selected_count = len(candidates)
        policy.last_run_at = scheduled_for
        policy.next_run_at = scheduled_for + timedelta(hours=policy.cadence_hours)
        session.flush()
        return run

    def get_run(self, session: Session, run_id: str) -> ContentRevalidationRun | None:
        return session.get(ContentRevalidationRun, run_id)

    def run_items(self, session: Session, run_id: str) -> list[ContentRevalidationItem]:
        return list(session.scalars(
            select(ContentRevalidationItem)
            .where(ContentRevalidationItem.run_id == run_id)
            .order_by(ContentRevalidationItem.created_at, ContentRevalidationItem.id)
        ))

    def policy(self, session: Session, policy_id: str) -> ContentRevalidationPolicy:
        policy = session.get(ContentRevalidationPolicy, policy_id)
        if policy is None:
            raise PeriodicRevalidationReferenceInvalid("revalidation policy not found")
        return policy

    def view_policy(self, item: ContentRevalidationPolicy) -> RevalidationPolicyView:
        return RevalidationPolicyView(
            id=item.id,
            policy_key=item.policy_key,
            enabled=item.enabled,
            cadence_hours=item.cadence_hours,
            max_items_per_run=item.max_items_per_run,
            subject=item.subject,
            topic_code=item.topic_code,
            problem_type=item.problem_type,
            execution_model_version_id=item.execution_model_version_id,
            review_model_version_id=item.review_model_version_id,
            condition_prompt_version_id=item.condition_prompt_version_id,
            solver_prompt_version_id=item.solver_prompt_version_id,
            review_prompt_version_id=item.review_prompt_version_id,
            sympy_verifier_version_id=item.sympy_verifier_version_id,
            numeric_verifier_version_id=item.numeric_verifier_version_id,
            duplicate_verifier_version_id=item.duplicate_verifier_version_id,
            leakage_verifier_version_id=item.leakage_verifier_version_id,
            next_run_at=item.next_run_at,
            last_run_at=item.last_run_at,
            config=item.config_json,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def view_run(
        self, run: ContentRevalidationRun, items: list[ContentRevalidationItem]
    ) -> RevalidationRunView:
        return RevalidationRunView(
            id=run.id,
            policy_id=run.policy_id,
            run_key=run.run_key,
            trigger_type=run.trigger_type,
            status=run.status,
            scheduled_for=run.scheduled_for,
            started_at=run.started_at,
            finished_at=run.finished_at,
            selected_count=run.selected_count,
            passed_count=run.passed_count,
            failed_count=run.failed_count,
            inconclusive_count=run.inconclusive_count,
            last_error_code=run.last_error_code,
            summary=run.summary_json,
            items=[RevalidationItemView(
                id=item.id,
                run_id=item.run_id,
                problem_id=item.problem_id,
                solution_id=item.solution_id,
                maintenance_job_id=item.maintenance_job_id,
                problem_content_hash=item.problem_content_hash,
                solution_content_hash=item.solution_content_hash,
                status=item.status,
                outcome=item.outcome,
                tool_evidence_ids=item.tool_evidence_ids_json,
                condition_evidence_id=item.condition_evidence_id,
                solution_independence_evidence_id=item.solution_independence_evidence_id,
                ai_review_evidence_id=item.ai_review_evidence_id,
                admission_evidence_id=item.admission_evidence_id,
                error_code=item.error_code,
                error_detail=item.error_detail,
                started_at=item.started_at,
                finished_at=item.finished_at,
            ) for item in items],
        )

    def _candidates(
        self,
        session: Session,
        policy: ContentRevalidationPolicy,
        now: datetime,
    ) -> list[KnowledgeProblem]:
        active_problem_ids = select(ContentRevalidationItem.problem_id).where(
            ContentRevalidationItem.status.not_in(["passed", "failed", "inconclusive"])
        )
        filters = [
            KnowledgeProblem.content_status.in_(["approved", "indexed"]),
            KnowledgeProblem.subject == policy.subject,
            KnowledgeProblem.id.not_in(active_problem_ids),
        ]
        if policy.topic_code:
            filters.append(
                func.json_contains(
                    KnowledgeProblem.knowledge_point_codes_json,
                    json.dumps(policy.topic_code),
                ) == 1
            )
        if policy.problem_type:
            filters.append(KnowledgeProblem.problem_type == policy.problem_type)
        candidates = list(session.scalars(
            select(KnowledgeProblem)
            .where(*filters)
            .order_by(KnowledgeProblem.status_changed_at, KnowledgeProblem.id)
            .limit(policy.max_items_per_run * 4)
        ))
        cutoff = now - timedelta(hours=policy.cadence_hours)
        selected: list[KnowledgeProblem] = []
        for problem in candidates:
            raw = (problem.metadata_json or {}).get("last_periodic_revalidation_at")
            if isinstance(raw, str):
                try:
                    last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if last.tzinfo is not None:
                        last = last.astimezone(timezone.utc).replace(tzinfo=None)
                    if last > cutoff:
                        continue
                except ValueError:
                    pass
            selected.append(problem)
            if len(selected) >= policy.max_items_per_run:
                break
        return selected

    def _validate_versions(self, session: Session, request: RevalidationPolicyInput) -> None:
        for field in ("execution_model_version_id", "review_model_version_id"):
            value = getattr(request, field)
            entity = session.get(ModelVersion, value)
            if entity is None or not entity.active:
                raise PeriodicRevalidationReferenceInvalid(f"active {field} is required")
        for field, purpose in self.PROMPT_PURPOSES.items():
            entity = session.get(PromptVersion, getattr(request, field))
            if entity is None or not entity.active or entity.purpose != purpose:
                raise PeriodicRevalidationReferenceInvalid(
                    f"active {purpose} prompt is required for {field}"
                )
        for field, key in self.VERIFIER_KEYS.items():
            entity = session.get(VerifierVersion, getattr(request, field))
            if entity is None or not entity.active or entity.verifier_key != key:
                raise PeriodicRevalidationReferenceInvalid(
                    f"active {key} verifier is required for {field}"
                )
