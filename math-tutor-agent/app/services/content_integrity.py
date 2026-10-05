from __future__ import annotations

import json
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.cache.knowledge_retrieval import KnowledgeIndexVersion
from app.core.config import Settings, settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.content_issue import (
    ContentIssueReportView,
    RuntimeContentIssueResult,
    StudentContentIssueRequest,
)
from app.domain.index_lifecycle import IndexMaintenanceRequest
from app.domain.schemas import TutoringSession
from app.models.content_issue import ContentIssueReport
from app.models.knowledge import KnowledgeProblem
from app.models.search_index import SearchIndexMaintenanceJob
from app.search_index.lifecycle_repository import SearchIndexLifecycleRepository
from app.search_index.lifecycle_service import SearchIndexLifecycleService


class ContentIssueReferenceInvalid(ValueError):
    pass


class ContentIntegrityService:
    """Suppress reported content and put its current version back into validation."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        session_factory: sessionmaker[Session] | None = None,
        lifecycle_service: SearchIndexLifecycleService | None = None,
    ) -> None:
        self.config = config
        self.session_factory = session_factory or create_session_factory(
            create_mysql_engine()
        )
        self.lifecycle_service = lifecycle_service or SearchIndexLifecycleService(
            config,
            session_factory=self.session_factory,
        )
        self.lifecycle_repository = SearchIndexLifecycleRepository()
        self.cache_version = self.lifecycle_service.cache_version

    def canonical_problem_statement(self, problem_id: str) -> str:
        with self.session_factory() as session:
            problem = session.get(KnowledgeProblem, problem_id)
            if problem is None or problem.content_status not in {"approved", "indexed"}:
                raise ContentIssueReferenceInvalid(
                    "the selected problem is not available for tutoring"
                )
            return problem.statement

    def report_student_issue(
        self,
        tutoring_session: TutoringSession,
        *,
        reporter_user_id: str,
        request: StudentContentIssueRequest,
    ) -> RuntimeContentIssueResult:
        problem_id = self._resolve_reported_problem(tutoring_session, request.problem_id)
        return self._submit(
            problem_id=problem_id,
            tutoring_session=tutoring_session,
            reporter_user_id=reporter_user_id,
            source="student_report",
            issue_type=request.issue_type,
            description=request.description.strip(),
            idempotency_key=request.client_report_id,
            evidence={
                "client_report_id": request.client_report_id,
                "reported_from_session": True,
            },
        )

    def process_runtime_signals(
        self,
        tutoring_session: TutoringSession,
        run_id: str,
    ) -> RuntimeContentIssueResult | None:
        problem_id = tutoring_session.knowledge_problem_id
        if problem_id is None:
            return None
        run_artifacts = [
            item for item in tutoring_session.artifacts if item.run_id == run_id
        ]
        solution = self._latest_payload(run_artifacts, "solution_plan")
        verification = self._latest_payload(run_artifacts, "verification_report")
        explicit_conflict = solution.get("answer_consistency") == "conflict"
        conflict_issues = [
            str(item)
            for item in verification.get("issues", [])
            if "答案不一致" in str(item) or "答案冲突" in str(item)
        ]
        if not explicit_conflict and not conflict_issues:
            return None
        methods = solution.get("methods", [])
        method_answers = [
            {
                "method_id": str(item.get("id") or "")[:100],
                "answer": str(item.get("answer") or "")[:700],
            }
            for item in methods
            if isinstance(item, dict)
        ][:10]
        return self._submit(
            problem_id=problem_id,
            tutoring_session=tutoring_session,
            reporter_user_id=None,
            source="runtime_answer_conflict",
            issue_type="answer_conflict",
            description="运行时独立解法或校验结果出现答案冲突。",
            idempotency_key=run_id,
            evidence={
                "run_id": run_id,
                "answer_consistency": solution.get("answer_consistency"),
                "method_answers": method_answers,
                "verification_issues": conflict_issues[:10],
                "verification_passed": verification.get("passed"),
            },
        )

    def close(self) -> None:
        self.lifecycle_service.close()

    def _submit(
        self,
        *,
        problem_id: str,
        tutoring_session: TutoringSession,
        reporter_user_id: str | None,
        source: str,
        issue_type: str,
        description: str,
        idempotency_key: str,
        evidence: dict,
    ) -> RuntimeContentIssueResult:
        identity = {
            "source": source,
            "problem_id": problem_id,
            "session_id": tutoring_session.id,
            "reporter_user_id": reporter_user_id,
            "idempotency_key": idempotency_key,
        }
        digest = self._hash(identity)
        generation: int | None = None
        maintenance_job_id: str | None = None
        created = False
        with self.session_factory.begin() as session:
            report = session.scalar(
                select(ContentIssueReport).where(
                    ContentIssueReport.idempotency_key_hash == digest
                )
            )
            if report is None:
                problem = session.get(KnowledgeProblem, problem_id, with_for_update=True)
                if problem is None:
                    raise ContentIssueReferenceInvalid("reported problem not found")
                if problem.content_status == "retired":
                    raise ContentIssueReferenceInvalid("retired content cannot be revalidated")
                if problem.content_status in {"candidate"}:
                    raise ContentIssueReferenceInvalid(
                        "candidate content is not exposed to tutoring sessions"
                    )
                report = ContentIssueReport(
                    problem_id=problem.id,
                    session_id=tutoring_session.id,
                    reporter_user_id=reporter_user_id,
                    source=source,
                    issue_type=issue_type,
                    description=description,
                    evidence_json=evidence,
                    idempotency_key_hash=digest,
                    status="received",
                )
                session.add(report)
                session.flush()
                created = True

                if problem.content_status in {"approved", "indexed"}:
                    job = self.lifecycle_repository.enqueue(
                        session,
                        IndexMaintenanceRequest(
                            problem_id=problem.id,
                            trigger_type="revalidation",
                            reason=(
                                f"{source}:{issue_type}:content_issue_report:{report.id}"
                            )[:1000],
                        ),
                        index_version=self.config.production_index_version,
                    )
                    report.maintenance_job_id = job.id
                    report.status = "revalidation_queued"
                    maintenance_job_id = job.id
                    generation = self.cache_version.bump(
                        session,
                        reason=f"content_issue:{report.id}",
                    )
                else:
                    existing_job = self._active_revalidation_job(session, problem.id)
                    report.maintenance_job_id = existing_job.id if existing_job else None
                    report.status = (
                        "validating"
                        if problem.content_status == "validating"
                        else "revalidation_queued"
                    )
                    maintenance_job_id = report.maintenance_job_id
            else:
                maintenance_job_id = report.maintenance_job_id
            report_id = report.id

        if generation is not None:
            self.cache_version.publish(generation, f"content_issue:{report_id}")
        if maintenance_job_id is not None:
            job = self.lifecycle_service.run_job(maintenance_job_id)
            if job.status in {"waiting_for_approval", "completed"}:
                with self.session_factory.begin() as session:
                    stored = session.get(ContentIssueReport, report_id, with_for_update=True)
                    if stored is not None and stored.status not in {"resolved", "dismissed"}:
                        stored.status = "validating"

        with self.session_factory() as session:
            stored = session.get(ContentIssueReport, report_id)
            if stored is None:
                raise RuntimeError("content issue report disappeared after persistence")
            return RuntimeContentIssueResult(
                report=self._view(stored),
                created=created,
            )

    @staticmethod
    def _active_revalidation_job(
        session: Session,
        problem_id: str,
    ) -> SearchIndexMaintenanceJob | None:
        return session.scalar(
            select(SearchIndexMaintenanceJob)
            .where(
                SearchIndexMaintenanceJob.problem_id == problem_id,
                SearchIndexMaintenanceJob.trigger_type == "revalidation",
                SearchIndexMaintenanceJob.status.not_in(["completed", "cancelled"]),
            )
            .order_by(SearchIndexMaintenanceJob.created_at.desc())
        )

    @staticmethod
    def _resolve_reported_problem(
        tutoring_session: TutoringSession,
        requested_problem_id: str | None,
    ) -> str:
        allowed: set[str] = set()
        if tutoring_session.knowledge_problem_id:
            allowed.add(tutoring_session.knowledge_problem_id)
        for artifact in tutoring_session.artifacts:
            if artifact.kind != "retrieved_teaching_context":
                continue
            for group in ("problem_patterns", "solution_outlines"):
                for item in artifact.payload.get(group, []):
                    if isinstance(item, dict) and item.get("problem_id"):
                        allowed.add(str(item["problem_id"]))
        if requested_problem_id:
            if requested_problem_id not in allowed:
                raise ContentIssueReferenceInvalid(
                    "the reported problem was not used in this tutoring session"
                )
            return requested_problem_id
        if len(allowed) == 1:
            return next(iter(allowed))
        if not allowed:
            raise ContentIssueReferenceInvalid(
                "this session has no reportable knowledge-base problem"
            )
        raise ContentIssueReferenceInvalid(
            "problem_id is required when the session used multiple knowledge-base problems"
        )

    @staticmethod
    def _latest_payload(artifacts: list, kind: str) -> dict:
        for artifact in reversed(artifacts):
            if artifact.kind == kind:
                return artifact.payload
        return {}

    @staticmethod
    def _hash(value: dict) -> str:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _view(report: ContentIssueReport) -> ContentIssueReportView:
        return ContentIssueReportView(
            id=report.id,
            problem_id=report.problem_id,
            session_id=report.session_id,
            reporter_user_id=report.reporter_user_id,
            source=report.source,
            issue_type=report.issue_type,
            description=report.description,
            evidence=report.evidence_json,
            status=report.status,
            maintenance_job_id=report.maintenance_job_id,
            created_at=report.created_at,
            updated_at=report.updated_at,
        )


content_integrity_service = ContentIntegrityService()
