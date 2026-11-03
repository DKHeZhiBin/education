from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import sympy as sp

from app.domain.evaluation import GenerationEvaluationCase
from app.domain.generation_evaluation import (
    FixedGenerationQualityMetric,
    FixedGenerationQualityReport,
    GenerationCaseQuality,
    GenerationEvaluationRunRecord,
)
from app.evaluation.datasets import (
    DEFAULT_GENERATION_MANIFEST,
    EvaluationDatasetError,
    load_generation_evaluation_suite,
)
from app.mcp_tools.safe_math import UnsafeMathExpression, parse_equation, parse_expression


class FixedGenerationQualityEvaluator:
    """中文：定义“fixed·生成·质量·evaluator”类，封装该职责相关的数据与行为。
    English: Defines the fixed generation quality evaluator class and encapsulates data and behavior for that responsibility.
    """
    def evaluate(
        self,
        records: list[GenerationEvaluationRunRecord],
        *,
        manifest_path: str | Path = DEFAULT_GENERATION_MANIFEST,
        production_collection: str,
    ) -> FixedGenerationQualityReport:
        """中文：处理“评估”相关操作。
        English: Handles the evaluate operation.
        """
        manifest, cases, summary = load_generation_evaluation_suite(
            manifest_path,
            production_collection=production_collection,
        )
        if not records:
            raise EvaluationDatasetError("Generation evaluation run is empty")
        case_by_id = {item.id: item for item in cases}
        record_ids = [item.case_id for item in records]
        if len(record_ids) != len(set(record_ids)):
            raise EvaluationDatasetError(
                "A generation run may contain only one record per fixed case"
            )
        unknown = set(record_ids) - case_by_id.keys()
        if unknown:
            raise EvaluationDatasetError(
                f"Generation run references unknown cases: {sorted(unknown)}"
            )
        run_ids = {item.run_id for item in records}
        if len(run_ids) != 1:
            raise EvaluationDatasetError("Generation records must share one run_id")
        model_versions = {item.model_version for item in records}
        prompt_versions = {item.prompt_version for item in records}
        code_revisions = {item.code_revision for item in records}
        if any(len(values) != 1 for values in (
            model_versions, prompt_versions, code_revisions
        )):
            raise EvaluationDatasetError(
                "One evaluation run must use one model, prompt and code revision"
            )

        results = [
            self._evaluate_case(record, case_by_id[record.case_id])
            for record in records
        ]
        admitted = [item for item in results if item.admitted]
        erroneous = [item for item in admitted if item.erroneous_admission]
        correct = [item for item in results if item.answer_correct]
        covered = [item for item in results if item.verification_fully_covered]
        total = len(results)
        return FixedGenerationQualityReport(
            generated_at=datetime.now(timezone.utc),
            run_id=next(iter(run_ids)),
            suite_name=manifest.name,
            dataset_sha256=summary.verified_sha256["dataset"],
            model_version=next(iter(model_versions)),
            prompt_version=next(iter(prompt_versions)),
            code_revision=next(iter(code_revisions)),
            expected_case_count=len(cases),
            evaluated_case_count=total,
            case_coverage=round(total / len(cases), 6),
            metrics=[
                self._metric(
                    key="erroneous_admission_rate",
                    label="错误准入率",
                    numerator=len(erroneous),
                    denominator=len(admitted),
                    definition=(
                        "自动 approve 的固定案例中，答案错误、条件检查未通过、"
                        "确定性验证覆盖不足、存在失败校验或硬失败的比例。"
                    ),
                ),
                self._metric(
                    key="answer_correctness_rate",
                    label="答案正确率",
                    numerator=len(correct),
                    denominator=total,
                    definition=(
                        "生成方程的实根集合和隔离解题结果均与冻结 Oracle 实根集合数学等价的比例。"
                    ),
                ),
                self._metric(
                    key="deterministic_verification_coverage_rate",
                    label="确定性验证覆盖率",
                    numerator=len(covered),
                    denominator=total,
                    definition=(
                        "覆盖级别为 full，且案例声明的全部确定性检查都形成 passed 或 failed 结论的比例。"
                    ),
                ),
            ],
            cases=results,
            notes=[
                "报告只读取冻结 manifest、Oracle 和隔离运行结果，不写入生产数据库或索引。",
                "答案解析失败按错误计入分母；缺失、not_run 和 inconclusive 检查按覆盖不足处理。",
                "错误准入率没有 approve 样本时返回 no_samples，不能解释为 0%。",
                "case_coverage 小于 1 时表示报告不是完整固定集结果。",
            ],
        )

    def _evaluate_case(
        self,
        record: GenerationEvaluationRunRecord,
        case: GenerationEvaluationCase,
    ) -> GenerationCaseQuality:
        """中文：处理“评估·case”相关操作。
        English: Handles the evaluate case operation.
        """
        expected_roots = self._expressions(case.oracle.real_solutions)
        try:
            generated_roots = self._equation_roots(record.normalized_equation)
            equation_correct = self._same_values(generated_roots, expected_roots)
        except (UnsafeMathExpression, ValueError, TypeError, sp.SympifyError):
            equation_correct = False
        try:
            solved_roots = self._expressions(record.independently_solved_real_roots)
            independent_correct = self._same_values(solved_roots, expected_roots)
        except (UnsafeMathExpression, ValueError, TypeError, sp.SympifyError):
            independent_correct = False
        answer_correct = equation_correct and independent_correct

        required_checks = set(case.scoring.get("deterministic_checks") or [])
        definitive = {"passed", "failed"}
        missing_checks = sorted(
            check
            for check in required_checks
            if record.deterministic_checks.get(check) not in definitive
        )
        failed_checks = sorted(
            check
            for check, status in record.deterministic_checks.items()
            if status == "failed"
        )
        fully_covered = (
            record.verification_coverage_level == "full" and not missing_checks
        )
        hard_failures = sorted(set(record.hard_failure_codes))
        admitted = record.admission_decision == "approve"
        reasons: list[str] = []
        if not answer_correct:
            reasons.append("answer_incorrect")
        if record.condition_check_status != "passed":
            reasons.append("condition_check_not_passed")
        if not fully_covered:
            reasons.append("verification_coverage_insufficient")
        if failed_checks:
            reasons.append("deterministic_check_failed")
        if hard_failures:
            reasons.append("hard_failure_detected")
        return GenerationCaseQuality(
            case_id=case.id,
            answer_correct=answer_correct,
            equation_roots_correct=equation_correct,
            independent_roots_correct=independent_correct,
            verification_fully_covered=fully_covered,
            admitted=admitted,
            erroneous_admission=bool(admitted and reasons),
            condition_check_status=record.condition_check_status,
            admission_decision=record.admission_decision,
            missing_deterministic_checks=missing_checks,
            failed_deterministic_checks=failed_checks,
            hard_failure_codes=hard_failures,
            reason_codes=reasons,
        )

    @staticmethod
    def _equation_roots(value: str) -> tuple[sp.Expr, ...]:
        """中文：处理“equation·roots”相关操作。
        English: Handles the equation roots operation.
        """
        parsed = parse_equation(value)
        symbols = sorted(parsed.residual.free_symbols, key=lambda item: item.name)
        if len(symbols) != 1:
            raise ValueError("evaluation equation must contain exactly one variable")
        roots = sp.solveset(parsed.residual, symbols[0], domain=sp.S.Reals)
        if not isinstance(roots, sp.FiniteSet):
            raise ValueError("evaluation equation must have a finite real solution set")
        return tuple(roots)

    @staticmethod
    def _expressions(values: list[str]) -> tuple[sp.Expr, ...]:
        """中文：处理“expressions”相关操作。
        English: Handles the expressions operation.
        """
        parsed = tuple(parse_expression(value) for value in values)
        if any(item.free_symbols or item.is_real is False for item in parsed):
            raise ValueError("evaluation roots must be known real values")
        return parsed

    @staticmethod
    def _same_values(left: tuple[sp.Expr, ...], right: tuple[sp.Expr, ...]) -> bool:
        """中文：处理“same·values”相关操作。
        English: Handles the same values operation.
        """
        if len(left) != len(right):
            return False
        unmatched = list(right)
        for value in left:
            match = next(
                (index for index, expected in enumerate(unmatched)
                 if sp.simplify(value - expected) == 0),
                None,
            )
            if match is None:
                return False
            unmatched.pop(match)
        return not unmatched

    @staticmethod
    def _metric(
        *, key: str, label: str, numerator: int, denominator: int, definition: str
    ) -> FixedGenerationQualityMetric:
        """中文：处理“指标”相关操作。
        English: Handles the metric operation.
        """
        rate = numerator / denominator if denominator else None
        return FixedGenerationQualityMetric(
            key=key,
            label=label,
            numerator=numerator,
            denominator=denominator,
            rate=round(rate, 6) if rate is not None else None,
            percentage=round(rate * 100, 2) if rate is not None else None,
            status="available" if denominator else "no_samples",
            definition=definition,
        )
