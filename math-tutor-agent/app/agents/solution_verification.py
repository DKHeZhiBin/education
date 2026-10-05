import json
import re
from typing import Any

from app.domain.verification import (
    ProofCriterionReview,
    ProofReview,
    VerificationCheck,
    VerificationReport,
)
from app.domain.verification_scope_policy import (
    ProblemVerificationScope,
    classify_problem_verification_scope,
    restricted_coverage_reason,
)
from app.mcp_tools.math_tools import (
    compare_math_steps,
    simplify_expression,
    solve_equation,
    verify_candidate_answer,
)
from app.prompts.policies import PROOF_VERIFICATION_PROMPT, SOLUTION_VERIFICATION_PROMPT
from app.providers.llm import OpenAICompatibleProvider


EQUATION_TYPES = {
    "equation",
    "linear_equation",
    "quadratic_equation",
}
EXPRESSION_TYPES = {"arithmetic", "algebraic_expression"}
MATH_CHARACTERS = r"A-Za-z0-9\s+\-−×÷*/^().（）"
PROOF_CRITERIA = (
    "claim_alignment",
    "condition_usage",
    "logical_continuity",
    "theorem_applicability",
    "case_completeness",
    "conclusion_closure",
)
PROOF_OPTIONAL_CRITERIA = {"theorem_applicability", "case_completeness"}
PROOF_CRITERION_CONFIDENCE_THRESHOLD = 0.75
PROOF_PASS_THRESHOLD = 0.80
PROOF_MODEL_CONFIDENCE_CAP = 0.74


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _string_list(value: object, limit: int = 30) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(
        text for item in value if (text := _clean_text(item))
    ))[:limit]


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _confidence(value: object, default: float) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return default


class SolutionVerificationAgent:
    """Uses safe SymPy tools first and model review only for uncovered reasoning."""

    name = "solution_verification"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(self, problem: dict, solution: dict) -> dict[str, Any]:
        if solution.get("answer_consistency") == "conflict":
            return VerificationReport(
                passed=False,
                verifier_type="unverified",
                coverage="none",
                evidence="候选解法给出了不一致的答案。",
                issues=["候选解法答案不一致，必须先修订 SolutionPlan"],
                confidence=0.98,
            ).model_dump(mode="json")

        if self._is_proof_problem(problem):
            return self._verify_proof(problem, solution).model_dump(mode="json")
        if self._is_open_ended_problem(problem):
            return self._verify_open_ended(problem, solution).model_dump(mode="json")

        cas_report = self._run_cas(problem, solution)
        has_failure = any(check.status == "failed" for check in cas_report.checks)
        if has_failure:
            cas_report.passed = False
            cas_report.verifier_type = "cas"
            cas_report.confidence = max(cas_report.confidence, 0.95)
            return cas_report.model_dump(mode="json")

        if cas_report.coverage == "full":
            cas_report.passed = True
            cas_report.verifier_type = "cas"
            cas_report.confidence = max(cas_report.confidence, 0.94)
            return cas_report.model_dump(mode="json")

        model_result = self.provider.complete_json(
            SOLUTION_VERIFICATION_PROMPT,
            json.dumps({
                "problem": problem,
                "candidate_solution": solution,
                "cas_report": cas_report.model_dump(mode="json"),
            }, ensure_ascii=False),
        )
        if not model_result:
            cas_report.passed = False
            cas_report.verifier_type = (
                "cas" if cas_report.coverage == "partial" else "unverified"
            )
            cas_report.limitations = list(dict.fromkeys([
                *cas_report.limitations,
                "SymPy 未完全覆盖该解法，且模型复核不可用",
            ]))
            cas_report.confidence = min(cas_report.confidence or 0.3, 0.49)
            return cas_report.model_dump(mode="json")

        model_passed = _boolean(model_result.get("passed", False))
        issues = list(dict.fromkeys([
            *cas_report.issues,
            *_string_list(model_result.get("issues")),
        ]))
        limitations = list(dict.fromkeys([
            *cas_report.limitations,
            *_string_list(model_result.get("limitations")),
        ]))
        model_evidence = _clean_text(model_result.get("evidence"))
        evidence = "；".join(
            item for item in (cas_report.evidence, model_evidence) if item
        )
        return VerificationReport(
            passed=model_passed,
            verifier_type="hybrid" if cas_report.checks else "model",
            coverage="full" if model_passed else cas_report.coverage,
            checks=cas_report.checks,
            evidence=evidence,
            issues=issues,
            limitations=limitations,
            confidence=_confidence(model_result.get("confidence"), 0.55),
        ).model_dump(mode="json")

    def _verify_proof(self, problem: dict, solution: dict) -> VerificationReport:
        structural_issues = self._proof_structure_issues(problem, solution)
        if structural_issues:
            return VerificationReport(
                passed=False,
                verifier_type="unverified",
                coverage="none",
                evidence="证明输入缺少形成可审查论证所需的结构。",
                issues=structural_issues,
                limitations=["尚未进入证明内容复核"],
                confidence=0.92,
            )

        result = self.provider.complete_json(
            PROOF_VERIFICATION_PROMPT,
            json.dumps({
                "problem": problem,
                "candidate_solution": solution,
            }, ensure_ascii=False),
        )
        if not result:
            return VerificationReport(
                passed=False,
                verifier_type="unverified",
                coverage="none",
                evidence="证明题不在 SymPy 覆盖范围内，且证明复核模型不可用。",
                limitations=[
                    "没有形式化证明器或人工审核证据",
                    "证明复核模型不可用",
                ],
                confidence=0.2,
            )

        criteria = self._proof_criteria(result.get("criteria"))
        by_name = {item.criterion: item for item in criteria}
        for criterion in PROOF_CRITERIA:
            if criterion not in by_name:
                missing = ProofCriterionReview(
                    criterion=criterion,
                    status="unverified",
                    evidence="模型没有返回该必需审查维度。",
                    confidence=0.0,
                )
                criteria.append(missing)
                by_name[criterion] = missing

        hard_blockers = _string_list(result.get("hard_blockers"))
        unverified_claims = _string_list(result.get("unverified_claims"))
        issues = list(dict.fromkeys([
            *_string_list(result.get("issues")),
            *hard_blockers,
        ]))
        limitations = list(dict.fromkeys([
            *_string_list(result.get("limitations")),
            "单模型证明审查不能替代形式化证明器或人工审核",
        ]))
        invalid_not_applicable = [
            item.criterion
            for item in criteria
            if item.status == "not_applicable"
            and item.criterion not in PROOF_OPTIONAL_CRITERIA
        ]
        failed = [item for item in criteria if item.status == "failed"]
        unverified = [item for item in criteria if item.status == "unverified"]
        if invalid_not_applicable:
            issues.append(
                "必需审查维度不能标记为不适用："
                + "、".join(invalid_not_applicable)
            )
        if unverified_claims:
            limitations.append("证明仍包含无法核验的关键主张")

        raw_confidence = _confidence(result.get("confidence"), 0.0)
        policy_passed = (
            _boolean(result.get("passed", False))
            and raw_confidence >= PROOF_PASS_THRESHOLD
            and not hard_blockers
            and not unverified_claims
            and not failed
            and not unverified
            and not invalid_not_applicable
        )
        if _boolean(result.get("passed", False)) and raw_confidence < PROOF_PASS_THRESHOLD:
            limitations.append(
                f"模型原始置信度低于暂时通过门槛 {PROOF_PASS_THRESHOLD:.2f}"
            )

        checks = [VerificationCheck(
            id=f"proof_{item.criterion}",
            kind="proof_criterion",
            status=("skipped" if item.status == "unverified" else item.status),
            tool="proof_model_review",
            evidence=item.evidence,
        ) for item in criteria]
        if policy_passed:
            final_confidence = min(raw_confidence, PROOF_MODEL_CONFIDENCE_CAP)
            evidence = _clean_text(result.get("evidence")) or (
                "六个证明审查维度均有证据，未发现阻断问题；仅允许教学流程暂时采用。"
            )
        elif failed or hard_blockers:
            final_confidence = min(max(raw_confidence, 0.75), 0.95)
            evidence = _clean_text(result.get("evidence")) or "证明存在明确的逻辑阻断问题。"
        else:
            final_confidence = min(raw_confidence, 0.49)
            evidence = _clean_text(result.get("evidence")) or "当前证据不足以接受该证明。"

        return VerificationReport(
            passed=policy_passed,
            verifier_type="model",
            coverage="partial",
            checks=checks,
            evidence=evidence,
            issues=list(dict.fromkeys(issues)),
            limitations=list(dict.fromkeys(limitations)),
            confidence=final_confidence,
            proof_review=ProofReview(
                criteria=criteria,
                hard_blockers=hard_blockers,
                unverified_claims=unverified_claims,
                raw_confidence=raw_confidence,
                confidence_cap=PROOF_MODEL_CONFIDENCE_CAP,
            ),
        )

    def _verify_open_ended(
        self,
        problem: dict,
        solution: dict,
    ) -> VerificationReport:
        result = self.provider.complete_json(
            SOLUTION_VERIFICATION_PROMPT,
            json.dumps({
                "problem": problem,
                "candidate_solution": solution,
                "coverage_policy": {
                    "maximum_automatic_coverage": "partial",
                    "full_coverage_requires": [
                        "exhaustive_rubric_verification",
                        "qualified_human_review",
                    ],
                },
            }, ensure_ascii=False),
        )
        limitation = restricted_coverage_reason(
            ProblemVerificationScope.OPEN_ENDED
        )
        if not result:
            return VerificationReport(
                passed=False,
                verifier_type="unverified",
                coverage="none",
                evidence="开放题缺少可用的结构化复核结果。",
                limitations=[limitation, "开放题复核模型不可用"],
                confidence=0.2,
            )
        return VerificationReport(
            passed=_boolean(result.get("passed", False)),
            verifier_type="model",
            coverage="partial",
            evidence=_clean_text(result.get("evidence")) or "完成开放题结构化模型复核。",
            issues=_string_list(result.get("issues")),
            limitations=list(dict.fromkeys([
                *_string_list(result.get("limitations")),
                limitation,
            ])),
            confidence=min(_confidence(result.get("confidence"), 0.5), 0.74),
        )

    @staticmethod
    def _is_proof_problem(problem: dict) -> bool:
        target = problem.get("target")
        return (
            _clean_text(problem.get("question_type")) == "proof"
            or (
                isinstance(target, dict)
                and (
                    _clean_text(target.get("action")) == "prove"
                    or _clean_text(target.get("expected_answer_type")) == "proof"
                )
            )
        )

    @staticmethod
    def _is_open_ended_problem(problem: dict) -> bool:
        return classify_problem_verification_scope(
            problem_type=_clean_text(problem.get("question_type")),
            answer_type=_clean_text(problem.get("answer_type")),
            target=(problem.get("target") if isinstance(problem.get("target"), dict) else None),
            metadata=(
                problem.get("metadata")
                if isinstance(problem.get("metadata"), dict)
                else None
            ),
        ) == ProblemVerificationScope.OPEN_ENDED

    @staticmethod
    def _proof_structure_issues(problem: dict, solution: dict) -> list[str]:
        issues: list[str] = []
        target = problem.get("target")
        if not isinstance(target, dict) or _clean_text(target.get("action")) != "prove":
            issues.append("ProblemSpec 缺少明确的证明目标")
        elif not _clean_text(target.get("object")):
            issues.append("ProblemSpec 的证明对象为空")

        methods = solution.get("methods")
        methods = methods if isinstance(methods, list) else []
        recommended_id = _clean_text(solution.get("recommended_method_id"))
        selected = next(
            (
                method for method in methods
                if isinstance(method, dict)
                and _clean_text(method.get("id")) == recommended_id
            ),
            None,
        )
        if selected is None:
            issues.append("SolutionPlan 缺少有效的推荐证明方法")
            return issues
        steps = selected.get("steps")
        if not isinstance(steps, list) or not steps:
            issues.append("推荐证明方法没有可审查步骤")
        if not _clean_text(selected.get("answer")):
            issues.append("推荐证明方法没有明确结论")
        return issues

    @staticmethod
    def _proof_criteria(value: object) -> list[ProofCriterionReview]:
        if not isinstance(value, list):
            return []
        reviews: list[ProofCriterionReview] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            criterion = _clean_text(item.get("criterion"))
            if criterion not in PROOF_CRITERIA or criterion in seen:
                continue
            status = _clean_text(item.get("status"))
            if status not in {"passed", "failed", "not_applicable", "unverified"}:
                status = "unverified"
            evidence = _clean_text(item.get("evidence"))
            if not evidence:
                status = "unverified"
                evidence = "该维度没有提供可定位的审查证据。"
            criterion_confidence = _confidence(item.get("confidence"), 0.0)
            if (
                status in {"passed", "not_applicable"}
                and criterion_confidence < PROOF_CRITERION_CONFIDENCE_THRESHOLD
            ):
                status = "unverified"
                evidence = (
                    f"{evidence} 该维度置信度低于 "
                    f"{PROOF_CRITERION_CONFIDENCE_THRESHOLD:.2f}。"
                )
            reviews.append(ProofCriterionReview(
                criterion=criterion,
                status=status,
                evidence=evidence,
                confidence=criterion_confidence,
            ))
            seen.add(criterion)
        return reviews

    def _run_cas(self, problem: dict, solution: dict) -> VerificationReport:
        question_type = _clean_text(problem.get("question_type"))
        if question_type in EQUATION_TYPES:
            return self._verify_equation(problem, solution)
        if question_type in EXPRESSION_TYPES:
            return self._verify_expression(problem, solution)
        return VerificationReport(
            passed=False,
            verifier_type="unverified",
            coverage="none",
            evidence="该题型不在当前 SymPy 自动校验范围内。",
            limitations=[
                "当前 SymPy 自动校验覆盖一元实方程、算术和基础代数式"
            ],
            confidence=0.2,
        )

    def _verify_equation(self, problem: dict, solution: dict) -> VerificationReport:
        checks: list[VerificationCheck] = []
        issues: list[str] = []
        limitations: list[str] = []
        equation = self._problem_equation(problem)
        if not equation:
            return VerificationReport(
                coverage="none",
                evidence="未能从 ProblemSpec 提取一个可安全解析的一元方程。",
                limitations=["缺少可供 SymPy 校验的规范方程"],
                confidence=0.2,
            )

        variable = self._single_variable(equation)
        if not variable:
            return VerificationReport(
                coverage="none",
                evidence="当前工具只支持含一个实变量的方程。",
                limitations=["方程没有变量或包含多个变量"],
                confidence=0.2,
            )

        solved = solve_equation(equation, variable)
        if not solved.ok:
            return VerificationReport(
                coverage="none",
                evidence="SymPy 无法得到可比较的可靠解集。",
                limitations=[solved.error or "方程求解失败", *solved.warnings],
                confidence=0.25,
            )

        checks.append(VerificationCheck(
            id="independent_solution_set",
            kind="solution_set",
            status="passed",
            tool="solve_equation",
            evidence=f"SymPy 独立求得实数解集：{', '.join(solved.solutions) or '空集'}",
        ))

        methods = solution.get("methods") if isinstance(solution.get("methods"), list) else []
        recommended_id = _clean_text(solution.get("recommended_method_id"))
        selected = next(
            (
                method for method in methods
                if isinstance(method, dict) and _clean_text(method.get("id")) == recommended_id
            ),
            None,
        )
        if selected is None:
            return VerificationReport(
                coverage="partial",
                checks=checks,
                evidence="已独立求出解集，但没有找到推荐方法。",
                issues=["SolutionPlan 缺少有效的推荐方法"],
                confidence=0.45,
            )

        recommended_complete = self._verify_step_chain(
            equation,
            variable,
            selected,
            checks,
            issues,
        )
        all_answers_checked = True
        for method in methods:
            if not isinstance(method, dict):
                all_answers_checked = False
                continue
            method_id = _clean_text(method.get("id")) or None
            answer = _clean_text(method.get("answer"))
            candidates = self._candidate_values(answer, variable)
            if not candidates:
                all_answers_checked = False
                checks.append(VerificationCheck(
                    id=f"answer_{method_id or 'unknown'}",
                    kind="candidate_answer",
                    status="skipped",
                    tool="verify_candidate_answer",
                    method_id=method_id,
                    evidence="无法把该方法的答案解析为候选值。",
                ))
                continue

            candidate_ok = True
            for position, candidate in enumerate(candidates, start=1):
                result = verify_candidate_answer(equation, candidate, variable)
                if not result.ok:
                    status = "skipped"
                    all_answers_checked = False
                else:
                    status = "passed" if result.valid else "failed"
                    candidate_ok = candidate_ok and result.valid
                checks.append(VerificationCheck(
                    id=f"answer_{method_id or 'unknown'}_{position}",
                    kind="candidate_answer",
                    status=status,
                    tool="verify_candidate_answer",
                    method_id=method_id,
                    evidence=(
                        f"候选值 {candidate} 代回后的残差为 {result.residual}。"
                        if result.ok
                        else result.error or "候选答案校验失败"
                    ),
                ))

            expected = self._normalized_values(solved.solutions)
            actual = self._normalized_values(candidates)
            if expected is None or actual is None:
                completeness_status = "skipped"
                complete = False
                all_answers_checked = False
            else:
                complete = expected == actual
                completeness_status = "passed" if complete else "failed"
            checks.append(VerificationCheck(
                id=f"completeness_{method_id or 'unknown'}",
                kind="solution_completeness",
                status=completeness_status,
                tool="solve_equation",
                method_id=method_id,
                evidence=(
                    "候选答案覆盖 SymPy 求得的完整解集。"
                    if complete
                    else (
                        "当前安全解析器无法比较完整解集。"
                        if completeness_status == "skipped"
                        else "候选答案与 SymPy 求得的完整解集不一致。"
                    )
                ),
            ))
            if not candidate_ok or completeness_status == "failed":
                issues.append(f"方法 {method_id or 'unknown'} 的答案未通过代回或完整性检查")

        if len(methods) > 1:
            limitations.append("替代方法只校验答案；逐步等价检查聚焦推荐方法")
        has_failure = any(check.status == "failed" for check in checks)
        coverage = "full" if recommended_complete and all_answers_checked else "partial"
        evidence = (
            "SymPy 已独立求解原方程、逐步检查推荐方法，并核对各方法答案。"
            if coverage == "full"
            else "SymPy 已完成部分方程校验，仍有步骤或答案无法解析。"
        )
        return VerificationReport(
            passed=coverage == "full" and not has_failure,
            verifier_type="cas",
            coverage=coverage,
            checks=checks,
            evidence=evidence,
            issues=list(dict.fromkeys(issues)),
            limitations=limitations,
            confidence=0.96 if coverage == "full" else 0.65,
        )

    def _verify_step_chain(
        self,
        original_equation: str,
        variable: str,
        method: dict,
        checks: list[VerificationCheck],
        issues: list[str],
    ) -> bool:
        method_id = _clean_text(method.get("id")) or None
        steps = method.get("steps") if isinstance(method.get("steps"), list) else []
        if not steps:
            issues.append("推荐方法没有可校验步骤")
            return False
        previous = original_equation
        complete = True
        for position, step in enumerate(steps, start=1):
            result_text = step.get("result") if isinstance(step, dict) else None
            equation = self._extract_equation(_clean_text(result_text))
            if not equation:
                complete = False
                checks.append(VerificationCheck(
                    id=f"step_{position}",
                    kind="step_equivalence",
                    status="skipped",
                    tool="compare_math_steps",
                    method_id=method_id,
                    step_index=position,
                    evidence="本步结果不是当前安全解析器支持的单一方程。",
                ))
                continue
            comparison = compare_math_steps(previous, equation, variable)
            if not comparison.ok:
                status = "skipped"
                complete = False
            else:
                status = "passed" if comparison.equivalent else "failed"
            checks.append(VerificationCheck(
                id=f"step_{position}",
                kind="step_equivalence",
                status=status,
                tool="compare_math_steps",
                method_id=method_id,
                step_index=position,
                evidence=(
                    f"{previous} 与 {equation} 的实数解集相同。"
                    if status == "passed"
                    else (
                        comparison.error
                        if status == "skipped"
                        else f"{previous} 与 {equation} 不等价。"
                    )
                ),
            ))
            if status == "failed":
                issues.append(f"推荐方法第 {position} 步不是等价变换")
            if status != "skipped":
                previous = equation
        return complete

    def _verify_expression(self, problem: dict, solution: dict) -> VerificationReport:
        expression = self._problem_expression(problem)
        answer = _clean_text(solution.get("answer"))
        if not expression or not answer:
            return VerificationReport(
                coverage="none",
                evidence="缺少可安全解析的原表达式或答案。",
                limitations=["表达式题无法形成 SymPy 比较输入"],
                confidence=0.2,
            )
        comparison = compare_math_steps(expression, answer)
        if not comparison.ok:
            return VerificationReport(
                coverage="none",
                evidence="SymPy 无法解析表达式比较。",
                limitations=[comparison.error or "表达式比较失败"],
                confidence=0.25,
            )
        check = VerificationCheck(
            id="expression_equivalence",
            kind="expression_equivalence",
            status="passed" if comparison.equivalent else "failed",
            tool="compare_math_steps",
            evidence=(
                "原表达式与候选答案的符号差化简为 0。"
                if comparison.equivalent
                else "原表达式与候选答案不等价。"
            ),
        )
        return VerificationReport(
            passed=comparison.equivalent,
            verifier_type="cas",
            coverage="full",
            checks=[check],
            evidence=check.evidence,
            issues=[] if comparison.equivalent else ["候选表达式与原式不等价"],
            confidence=0.96,
        )

    @staticmethod
    def _problem_equation(problem: dict) -> str | None:
        conditions = problem.get("known_conditions")
        if isinstance(conditions, list):
            for condition in conditions:
                if isinstance(condition, dict):
                    equation = SolutionVerificationAgent._extract_equation(
                        _clean_text(condition.get("statement"))
                    )
                    if equation:
                        return equation
        return SolutionVerificationAgent._extract_equation(
            _clean_text(problem.get("normalized_question"))
        )

    @staticmethod
    def _extract_equation(text: str) -> str | None:
        if text.count("=") != 1:
            return None
        matches = re.findall(
            rf"[{MATH_CHARACTERS}]+=[{MATH_CHARACTERS}]+",
            text,
        )
        for candidate in matches:
            candidate = candidate.strip(" .,，。；;：:")
            if candidate and solve_equation(candidate, SolutionVerificationAgent._single_variable(candidate) or "_").ok:
                return candidate
        return None

    @staticmethod
    def _single_variable(equation: str) -> str | None:
        names = set(re.findall(r"[A-Za-z][A-Za-z0-9_]*", equation))
        return next(iter(names)) if len(names) == 1 else None

    @staticmethod
    def _candidate_values(answer: str, variable: str) -> list[str]:
        if not answer:
            return []
        normalized = answer.replace("−", "-")
        assignments = re.findall(
            rf"\b{re.escape(variable)}\s*=\s*([^,，;；、}}]+?)(?=\s*(?:或|$|[,，;；、}}]))",
            normalized,
        )
        if assignments:
            return [_clean_text(item) for item in assignments if _clean_text(item)]
        set_match = re.search(r"[{{]\s*([^}}]+)\s*[}}]", normalized)
        if set_match:
            return [
                item.strip()
                for item in re.split(r"[,，、]", set_match.group(1))
                if item.strip()
            ]
        if re.fullmatch(rf"[{MATH_CHARACTERS}]+", normalized):
            return [normalized.strip()]
        return []

    @staticmethod
    def _normalized_values(values: list[str]) -> set[str] | None:
        normalized: set[str] = set()
        for value in values:
            result = simplify_expression(value)
            if not result.ok or result.simplified is None:
                return None
            normalized.add(result.simplified)
        return normalized

    @staticmethod
    def _problem_expression(problem: dict) -> str | None:
        text = _clean_text(problem.get("normalized_question"))
        text = re.sub(r"^(?:计算|化简|展开|因式分解)\s*", "", text)
        text = text.rstrip("？?。")
        if text and re.fullmatch(rf"[{MATH_CHARACTERS}]+", text):
            parsed = simplify_expression(text)
            return text if parsed.ok else None
        return None
