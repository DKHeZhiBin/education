from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import create_mysql_engine, create_session_factory
from app.domain.knowledge import StructuredSolutionStep
from app.domain.teaching_content import (
    ErrorPatternLinkView,
    HINT_BOUNDARIES,
    HintBlueprintUpsert,
    HintBlueprintView,
    HintReviewStatus,
    HintSourceType,
    HintStage,
    ProblemErrorPatternUpsert,
    ProblemTeachingMap,
    RevealScope,
    SolutionStepView,
    TeachingSolutionView,
)
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution
from app.models.teaching import (
    ErrorPattern,
    HintBlueprint,
    KnowledgeSolutionStep,
    ProblemErrorPattern,
)


class TeachingContentNotFound(LookupError):
    pass


class TeachingContentConflict(ValueError):
    pass


class TeachingContentRepository:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())

    @staticmethod
    def sync_solution_steps(
        session: Session,
        solution: KnowledgeSolution,
    ) -> list[KnowledgeSolutionStep]:
        """Project validated JSON steps into stable relational rows in the same transaction."""
        session.flush()
        try:
            parsed_steps = [
                StructuredSolutionStep.model_validate(item) for item in solution.steps_json
            ]
            TeachingContentRepository._validate_step_set(parsed_steps)
        except ValueError as error:
            raise TeachingContentConflict(
                f"solution contains invalid structured steps: {error}"
            ) from error
        existing_rows = session.scalars(select(KnowledgeSolutionStep).where(
            KnowledgeSolutionStep.solution_id == solution.id
        )).all()
        existing_by_key = {row.step_key: row for row in existing_rows}
        current_keys: set[str] = set()
        projected: list[KnowledgeSolutionStep] = []

        for step in parsed_steps:
            current_keys.add(step.step_id)
            payload = step.model_dump(mode="json")
            content_hash = sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            row = existing_by_key.get(step.step_id)
            if row is None:
                row = KnowledgeSolutionStep(
                    problem_id=solution.problem_id,
                    solution_id=solution.id,
                    step_key=step.step_id,
                    sequence=step.sequence,
                    action=step.action,
                    result=step.result,
                    justifications_json=[item.model_dump(mode="json") for item in step.justifications],
                    depends_on_step_keys_json=step.depends_on_step_ids,
                    condition_refs_json=step.condition_refs,
                    knowledge_point_codes_json=step.knowledge_point_codes,
                    content_hash=content_hash,
                    active=True,
                )
                session.add(row)
            else:
                if row.problem_id != solution.problem_id:
                    raise TeachingContentConflict("solution step points to a different problem")
                row.sequence = step.sequence
                row.action = step.action
                row.result = step.result
                row.justifications_json = [
                    item.model_dump(mode="json") for item in step.justifications
                ]
                row.depends_on_step_keys_json = step.depends_on_step_ids
                row.condition_refs_json = step.condition_refs
                row.knowledge_point_codes_json = step.knowledge_point_codes
                row.content_hash = content_hash
                row.active = True
            projected.append(row)

        for row in existing_rows:
            if row.step_key not in current_keys:
                row.active = False
        session.flush()
        return sorted(projected, key=lambda item: item.sequence)

    def sync_steps(self, problem_id: str, solution_id: str) -> list[SolutionStepView]:
        with self.session_factory.begin() as session:
            solution = self._require_solution(session, problem_id, solution_id)
            rows = self.sync_solution_steps(session, solution)
            return [self._step_view(row) for row in rows]

    def upsert_error_pattern_link(
        self,
        problem_id: str,
        payload: ProblemErrorPatternUpsert,
    ) -> ErrorPatternLinkView:
        with self.session_factory.begin() as session:
            problem = self._require_problem(session, problem_id)
            solution = self._require_solution(session, problem_id, payload.solution_id)
            self.sync_solution_steps(session, solution)
            step = self._require_step(
                session, solution.id, payload.solution_step_key
            )
            pattern = session.scalar(select(ErrorPattern).where(
                ErrorPattern.code == payload.pattern.code
            ))
            if pattern is None:
                pattern = ErrorPattern(code=payload.pattern.code)
                session.add(pattern)
            elif (
                pattern.subject != problem.subject
                or pattern.grade_band not in {None, problem.grade_band}
            ):
                raise TeachingContentConflict(
                    "error pattern code is already used in a different teaching scope"
                )
            pattern.title = payload.pattern.title
            pattern.description = payload.pattern.description
            pattern.subject = problem.subject
            pattern.grade_band = problem.grade_band
            pattern.severity = payload.pattern.severity
            pattern.detection_rule_json = payload.pattern.detection_rule
            pattern.remediation_json = payload.pattern.remediation
            pattern.active = True
            session.flush()

            link = session.scalar(select(ProblemErrorPattern).where(
                ProblemErrorPattern.solution_step_id == step.id,
                ProblemErrorPattern.error_pattern_id == pattern.id,
            ))
            if link is None:
                link = ProblemErrorPattern(
                    problem_id=problem.id,
                    solution_id=solution.id,
                    solution_step_id=step.id,
                    error_pattern_id=pattern.id,
                )
                session.add(link)
            link.trigger_evidence_json = payload.trigger_evidence
            link.diagnostic_prompt = payload.diagnostic_prompt
            link.remediation_goal = payload.remediation_goal
            link.priority = payload.priority
            link.active = payload.active
            session.flush()
            return self._error_link_view(link, step, pattern)

    def upsert_hint(
        self,
        problem_id: str,
        payload: HintBlueprintUpsert,
    ) -> HintBlueprintView:
        with self.session_factory.begin() as session:
            self._require_problem(session, problem_id)
            solution = self._require_solution(session, problem_id, payload.solution_id)
            self.sync_solution_steps(session, solution)
            step = None
            if payload.solution_step_key:
                step = self._require_step(session, solution.id, payload.solution_step_key)

            error_link = None
            if payload.problem_error_pattern_id:
                error_link = session.get(
                    ProblemErrorPattern, payload.problem_error_pattern_id
                )
                if error_link is None or error_link.problem_id != problem_id:
                    raise TeachingContentNotFound("problem error pattern not found")
                if error_link.solution_id != solution.id:
                    raise TeachingContentConflict(
                        "error pattern link belongs to a different solution"
                    )
                if step is not None and error_link.solution_step_id != step.id:
                    raise TeachingContentConflict(
                        "hint step does not match the error pattern step"
                    )
                step = session.get(KnowledgeSolutionStep, error_link.solution_step_id)

            if payload.hint_level == 3 and step is None:
                raise TeachingContentConflict("level 3 hint requires an active solution step")
            if step is not None and not step.active:
                raise TeachingContentConflict("hint cannot target an inactive solution step")
            if (
                payload.hint_level == 4
                and payload.review_status == HintReviewStatus.APPROVED
                and not self._is_fully_verified(solution)
            ):
                raise TeachingContentConflict(
                    "approved level 4 hint requires a fully verified solution"
                )

            hint_stage, reveal_scope = HINT_BOUNDARIES[payload.hint_level]
            binding_key = (
                f"error:{error_link.id}"
                if error_link is not None
                else f"step:{step.id}" if step is not None
                else f"solution:{solution.id}"
            )
            content_hash = self._hint_hash(
                payload,
            )
            hint = session.scalar(select(HintBlueprint).where(
                HintBlueprint.problem_id == problem_id,
                HintBlueprint.binding_key == binding_key,
                HintBlueprint.hint_level == payload.hint_level,
            ))
            duplicate = session.scalar(select(HintBlueprint).where(
                HintBlueprint.problem_id == problem_id,
                HintBlueprint.content_hash == content_hash,
                HintBlueprint.id != (hint.id if hint is not None else ""),
            ))
            if duplicate is not None:
                raise TeachingContentConflict(
                    "identical hint content already exists for this problem"
                )
            if hint is None:
                hint = HintBlueprint(
                    problem_id=problem_id,
                    solution_id=solution.id,
                    binding_key=binding_key,
                    hint_level=payload.hint_level,
                )
                session.add(hint)
            hint.solution_step_id = step.id if step else None
            hint.problem_error_pattern_id = error_link.id if error_link else None
            hint.hint_stage = hint_stage.value
            hint.reveal_scope = reveal_scope.value
            hint.content = payload.content
            hint.understanding_check = payload.understanding_check
            hint.knowledge_point_codes_json = payload.knowledge_point_codes
            hint.review_status = payload.review_status.value
            hint.source_type = payload.source_type.value
            hint.content_hash = content_hash
            hint.priority = payload.priority
            hint.active = (
                payload.active and payload.review_status != HintReviewStatus.RETIRED
            )
            session.flush()
            return self._hint_view(hint, step)

    def get_problem_teaching_map(self, problem_id: str) -> ProblemTeachingMap:
        with self.session_factory() as session:
            problem = self._require_problem(session, problem_id)
            solutions = session.scalars(
                select(KnowledgeSolution)
                .where(KnowledgeSolution.problem_id == problem_id)
                .order_by(KnowledgeSolution.is_preferred.desc(), KnowledgeSolution.created_at)
            ).all()
            steps = session.scalars(
                select(KnowledgeSolutionStep)
                .where(KnowledgeSolutionStep.problem_id == problem_id)
                .order_by(KnowledgeSolutionStep.solution_id, KnowledgeSolutionStep.sequence)
            ).all()
            step_by_id = {row.id: row for row in steps}
            steps_by_solution: dict[str, list[KnowledgeSolutionStep]] = {}
            for row in steps:
                steps_by_solution.setdefault(row.solution_id, []).append(row)

            links = session.scalars(
                select(ProblemErrorPattern)
                .where(ProblemErrorPattern.problem_id == problem_id)
                .order_by(ProblemErrorPattern.priority, ProblemErrorPattern.created_at)
            ).all()
            hints = session.scalars(
                select(HintBlueprint)
                .where(HintBlueprint.problem_id == problem_id)
                .order_by(HintBlueprint.hint_level, HintBlueprint.priority)
            ).all()
            return ProblemTeachingMap(
                problem_id=problem.id,
                problem_status=problem.content_status,
                solutions=[
                    TeachingSolutionView(
                        solution_id=solution.id,
                        method_name=solution.method_name,
                        verification_status=solution.verification_status,
                        verification_coverage=solution.verification_coverage_json,
                        steps=[
                            self._step_view(row)
                            for row in steps_by_solution.get(solution.id, [])
                        ],
                    )
                    for solution in solutions
                ],
                error_pattern_links=[
                    self._error_link_view(
                        link,
                        step_by_id[link.solution_step_id],
                        link.error_pattern,
                    )
                    for link in links
                ],
                hints=[
                    self._hint_view(
                        hint,
                        step_by_id.get(hint.solution_step_id),
                    )
                    for hint in hints
                ],
            )

    @staticmethod
    def _require_problem(session: Session, problem_id: str) -> KnowledgeProblem:
        problem = session.get(KnowledgeProblem, problem_id)
        if problem is None:
            raise TeachingContentNotFound("problem not found")
        return problem

    @staticmethod
    def _require_solution(
        session: Session,
        problem_id: str,
        solution_id: str,
    ) -> KnowledgeSolution:
        solution = session.get(KnowledgeSolution, solution_id)
        if solution is None or solution.problem_id != problem_id:
            raise TeachingContentNotFound("solution not found for problem")
        return solution

    @staticmethod
    def _require_step(
        session: Session,
        solution_id: str,
        step_key: str,
    ) -> KnowledgeSolutionStep:
        step = session.scalar(select(KnowledgeSolutionStep).where(
            KnowledgeSolutionStep.solution_id == solution_id,
            KnowledgeSolutionStep.step_key == step_key,
            KnowledgeSolutionStep.active.is_(True),
        ))
        if step is None:
            raise TeachingContentNotFound("active solution step not found")
        return step

    @staticmethod
    def _hint_hash(
        payload: HintBlueprintUpsert,
    ) -> str:
        canonical = {
            "hint_level": payload.hint_level,
            "content": payload.content.strip(),
            "understanding_check": payload.understanding_check.strip(),
            "knowledge_point_codes": sorted(payload.knowledge_point_codes),
        }
        return sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validate_step_set(steps: list[StructuredSolutionStep]) -> None:
        step_keys = [step.step_id for step in steps]
        sequences = [step.sequence for step in steps]
        if len(step_keys) != len(set(step_keys)):
            raise ValueError("step keys must be unique")
        if len(sequences) != len(set(sequences)):
            raise ValueError("step sequences must be unique")
        if sequences and sorted(sequences) != list(range(1, len(sequences) + 1)):
            raise ValueError("step sequences must be contiguous and start at 1")
        sequence_by_key = {step.step_id: step.sequence for step in steps}
        for step in steps:
            for dependency in step.depends_on_step_ids:
                if dependency not in sequence_by_key:
                    raise ValueError(f"unknown step dependency: {dependency}")
                if sequence_by_key[dependency] >= step.sequence:
                    raise ValueError("step dependency must point to an earlier step")

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
    def _step_view(row: KnowledgeSolutionStep) -> SolutionStepView:
        return SolutionStepView(
            id=row.id,
            problem_id=row.problem_id,
            solution_id=row.solution_id,
            step_key=row.step_key,
            sequence=row.sequence,
            action=row.action,
            result=row.result,
            justifications=row.justifications_json,
            depends_on_step_keys=row.depends_on_step_keys_json,
            condition_refs=row.condition_refs_json,
            knowledge_point_codes=row.knowledge_point_codes_json,
            content_hash=row.content_hash,
            active=row.active,
            updated_at=TeachingContentRepository._utc(row.updated_at),
        )

    @staticmethod
    def _error_link_view(
        link: ProblemErrorPattern,
        step: KnowledgeSolutionStep,
        pattern: ErrorPattern,
    ) -> ErrorPatternLinkView:
        return ErrorPatternLinkView(
            id=link.id,
            problem_id=link.problem_id,
            solution_id=link.solution_id,
            solution_step_id=step.id,
            solution_step_key=step.step_key,
            error_pattern_id=pattern.id,
            pattern_code=pattern.code,
            pattern_title=pattern.title,
            pattern_description=pattern.description,
            severity=pattern.severity,
            detection_rule=pattern.detection_rule_json,
            remediation=pattern.remediation_json,
            trigger_evidence=link.trigger_evidence_json,
            diagnostic_prompt=link.diagnostic_prompt,
            remediation_goal=link.remediation_goal,
            priority=link.priority,
            active=link.active and pattern.active and step.active,
            updated_at=TeachingContentRepository._utc(link.updated_at),
        )

    @staticmethod
    def _hint_view(
        hint: HintBlueprint,
        step: KnowledgeSolutionStep | None,
    ) -> HintBlueprintView:
        return HintBlueprintView(
            id=hint.id,
            problem_id=hint.problem_id,
            solution_id=hint.solution_id,
            solution_step_id=hint.solution_step_id,
            solution_step_key=step.step_key if step else None,
            problem_error_pattern_id=hint.problem_error_pattern_id,
            hint_level=hint.hint_level,
            hint_stage=HintStage(hint.hint_stage),
            reveal_scope=RevealScope(hint.reveal_scope),
            content=hint.content,
            understanding_check=hint.understanding_check,
            knowledge_point_codes=hint.knowledge_point_codes_json,
            review_status=HintReviewStatus(hint.review_status),
            source_type=HintSourceType(hint.source_type),
            priority=hint.priority,
            active=(
                hint.active
                and (step is None or step.active)
                and (
                    hint.problem_error_pattern is None
                    or hint.problem_error_pattern.active
                )
            ),
            content_hash=hint.content_hash,
            updated_at=TeachingContentRepository._utc(hint.updated_at),
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
