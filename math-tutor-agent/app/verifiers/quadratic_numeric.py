from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext

from app.domain.numeric_verification import (
    NumericCheckStatus,
    NumericVerificationCheck,
    NumericVerificationReport,
)
from app.domain.quadratic_verification import QuadraticVerificationContext


EMPTY_ANSWER_MARKERS = ("无实数解", "无解", "空集", "∅", "emptyset")
SAMPLE_POINTS = (-7, -5, -3, -2, 2, 3, 5, 7)
MAX_EXPRESSION_LENGTH = 500
MAX_AST_NODES = 100
MAX_POWER = 12


class UnsafeNumericExpression(ValueError):
    pass


@dataclass(frozen=True)
class NumericVerificationPolicy:
    precision: int = 50
    absolute_tolerance: Decimal = Decimal("1e-20")
    relative_tolerance: Decimal = Decimal("1e-18")
    max_exhaustive_points: int = 1001


class DecimalExpression:
    """Evaluate a small arithmetic AST without SymPy or Python eval."""

    def __init__(self, source: str) -> None:
        normalized = self._normalize(source)
        try:
            self.tree = ast.parse(normalized, mode="eval")
        except SyntaxError as error:
            raise UnsafeNumericExpression("表达式格式不正确") from error
        self.node_count = sum(1 for _ in ast.walk(self.tree))
        if self.node_count > MAX_AST_NODES:
            raise UnsafeNumericExpression("表达式结构过于复杂")

    def evaluate(self, variables: dict[str, Decimal]) -> Decimal:
        try:
            return self._visit(self.tree.body, variables)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as error:
            raise UnsafeNumericExpression("表达式在该采样点无定义") from error

    def names(self) -> set[str]:
        return {
            node.id for node in ast.walk(self.tree)
            if isinstance(node, ast.Name) and node.id != "sqrt"
        }

    @staticmethod
    def _normalize(value: str) -> str:
        if not value or not value.strip() or len(value) > MAX_EXPRESSION_LENGTH:
            raise UnsafeNumericExpression("表达式为空或过长")
        normalized = (
            value.strip()
            .replace("−", "-")
            .replace("–", "-")
            .replace("×", "*")
            .replace("÷", "/")
            .replace("^", "**")
            .replace("（", "(")
            .replace("）", ")")
            .replace("√", "sqrt")
        )
        normalized = re.sub(r"sqrt([A-Za-z0-9.]+)", r"sqrt(\1)", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        normalized = re.sub(r"(?<=\d)(?=[A-DF-Za-df-z(])", "*", normalized)
        normalized = re.sub(r"(?<=\))(?=[A-Za-z0-9(])", "*", normalized)
        normalized = re.sub(r"(?<!sqrt)(?<=[A-Za-z])(?=\()", "*", normalized)
        return normalized

    def _visit(self, node: ast.AST, variables: dict[str, Decimal]) -> Decimal:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise UnsafeNumericExpression("只允许数字常量")
            value = Decimal(str(node.value))
            if abs(value) > Decimal("1e9"):
                raise UnsafeNumericExpression("数字超出允许范围")
            return value
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise UnsafeNumericExpression(f"未知变量：{node.id}")
            return variables[node.id]
        if isinstance(node, ast.UnaryOp):
            value = self._visit(node.operand, variables)
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
            raise UnsafeNumericExpression("不支持该一元运算")
        if isinstance(node, ast.BinOp):
            left = self._visit(node.left, variables)
            right = self._visit(node.right, variables)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                if any(isinstance(item, ast.Name) for item in ast.walk(node.right)):
                    raise UnsafeNumericExpression("指数必须是数字常量")
                if right != right.to_integral_value() or abs(right) > MAX_POWER:
                    raise UnsafeNumericExpression("指数必须是允许范围内的整数")
                return left ** int(right)
            raise UnsafeNumericExpression("不支持该运算")
        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id != "sqrt"
                or len(node.args) != 1
                or node.keywords
            ):
                raise UnsafeNumericExpression("只允许使用单参数 sqrt 函数")
            value = self._visit(node.args[0], variables)
            if value < 0:
                raise UnsafeNumericExpression("实数域内不能对负数开平方")
            return value.sqrt()
        raise UnsafeNumericExpression(f"不支持的表达式结构：{type(node).__name__}")


@dataclass(frozen=True)
class DecimalEquation:
    source: str
    variable: str
    left: DecimalExpression
    right: DecimalExpression

    def residual(self, value: Decimal) -> Decimal:
        variables = {self.variable: value}
        return self.left.evaluate(variables) - self.right.evaluate(variables)


class QuadraticNumericVerifier:
    """Independent Decimal sampling and bounded enumeration for quadratic equations."""

    name = "quadratic_numeric"
    schema_version = "1.0"

    def __init__(self, policy: NumericVerificationPolicy | None = None) -> None:
        self.policy = policy or NumericVerificationPolicy()

    def verify(self, context: QuadraticVerificationContext) -> NumericVerificationReport:
        with localcontext() as decimal_context:
            decimal_context.prec = self.policy.precision
            try:
                equation = self._parse_equation(context)
                claimed = self._claimed_roots(context.final_answer, equation.variable)
                integer_bounds = self._integer_bounds(context, equation.variable)
                if integer_bounds is not None:
                    return self._verify_exhaustive(context, equation, claimed, integer_bounds)
                return self._verify_sampling(context, equation, claimed)
            except UnsafeNumericExpression as error:
                return NumericVerificationReport(
                    problem_id=context.problem_id,
                    solution_id=context.solution_id,
                    context_fingerprint=context.fingerprint(),
                    mode="numeric_sampling",
                    checks=[NumericVerificationCheck(
                        check_type="coefficient_reconstruction",
                        status=NumericCheckStatus.INCONCLUSIVE,
                        summary=str(error),
                    )],
                    status=NumericCheckStatus.INCONCLUSIVE,
                    tolerance=str(self.policy.absolute_tolerance),
                    relative_tolerance=str(self.policy.relative_tolerance),
                    precision=self.policy.precision,
                    sample_points=[str(item) for item in SAMPLE_POINTS],
                    limitations=[str(error)],
                    confidence=0.2,
                )

    def _verify_sampling(
        self,
        context: QuadraticVerificationContext,
        equation: DecimalEquation,
        claimed: tuple[Decimal, ...],
    ) -> NumericVerificationReport:
        checks: list[NumericVerificationCheck] = []
        try:
            f0 = equation.residual(Decimal(0))
            f1 = equation.residual(Decimal(1))
            fm1 = equation.residual(Decimal(-1))
        except UnsafeNumericExpression as error:
            return self._inconclusive(context, equation, str(error))

        two = Decimal(2)
        c = f0
        a = (f1 + fm1) / two - c
        b = (f1 - fm1) / two
        if a == 0:
            checks.append(NumericVerificationCheck(
                check_type="coefficient_reconstruction",
                status=NumericCheckStatus.FAILED,
                summary="数值重建得到的二次项系数为零。",
                evidence={"a": str(a), "b": str(b), "c": str(c)},
            ))
            return self._finish(context, equation, claimed, (), checks, 3)
        if self._close(a, Decimal(0)):
            return self._inconclusive(
                context,
                equation,
                "二次项系数小于当前数值容差，无法可靠判断是否退化。",
            )
        checks.append(NumericVerificationCheck(
            check_type="coefficient_reconstruction",
            status=NumericCheckStatus.PASSED,
            summary="使用 x=-1、0、1 独立重建了非退化二次函数。",
            evidence={"a": str(a), "b": str(b), "c": str(c)},
        ))

        samples: list[dict[str, str | bool]] = []
        consistent = True
        for raw_point in SAMPLE_POINTS:
            point = Decimal(raw_point)
            try:
                observed = equation.residual(point)
            except UnsafeNumericExpression as error:
                return self._inconclusive(context, equation, str(error), checks)
            reconstructed = a * point * point + b * point + c
            passed = self._close(observed, reconstructed)
            consistent = consistent and passed
            samples.append({
                "x": str(point),
                "observed": str(observed),
                "reconstructed": str(reconstructed),
                "passed": passed,
            })
        checks.append(NumericVerificationCheck(
            check_type="sample_consistency",
            status=(NumericCheckStatus.PASSED if consistent else NumericCheckStatus.FAILED),
            summary=(
                "所有固定采样点均符合重建的二次函数。"
                if consistent else "至少一个采样点与重建的二次函数不一致。"
            ),
            evidence={"samples": samples},
        ))
        if not consistent:
            return self._finish(context, equation, claimed, (), checks, len(samples) + 3)

        discriminant = b * b - Decimal(4) * a * c
        roots: tuple[Decimal, ...]
        if discriminant < -self.policy.absolute_tolerance:
            roots = ()
        elif self._close(discriminant, Decimal(0)):
            roots = (-b / (Decimal(2) * a),)
        else:
            square_root = discriminant.sqrt()
            values = (
                (-b - square_root) / (Decimal(2) * a),
                (-b + square_root) / (Decimal(2) * a),
            )
            roots = tuple(sorted(values))
        roots = self._filter_real_domain(context, equation.variable, roots)
        roots_match = self._sets_close(roots, claimed)
        checks.append(NumericVerificationCheck(
            check_type="root_estimation",
            status=(NumericCheckStatus.PASSED if roots_match else NumericCheckStatus.FAILED),
            summary=(
                "数值公式独立计算的根与候选答案一致。"
                if roots_match else "数值公式计算的根与候选答案不一致。"
            ),
            evidence={
                "discriminant": str(discriminant),
                "computed_roots": [str(item) for item in roots],
                "claimed_roots": [str(item) for item in claimed],
            },
        ))
        checks.append(self._substitution_check(equation, claimed))
        return self._finish(context, equation, claimed, roots, checks, len(samples) + 3)

    def _verify_exhaustive(
        self,
        context: QuadraticVerificationContext,
        equation: DecimalEquation,
        claimed: tuple[Decimal, ...],
        bounds: tuple[int, int],
    ) -> NumericVerificationReport:
        lower, upper = bounds
        solutions: list[Decimal] = []
        evaluations: list[dict[str, str | bool]] = []
        for integer in range(lower, upper + 1):
            value = Decimal(integer)
            try:
                residual = equation.residual(value)
            except UnsafeNumericExpression as error:
                return self._inconclusive(
                    context,
                    equation,
                    str(error),
                    mode="exhaustive_integer",
                )
            is_solution = self._close(residual, Decimal(0))
            if is_solution:
                solutions.append(value)
            evaluations.append({
                "x": str(value), "residual": str(residual), "is_solution": is_solution
            })
        computed = tuple(solutions)
        passed = self._sets_close(computed, claimed)
        checks = [NumericVerificationCheck(
            check_type="exhaustive_domain",
            status=(NumericCheckStatus.PASSED if passed else NumericCheckStatus.FAILED),
            summary=(
                "已穷举有限整数定义域，候选答案与全部解一致。"
                if passed else "穷举结果与候选答案不一致。"
            ),
            evidence={
                "lower": lower,
                "upper": upper,
                "evaluations": evaluations,
                "computed_roots": [str(item) for item in computed],
            },
        ), self._substitution_check(equation, claimed)]
        return self._finish(
            context, equation, claimed, computed, checks, upper - lower + 1,
            mode="exhaustive_integer",
        )

    def _parse_equation(self, context: QuadraticVerificationContext) -> DecimalEquation:
        if context.problem_type != "quadratic_equation":
            raise UnsafeNumericExpression("数值验证器只接受 quadratic_equation")
        equations = [
            str(item.get("normalized_expression") or item.get("statement") or "").strip()
            for item in context.explicit_conditions
            if item.get("condition_type") == "equation"
        ]
        equations = [item for item in equations if item.count("=") == 1]
        normalized = (context.normalized_statement or "").strip()
        if not equations and normalized.count("=") == 1:
            equations = [normalized]
        if len(equations) != 1:
            raise UnsafeNumericExpression("必须提供且只能提供一个规范化方程")
        source = equations[0]
        left_source, right_source = source.split("=", maxsplit=1)
        left = DecimalExpression(left_source)
        right = DecimalExpression(right_source)
        names = left.names() | right.names()
        if len(names) != 1:
            raise UnsafeNumericExpression("方程必须且只能包含一个变量")
        return DecimalEquation(source, next(iter(names)), left, right)

    def _claimed_roots(self, answer: str, variable: str) -> tuple[Decimal, ...]:
        lowered = answer.strip().lower()
        if any(marker in lowered for marker in EMPTY_ANSWER_MARKERS):
            return ()
        escaped = re.escape(variable)
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
            raise UnsafeNumericExpression("无法从 final_answer 提取候选根")
        roots: list[Decimal] = []
        for raw in matches:
            raw = raw.strip().rstrip("。.")
            expanded = [raw.replace("±", "+", 1), raw.replace("±", "-", 1)] if "±" in raw else [raw]
            for candidate in expanded:
                expression = DecimalExpression(candidate)
                if expression.names():
                    raise UnsafeNumericExpression("候选根不能包含变量")
                value = expression.evaluate({})
                if not any(self._close(value, existing) for existing in roots):
                    roots.append(value)
        return tuple(sorted(roots))

    def _integer_bounds(
        self,
        context: QuadraticVerificationContext,
        variable: str,
    ) -> tuple[int, int] | None:
        texts = [
            str(item.get("normalized_expression") or item.get("statement") or "")
            for item in [*context.explicit_conditions, *context.implicit_conditions]
            if item.get("condition_type") in {"domain", "inequality"}
        ]
        texts.extend(str(item) for item in context.target.get("constraints", []))
        joined = " ".join(texts)
        if not any(marker in joined.lower() for marker in ("整数", "正整数", "integer")):
            return None
        escaped = re.escape(variable)
        lower_match = re.search(rf"(-?\d+)\s*(?:<=|≤)\s*{escaped}", joined)
        upper_match = re.search(rf"{escaped}\s*(?:<=|≤)\s*(-?\d+)", joined)
        if not lower_match or not upper_match:
            raise UnsafeNumericExpression("整数穷举要求显式闭区间上下界")
        lower, upper = int(lower_match.group(1)), int(upper_match.group(1))
        if lower > upper or upper - lower + 1 > self.policy.max_exhaustive_points:
            raise UnsafeNumericExpression("整数穷举区间无效或超过预算")
        return lower, upper

    def _filter_real_domain(
        self,
        context: QuadraticVerificationContext,
        variable: str,
        roots: tuple[Decimal, ...],
    ) -> tuple[Decimal, ...]:
        texts = [
            str(item.get("normalized_expression") or item.get("statement") or "").strip()
            for item in [*context.explicit_conditions, *context.implicit_conditions]
            if item.get("condition_type") in {"domain", "inequality"}
        ]
        texts.extend(str(item).strip() for item in context.target.get("constraints", []))
        escaped = re.escape(variable)
        predicates: list[tuple[str, Decimal]] = []
        for text in texts:
            normalized = text.replace("≥", ">=").replace("≤", "<=").replace("≠", "!=")
            compact = re.sub(r"\s+", "", normalized).lower()
            if compact in {
                f"{variable.lower()}∈r",
                f"{variable.lower()}∈ℝ".lower(),
                f"{variable.lower()}inr",
            }:
                continue
            direct = re.fullmatch(
                rf"\s*{escaped}\s*(>=|<=|>|<|!=)\s*(.+?)\s*",
                normalized,
            )
            reverse = re.fullmatch(
                rf"\s*(.+?)\s*(>=|<=|>|<)\s*{escaped}\s*",
                normalized,
            )
            if direct:
                operator, raw_bound = direct.groups()
            elif reverse:
                raw_bound, reverse_operator = reverse.groups()
                operator = {
                    ">": "<", ">=": "<=", "<": ">", "<=": ">="
                }[reverse_operator]
            else:
                if variable in normalized and any(
                    token in normalized for token in (">", "<", "!", "∈")
                ):
                    raise UnsafeNumericExpression(f"无法安全解析定义域约束：{text}")
                continue
            expression = DecimalExpression(raw_bound)
            if expression.names():
                raise UnsafeNumericExpression(f"定义域边界必须是已知数值：{text}")
            predicates.append((operator, expression.evaluate({})))

        def allowed(root: Decimal) -> bool:
            for operator, bound in predicates:
                if operator == ">" and not root > bound:
                    return False
                if operator == ">=" and not root >= bound:
                    return False
                if operator == "<" and not root < bound:
                    return False
                if operator == "<=" and not root <= bound:
                    return False
                if operator == "!=" and self._close(root, bound):
                    return False
            return True

        return tuple(root for root in roots if allowed(root))

    def _substitution_check(
        self,
        equation: DecimalEquation,
        claimed: tuple[Decimal, ...],
    ) -> NumericVerificationCheck:
        substitutions = []
        passed = True
        for root in claimed:
            try:
                residual = equation.residual(root)
                valid = self._close(residual, Decimal(0))
                residual_text = str(residual)
            except UnsafeNumericExpression as error:
                valid = False
                residual_text = str(error)
            passed = passed and valid
            substitutions.append({
                "root": str(root), "residual": residual_text, "passed": valid
            })
        return NumericVerificationCheck(
            check_type="candidate_substitution",
            status=(NumericCheckStatus.PASSED if passed else NumericCheckStatus.FAILED),
            summary=(
                "所有候选根在数值容差内代回成立。"
                if passed else "至少一个候选根数值代回不成立。"
            ),
            evidence={"substitutions": substitutions},
        )

    def _close(self, left: Decimal, right: Decimal) -> bool:
        difference = abs(left - right)
        scale = max(abs(left), abs(right), Decimal(1))
        return difference <= max(
            self.policy.absolute_tolerance,
            self.policy.relative_tolerance * scale,
        )

    def _sets_close(
        self,
        expected: tuple[Decimal, ...],
        actual: tuple[Decimal, ...],
    ) -> bool:
        if len(expected) != len(actual):
            return False
        unmatched = list(actual)
        for value in expected:
            match = next((item for item in unmatched if self._close(value, item)), None)
            if match is None:
                return False
            unmatched.remove(match)
        return not unmatched

    def _finish(
        self,
        context: QuadraticVerificationContext,
        equation: DecimalEquation,
        claimed: tuple[Decimal, ...],
        computed: tuple[Decimal, ...],
        checks: list[NumericVerificationCheck],
        sample_count: int,
        *,
        mode: str = "numeric_sampling",
    ) -> NumericVerificationReport:
        if any(item.status == NumericCheckStatus.FAILED for item in checks):
            status = NumericCheckStatus.FAILED
            confidence = 0.98
            limitations: list[str] = []
        elif all(item.status == NumericCheckStatus.PASSED for item in checks):
            status = NumericCheckStatus.PASSED
            confidence = 0.96
            limitations = []
        else:
            status = NumericCheckStatus.INCONCLUSIVE
            confidence = 0.45
            limitations = ["至少一个数值检查未能形成结论"]
        return NumericVerificationReport(
            problem_id=context.problem_id,
            solution_id=context.solution_id,
            context_fingerprint=context.fingerprint(),
            mode=mode,
            equation=equation.source,
            variable=equation.variable,
            checks=checks,
            status=status,
            independently_computed_roots=[str(item) for item in computed],
            claimed_roots=[str(item) for item in claimed],
            sample_count=sample_count,
            tolerance=str(self.policy.absolute_tolerance),
            relative_tolerance=str(self.policy.relative_tolerance),
            precision=self.policy.precision,
            sample_points=(
                [] if mode == "exhaustive_integer"
                else [str(item) for item in SAMPLE_POINTS]
            ),
            limitations=limitations,
            confidence=confidence,
        )

    def _inconclusive(
        self,
        context: QuadraticVerificationContext,
        equation: DecimalEquation,
        reason: str,
        existing_checks: list[NumericVerificationCheck] | None = None,
        *,
        mode: str = "numeric_sampling",
    ) -> NumericVerificationReport:
        checks = list(existing_checks or [])
        checks.append(NumericVerificationCheck(
            check_type=(
                "exhaustive_domain"
                if mode == "exhaustive_integer"
                else "sample_consistency"
            ),
            status=NumericCheckStatus.INCONCLUSIVE,
            summary=reason,
        ))
        return NumericVerificationReport(
            problem_id=context.problem_id,
            solution_id=context.solution_id,
            context_fingerprint=context.fingerprint(),
            mode=mode,
            equation=equation.source,
            variable=equation.variable,
            checks=checks,
            status=NumericCheckStatus.INCONCLUSIVE,
            tolerance=str(self.policy.absolute_tolerance),
            relative_tolerance=str(self.policy.relative_tolerance),
            precision=self.policy.precision,
            sample_points=(
                [] if mode == "exhaustive_integer"
                else [str(item) for item in SAMPLE_POINTS]
            ),
            limitations=[reason],
            confidence=0.3,
        )
