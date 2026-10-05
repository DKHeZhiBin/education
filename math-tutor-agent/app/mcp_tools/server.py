from datetime import date

from mcp.server import MCPServer

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
from app.mcp_tools.review_tools import calculate_review_schedule


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
    """Safely simplify an arithmetic or algebraic expression without arbitrary code execution."""
    return simplify_expression(expression)


@mcp.tool()
def solve_math_equation(equation: str, variable: str = "x") -> EquationSolutionResult:
    """Solve a one-variable equation over the real numbers and verify finite solutions."""
    return solve_equation(equation, variable)


@mcp.tool()
def verify_math_candidate(
    equation: str,
    candidate: str,
    variable: str = "x",
) -> CandidateVerificationResult:
    """Substitute a proposed numeric answer into an equation and return its residual."""
    return verify_candidate_answer(equation, candidate, variable)


@mcp.tool()
def compare_solution_steps(
    before: str,
    after: str,
    variable: str = "x",
) -> StepComparisonResult:
    """Check whether two algebraic expressions or two one-variable equations are equivalent."""
    return compare_math_steps(before, after, variable)


@mcp.tool()
def create_similar_linear_problem(
    target_answer: int,
    difficulty: int = 1,
    seed: int = 0,
) -> SimilarProblemResult:
    """Create a deterministic linear-equation practice problem with a known integer answer."""
    return generate_similar_linear_problem(target_answer, difficulty, seed)


@mcp.tool()
def schedule_question_review(
    mastery_status: str,
    review_count: int,
    last_result: str,
    reference_date: date | None = None,
) -> ReviewScheduleResult:
    """Calculate the next review date from mastery state and the latest attempt result."""
    return calculate_review_schedule(mastery_status, review_count, last_result, reference_date)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
