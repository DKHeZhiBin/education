from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.core.config import settings
from app.core.database import create_mysql_engine, create_session_factory
from app.domain.admission_gate import PersistedAdmissionGateResult
from app.domain.generation import (
    AdmissionEvidence as DomainAdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)
from app.domain.knowledge import ProblemContentStatus
from app.domain.knowledge_admin import (
    AdmissionEvidenceView,
    GenerationAuditRecordView,
    PersistedProblemTransition,
    ProblemAdminDetail,
    ProblemAdminListItem,
    ProblemAdminPage,
    ProblemStatusCount,
    ProblemStatusTransitionView,
)
from app.domain.problem_lifecycle import (
    ProblemContentStateMachine,
    ProblemTransitionRequest,
)
from app.domain.verification_scope_policy import (
    classify_problem_verification_scope,
    has_authoritative_full_coverage,
)
from app.models.generation import AdmissionEvidence
from app.models.knowledge import (
    KnowledgeProblem,
    KnowledgeSolution,
    ProblemStatusTransition,
)
from app.repositories.admission_gate import AdmissionGateRepository


class KnowledgeProblemNotFound(LookupError):
    pass


class KnowledgeProblemVersionConflict(RuntimeError):
    def __init__(self, problem_id: str, expected: int, actual: int) -> None:
        self.problem_id = problem_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"problem {problem_id} status version conflict: expected {expected}, actual {actual}"
        )


class KnowledgeRepository:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        state_machine: ProblemContentStateMachine | None = None,
        admission_gate_repository: AdmissionGateRepository | None = None,
    ) -> None:
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())
        self.state_machine = state_machine or ProblemContentStateMachine()
        self.admission_gate_repository = (
            admission_gate_repository
            or AdmissionGateRepository(state_machine=self.state_machine)
        )

    def status_summary(self) -> list[ProblemStatusCount]:
        with self.session_factory() as db:
            rows = db.execute(
                select(KnowledgeProblem.content_status, func.count(KnowledgeProblem.id))
                .group_by(KnowledgeProblem.content_status)
                .order_by(KnowledgeProblem.content_status)
            ).all()
        counts = {status: count for status, count in rows}
        return [
            ProblemStatusCount(status=status, count=counts.get(status.value, 0))
            for status in ProblemContentStatus
        ]

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
        filters = []
        if statuses:
            filters.append(KnowledgeProblem.content_status.in_([item.value for item in statuses]))
        if subject:
            filters.append(KnowledgeProblem.subject == subject)
        if grade_band:
            filters.append(KnowledgeProblem.grade_band == grade_band)
        if grade_code:
            filters.append(func.json_contains(
                KnowledgeProblem.grade_codes_json,
                json.dumps(grade_code),
            ) == 1)
        if problem_type:
            filters.append(KnowledgeProblem.problem_type == problem_type)
        if content_type:
            filters.append(KnowledgeProblem.content_type == content_type)
        if curriculum_version_id:
            filters.append(
                KnowledgeProblem.curriculum_version_id == curriculum_version_id
            )
        if knowledge_point_code:
            filters.append(func.json_contains(
                KnowledgeProblem.knowledge_point_codes_json,
                json.dumps(knowledge_point_code),
            ) == 1)
        if difficulty_source:
            filters.append(func.json_contains(
                KnowledgeProblem.difficulty_factors_json,
                json.dumps({"factor_type": difficulty_source}),
            ) == 1)
        if generation_batch_id:
            filters.append(KnowledgeProblem.generation_batch_id == generation_batch_id)
        if search and search.strip():
            filters.append(KnowledgeProblem.statement.like(f"%{search.strip()}%"))

        query = (
            select(KnowledgeProblem)
            .options(
                selectinload(KnowledgeProblem.source_reference),
                selectinload(KnowledgeProblem.generation_batch),
            )
            .where(*filters)
            .order_by(KnowledgeProblem.status_changed_at.desc(), KnowledgeProblem.id)
            .limit(limit)
            .offset(offset)
        )
        count_query = select(func.count(KnowledgeProblem.id)).where(*filters)
        with self.session_factory() as db:
            total = db.scalar(count_query) or 0
            entities = db.scalars(query).all()
            items = [self._list_item(entity) for entity in entities]
        return ProblemAdminPage(items=items, total=total, limit=limit, offset=offset)

    def get_problem(self, problem_id: str) -> ProblemAdminDetail | None:
        with self.session_factory() as db:
            entity = db.scalar(self._detail_query().where(KnowledgeProblem.id == problem_id))
            return self._detail(entity) if entity is not None else None

    def evaluate_automatic_admission(
        self,
        *,
        problem_id: str,
        expected_status_version: int,
        actor_id: str | None = "admission-gate",
    ) -> PersistedAdmissionGateResult:
        with self.session_factory() as db, db.begin():
            return self.admission_gate_repository.evaluate_and_persist(
                db,
                problem_id=problem_id,
                expected_status_version=expected_status_version,
                actor_id=actor_id,
            )

    def transition_problem(
        self,
        *,
        problem_id: str,
        target_status: ProblemContentStatus,
        expected_status_version: int,
        actor_type: Literal["admin", "agent", "job", "system"],
        actor_id: str | None,
        reason: str | None = None,
        index_is_active: bool = False,
    ) -> PersistedProblemTransition:
        if actor_type not in {"admin", "agent", "job", "system"}:
            raise ValueError(f"unsupported lifecycle actor type: {actor_type}")
        with self.session_factory() as db, db.begin():
            entity = db.scalar(
                select(KnowledgeProblem)
                .where(KnowledgeProblem.id == problem_id)
                .with_for_update()
            )
            if entity is None:
                raise KnowledgeProblemNotFound(problem_id)
            if entity.status_version != expected_status_version:
                raise KnowledgeProblemVersionConflict(
                    problem_id, expected_status_version, entity.status_version
                )

            evidence_entities = db.scalars(
                select(AdmissionEvidence)
                .where(AdmissionEvidence.problem_id == problem_id)
                .order_by(AdmissionEvidence.created_at, AdmissionEvidence.id)
                .with_for_update()
            ).all()
            solutions = db.scalars(
                select(KnowledgeSolution)
                .where(KnowledgeSolution.problem_id == problem_id)
                .with_for_update()
            ).all()
            fully_verified_solutions = [
                solution for solution in solutions if self._is_fully_verified(solution)
            ]
            selected_verified_solution = (
                max(
                    fully_verified_solutions,
                    key=lambda solution: (solution.updated_at, solution.id),
                )
                if fully_verified_solutions
                else None
            )
            evidence = [self._domain_evidence(item) for item in evidence_entities]
            if target_status == ProblemContentStatus.APPROVED:
                evidence = [
                    item
                    for item in evidence
                    if item.generation_batch_id == entity.generation_batch_id
                ]
            rights_cleared = self._latest_evidence_passed(
                evidence, "source_rights_clearance"
            )
            verification_scope = classify_problem_verification_scope(
                problem_type=entity.problem_type,
                answer_type=entity.answer_type,
                target=entity.target_json,
                metadata=entity.metadata_json,
            )
            authoritative_full_coverage = has_authoritative_full_coverage(
                scope=verification_scope,
                problem_content_hash=entity.content_hash,
                solution_id=(
                    selected_verified_solution.id
                    if selected_verified_solution
                    else None
                ),
                solution_content_hash=(
                    selected_verified_solution.content_hash
                    if selected_verified_solution
                    else None
                ),
                evidence=evidence,
            )
            result = self.state_machine.transition(ProblemTransitionRequest(
                problem_id=entity.id,
                generation_batch_id=entity.generation_batch_id,
                current_status=ProblemContentStatus(entity.content_status),
                target_status=target_status,
                current_status_reason=entity.status_reason,
                reason=reason,
                revision_attempts=entity.revision_attempts,
                max_revision_attempts=settings.knowledge_problem_max_revision_attempts,
                structured_problem_complete=self._structured_problem_complete(entity),
                source_rights_cleared=rights_cleared,
                has_fully_verified_solution=selected_verified_solution is not None,
                verification_scope=verification_scope,
                has_authoritative_full_coverage=authoritative_full_coverage,
                problem_content_hash=entity.content_hash,
                fully_verified_solution_id=(
                    selected_verified_solution.id if selected_verified_solution else None
                ),
                fully_verified_solution_content_hash=(
                    selected_verified_solution.content_hash
                    if selected_verified_solution
                    else None
                ),
                index_is_active=index_is_active,
                evidence=evidence,
            ))

            if result.changed:
                changed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                next_version = entity.status_version + 1
                db.add(ProblemStatusTransition(
                    problem_id=entity.id,
                    from_status=result.previous_status.value,
                    to_status=result.current_status.value,
                    reason=result.status_reason,
                    revision_attempts=result.revision_attempts,
                    status_version=next_version,
                    checked_requirements_json=result.checked_requirements,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    created_at=changed_at,
                ))
                entity.content_status = result.current_status.value
                entity.status_reason = result.status_reason
                entity.revision_attempts = result.revision_attempts
                entity.status_version = next_version
                entity.status_changed_at = changed_at
                db.flush()
            else:
                changed_at = entity.status_changed_at

            response = PersistedProblemTransition(
                problem_id=entity.id,
                previous_status=result.previous_status,
                current_status=result.current_status,
                changed=result.changed,
                status_reason=result.status_reason,
                revision_attempts=result.revision_attempts,
                status_version=entity.status_version,
                status_changed_at=self._utc(changed_at),
                checked_requirements=result.checked_requirements,
            )
        return response

    @staticmethod
    def _detail_query():
        return select(KnowledgeProblem).options(
            selectinload(KnowledgeProblem.source_reference),
            selectinload(KnowledgeProblem.generation_batch),
            selectinload(KnowledgeProblem.solutions),
            selectinload(KnowledgeProblem.admission_evidence),
            selectinload(KnowledgeProblem.status_transitions),
        )

    @classmethod
    def _list_item(cls, entity: KnowledgeProblem) -> ProblemAdminListItem:
        return ProblemAdminListItem(
            id=entity.id,
            statement=entity.statement,
            subject=entity.subject,
            grade_band=entity.grade_band,
            problem_type=entity.problem_type,
            content_type=entity.content_type,
            difficulty=entity.difficulty,
            difficulty_source_types=list(dict.fromkeys(
                item.get("factor_type", "other")
                for item in entity.difficulty_factors_json
            )),
            grade_codes=entity.grade_codes_json,
            knowledge_point_codes=entity.knowledge_point_codes_json,
            curriculum_version_id=entity.curriculum_version_id,
            content_status=ProblemContentStatus(entity.content_status),
            status_reason=entity.status_reason,
            revision_attempts=entity.revision_attempts,
            status_version=entity.status_version,
            status_changed_at=cls._utc(entity.status_changed_at),
            source_reference_id=entity.source_reference_id,
            source_title=entity.source_reference.title,
            source_license_name=entity.source_reference.license_name,
            generation_batch_id=entity.generation_batch_id,
            generation_batch_key=(
                entity.generation_batch.batch_key if entity.generation_batch else None
            ),
            updated_at=cls._utc(entity.updated_at),
        )

    @classmethod
    def _detail(cls, entity: KnowledgeProblem) -> ProblemAdminDetail:
        base = cls._list_item(entity).model_dump()
        return ProblemAdminDetail(
            **base,
            explicit_conditions=entity.explicit_conditions_json,
            implicit_conditions=entity.implicit_conditions_json,
            target=entity.target_json,
            difficulty_factors=entity.difficulty_factors_json,
            solution_count=len(entity.solutions),
            fully_verified_solution_count=sum(
                cls._is_fully_verified(solution) for solution in entity.solutions
            ),
            evidence=[
                AdmissionEvidenceView(
                    id=item.id,
                    generation_batch_id=item.generation_batch_id,
                    evidence_type=item.evidence_type,
                    producer_type=EvidenceProducerType(item.producer_type),
                    status=AdmissionEvidenceStatus(item.status),
                    is_blocking=item.is_blocking,
                    summary=item.summary,
                    solution_id=item.solution_id,
                    model_version_id=item.model_version_id,
                    prompt_version_id=item.prompt_version_id,
                    verifier_version_id=item.verifier_version_id,
                    evidence_hash=item.evidence_hash,
                    payload=item.payload_json,
                    created_at=cls._utc(item.created_at),
                )
                for item in sorted(
                    entity.admission_evidence,
                    key=lambda value: (value.created_at, value.id),
                    reverse=True,
                )
            ],
            transitions=[
                ProblemStatusTransitionView(
                    id=item.id,
                    from_status=ProblemContentStatus(item.from_status),
                    to_status=ProblemContentStatus(item.to_status),
                    reason=item.reason,
                    revision_attempts=item.revision_attempts,
                    status_version=item.status_version,
                    checked_requirements=item.checked_requirements_json,
                    actor_type=item.actor_type,
                    actor_id=item.actor_id,
                    created_at=cls._utc(item.created_at),
                )
                for item in reversed(entity.status_transitions)
            ],
            audit_timeline=cls._audit_timeline(entity),
        )

    @classmethod
    def _audit_timeline(
        cls,
        entity: KnowledgeProblem,
    ) -> list[GenerationAuditRecordView]:
        records: list[GenerationAuditRecordView] = []
        for item in entity.admission_evidence:
            payload = item.payload_json or {}
            records.append(GenerationAuditRecordView(
                id=f"evidence:{item.id}",
                stage=cls._audit_stage(item.evidence_type),
                event_type=item.evidence_type,
                source_type="admission_evidence",
                source_id=item.id,
                outcome=item.status,
                summary=item.summary,
                solution_id=item.solution_id,
                model_version_id=(
                    item.model_version_id
                    or payload.get("solver_model_version_id")
                    or payload.get("model_version_id")
                ),
                prompt_version_id=(
                    item.prompt_version_id
                    or payload.get("solver_prompt_version_id")
                    or payload.get("prompt_version_id")
                ),
                verifier_version_id=item.verifier_version_id,
                problem_content_hash=(
                    payload.get("problem_content_hash")
                    or payload.get("revised_content_hash")
                ),
                solution_content_hash=payload.get("solution_content_hash"),
                status_version=payload.get("problem_status_version"),
                payload=payload,
                created_at=cls._utc(item.created_at),
            ))
        for item in entity.status_transitions:
            records.append(GenerationAuditRecordView(
                id=f"transition:{item.id}",
                stage="state_change",
                event_type=f"{item.from_status}_to_{item.to_status}",
                source_type="problem_status_transition",
                source_id=item.id,
                outcome=item.to_status,
                summary=(
                    item.reason
                    or f"题目状态从 {item.from_status} 变更为 {item.to_status}。"
                ),
                actor_type=item.actor_type,
                actor_id=item.actor_id,
                problem_content_hash=entity.content_hash,
                status_version=item.status_version,
                payload={
                    "from_status": item.from_status,
                    "to_status": item.to_status,
                    "revision_attempts": item.revision_attempts,
                    "checked_requirements": item.checked_requirements_json,
                },
                created_at=cls._utc(item.created_at),
            ))
        return sorted(records, key=lambda item: (item.created_at, item.id))

    @staticmethod
    def _audit_stage(evidence_type: str) -> str:
        stage_by_type = {
            "candidate_generation": "generation",
            "condition_completeness": "condition_check",
            "solution_independence": "independent_solving",
            "symbolic_verification": "tool_verification",
            "numeric_verification": "tool_verification",
            "constraint_verification": "tool_verification",
            "duplicate_detection": "tool_verification",
            "evaluation_leakage_detection": "tool_verification",
            "formal_proof_verification": "tool_verification",
            "exhaustive_rubric_verification": "tool_verification",
            "pedagogical_review": "independent_review",
            "qualified_human_review": "independent_review",
            "revision_generation": "revision",
            "admission_decision": "admission",
            "source_rights_clearance": "condition_check",
            "index_sync": "indexing",
            "index_removal": "indexing",
        }
        return stage_by_type.get(evidence_type, "other")

    @staticmethod
    def _domain_evidence(entity: AdmissionEvidence) -> DomainAdmissionEvidence:
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
            created_at=KnowledgeRepository._utc(entity.created_at),
        )

    @staticmethod
    def _latest_evidence_passed(
        evidence: list[DomainAdmissionEvidence], evidence_type: str
    ) -> bool:
        matches = [item for item in evidence if item.evidence_type == evidence_type]
        if not matches:
            return False
        latest = max(matches, key=lambda item: (item.created_at, item.id))
        return latest.status == AdmissionEvidenceStatus.PASSED

    @staticmethod
    def _structured_problem_complete(entity: KnowledgeProblem) -> bool:
        return bool(
            entity.statement.strip()
            and entity.problem_type.strip()
            and entity.content_type.strip()
            and entity.grade_band
            and entity.grade_codes_json
            and entity.knowledge_point_codes_json
            and entity.difficulty_factors_json
            and entity.target_json
            and (entity.explicit_conditions_json or entity.implicit_conditions_json)
        )

    @staticmethod
    def _is_fully_verified(solution: KnowledgeSolution) -> bool:
        coverage = solution.verification_coverage_json or {}
        return bool(
            solution.verification_status == "verified"
            and solution.steps_json
            and coverage.get("level") == "full"
            and not coverage.get("uncovered_step_ids")
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
