from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RetrievalPurpose = Literal[
    "problem_understanding",
    "solution_analysis",
    "hint_teaching",
    "source_lookup",
]


@dataclass(frozen=True)
class RetrievalDecision:
    should_retrieve: bool
    purpose: RetrievalPurpose
    reason_code: str
    explanation: str

    def as_payload(self) -> dict[str, object]:
        return {
            "should_retrieve": self.should_retrieve,
            "purpose": self.purpose,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
        }


class OnDemandRetrievalPolicy:
    """Deterministic gate that keeps RAG optional and auditable."""

    _SOURCE_TERMS = (
        "出处",
        "来源",
        "教材",
        "课程标准",
        "哪个版本",
        "定义",
        "符号含义",
        "定理原文",
    )
    _METHOD_TERMS = (
        "多种解法",
        "另一种解法",
        "同类题",
        "类似题",
        "例题",
        "用什么定理",
        "公式依据",
    )
    _HINT_TERMS = (
        "提示",
        "不会",
        "不知道",
        "卡住",
        "怎么做",
        "为什么",
        "公式",
        "定理",
        "例题",
        "类似题",
        "关键关系",
    )
    _COMPLEX_TYPES = {
        "quadratic_equation",
        "trigonometry",
        "geometry",
        "analytic_geometry",
        "proof",
        "sequence",
        "combinatorics",
        "probability",
        "number_theory",
        "optimization",
        "calculus",
    }

    def decide_problem_understanding(
        self,
        question: str,
        *,
        retriever_available: bool,
    ) -> RetrievalDecision:
        unavailable = self._unavailable("problem_understanding", retriever_available)
        if unavailable:
            return unavailable
        if self._contains(question, self._SOURCE_TERMS):
            return RetrievalDecision(
                True,
                "problem_understanding",
                "explicit_source_or_definition_need",
                "题目明确要求教材定义、符号解释、来源或版本信息。",
            )
        return RetrievalDecision(
            False,
            "problem_understanding",
            "plain_problem_statement",
            "题目可先由题意识别 Agent 直接结构化。",
        )

    def decide_solution_analysis(
        self,
        question: str,
        problem: dict,
        *,
        retriever_available: bool,
        retrieval_already_used: bool = False,
    ) -> RetrievalDecision:
        unavailable = self._unavailable("solution_analysis", retriever_available)
        if unavailable:
            return unavailable
        if retrieval_already_used:
            return RetrievalDecision(
                False,
                "solution_analysis",
                "run_retrieval_budget_used",
                "本轮已经执行过一次检索。",
            )
        if problem.get("needs_clarification"):
            return RetrievalDecision(
                False,
                "solution_analysis",
                "blocking_ambiguity",
                "题目仍有阻断性歧义，先向学生澄清。",
            )
        if self._contains(question, self._METHOD_TERMS):
            return RetrievalDecision(
                True,
                "solution_analysis",
                "explicit_method_or_example_need",
                "用户明确需要其他方法、定理依据或同构例题。",
            )
        question_type = str(problem.get("question_type") or "unknown")
        confidence = self._number(problem.get("confidence"), 0.5)
        warning_count = sum(
            1
            for item in problem.get("ambiguities", [])
            if isinstance(item, dict) and item.get("severity") == "warning"
        )
        condition_count = len(problem.get("known_conditions") or [])
        if question_type in self._COMPLEX_TYPES:
            return RetrievalDecision(
                True,
                "solution_analysis",
                "complex_question_type",
                f"题型 {question_type} 可能受益于可追溯定理或同构题结构。",
            )
        if confidence < 0.65 or warning_count > 0 or condition_count >= 5:
            return RetrievalDecision(
                True,
                "solution_analysis",
                "low_confidence_or_dense_conditions",
                "题意置信度较低、存在警告或条件较多。",
            )
        return RetrievalDecision(
            False,
            "solution_analysis",
            "reliable_direct_solution_path",
            "题意清楚且现有解题与验证链路足以处理。",
        )

    def decide_hint_teaching(
        self,
        message: str,
        intent: str,
        *,
        retriever_available: bool,
        has_verified_solution: bool,
    ) -> RetrievalDecision:
        unavailable = self._unavailable("hint_teaching", retriever_available)
        if unavailable:
            return unavailable
        if intent == "complete":
            return RetrievalDecision(
                False,
                "hint_teaching",
                "session_completion",
                "完成确认不需要访问知识库。",
            )
        if intent == "practice":
            return RetrievalDecision(
                False,
                "hint_teaching",
                "practice_generation_not_retrieval",
                "练习题生成由独立流程处理，本轮不检索教学上下文。",
            )
        if not has_verified_solution:
            return RetrievalDecision(
                False,
                "hint_teaching",
                "verified_solution_unavailable",
                "检索不能替代解答校验；当前先走澄清或修订流程。",
            )
        if self._contains(message, self._METHOD_TERMS):
            return RetrievalDecision(
                True,
                "hint_teaching",
                "example_or_method_request",
                "学生请求例题、类似题或其他方法。",
            )
        if self._contains(message, self._HINT_TERMS):
            return RetrievalDecision(
                True,
                "hint_teaching",
                "explicit_scaffolding_request",
                "学生明确请求提示、公式、定理或关键关系。",
            )
        return RetrievalDecision(
            False,
            "hint_teaching",
            "student_attempt_can_be_diagnosed_directly",
            "本轮作答可直接依据已校验解法诊断。",
        )

    @staticmethod
    def _contains(text: str, terms: tuple[str, ...]) -> bool:
        normalized = str(text or "").lower()
        return any(term.lower() in normalized for term in terms)

    @staticmethod
    def _number(value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _unavailable(
        purpose: RetrievalPurpose,
        retriever_available: bool,
    ) -> RetrievalDecision | None:
        if retriever_available:
            return None
        return RetrievalDecision(
            False,
            purpose,
            "retriever_unavailable",
            "RAG 已关闭或 Provider 当前不可用。",
        )
