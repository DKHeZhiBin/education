from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.domain.generation import (
    AdmissionEvidence as DomainAdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)
from app.domain.index_lifecycle import (
    IndexMaintenanceJobView,
    IndexMaintenanceRequest,
)
from app.domain.knowledge import ProblemContentStatus
from app.domain.problem_lifecycle import (
    ProblemContentStateMachine,
    ProblemTransitionRequest,
)
from app.models.generation import AdmissionEvidence
from app.models.content_issue import ContentIssueReport
from app.models.knowledge import KnowledgeProblem, ProblemStatusTransition
from app.models.search_index import (
    KnowledgeSearchDocument,
    SearchIndexMaintenanceJob,
)


class SearchIndexLifecycleRepository:
    def __init__(self) -> None:
        self.state_machine = ProblemContentStateMachine()

    @staticmethod
    def enqueue(
        session: Session,
        request: IndexMaintenanceRequest,
        *,
        index_version: str,
    ) -> SearchIndexMaintenanceJob:
        problem = session.get(
            KnowledgeProblem,
            request.problem_id,
            with_for_update=True,
        )
        if problem is None:
            raise LookupError("problem not found")
        if problem.content_status not in {"approved", "indexed"}:
            raise ValueError(
                "index maintenance source must be approved or indexed"
            )
        replacement = None
        if request.replacement_problem_id:
            replacement = session.get(KnowledgeProblem, request.replacement_problem_id)
            if replacement is None:
                raise LookupError("replacement problem not found")
        action = "remove" if request.trigger_type == "retired" else "rebuild"
        identity = {
            "problem_id": problem.id,
            "replacement_problem_id": request.replacement_problem_id,
            "trigger_type": request.trigger_type,
            "content_hash": problem.content_hash,
            "problem_status_version": problem.status_version,
            "replacement_content_hash": (
                replacement.content_hash if replacement else None
            ),
            "index_version": index_version,
        }
        identity_json = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        idempotency_hash = sha256(identity_json.encode("utf-8")).hexdigest()
        existing = session.scalar(select(SearchIndexMaintenanceJob).where(
            SearchIndexMaintenanceJob.idempotency_key_hash == idempotency_hash
        ))
        if existing is not None:
            return existing

        rows = list(session.scalars(
            select(KnowledgeSearchDocument)
            .where(
                KnowledgeSearchDocument.problem_id == problem.id,
                KnowledgeSearchDocument.index_status != "retired",
            )
            .with_for_update()
        ))
        point_ids = sorted({row.point_id for row in rows})
        for row in rows:
            payload = dict(row.payload_json)
            payload["index_status"] = "retired"
            row.payload_json = payload
            row.index_status = "retired"

        job = SearchIndexMaintenanceJob(
            problem_id=problem.id,
            replacement_problem_id=request.replacement_problem_id,
            action=action,
            trigger_type=request.trigger_type,
            reason=request.reason,
            expected_content_hash=problem.content_hash,
            target_index_version=index_version,
            point_ids_json=point_ids,
            idempotency_key_hash=idempotency_hash,
            status="pending",
            attempt_count=0,
        )
        session.add(job)
        session.flush()
        return job

    @staticmethod
    def work_ids(
        session: Session,
        *,
        limit: int,
        max_attempts: int,
        recovery_before: datetime,
    ) -> list[str]:
        return list(session.scalars(
            select(SearchIndexMaintenanceJob.id)
            .where(
                or_(
                    SearchIndexMaintenanceJob.status == "waiting_for_approval",
                    and_(
                        SearchIndexMaintenanceJob.status.in_([
                            "deleting",
                            "rebuilding",
                        ]),
                        SearchIndexMaintenanceJob.updated_at < recovery_before,
                    ),
                    and_(
                        SearchIndexMaintenanceJob.status.in_([
                            "pending",
                            "failed",
                        ]),
                        SearchIndexMaintenanceJob.attempt_count < max_attempts,
                    ),
                ),
            )
            .order_by(
                SearchIndexMaintenanceJob.created_at,
                SearchIndexMaintenanceJob.id,
            )
            .limit(limit)
        ))

    @staticmethod
    def start_deletion(
        session: Session,
        job_id: str,
        *,
        recovery_before: datetime,
    ) -> tuple[bool, list[str] | None]:
        job = session.get(
            SearchIndexMaintenanceJob,
            job_id,
            with_for_update=True,
        )
        if job is None:
            raise LookupError("index maintenance job not found")
        if job.deletion_completed_at is not None:
            return True, None
        if job.status == "deleting" and job.updated_at >= recovery_before:
            return False, None
        job.status = "deleting"
        job.attempt_count += 1
        job.last_error_code = None
        return True, list(job.point_ids_json)

    def finish_deletion(self, session: Session, job_id: str) -> str:
        job = session.get(
            SearchIndexMaintenanceJob,
            job_id,
            with_for_update=True,
        )
        if job is None:
            raise LookupError("index maintenance job not found")
        problem = session.get(KnowledgeProblem, job.problem_id, with_for_update=True)
        if problem is None:
            raise LookupError("maintenance source problem not found")
        removed_at = self._now()
        self._removal_evidence(
            session,
            problem=problem,
            job=job,
            removed_at=removed_at,
        )
        if problem.content_status in {"approved", "indexed"}:
            target = (
                ProblemContentStatus.QUARANTINED
                if job.trigger_type == "revalidation"
                else ProblemContentStatus.RETIRED
            )
            evidence_items = self._problem_evidence(session, problem.id)
            transition = self.state_machine.transition(ProblemTransitionRequest(
                problem_id=problem.id,
                generation_batch_id=problem.generation_batch_id,
                current_status=ProblemContentStatus(problem.content_status),
                target_status=target,
                current_status_reason=problem.status_reason,
                reason=job.reason,
                revision_attempts=problem.revision_attempts,
                index_is_active=False,
                evidence=evidence_items,
            ))
            self._persist_transition(session, problem, transition)
            if job.trigger_type == "revalidation":
                validating = self.state_machine.transition(ProblemTransitionRequest(
                    problem_id=problem.id,
                    generation_batch_id=problem.generation_batch_id,
                    current_status=ProblemContentStatus(problem.content_status),
                    target_status=ProblemContentStatus.VALIDATING,
                    current_status_reason=problem.status_reason,
                    revision_attempts=problem.revision_attempts,
                    index_is_active=False,
                    evidence=evidence_items,
                ))
                self._persist_transition(session, problem, validating)
                metadata = dict(problem.metadata_json or {})
                metadata["revalidation_started_status_version"] = problem.status_version
                metadata["revalidation_maintenance_job_id"] = job.id
                metadata["revalidation_reason"] = job.reason
                problem.metadata_json = metadata
        job.deletion_completed_at = removed_at
        job.last_error_code = None
        job.status = "completed" if job.action == "remove" else "waiting_for_approval"
        return job.status

    @staticmethod
    def prepare_rebuild(
        session: Session,
        job_id: str,
        *,
        recovery_before: datetime,
    ) -> tuple[bool, str | None]:
        job = session.get(
            SearchIndexMaintenanceJob,
            job_id,
            with_for_update=True,
        )
        if job is None:
            raise LookupError("index maintenance job not found")
        if job.action != "rebuild" or job.deletion_completed_at is None:
            return True, None
        if job.status == "rebuilding" and job.updated_at >= recovery_before:
            return False, None
        target_id = job.replacement_problem_id or job.problem_id
        target = session.get(KnowledgeProblem, target_id)
        if target is None:
            raise LookupError("rebuild target problem not found")
        if target.content_status == "indexed":
            job.status = "completed"
            job.rebuild_completed_at = SearchIndexLifecycleRepository._now()
            job.last_error_code = None
            SearchIndexLifecycleRepository._resolve_content_issues(session, job.id)
            return True, None
        if target.content_status != "approved":
            job.status = "waiting_for_approval"
            job.last_error_code = None
            return True, None
        job.status = "rebuilding"
        job.attempt_count += 1
        job.last_error_code = None
        return True, target.id

    @staticmethod
    def finish_rebuild(session: Session, job_id: str) -> None:
        job = session.get(
            SearchIndexMaintenanceJob,
            job_id,
            with_for_update=True,
        )
        if job is None:
            raise LookupError("index maintenance job not found")
        job.status = "completed"
        job.rebuild_completed_at = SearchIndexLifecycleRepository._now()
        job.last_error_code = None
        SearchIndexLifecycleRepository._resolve_content_issues(session, job.id)

    @staticmethod
    def _resolve_content_issues(session: Session, job_id: str) -> None:
        reports = session.scalars(
            select(ContentIssueReport)
            .where(
                ContentIssueReport.maintenance_job_id == job_id,
                ContentIssueReport.status.not_in(["dismissed", "resolved"]),
            )
            .with_for_update()
        ).all()
        for report in reports:
            report.status = "resolved"

    @staticmethod
    def mark_failed(session: Session, job_id: str, error_code: str) -> None:
        job = session.get(
            SearchIndexMaintenanceJob,
            job_id,
            with_for_update=True,
        )
        if job is None:
            return
        job.status = "failed"
        job.last_error_code = error_code[:100]

    @staticmethod
    def get(session: Session, job_id: str) -> SearchIndexMaintenanceJob | None:
        return session.get(SearchIndexMaintenanceJob, job_id)

    @staticmethod
    def view(job: SearchIndexMaintenanceJob) -> IndexMaintenanceJobView:
        return IndexMaintenanceJobView(
            id=job.id,
            problem_id=job.problem_id,
            replacement_problem_id=job.replacement_problem_id,
            action=job.action,
            trigger_type=job.trigger_type,
            reason=job.reason,
            expected_content_hash=job.expected_content_hash,
            target_index_version=job.target_index_version,
            point_ids=job.point_ids_json,
            status=job.status,
            attempt_count=job.attempt_count,
            last_error_code=job.last_error_code,
            deletion_completed_at=job.deletion_completed_at,
            rebuild_completed_at=job.rebuild_completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _removal_evidence(
        session: Session,
        *,
        problem: KnowledgeProblem,
        job: SearchIndexMaintenanceJob,
        removed_at: datetime,
    ) -> DomainAdmissionEvidence:
        if problem.generation_batch_id is None:
            raise RuntimeError("indexed problem is missing generation_batch_id")
        payload = {
            "maintenance_job_id": job.id,
            "trigger_type": job.trigger_type,
            "point_ids": sorted(job.point_ids_json),
            "expected_content_hash": job.expected_content_hash,
            "target_index_version": job.target_index_version,
            "removed_at": removed_at.isoformat(),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        evidence_hash = sha256(serialized.encode("utf-8")).hexdigest()
        entity = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "index_removal",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if entity is None:
            entity = AdmissionEvidence(
                generation_batch_id=problem.generation_batch_id,
                problem_id=problem.id,
                solution_id=None,
                evidence_type="index_removal",
                producer_type="system",
                status="passed",
                is_blocking=False,
                summary="production keyword and vector indexes removed",
                payload_json=payload,
                evidence_hash=evidence_hash,
                created_at=removed_at,
            )
            session.add(entity)
            session.flush()
        return SearchIndexLifecycleRepository._domain_evidence(entity)

    @staticmethod
    def _problem_evidence(
        session: Session,
        problem_id: str,
    ) -> list[DomainAdmissionEvidence]:
        entities = session.scalars(
            select(AdmissionEvidence)
            .where(AdmissionEvidence.problem_id == problem_id)
            .order_by(AdmissionEvidence.created_at, AdmissionEvidence.id)
        ).all()
        return [SearchIndexLifecycleRepository._domain_evidence(item) for item in entities]

    @staticmethod
    def _domain_evidence(entity: AdmissionEvidence) -> DomainAdmissionEvidence:
        created_at = entity.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return DomainAdmissionEvidence(
            id=entity.id,
            generation_batch_id=entity.generation_batch_id,
            problem_id=entity.problem_id,
            solution_id=entity.solution_id,
            evidence_type=entity.evidence_type,
            producer_type=EvidenceProducerType(entity.producer_type),
            status=AdmissionEvidenceStatus(entity.status),
            model_version_id=entity.model_version_id,
            prompt_version_id=entity.prompt_version_id,
            verifier_version_id=entity.verifier_version_id,
            is_blocking=entity.is_blocking,
            summary=entity.summary,
            payload=entity.payload_json,
            evidence_hash=entity.evidence_hash,
            created_at=created_at,
        )

    @staticmethod
    def _persist_transition(session: Session, problem: KnowledgeProblem, transition) -> None:
        changed_at = SearchIndexLifecycleRepository._now()
        next_version = problem.status_version + 1
        session.add(ProblemStatusTransition(
            problem_id=problem.id,
            from_status=transition.previous_status.value,
            to_status=transition.current_status.value,
            reason=transition.status_reason,
            revision_attempts=transition.revision_attempts,
            status_version=next_version,
            checked_requirements_json=[
                "search_index_maintenance",
                *transition.checked_requirements,
            ],
            actor_type="system",
            actor_id=None,
            created_at=changed_at,
        ))
        problem.content_status = transition.current_status.value
        problem.status_reason = transition.status_reason
        problem.revision_attempts = transition.revision_attempts
        problem.status_version = next_version
        problem.status_changed_at = changed_at

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)
