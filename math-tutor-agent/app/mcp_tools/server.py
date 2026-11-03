from datetime import date

from mcp.server import MCPServer

from app.core.logging import configure_cli_logging
from app.mcp_tools.contracts import (
    CandidateVerificationResult,
    EquationSolutionResult,
    ExpressionResult,
    ReviewScheduleResult,
    SimilarProblemResult,
    StepComparisonResult,
)
from app.mcp_tools.math_tools import (
    compare_math_steps,
    generate_similar_linear_problem,
    simplify_expression,
    solve_equation,
    verify_candidate_answer,
)
from app.mcp_tools.review_tools import (
    calculate_initial_review_schedule,
    calculate_review_schedule,
)


mcp = MCPServer(
    "math-tutor-tools",
    version="0.1.0",
    instructions=(
        "Tools for verified mathematical calculation and review scheduling. "
        "Use them as evidence for the tutoring agents; do not expose a full answer "
        "before the teaching policy allows it."
    ),
)


@mcp.tool()
def simplify_math_expression(expression: str) -> ExpressionResult:
    """中文：处理“simplify·math·expression”相关操作。
    English: Handles the simplify math expression operation.

    原有说明 / Existing notes:
    Safely simplify an arithmetic or algebraic expression without arbitrary code execution.
    """
    return simplify_expression(expression)


@mcp.tool()
def solve_math_equation(equation: str, variable: str = "x") -> EquationSolutionResult:
    """中文：处理“solve·math·equation”相关操作。
    English: Handles the solve math equation operation.

    原有说明 / Existing notes:
    Solve a one-variable equation over the real numbers and verify finite solutions.
    """
    return solve_equation(equation, variable)


@mcp.tool()
def verify_math_candidate(
    equation: str,
    candidate: str,
    variable: str = "x",
) -> CandidateVerificationResult:
    """中文：处理“校验·math·候选内容”相关操作。
    English: Handles the verify math candidate operation.
    """
    return verify_candidate_answer(equation, candidate, variable)


@mcp.tool()
def compare_solution_steps(
    before: str,
    after: str,
    variable: str = "x",
) -> StepComparisonResult:
    """中文：处理“compare·解答·steps”相关操作。
    English: Handles the compare solution steps operation.
    """
    return compare_math_steps(before, after, variable)


@mcp.tool()
def create_similar_linear_problem(
    target_answer: int,
    difficulty: int = 1,
    seed: int = 0,
) -> SimilarProblemResult:
    """中文：处理“创建·similar·linear·题目”相关操作。
    English: Handles the create similar linear problem operation.
    """
    return generate_similar_linear_problem(target_answer, difficulty, seed)


@mcp.tool()
def schedule_question_review(
    mastery_status: str,
    review_count: int,
    last_result: str,
    reference_date: date | None = None,
) -> ReviewScheduleResult:
    """中文：处理“schedule·问题·复核”相关操作。
    English: Handles the schedule question review operation.
    """
    return calculate_review_schedule(mastery_status, review_count, last_result, reference_date)


@mcp.tool()
def schedule_initial_question_review(
    mastery_status: str,
    reference_date: date | None = None,
) -> ReviewScheduleResult:
    """中文：处理“schedule·initial·问题·复核”相关操作。
    English: Handles the schedule initial question review operation.
    """
    return calculate_initial_review_schedule(mastery_status, reference_date)


def main() -> None:
    """中文：处理“main”相关操作。
    English: Handles the main operation.
    """
    configure_cli_logging()
    mcp.run()


if __name__ == "__main__":
    main()
