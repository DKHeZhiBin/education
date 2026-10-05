from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import sympy as sp

from app.domain.quadratic_verification import (
    QuadraticCheckStatus,
    QuadraticVerificationCheck,
    QuadraticVerificationContext,
    QuadraticVerificationReport,
)
from app.mcp_tools.math_tools import compare_math_steps
from app.mcp_tools.safe_math import (
    UnsafeMathExpression,
    display,
    parse_equation,
    parse_expression,
)


EMPTY_ANSWER_MARKERS = ("无实数解", "无解", "空集", "∅", "emptyset")
REAL_DOMAIN_MARKERS = ("实数", "real", "ℝ", "\\mathbb{r}")
UNSUPPORTED_DOMAIN_MARKERS = ("整数", "自然数", "正整数", "复数", "integer", "complex")


@dataclass(frozen=True)
class ParsedQuadratic:
    equation: str
    symbol: sp.Symbol
    residual: sp.Expr
    numerator: sp.Expr
    denominator: sp.Expr
    polynomial: sp.Poly
    domain: sp.Set
    roots: tuple[sp.Expr, ...]


class QuadraticSympyVerifier:
    """Verify one-variable quadratic equations without model judgment."""

    name = "quadratic_sympy"
    schema_version = "1.0"

    def verify(self, context: QuadraticVerificationContext) -> QuadraticVerificationReport:
        step_ids = [str(item.get("step_id", "")) for item in context.solution_steps]
        step_ids = [item for item in step_ids if item]
        checks: list[QuadraticVerificationCheck] = []
        limitations: list[str] = []
        try:
            parsed = self._parse_problem(context)
        except (UnsafeMathExpression, ValueError, TypeError) as error:
            checks.extend(self._inconclusive_core_checks(str(error)))
            return self._report(
                context=context,
                checks=checks,
                step_ids=step_ids,
                covered_step_ids=[],
                limitations=[str(error)],
                confidence=0.2,
            )

        coefficients = {
            "a": display(parsed.polynomial.nth(2)),
            "b": display(parsed.polynomial.nth(1)),
            "c": display(parsed.polynomial.nth(0)),
        }
        discriminant = sp.simplify(
            parsed.polynomial.nth(1) ** 2
            - 4 * parsed.polynomial.nth(2) * parsed.polynomial.nth(0)
        )
        checks.append(QuadraticVerificationCheck(
            check_type="solve",
            status=QuadraticCheckStatus.PASSED,
            summary="SymPy 已在实数域独立求出有限解集。",
            evidence={
                "standard_form": f"{display(parsed.numerator)} = 0",
                "coefficients": coefficients,
                "discriminant": display(discriminant),
                "computed_roots": [display(root) for root in parsed.roots],
            },
        ))

        claimed_roots, answer_error = self._claimed_roots(
            context.final_answer, parsed.symbol
        )
        substitution_check = self._substitution_check(parsed, claimed_roots, answer_error)
        root_count_check = self._root_count_check(parsed, claimed_roots, answer_error)
        checks.extend([substitution_check, root_count_check])
        checks.append(self._domain_check(context, parsed, claimed_roots))
        checks.append(self._boundary_check(context, parsed, claimed_roots))

        covered_steps: list[str] = []
        previous_equation = parsed.equation
        for step in context.solution_steps:
            step_id = str(step.get("step_id", ""))
            if not step_id:
                continue
            result = str(step.get("result", "")).strip()
            equation = self._extract_equation(result)
            if equation:
                comparison = compare_math_steps(
                    previous_equation, equation, parsed.symbol.name
                )
                if comparison.ok and comparison.equivalent:
                    covered_steps.append(step_id)
                    checks.append(QuadraticVerificationCheck(
                        check_type="step_equivalence",
                        status=QuadraticCheckStatus.PASSED,
                        summary=f"步骤 {step_id} 与前一方程解集等价。",
                        evidence={"before": previous_equation, "after": equation},
                        covered_step_ids=[step_id],
                    ))
                    previous_equation = equation
                elif comparison.ok:
                    checks.append(QuadraticVerificationCheck(
                        check_type="step_equivalence",
                        status=QuadraticCheckStatus.FAILED,
                        summary=f"步骤 {step_id} 改变了原方程的实数解集。",
                        evidence={"before": previous_equation, "after": equation},
                    ))
                else:
                    limitations.append(f"步骤 {step_id} 无法进行符号等价比较")
            elif (
                root_count_check.status == QuadraticCheckStatus.PASSED
                and self._answer_like(result, parsed.symbol)
            ):
                covered_steps.append(step_id)
                root_count_check.covered_step_ids.append(step_id)
            else:
                limitations.append(f"步骤 {step_id} 是文字推理或非标准公式，未被 SymPy 覆盖")

        return self._report(
            context=context,
            parsed=parsed,
            claimed_roots=claimed_roots,
            coefficients=coefficients,
            discriminant=display(discriminant),
            checks=checks,
            step_ids=step_ids,
            covered_step_ids=list(dict.fromkeys(covered_steps)),
            limitations=list(dict.fromkeys(limitations)),
            confidence=0.98,
        )

    def _parse_problem(self, context: QuadraticVerificationContext) -> ParsedQuadratic:
        if context.problem_type != "quadratic_equation":
            raise ValueError("验证器只接受 quadratic_equation 题型")
        equation = self._problem_equation(context)
        parsed = parse_equation(equation)
        residual = sp.together(parsed.residual)
        symbols = sorted(residual.free_symbols, key=lambda item: item.name)
        if len(symbols) != 1:
            raise ValueError("方程必须且只能包含一个实变量")
        symbol = symbols[0]
        numerator, denominator = residual.as_numer_denom()
        try:
            polynomial = sp.Poly(sp.expand(numerator), symbol)
        except sp.PolynomialError as error:
            raise ValueError("方程不能规范化为一元多项式") from error
        if polynomial.degree() != 2 or sp.simplify(polynomial.nth(2)) == 0:
            raise ValueError("规范方程的二次项系数必须非零且次数必须为 2")
        domain = self._declared_domain(context, symbol)
        solution_set = sp.solveset(residual, symbol, domain=domain)
        if not isinstance(solution_set, sp.FiniteSet):
            raise ValueError("SymPy 未返回有限实数解集")
        roots = tuple(sorted(solution_set, key=sp.default_sort_key))
        return ParsedQuadratic(
            equation=equation,
            symbol=symbol,
            residual=residual,
            numerator=sp.expand(numerator),
            denominator=sp.factor(denominator),
            polynomial=polynomial,
            domain=domain,
            roots=roots,
        )

    @staticmethod
    def _declared_domain(
        context: QuadraticVerificationContext,
        symbol: sp.Symbol,
    ) -> sp.Set:
        items = [
            str(item.get("normalized_expression") or item.get("statement") or "").strip()
            for item in [*context.explicit_conditions, *context.implicit_conditions]
            if item.get("condition_type") in {"domain", "inequality"}
        ]
        items.extend(str(item).strip() for item in context.target.get("constraints", []))
        lowered = " ".join(items).lower()
        if any(marker in lowered for marker in UNSUPPORTED_DOMAIN_MARKERS):
            raise ValueError("题目声明了当前验证器不支持的非实数连续定义域")

        domain: sp.Set = sp.S.Reals
        escaped = re.escape(symbol.name)
        for item in items:
            normalized = item.replace("≥", ">=").replace("≤", "<=").replace("≠", "!=")
            compact_lowered = re.sub(r"\s+", "", normalized).lower()
            if compact_lowered in {
                f"{symbol.name.lower()}∈r",
                f"{symbol.name.lower()}∈ℝ".lower(),
                f"{symbol.name.lower()}inr",
            }:
                continue
            direct = re.fullmatch(rf"\s*{escaped}\s*(>=|<=|>|<|!=)\s*(.+?)\s*", normalized)
            reverse = re.fullmatch(rf"\s*(.+?)\s*(>=|<=|>|<)\s*{escaped}\s*", normalized)
            if direct:
                operator, raw_bound = direct.groups()
            elif reverse:
                raw_bound, reverse_operator = reverse.groups()
                operator = {">": "<", ">=": "<=", "<": ">", "<=": ">="}[reverse_operator]
            else:
                if symbol.name in normalized and any(token in normalized for token in (">", "<", "!", "∈")):
                    raise ValueError(f"无法安全解析定义域约束：{item}")
                continue
            bound = parse_expression(raw_bound)
            if bound.free_symbols or bound.is_real is False:
                raise ValueError(f"定义域边界必须是已知实数：{item}")
            if operator == ">":
                constraint = sp.Interval.open(bound, sp.oo)
            elif operator == ">=":
                constraint = sp.Interval(bound, sp.oo)
            elif operator == "<":
                constraint = sp.Interval.open(-sp.oo, bound)
            elif operator == "<=":
                constraint = sp.Interval(-sp.oo, bound)
            else:
                constraint = sp.Complement(sp.S.Reals, sp.FiniteSet(bound))
            domain = sp.Intersection(domain, constraint)
        return domain

    @staticmethod
    def _problem_equation(context: QuadraticVerificationContext) -> str:
        equations = [
            str(item.get("normalized_expression") or item.get("statement") or "").strip()
            for item in context.explicit_conditions
            if item.get("condition_type") == "equation"
        ]
        equations = [item for item in equations if item.count("=") == 1]
        if len(equations) == 1:
            return equations[0]
        normalized = (context.normalized_statement or "").strip()
        if not equations and normalized.count("=") == 1:
            return normalized
        raise ValueError("必须提供且只能提供一个规范化方程条件")

    @staticmethod
    def _claimed_roots(
        answer: str, symbol: sp.Symbol
    ) -> tuple[tuple[sp.Expr, ...], str | None]:
        lowered = answer.strip().lower()
        if any(marker in lowered for marker in EMPTY_ANSWER_MARKERS):
            return (), None
        escaped = re.escape(symbol.name)
        matches = re.findall(
            rf"(?:{escaped}(?:_[12]|[₁₂])?\s*=)\s*([^,，;；、或和]+)",
            answer,
            flags=re.IGNORECASE,
        )
        if not matches:
            braced = re.search(r"[\{｛]([^\}｝]+)[\}｝]", answer)
            if braced:
                matches = re.split(r"[,，;；、]", braced.group(1))
        if not matches:
            return (), "无法从独立题解的 final_answer 提取根"
        roots: list[sp.Expr] = []
        try:
            for raw in matches:
                raw = raw.strip().rstrip("。.")
                expanded = [raw.replace("±", "+", 1), raw.replace("±", "-", 1)] if "±" in raw else [raw]
                for candidate in expanded:
                    value = parse_expression(candidate)
                    if value.free_symbols:
                        return (), "候选根不能包含未求值变量"
                    if value.is_real is False:
                        return (), "候选根不在实数域"
                    if not any(sp.simplify(value - existing) == 0 for existing in roots):
                        roots.append(value)
        except UnsafeMathExpression as error:
            return (), f"候选根无法安全解析：{error}"
        return tuple(sorted(roots, key=sp.default_sort_key)), None

    @staticmethod
    def _substitution_check(
        parsed: ParsedQuadratic,
        claimed_roots: tuple[sp.Expr, ...],
        answer_error: str | None,
    ) -> QuadraticVerificationCheck:
        if answer_error:
            return QuadraticVerificationCheck(
                check_type="substitution",
                status=QuadraticCheckStatus.INCONCLUSIVE,
                summary=answer_error,
            )
        substitutions = []
        valid = True
        for root in claimed_roots:
            denominator = sp.simplify(parsed.denominator.subs(parsed.symbol, root))
            residual = sp.simplify(parsed.residual.subs(parsed.symbol, root))
            passed = denominator != 0 and residual == 0
            valid = valid and passed
            substitutions.append({
                "root": display(root),
                "residual": display(residual),
                "denominator": display(denominator),
                "passed": bool(passed),
            })
        return QuadraticVerificationCheck(
            check_type="substitution",
            status=(QuadraticCheckStatus.PASSED if valid else QuadraticCheckStatus.FAILED),
            summary=("所有候选根代回原方程均成立。" if valid else "至少一个候选根代回原方程不成立。"),
            evidence={"substitutions": substitutions},
        )

    @staticmethod
    def _root_count_check(
        parsed: ParsedQuadratic,
        claimed_roots: tuple[sp.Expr, ...],
        answer_error: str | None,
    ) -> QuadraticVerificationCheck:
        if answer_error:
            return QuadraticVerificationCheck(
                check_type="root_count",
                status=QuadraticCheckStatus.INCONCLUSIVE,
                summary=answer_error,
            )
        missing = [
            root for root in parsed.roots
            if not any(sp.simplify(root - item) == 0 for item in claimed_roots)
        ]
        extra = [
            root for root in claimed_roots
            if not any(sp.simplify(root - item) == 0 for item in parsed.roots)
        ]
        passed = not missing and not extra
        return QuadraticVerificationCheck(
            check_type="root_count",
            status=(QuadraticCheckStatus.PASSED if passed else QuadraticCheckStatus.FAILED),
            summary=("候选答案与完整实数解集一致。" if passed else "候选答案存在漏根或增根。"),
            evidence={
                "expected_count": len(parsed.roots),
                "claimed_count": len(claimed_roots),
                "missing_roots": [display(item) for item in missing],
                "extra_roots": [display(item) for item in extra],
            },
        )

    @staticmethod
    def _domain_check(
        context: QuadraticVerificationContext,
        parsed: ParsedQuadratic,
        claimed_roots: tuple[sp.Expr, ...],
    ) -> QuadraticVerificationCheck:
        domain_text = " ".join(
            str(item.get("normalized_expression") or item.get("statement") or "")
            for item in [*context.explicit_conditions, *context.implicit_conditions]
            if item.get("condition_type") == "domain"
        )
        domain_text += " " + " ".join(str(item) for item in context.target.get("constraints", []))
        lowered = domain_text.lower()
        unsupported = [marker for marker in UNSUPPORTED_DOMAIN_MARKERS if marker in lowered]
        roots_real = all(root.is_real is not False for root in [*parsed.roots, *claimed_roots])
        roots_in_domain = all(
            parsed.domain.contains(root) == sp.S.true
            for root in [*parsed.roots, *claimed_roots]
        )
        if unsupported:
            return QuadraticVerificationCheck(
                check_type="domain",
                status=QuadraticCheckStatus.INCONCLUSIVE,
                summary="题目声明了当前验证器不支持的定义域。",
                evidence={"domain_text": domain_text, "unsupported_markers": unsupported},
            )
        passed = roots_real and roots_in_domain
        explicit_real = any(marker in lowered for marker in REAL_DOMAIN_MARKERS)
        return QuadraticVerificationCheck(
            check_type="domain",
            status=(QuadraticCheckStatus.PASSED if passed else QuadraticCheckStatus.FAILED),
            summary=(
                "所有解均满足题目声明的实数域。"
                if explicit_real and passed
                else "按初中一元二次方程范围采用实数域，所有解均为实数。"
                if passed
                else "至少一个候选解不满足实数域。"
            ),
            evidence={
                "domain": display(parsed.domain),
                "explicit": explicit_real or parsed.domain != sp.S.Reals,
                "all_roots_in_domain": roots_in_domain,
            },
        )

    @staticmethod
    def _boundary_check(
        context: QuadraticVerificationContext,
        parsed: ParsedQuadratic,
        claimed_roots: tuple[sp.Expr, ...],
    ) -> QuadraticVerificationCheck:
        leading = sp.simplify(parsed.polynomial.nth(2))
        denominator_values = [
            sp.simplify(parsed.denominator.subs(parsed.symbol, root))
            for root in [*parsed.roots, *claimed_roots]
        ]
        passed = leading != 0 and all(value != 0 for value in denominator_values)
        return QuadraticVerificationCheck(
            check_type="boundary",
            status=(QuadraticCheckStatus.PASSED if passed else QuadraticCheckStatus.FAILED),
            summary=(
                "二次项系数非零，全部根避开原式分母零点。"
                if passed
                else "二次项退化或至少一个根落在原式分母零点。"
            ),
            evidence={
                "leading_coefficient": display(leading),
                "denominator": display(parsed.denominator),
                "denominator_values": [display(item) for item in denominator_values],
                "target_constraints": context.target.get("constraints", []),
            },
        )

    @staticmethod
    def _extract_equation(value: str) -> str | None:
        if value.count("=") != 1:
            return None
        candidate = value.strip().rstrip("。.;；")
        try:
            parse_equation(candidate)
        except UnsafeMathExpression:
            return None
        return candidate

    def _answer_like(self, value: str, symbol: sp.Symbol) -> bool:
        roots, error = self._claimed_roots(value, symbol)
        return error is None and bool(roots or any(marker in value.lower() for marker in EMPTY_ANSWER_MARKERS))

    @staticmethod
    def _inconclusive_core_checks(reason: str) -> list[QuadraticVerificationCheck]:
        return [QuadraticVerificationCheck(
            check_type=check_type,
            status=QuadraticCheckStatus.INCONCLUSIVE,
            summary=reason,
        ) for check_type in ("solve", "substitution", "root_count", "domain", "boundary")]

    @staticmethod
    def _report(
        *,
        context: QuadraticVerificationContext,
        checks: list[QuadraticVerificationCheck],
        step_ids: list[str],
        covered_step_ids: list[str],
        limitations: list[str],
        confidence: float,
        parsed: ParsedQuadratic | None = None,
        claimed_roots: tuple[sp.Expr, ...] = (),
        coefficients: dict[str, str] | None = None,
        discriminant: str | None = None,
    ) -> QuadraticVerificationReport:
        failed = any(item.status == QuadraticCheckStatus.FAILED for item in checks)
        inconclusive = any(item.status == QuadraticCheckStatus.INCONCLUSIVE for item in checks)
        uncovered = [item for item in step_ids if item not in covered_step_ids]
        if failed:
            verification_status = "failed"
            coverage_level = "partial" if covered_step_ids else "none"
            confidence = max(confidence, 0.98)
        elif not inconclusive and not uncovered and step_ids:
            verification_status = "verified"
            coverage_level = "full"
        else:
            coverage_level = "partial" if covered_step_ids else "none"
            verification_status = "partial" if covered_step_ids else "unverified"
            if inconclusive:
                limitations.append("至少一个确定性校验维度证据不足")
            if uncovered:
                limitations.append("存在未被确定性工具覆盖的题解步骤")
            if not step_ids:
                limitations.append("题解没有可建立完整覆盖的结构化步骤")
            confidence = min(confidence, 0.79)
        return QuadraticVerificationReport(
            problem_id=context.problem_id,
            solution_id=context.solution_id,
            context_fingerprint=context.fingerprint(),
            equation=parsed.equation if parsed else None,
            variable=parsed.symbol.name if parsed else None,
            standard_form=f"{display(parsed.numerator)} = 0" if parsed else None,
            coefficients=coefficients or {},
            discriminant=discriminant,
            computed_roots=[display(item) for item in parsed.roots] if parsed else [],
            claimed_roots=[display(item) for item in claimed_roots],
            checks=checks,
            verification_status=verification_status,
            coverage_level=coverage_level,
            covered_step_ids=covered_step_ids,
            uncovered_step_ids=uncovered,
            limitations=list(dict.fromkeys(limitations)),
            confidence=confidence,
        )
