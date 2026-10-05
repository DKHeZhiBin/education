from __future__ import annotations

import random

import sympy as sp

from app.mcp_tools.contracts import (
    CandidateVerificationResult,
    EquationSolutionResult,
    ExpressionResult,
    SimilarProblemResult,
    StepComparisonResult,
)
from app.mcp_tools.safe_math import (
    UnsafeMathExpression,
    display,
    normalize_expression,
    parse_equation,
    parse_expression,
    validate_variable,
)


def simplify_expression(expression: str) -> ExpressionResult:
    """Safely simplify an arithmetic or algebraic expression."""
    try:
        parsed = parse_expression(expression)
        return ExpressionResult(
            ok=True,
            original=expression,
            normalized=normalize_expression(expression),
            simplified=display(sp.simplify(parsed)),
        )
    except (UnsafeMathExpression, TypeError, ValueError) as error:
        return ExpressionResult(ok=False, original=expression, error=str(error))


def solve_equation(equation: str, variable: str = "x") -> EquationSolutionResult:
    """Solve one real-valued algebraic equation and verify each returned solution."""
    try:
        variable = validate_variable(variable)
        parsed = parse_equation(equation)
        symbol = sp.Symbol(variable, real=True)
        if parsed.residual.free_symbols - {symbol}:
            raise UnsafeMathExpression("方程只能包含指定变量")
        solution_set = sp.solveset(parsed.residual, symbol, domain=sp.S.Reals)
        if isinstance(solution_set, sp.ConditionSet):
            return EquationSolutionResult(
                ok=False,
                equation=equation,
                variable=variable,
                error="无法得到可枚举的可靠解集",
                warnings=[display(solution_set)],
            )
        if solution_set is sp.S.EmptySet:
            return EquationSolutionResult(
                ok=True,
                equation=equation,
                variable=variable,
                solutions=[],
                verification=[],
            )
        if not isinstance(solution_set, sp.FiniteSet):
            return EquationSolutionResult(
                ok=True,
                equation=equation,
                variable=variable,
                solutions=[display(solution_set)],
                warnings=["结果是解集表达式，不是有限个离散解"],
            )
        solutions = list(solution_set)
        rendered = [display(item) for item in solutions]
        verified = [sp.simplify(parsed.residual.subs(symbol, item)) == 0 for item in solutions]
        return EquationSolutionResult(
            ok=True,
            equation=equation,
            variable=variable,
            solutions=rendered,
            verification=verified,
        )
    except (UnsafeMathExpression, TypeError, ValueError, NotImplementedError) as error:
        return EquationSolutionResult(ok=False, equation=equation, variable=variable, error=str(error))


def verify_candidate_answer(
    equation: str,
    candidate: str,
    variable: str = "x",
) -> CandidateVerificationResult:
    """Substitute a candidate into an equation and report whether the residual is zero."""
    try:
        variable = validate_variable(variable)
        parsed = parse_equation(equation)
        candidate_value = parse_expression(candidate)
        symbol = sp.Symbol(variable, real=True)
        if candidate_value.free_symbols:
            raise UnsafeMathExpression("候选答案必须是确定的数值")
        if parsed.residual.free_symbols - {symbol}:
            raise UnsafeMathExpression("方程只能包含指定变量")
        residual = sp.simplify(parsed.residual.subs(symbol, candidate_value))
        return CandidateVerificationResult(
            ok=True,
            equation=equation,
            variable=variable,
            candidate=candidate,
            valid=residual == 0,
            residual=display(residual),
        )
    except (UnsafeMathExpression, TypeError, ValueError) as error:
        return CandidateVerificationResult(
            ok=False,
            equation=equation,
            variable=variable,
            candidate=candidate,
            error=str(error),
        )


def compare_math_steps(before: str, after: str, variable: str = "x") -> StepComparisonResult:
    """Check whether two expressions or two equations are mathematically equivalent over the reals."""
    try:
        variable = validate_variable(variable)
        if "=" in before or "=" in after:
            if "=" not in before or "=" not in after:
                raise UnsafeMathExpression("比较对象必须同为表达式或同为方程")
            symbol = sp.Symbol(variable, real=True)
            before_equation = parse_equation(before)
            after_equation = parse_equation(after)
            if (before_equation.residual.free_symbols | after_equation.residual.free_symbols) - {symbol}:
                raise UnsafeMathExpression("方程只能包含指定变量")
            before_set = sp.solveset(before_equation.residual, symbol, domain=sp.S.Reals)
            after_set = sp.solveset(after_equation.residual, symbol, domain=sp.S.Reals)
            if isinstance(before_set, sp.ConditionSet) or isinstance(after_set, sp.ConditionSet):
                return StepComparisonResult(
                    ok=False,
                    before=before,
                    after=after,
                    variable=variable,
                    error="无法可靠比较两个方程的解集",
                )
            return StepComparisonResult(
                ok=True,
                before=before,
                after=after,
                variable=variable,
                equivalent=before_set == after_set,
                method="real_solution_set",
            )
        difference = sp.simplify(parse_expression(before) - parse_expression(after))
        return StepComparisonResult(
            ok=True,
            before=before,
            after=after,
            variable=variable,
            equivalent=difference == 0,
            method="symbolic_difference",
        )
    except (UnsafeMathExpression, TypeError, ValueError, NotImplementedError) as error:
        return StepComparisonResult(
            ok=False,
            before=before,
            after=after,
            variable=variable,
            error=str(error),
        )


def generate_similar_linear_problem(
    target_answer: int,
    difficulty: int = 1,
    seed: int = 0,
) -> SimilarProblemResult:
    """Generate a deterministic one-variable linear equation with a known integer answer."""
    if difficulty not in {1, 2, 3}:
        return SimilarProblemResult(ok=False, difficulty=1, error="difficulty 必须是 1、2、3")
    if abs(target_answer) > 10_000:
        return SimilarProblemResult(ok=False, difficulty=difficulty, error="目标答案超出允许范围")
    rng = random.Random(seed)
    left_coefficient = rng.randint(2, 5 + difficulty * 2)
    right_coefficient = rng.randint(1, left_coefficient - 1)
    offset = rng.randint(1, 3 + difficulty * 2)
    right_constant = left_coefficient * (target_answer + offset) - right_coefficient * target_answer
    question = f"{left_coefficient}(x + {offset}) = {right_coefficient}x + {right_constant}"
    return SimilarProblemResult(
        ok=True,
        question=question,
        answer=f"x = {target_answer}",
        knowledge_points=["分配律", "一元一次方程", "移项"],
        difficulty=difficulty,
    )
