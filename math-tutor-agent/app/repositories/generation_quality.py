from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import create_mysql_engine, create_session_factory
from app.domain.generation_quality import (
    ErroneousAdmissionFinding,
    GenerationQualityReport,
    GenerationQualityScope,
    build_quality_metric,
)
from app.domain.problem_lifecycle import (
    PROBLEM_SCOPED_APPROVAL_EVIDENCE,
    REQUIRED_APPROVAL_EVIDENCE,
    SOLUTION_SCOPED_APPROVAL_EVIDENCE,
)
from app.models.generation import AdmissionEvidence, GenerationBatch
from app.models.knowledge import KnowledgeProblem, KnowledgeSolution


ANSWER_EVIDENCE = frozenset({
    "symbolic_verification",
    "numeric_verification",
    "constraint_verification",
})
SOLUTION_DETERMINISTIC_EVIDENCE = frozenset({
    *ANSWER_EVIDENCE,
    "duplicate_detection",
})
DEFINITIVE_STATUSES = frozenset({"passed", "failed"})
FINAL_ADMISSION_DECISIONS = frozenset({"approve", "revise", "quarantine"})


class GenerationQualityRepository:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self.session_factory = session_factory or create_session_factory(create_mysql_engine())

    def report(self, scope: GenerationQualityScope) -> GenerationQualityReport:
        with self.session_factory() as session:
            return self._report(session, scope)

    def _report(
        self, session: Session, scope: GenerationQualityScope
    ) -> GenerationQualityReport:
        filters = [KnowledgeProblem.generation_batch_id.is_not(None)]
        if scope.batch_id:
            filters.append(KnowledgeProblem.generation_batch_id == scope.batch_id)
        if scope.topic_code:
            filters.append(GenerationBatch.topic_code == scope.topic_code)
        if scope.batch_purpose:
            filters.append(GenerationBatch.purpose == scope.batch_purpose)
        if scope.created_from:
            filters.append(
                KnowledgeProblem.created_at >= self._mysql_datetime(scope.created_from)
            )
        if scope.created_to:
            filters.append(
                KnowledgeProblem.created_at < self._mysql_datetime(scope.created_to)
            )

        problems = list(session.scalars(
            select(KnowledgeProblem)
            .join(GenerationBatch, GenerationBatch.id == KnowledgeProblem.generation_batch_id)
            .where(*filters)
            .order_by(KnowledgeProblem.created_at, KnowledgeProblem.id)
        ))
        problem_ids = [item.id for item in problems]
        if not problem_ids:
            return self._empty_report(scope)

        evidence = list(session.scalars(
            select(AdmissionEvidence)
            .where(AdmissionEvidence.problem_id.in_(problem_ids))
            .order_by(AdmissionEvidence.created_at, AdmissionEvidence.id)
        ))
        solutions = list(session.scalars(
            select(KnowledgeSolution).where(KnowledgeSolution.problem_id.in_(problem_ids))
        ))
        solution_by_id = {item.id: item for item in solutions}
        evidence_by_problem: dict[str, list[AdmissionEvidence]] = defaultdict(list)
        for item in evidence:
            evidence_by_problem[item.problem_id].append(item)

        valid_numerator = 0
        valid_denominator = 0
        answer_numerator = 0
        answer_denominator = 0
        covered_count = 0
        duplicate_detected = 0
        duplicate_blocked = 0
        admitted = 0
        final_decisions = 0
        auto_approved_content = 0
        erroneous_admissions: list[ErroneousAdmissionFinding] = []

        for problem in problems:
            current = self._current_evidence(
                problem,
                evidence_by_problem.get(problem.id, []),
                solution_by_id,
            )
            condition = current.get("condition_completeness")
            if condition is not None and condition.status in DEFINITIVE_STATUSES:
                valid_denominator += 1
                valid_numerator += condition.status == "passed"

            selected_solution_id = self._selected_solution_id(current)
            answer_items = [
                current.get((evidence_type, selected_solution_id))
                for evidence_type in ANSWER_EVIDENCE
            ] if selected_solution_id else []
            if answer_items and all(
                item is not None and item.status in DEFINITIVE_STATUSES
                for item in answer_items
            ):
                answer_denominator += 1
                answer_numerator += all(item.status == "passed" for item in answer_items)

            coverage_items = (
                [
                    current.get((evidence_type, selected_solution_id))
                    for evidence_type in SOLUTION_DETERMINISTIC_EVIDENCE
                ]
                + [current.get("evaluation_leakage_detection")]
                if selected_solution_id
                else []
            )
            if coverage_items and all(
                item is not None and item.status in DEFINITIVE_STATUSES
                for item in coverage_items
            ):
                covered_count += 1

            duplicate = (
                current.get(("duplicate_detection", selected_solution_id))
                if selected_solution_id else None
            )
            decision = current.get("admission_decision")
            decision_name = self._decision_name(decision)
            if duplicate is not None and duplicate.status == "failed":
                duplicate_detected += 1
                if decision_name in {"revise", "quarantine"}:
                    duplicate_blocked += 1

            if decision_name in FINAL_ADMISSION_DECISIONS:
                final_decisions += 1
                admitted += decision_name == "approve"

            problem_evidence = evidence_by_problem.get(problem.id, [])
            if self._has_current_content_approval(problem, problem_evidence):
                auto_approved_content += 1
                finding = self._erroneous_admission_finding(
                    problem,
                    problem_evidence,
                    solution_by_id,
                )
                if finding is not None:
                    erroneous_admissions.append(finding)

        total = len(problems)
        metrics = [
            build_quality_metric(
                key="problem_validity_rate",
                label="题意有效率",
                numerator=valid_numerator,
                denominator=valid_denominator,
                unavailable_count=total - valid_denominator,
                numerator_definition="最新且绑定当前题目内容的 condition_completeness=passed",
                denominator_definition="已有 passed 或 failed 条件完整性结论的生成题",
            ),
            build_quality_metric(
                key="answer_correctness_rate",
                label="答案正确率",
                numerator=answer_numerator,
                denominator=answer_denominator,
                unavailable_count=total - answer_denominator,
                numerator_definition="同一选定题解的符号、数值、约束验证全部 passed",
                denominator_definition="同一选定题解的三类答案验证均已有 passed 或 failed 结论的生成题",
            ),
            build_quality_metric(
                key="deterministic_verification_coverage_rate",
                label="确定性验证覆盖率",
                numerator=covered_count,
                denominator=total,
                unavailable_count=total - covered_count,
                numerator_definition="当前内容已完成符号、数值、约束、重复及评估泄漏五类确定性检查",
                denominator_definition="范围内全部生成题",
            ),
            build_quality_metric(
                key="duplicate_block_rate",
                label="重复拦截率",
                numerator=duplicate_blocked,
                denominator=duplicate_detected,
                unavailable_count=0,
                numerator_definition="重复检测失败后自动决策为 revise 或 quarantine 的题",
                denominator_definition="最新重复检测结论为 failed 的题；没有确认重复时返回 no_samples",
            ),
            build_quality_metric(
                key="automatic_admission_rate",
                label="自动准入率",
                numerator=admitted,
                denominator=final_decisions,
                unavailable_count=total - final_decisions,
                numerator_definition="最终自动准入决策为 approve 的题",
                denominator_definition="已形成 approve、revise 或 quarantine 最终自动决策的生成题",
            ),
            build_quality_metric(
                key="erroneous_admission_rate",
                label="错误内容自动准入率",
                numerator=len(erroneous_admissions),
                denominator=auto_approved_content,
                unavailable_count=0,
                numerator_definition="自动批准时证据不满足门槛，或批准后同一内容被确定性阻断证据确认失败",
                denominator_definition="当前内容版本曾获得 approve 自动决策的生成题",
            ),
        ]
        return GenerationQualityReport(
            generated_at=datetime.now(timezone.utc),
            scope=scope,
            candidate_count=total,
            metrics=metrics,
            erroneous_admissions=erroneous_admissions,
            notes=[
                "not_run、inconclusive 和缺失证据不进入正确率分母，并计入 unavailable_count。",
                "重复拦截率衡量规则门是否阻止已确认重复内容，不代表题库自然重复发生率。",
                "学生报告和运行时冲突只触发重新验证；没有确定性失败证据时不直接计为错误准入。",
            ],
        )

    @classmethod
    def _erroneous_admission_finding(
        cls,
        problem: KnowledgeProblem,
        evidence: list[AdmissionEvidence],
        solution_by_id: dict[str, KnowledgeSolution],
    ) -> ErroneousAdmissionFinding | None:
        approvals = [
            item for item in evidence
            if item.evidence_type == "admission_decision"
            and item.generation_batch_id == problem.generation_batch_id
            and (item.payload_json or {}).get("problem_content_hash") == problem.content_hash
            and (item.payload_json or {}).get("decision") == "approve"
        ]
        if not approvals:
            return None
        approval = approvals[0]
        payload = approval.payload_json or {}
        selected_solution_id = payload.get("selected_solution_id")
        reasons: set[str] = set()
        failed_ids: set[str] = set()

        for field in (
            "deterministic_failures",
            "other_failures",
            "missing_evidence",
            "inconclusive_evidence",
        ):
            if payload.get(field):
                reasons.add(f"approval_payload_{field}")

        checked_ids = {
            value for value in payload.get("checked_evidence_ids", [])
            if isinstance(value, str)
        }
        latest_at_approval: dict[str, AdmissionEvidence] = {}
        for item in evidence:
            if item.id == approval.id or item.evidence_type == "admission_decision":
                continue
            if item.generation_batch_id != problem.generation_batch_id:
                continue
            if item.id not in checked_ids:
                continue
            if not cls._matches_approved_content(
                problem, item, selected_solution_id, solution_by_id
            ):
                continue
            if item.evidence_type in REQUIRED_APPROVAL_EVIDENCE:
                latest_at_approval[item.evidence_type] = item

        missing = REQUIRED_APPROVAL_EVIDENCE - latest_at_approval.keys()
        if missing:
            reasons.add("approval_missing_required_evidence")
        non_passed = [
            item for item in latest_at_approval.values() if item.status != "passed"
        ]
        if non_passed:
            reasons.add("approval_with_non_passed_evidence")
            failed_ids.update(item.id for item in non_passed)

        for item in evidence:
            if item.evidence_type == "admission_decision" or not item.is_blocking:
                continue
            if item.status != "failed" or item.created_at <= approval.created_at:
                continue
            if not cls._matches_approved_content(
                problem, item, selected_solution_id, solution_by_id
            ):
                continue
            reasons.add("post_admission_blocking_failure")
            failed_ids.add(item.id)

        if not reasons:
            return None
        return ErroneousAdmissionFinding(
            problem_id=problem.id,
            generation_batch_id=problem.generation_batch_id,
            problem_content_hash=problem.content_hash,
            admission_evidence_id=approval.id,
            selected_solution_id=(
                selected_solution_id if isinstance(selected_solution_id, str) else None
            ),
            current_content_status=problem.content_status,
            reason_codes=sorted(reasons),
            failed_evidence_ids=sorted(failed_ids),
        )

    @staticmethod
    def _has_current_content_approval(
        problem: KnowledgeProblem, evidence: list[AdmissionEvidence]
    ) -> bool:
        return any(
            item.evidence_type == "admission_decision"
            and item.generation_batch_id == problem.generation_batch_id
            and (item.payload_json or {}).get("problem_content_hash") == problem.content_hash
            and (item.payload_json or {}).get("decision") == "approve"
            for item in evidence
        )

    @staticmethod
    def _matches_approved_content(
        problem: KnowledgeProblem,
        evidence: AdmissionEvidence,
        selected_solution_id: object,
        solution_by_id: dict[str, KnowledgeSolution],
    ) -> bool:
        payload = evidence.payload_json or {}
        if evidence.evidence_type in PROBLEM_SCOPED_APPROVAL_EVIDENCE:
            if evidence.solution_id is not None:
                return False
            if evidence.evidence_type == "source_rights_clearance":
                return True
            return payload.get("problem_content_hash") == problem.content_hash
        if evidence.evidence_type in SOLUTION_SCOPED_APPROVAL_EVIDENCE:
            if not isinstance(selected_solution_id, str):
                return False
            solution = solution_by_id.get(selected_solution_id)
            return bool(
                solution is not None
                and evidence.solution_id == selected_solution_id
                and payload.get("problem_content_hash") == problem.content_hash
                and payload.get("solution_content_hash") == solution.content_hash
            )
        return payload.get("problem_content_hash") == problem.content_hash

    @staticmethod
    def _current_evidence(
        problem: KnowledgeProblem,
        evidence: list[AdmissionEvidence],
        solution_by_id: dict[str, KnowledgeSolution],
    ) -> dict:
        latest: dict = {}
        for item in evidence:
            if item.generation_batch_id != problem.generation_batch_id:
                continue
            payload = item.payload_json or {}
            if payload.get("problem_content_hash") != problem.content_hash:
                continue
            if item.solution_id is not None:
                solution = solution_by_id.get(item.solution_id)
                if solution is None or solution.problem_id != problem.id:
                    continue
                if payload.get("solution_content_hash") != solution.content_hash:
                    continue
                latest[(item.evidence_type, item.solution_id)] = item
            else:
                latest[item.evidence_type] = item
        decisions = [
            item for item in evidence
            if item.evidence_type == "admission_decision"
            and item.generation_batch_id == problem.generation_batch_id
            and (item.payload_json or {}).get("problem_content_hash") == problem.content_hash
        ]
        if decisions:
            latest["admission_decision"] = decisions[-1]
        return latest

    @staticmethod
    def _selected_solution_id(current: dict) -> str | None:
        decision = current.get("admission_decision")
        if decision is not None:
            selected = (decision.payload_json or {}).get("selected_solution_id")
            if isinstance(selected, str) and selected:
                return selected
        candidates = {
            key[1]
            for key in current
            if isinstance(key, tuple) and key[0] in ANSWER_EVIDENCE
        }
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda solution_id: max(
                (
                    current[(evidence_type, solution_id)].created_at
                    for evidence_type in ANSWER_EVIDENCE
                    if (evidence_type, solution_id) in current
                ),
                default=datetime.min,
            ),
        )

    @staticmethod
    def _decision_name(decision: AdmissionEvidence | None) -> str | None:
        if decision is None:
            return None
        value = (decision.payload_json or {}).get("decision")
        return value if isinstance(value, str) else None

    @staticmethod
    def _mysql_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _empty_report(scope: GenerationQualityScope) -> GenerationQualityReport:
        definitions = [
            ("problem_validity_rate", "题意有效率", "有效题意", "已有明确条件检查结论的生成题"),
            ("answer_correctness_rate", "答案正确率", "答案验证全部通过", "三类答案验证均有明确结论的生成题"),
            ("deterministic_verification_coverage_rate", "确定性验证覆盖率", "完成全部确定性检查", "范围内全部生成题"),
            ("duplicate_block_rate", "重复拦截率", "已阻止的确认重复题", "确认重复的生成题"),
            ("automatic_admission_rate", "自动准入率", "自动批准题", "已有最终自动决策的生成题"),
            ("erroneous_admission_rate", "错误内容自动准入率", "错误自动批准题", "曾获得自动批准的生成题"),
        ]
        return GenerationQualityReport(
            generated_at=datetime.now(timezone.utc),
            scope=scope,
            candidate_count=0,
            metrics=[
                build_quality_metric(
                    key=key,
                    label=label,
                    numerator=0,
                    denominator=0,
                    unavailable_count=0,
                    numerator_definition=numerator_definition,
                    denominator_definition=denominator_definition,
                )
                for key, label, numerator_definition, denominator_definition in definitions
            ],
            erroneous_admissions=[],
            notes=["当前筛选范围内没有生成题，所有指标均为 no_samples。"],
        )
