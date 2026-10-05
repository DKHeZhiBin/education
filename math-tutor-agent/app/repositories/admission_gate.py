from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.admission_gate import (
    AdmissionGateContext,
    AdmissionGateDecision,
    PersistedAdmissionGateResult,
    RuleBasedAdmissionGate,
)
from app.domain.candidate_revision import MAX_CANDIDATE_REVISION_ATTEMPTS
from app.domain.generation import (
    AdmissionEvidence as DomainAdmissionEvidence,
    AdmissionEvidenceStatus,
    EvidenceProducerType,
)
from app.domain.knowledge import ProblemContentStatus
from app.domain.question_generation import QuestionGenerationBudget
from app.domain.verification_scope_policy import (
    ProblemVerificationScope,
    classify_problem_verification_scope,
    has_authoritative_full_coverage,
    restricted_coverage_reason,
)
from app.domain.problem_lifecycle import (
    ProblemContentStateMachine,
    ProblemTransitionRequest,
)
from app.models.generation import (
    AdmissionEvidence,
    GenerationBatch,
    QuestionGenerationJob,
)
from app.models.knowledge import (
    KnowledgeProblem,
    KnowledgeSolution,
    ProblemStatusTransition,
)


class AdmissionGateReferenceInvalid(ValueError):
    pass


class AdmissionGateVersionConflict(RuntimeError):
    pass


class AdmissionGateRepository:
    """Evaluate and persist one automatic admission decision in one transaction."""

    PROBLEM_LEVEL_EVIDENCE = frozenset({
        "condition_completeness",
        "evaluation_leakage_detection",
        "source_rights_clearance",
    })
    SOLUTION_LEVEL_EVIDENCE = frozenset({
        "solution_independence",
        "symbolic_verification",
        "numeric_verification",
        "constraint_verification",
        "duplicate_detection",
        "pedagogical_review",
    })
    VERSIONED_VERIFIER_EVIDENCE = frozenset({
        "symbolic_verification",
        "numeric_verification",
        "constraint_verification",
        "duplicate_detection",
        "evaluation_leakage_detection",
    })

    def __init__(
        self,
        *,
        gate: RuleBasedAdmissionGate | None = None,
        state_machine: ProblemContentStateMachine | None = None,
    ) -> None:
        self.gate = gate or RuleBasedAdmissionGate()
        self.state_machine = state_machine or ProblemContentStateMachine()

    def evaluate_and_persist(
        self,
        session: Session,
        *,
        problem_id: str,
        expected_status_version: int,
        actor_id: str | None = None,
    ) -> PersistedAdmissionGateResult:
        problem = session.scalar(
            select(KnowledgeProblem)
            .where(KnowledgeProblem.id == problem_id)
            .with_for_update()
        )
        if problem is None:
            raise AdmissionGateReferenceInvalid("candidate problem not found")
        if problem.generation_batch_id is None:
            raise AdmissionGateReferenceInvalid("generated candidate batch is required")
        if problem.status_version != expected_status_version:
            raise AdmissionGateVersionConflict(
                f"expected status version {expected_status_version}, "
                f"found {problem.status_version}"
            )
        if problem.content_status != "validating":
            raise AdmissionGateReferenceInvalid(
                "automatic admission gate only accepts validating content"
            )

        batch = session.scalar(
            select(GenerationBatch)
            .where(GenerationBatch.id == problem.generation_batch_id)
            .with_for_update()
        )
        if batch is None:
            raise AdmissionGateReferenceInvalid("generation batch not found")
        solutions = list(session.scalars(
            select(KnowledgeSolution)
            .where(KnowledgeSolution.problem_id == problem.id)
            .with_for_update()
        ))
        evidence_entities = list(session.scalars(
            select(AdmissionEvidence)
            .where(AdmissionEvidence.problem_id == problem.id)
            .order_by(AdmissionEvidence.created_at, AdmissionEvidence.id)
            .with_for_update()
        ))
        selected_solution = self._select_solution(
            problem,
            solutions,
            evidence_entities,
        )
        verification_scope = classify_problem_verification_scope(
            problem_type=problem.problem_type,
            answer_type=problem.answer_type,
            target=problem.target_json,
            metadata=problem.metadata_json,
        )
        all_domain_evidence = [
            self._to_domain(item)
            for item in evidence_entities
            if item.generation_batch_id == problem.generation_batch_id
        ]
        authoritative_full_coverage = has_authoritative_full_coverage(
            scope=verification_scope,
            problem_content_hash=problem.content_hash,
            solution_id=selected_solution.id if selected_solution else None,
            solution_content_hash=(
                selected_solution.content_hash if selected_solution else None
            ),
            evidence=all_domain_evidence,
        )
        if (
            selected_solution is not None
            and verification_scope != ProblemVerificationScope.PROGRAMMATIC
            and not authoritative_full_coverage
        ):
            self._cap_restricted_solution_coverage(
                selected_solution,
                verification_scope,
            )
        coherent_entities = self._coherent_latest_evidence(
            problem,
            selected_solution,
            evidence_entities,
        )
        coherent_evidence = [self._to_domain(item) for item in coherent_entities]
        max_revision_attempts = self._max_revision_attempts(session, problem)
        context = AdmissionGateContext(
            problem_id=problem.id,
            generation_batch_id=problem.generation_batch_id,
            problem_content_hash=problem.content_hash,
            status_version=problem.status_version,
            current_status=ProblemContentStatus(problem.content_status),
            revision_attempts=problem.revision_attempts,
            max_revision_attempts=max_revision_attempts,
            structured_problem_complete=self._structured_problem_complete(problem),
            index_is_active=False,
            selected_solution_id=(selected_solution.id if selected_solution else None),
            selected_solution_content_hash=(
                selected_solution.content_hash if selected_solution else None
            ),
            has_fully_verified_solution=(
                self._is_fully_verified(selected_solution)
                if selected_solution is not None
                else False
            ),
            verification_scope=verification_scope,
            has_authoritative_full_coverage=authoritative_full_coverage,
            selected_solution_verification_status=(
                selected_solution.verification_status if selected_solution else None
            ),
            selected_solution_coverage_level=(
                (selected_solution.verification_coverage_json or {}).get("level")
                if selected_solution
                else None
            ),
            evidence=coherent_evidence,
        )
        gate_result = self.gate.evaluate(context)
        decision_entity = self._get_or_create_decision_evidence(
            session,
            problem=problem,
            context=context,
            result=gate_result,
        )
        decision_evidence = self._to_domain(decision_entity)

        transition = None
        if gate_result.target_status is not None:
            transition = self.state_machine.transition(ProblemTransitionRequest(
                problem_id=problem.id,
                generation_batch_id=problem.generation_batch_id,
                current_status=ProblemContentStatus(problem.content_status),
                target_status=gate_result.target_status,
                current_status_reason=problem.status_reason,
                reason=(
                    gate_result.reason
                    if gate_result.target_status in {
                        ProblemContentStatus.REVISION_REQUIRED,
                        ProblemContentStatus.QUARANTINED,
                    }
                    else None
                ),
                revision_attempts=problem.revision_attempts,
                max_revision_attempts=max_revision_attempts,
                structured_problem_complete=context.structured_problem_complete,
                source_rights_cleared=self._passed(
                    coherent_evidence, "source_rights_clearance"
                ),
                has_fully_verified_solution=context.has_fully_verified_solution,
                verification_scope=context.verification_scope,
                has_authoritative_full_coverage=(
                    context.has_authoritative_full_coverage
                ),
                problem_content_hash=problem.content_hash,
                fully_verified_solution_id=(
                    context.selected_solution_id
                    if context.has_fully_verified_solution
                    else None
                ),
                fully_verified_solution_content_hash=(
                    context.selected_solution_content_hash
                    if context.has_fully_verified_solution
                    else None
                ),
                index_is_active=False,
                evidence=[*coherent_evidence, decision_evidence],
            ))
            self._persist_transition(
                session,
                problem=problem,
                transition=transition,
                actor_id=actor_id,
            )
            self._refresh_batch_counts(session, batch)
        session.flush()
        return PersistedAdmissionGateResult(
            gate_result=gate_result,
            decision_evidence=decision_evidence,
            transition=transition,
            status_version=problem.status_version,
        )

    def _coherent_latest_evidence(
        self,
        problem: KnowledgeProblem,
        solution: KnowledgeSolution | None,
        evidence: list[AdmissionEvidence],
    ) -> list[AdmissionEvidence]:
        latest: dict[str, AdmissionEvidence] = {}
        for item in evidence:
            if item.evidence_type == "admission_decision":
                continue
            if item.generation_batch_id != problem.generation_batch_id:
                continue
            if item.evidence_type in self.PROBLEM_LEVEL_EVIDENCE:
                if item.solution_id is not None:
                    continue
            elif item.evidence_type in self.SOLUTION_LEVEL_EVIDENCE:
                if solution is None or item.solution_id != solution.id:
                    continue
            elif item.solution_id is not None and (
                solution is None or item.solution_id != solution.id
            ):
                continue
            if not self._evidence_is_fresh(problem, solution, item):
                continue
            latest[item.evidence_type] = item
        return sorted(latest.values(), key=lambda item: (item.created_at, item.id))

    def _evidence_is_fresh(
        self,
        problem: KnowledgeProblem,
        solution: KnowledgeSolution | None,
        evidence: AdmissionEvidence,
    ) -> bool:
        payload = evidence.payload_json or {}
        if evidence.evidence_type in self.VERSIONED_VERIFIER_EVIDENCE and (
            evidence.producer_type != "verifier"
            or evidence.verifier_version_id is None
        ):
            return False
        if evidence.evidence_type == "condition_completeness" and (
            evidence.producer_type != "model"
            or evidence.model_version_id is None
            or evidence.prompt_version_id is None
        ):
            return False
        if evidence.evidence_type == "pedagogical_review" and (
            evidence.producer_type != "model"
            or evidence.model_version_id is None
            or evidence.prompt_version_id is None
        ):
            return False
        if evidence.evidence_type == "solution_independence" and (
            evidence.producer_type != "system"
            or evidence.model_version_id is not None
            or evidence.prompt_version_id is not None
            or evidence.verifier_version_id is not None
        ):
            return False
        if evidence.evidence_type == "source_rights_clearance" and (
            evidence.producer_type != "system"
            or evidence.model_version_id is not None
            or evidence.prompt_version_id is not None
            or evidence.verifier_version_id is not None
        ):
            return False
        content_bound_types = (
            self.VERSIONED_VERIFIER_EVIDENCE
            | {"condition_completeness", "solution_independence", "pedagogical_review"}
        )
        if (
            evidence.evidence_type in content_bound_types
            and payload.get("problem_content_hash") != problem.content_hash
        ):
            return False
        revalidation_version = (problem.metadata_json or {}).get(
            "revalidation_started_status_version"
        )
        if evidence.evidence_type in content_bound_types and revalidation_version:
            evidence_version = payload.get("problem_status_version")
            if (
                not isinstance(evidence_version, int)
                or evidence_version < int(revalidation_version)
            ):
                return False
        if evidence.evidence_type in self.SOLUTION_LEVEL_EVIDENCE:
            if (
                solution is None
                or payload.get("solution_content_hash") != solution.content_hash
            ):
                return False
        return True

    def _select_solution(
        self,
        problem: KnowledgeProblem,
        solutions: list[KnowledgeSolution],
        evidence: list[AdmissionEvidence],
    ) -> KnowledgeSolution | None:
        eligible = [
            solution
            for solution in solutions
            if (solution.metadata_json or {}).get("content_origin")
            == "independent_solving_agent"
        ]
        if not eligible:
            return None
        evidence_counts: dict[str, int] = {}
        for solution in eligible:
            evidence_counts[solution.id] = len({
                item.evidence_type
                for item in evidence
                if item.generation_batch_id == problem.generation_batch_id
                and item.solution_id == solution.id
                and item.evidence_type in self.SOLUTION_LEVEL_EVIDENCE
                and self._evidence_is_fresh(problem, solution, item)
            })
        return max(
            eligible,
            key=lambda solution: (
                self._is_fully_verified(solution),
                evidence_counts.get(solution.id, 0),
                solution.updated_at,
                solution.id,
            ),
        )

    def _get_or_create_decision_evidence(
        self,
        session: Session,
        *,
        problem: KnowledgeProblem,
        context: AdmissionGateContext,
        result,
    ) -> AdmissionEvidence:
        payload = {
            "schema_version": "1.0",
            "problem_content_hash": problem.content_hash,
            "problem_status_version": problem.status_version,
            "selected_solution_id": context.selected_solution_id,
            "selected_solution_content_hash": context.selected_solution_content_hash,
            "verification_scope": context.verification_scope.value,
            "has_authoritative_full_coverage": (
                context.has_authoritative_full_coverage
            ),
            "selected_solution_verification_status": (
                context.selected_solution_verification_status
            ),
            "selected_solution_coverage_level": (
                context.selected_solution_coverage_level
            ),
            "decision": result.decision.value,
            "target_status": result.target_status.value if result.target_status else None,
            "reason": result.reason,
            "deterministic_failures": result.deterministic_failures,
            "other_failures": result.other_failures,
            "missing_evidence": result.missing_evidence,
            "inconclusive_evidence": result.inconclusive_evidence,
            "checked_evidence_ids": result.checked_evidence_ids,
            "ignored_model_pass": result.ignored_model_pass,
            "rule_policy": {
                "max_revision_attempts": context.max_revision_attempts,
                "deterministic_failure_priority": True,
                "model_override_allowed": False,
            },
        }
        evidence_hash = self._hash_json(payload)
        existing = session.scalar(select(AdmissionEvidence).where(
            AdmissionEvidence.generation_batch_id == problem.generation_batch_id,
            AdmissionEvidence.problem_id == problem.id,
            AdmissionEvidence.evidence_type == "admission_decision",
            AdmissionEvidence.evidence_hash == evidence_hash,
        ))
        if existing is not None:
            return existing
        status = {
            AdmissionGateDecision.APPROVE: "passed",
            AdmissionGateDecision.REVISE: "failed",
            AdmissionGateDecision.QUARANTINE: "failed",
            AdmissionGateDecision.WAIT: "inconclusive",
        }[result.decision]
        entity = AdmissionEvidence(
            generation_batch_id=problem.generation_batch_id,
            problem_id=problem.id,
            solution_id=context.selected_solution_id,
            evidence_type="admission_decision",
            producer_type="system",
            status=status,
            model_version_id=None,
            prompt_version_id=None,
            verifier_version_id=None,
            is_blocking=True,
            summary=result.reason,
            payload_json=payload,
            evidence_hash=evidence_hash,
        )
        session.add(entity)
        session.flush()
        return entity

    @staticmethod
    def _cap_restricted_solution_coverage(
        solution: KnowledgeSolution,
        scope: ProblemVerificationScope,
    ) -> None:
        coverage = dict(solution.verification_coverage_json or {})
        limitation = restricted_coverage_reason(scope)
        limitations = list(coverage.get("limitations") or [])
        if limitation not in limitations:
            limitations.append(limitation)
        coverage["limitations"] = limitations

        covered_step_ids = list(coverage.get("covered_step_ids") or [])
        if not covered_step_ids:
            covered_step_ids = [
                str(step.get("step_id"))
                for step in solution.steps_json
                if isinstance(step, dict) and step.get("step_id")
            ]
            coverage["covered_step_ids"] = covered_step_ids
        checks = list(coverage.get("checks") or [])
        has_failed_check = any(
            isinstance(check, dict) and check.get("status") == "failed"
            for check in checks
        )
        can_retain_partial = bool(
            solution.steps_json
            and covered_step_ids
            and checks
            and not has_failed_check
        )
        if solution.verification_status == "verified":
            if has_failed_check:
                solution.verification_status = "failed"
                coverage["level"] = "partial"
            elif can_retain_partial:
                solution.verification_status = "partial"
                coverage["level"] = "partial"
            else:
                solution.verification_status = "unverified"
                coverage.update({
                    "level": "none",
                    "covered_step_ids": [],
                    "uncovered_step_ids": [],
                    "checks": [],
                })
        elif solution.verification_status == "partial" and coverage.get("level") == "full":
            coverage["level"] = "partial"
        solution.verification_coverage_json = coverage
        metadata = dict(solution.metadata_json or {})
        metadata["verification_scope_policy"] = {
            "scope": scope.value,
            "authoritative_full_coverage": False,
            "maximum_automatic_status": "partial",
            "limitation": limitation,
        }
        solution.metadata_json = metadata

    @staticmethod
    def _max_revision_attempts(
        session: Session,
        problem: KnowledgeProblem,
    ) -> int:
        maximum = min(
            settings.knowledge_problem_max_revision_attempts,
            MAX_CANDIDATE_REVISION_ATTEMPTS,
        )
        if problem.generation_batch_id is None:
            return maximum
        job = session.scalar(
            select(QuestionGenerationJob)
            .where(QuestionGenerationJob.generation_batch_id == problem.generation_batch_id)
            .with_for_update()
        )
        if job is None:
            return maximum
        budget = QuestionGenerationBudget.model_validate(job.budget_json)
        return min(maximum, budget.max_revision_rounds)

    @staticmethod
    def _persist_transition(
        session: Session,
        *,
        problem: KnowledgeProblem,
        transition,
        actor_id: str | None,
    ) -> None:
        if not transition.changed:
            return
        changed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        next_version = problem.status_version + 1
        session.add(ProblemStatusTransition(
            problem_id=problem.id,
            from_status=transition.previous_status.value,
            to_status=transition.current_status.value,
            reason=transition.status_reason,
            revision_attempts=transition.revision_attempts,
            status_version=next_version,
            checked_requirements_json=[
                "rule_based_admission_gate",
                *transition.checked_requirements,
            ],
            actor_type="system",
            actor_id=actor_id,
            created_at=changed_at,
        ))
        problem.content_status = transition.current_status.value
        problem.status_reason = transition.status_reason
        problem.revision_attempts = transition.revision_attempts
        problem.status_version = next_version
        problem.status_changed_at = changed_at
        session.flush()

    @staticmethod
    def _refresh_batch_counts(session: Session, batch: GenerationBatch) -> None:
        approved = session.scalar(
            select(func.count(KnowledgeProblem.id)).where(
                KnowledgeProblem.generation_batch_id == batch.id,
                KnowledgeProblem.content_status.in_(["approved", "indexed"]),
            )
        ) or 0
        quarantined = session.scalar(
            select(func.count(KnowledgeProblem.id)).where(
                KnowledgeProblem.generation_batch_id == batch.id,
                KnowledgeProblem.content_status == "quarantined",
            )
        ) or 0
        batch.approved_count = approved
        batch.quarantined_count = quarantined

    @staticmethod
    def _structured_problem_complete(problem: KnowledgeProblem) -> bool:
        return bool(
            problem.statement.strip()
            and problem.problem_type.strip()
            and problem.content_type.strip()
            and problem.grade_band
            and problem.grade_codes_json
            and problem.knowledge_point_codes_json
            and problem.difficulty_factors_json
            and problem.target_json
            and (problem.explicit_conditions_json or problem.implicit_conditions_json)
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
    def _passed(
        evidence: list[DomainAdmissionEvidence],
        evidence_type: str,
    ) -> bool:
        matches = [item for item in evidence if item.evidence_type == evidence_type]
        return bool(matches and matches[-1].status == AdmissionEvidenceStatus.PASSED)

    @staticmethod
    def _hash_json(payload: dict) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_domain(entity: AdmissionEvidence) -> DomainAdmissionEvidence:
        created_at = (
            entity.created_at.replace(tzinfo=timezone.utc)
            if entity.created_at.tzinfo is None
            else entity.created_at.astimezone(timezone.utc)
        )
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
