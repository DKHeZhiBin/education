import re
import unittest

from app.agents.similar_practice import ConstrainedSimilarPracticeAgent
from app.domain.curriculum import KnowledgePracticeSource
from app.domain.practice import KnowledgeExamplePracticeRequest, MotherProblemAnalysis


class _CandidateProvider:
    """中文：返回简短且可区分的候选题，用于验证并行编排。
    English: Returns compact distinct candidates for testing parallel orchestration.
    """

    provider_id = "fake"
    model_name = "fake-model"
    available = True

    def complete_json(self, system: str, user: str) -> dict:
        """中文：根据服务端分配的候选编号构造响应。 English: Builds a response from the server-assigned candidate id."""

        matched = re.search(r"候选编号：(c[123])", user)
        if matched is None:
            raise AssertionError("缺少候选编号")
        candidate_id = matched.group(1)
        return {"candidate": _candidate(candidate_id, score_suffix=candidate_id[-1])}

    def check_readiness(self) -> tuple[bool, str]:
        """中文：模拟可用的提供方。 English: Simulates an available provider."""

        return True, "ready"


class _AnalysisProvider:
    """中文：记录母题分析调用次数的可用提供方。 English: An available provider that counts mother-analysis calls."""

    provider_id = "fake"
    model_name = "analysis-cache-model"
    available = True

    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict:
        """中文：返回合法分析并记录调用。 English: Returns a valid analysis while recording the call."""

        self.calls += 1
        return _analysis().model_dump(mode="json")

    def check_readiness(self) -> tuple[bool, str]:
        return True, "ready"


class SimilarPracticeAgentTests(unittest.TestCase):
    """中文：验证 S/M/T 相似题编排与硬性质量门。 English: Verifies S/M/T orchestration and hard quality gates."""

    def setUp(self) -> None:
        """中文：创建不依赖数据库的 Agent 与母题。 English: Creates an Agent and mother problem without database dependencies."""

        self.agent = ConstrainedSimilarPracticeAgent(None)  # type: ignore[arg-type]
        self.source = KnowledgePracticeSource(
            knowledge_point_code="UC.C1.LIMIT.SEQ_LIMIT",
            knowledge_point_name="数列极限",
            subject="math",
            grade_band="university",
            content_key="recursive-sequence-limits",
            title="递推数列的极限",
            summary="先证明收敛，再求固定点。",
            body_markdown="a_{n+1}=sqrt(2+a_n)",
            formula_latex=None,
            structured_json={"difficulty": 2},
            solution_framework_json=[],
        )
        self.analysis = _analysis()

    def test_analysis_normalizes_relation_list_to_primary_label(self) -> None:
        """中文：模型误返多个关系标签时不应中断整条流程。 English: Multiple returned relation labels must not abort the pipeline."""

        payload = self.analysis.model_dump()
        payload["relation_form"] = ["explicit_recurrence", "fixed_point_equation"]
        normalized = MotherProblemAnalysis.model_validate(payload)
        self.assertEqual(normalized.relation_form, "explicit_recurrence")

    def test_s2_rejects_parameter_only_change(self) -> None:
        """中文：S2 不能放行仅改初值或参数的题。 English: S2 must reject a parameter-only variation."""

        unchanged = _candidate("c1", score_suffix="1")
        unchanged["structure_type"] = self.analysis.structure_type
        unchanged["function_family"] = self.analysis.function_family
        self.assertFalse(self.agent._structure_target_met(unchanged, self.analysis, "S2"))

    def test_selection_prefers_review_quality_over_text_distance(self) -> None:
        """中文：在通过硬规则的题中选教学质量更高者。 English: Selects the higher teaching-quality candidate among hard-rule passes."""

        low = _candidate("c1", score_suffix="1")
        high = _candidate("c2", score_suffix="2")
        chosen, _ = self.agent._select_candidate(
            self.source,
            self.analysis,
            [low, high],
            [_review("c1", 76), _review("c2", 92)],
            structure_level="S2",
            reasoning_level="M2",
            teaching_goal="T1",
            quality_threshold=78,
        )
        self.assertEqual(chosen["candidate_id"], "c2")

    def test_candidate_generation_returns_three_server_assigned_ids(self) -> None:
        """中文：三个短候选并行生成后仍按 c1、c2、c3 稳定排序。 English: Parallel compact generation preserves stable c1/c2/c3 ordering."""

        plan = self.agent._build_variation_plan(
            self.analysis,
            structure_level="S2",
            reasoning_level="M2",
            teaching_goal="T1",
        )
        candidates = self.agent._generate_candidates(
            self.source,
            self.analysis,
            plan,
            grade="大学",
            target_difficulty=2,
            structure_level="S2",
            reasoning_level="M2",
            teaching_goal="T1",
            candidate_count=3,
            revision_feedback=[],
            provider=_CandidateProvider(),
        )
        self.assertEqual([item["candidate_id"] for item in candidates], ["c1", "c2", "c3"])

    def test_difficulty_profiles_define_fixed_smt_and_candidate_budgets(self) -> None:
        """中文：简单、中等、困难由后端映射为固定 S/M/T 与 1/2/3 道候选。 English: Server profiles map easy, medium, and hard to fixed S/M/T targets and 1/2/3 candidates."""

        expected = {
            "easy": ("S1", "M1", "T2", 1),
            "medium": ("S2", "M2", "T1", 2),
            "hard": ("S3", "M3", "T4", 3),
        }
        for difficulty, target in expected.items():
            request = KnowledgeExamplePracticeRequest(
                knowledge_point_code="UC.C1.LIMIT.SEQ_LIMIT",
                content_key="recursive-sequence-limits",
                difficulty=difficulty,
                client_request_id=f"request-{difficulty}",
            )
            profile = request.difficulty_profile()
            self.assertEqual(
                (profile.structure_level, profile.reasoning_level, profile.teaching_goal, profile.candidate_count),
                target,
            )

    def test_mother_analysis_is_reused_for_same_source_and_model(self) -> None:
        """中文：同一母题与模型重复出题时只分析一次。 English: Reuses one analysis for repeated generation from the same source and model."""

        provider = _AnalysisProvider()
        first = self.agent._analyze_mother_problem(self.source, provider)
        second = self.agent._analyze_mother_problem(self.source, provider)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)


def _analysis() -> MotherProblemAnalysis:
    """中文：构造根式递推母题分析。 English: Builds a square-root recurrence analysis fixture."""

    return MotherProblemAnalysis(
        knowledge_points=["数列极限", "单调有界"],
        prerequisite_knowledge=["归纳法"],
        mathematical_objects=["实数列"],
        structure_type="explicit_first_order_recurrence",
        relation_form="explicit_recurrence",
        function_family="square_root",
        problem_goals=["证明收敛", "求极限"],
        proof_obligations=["不变区间", "单调性", "有界性"],
        strategies=["不变区间", "单调有界", "固定点筛选"],
        reasoning_steps=["建立范围", "证明单调", "求固定点"],
        key_breakthrough="建立不变区间后判断单调性",
        mechanical_routine_risk=["未证明收敛就直接取极限"],
        mutable_dimensions=["函数族"],
        method_breaking_changes=["失去单调性"],
        migration_directions=["改为分式递推"],
    )


def _candidate(candidate_id: str, *, score_suffix: str) -> dict:
    """中文：构造满足 S2/M2 字段合同的候选题。 English: Builds a candidate satisfying the S2/M2 field contract."""

    return {
        "candidate_id": candidate_id,
        "question": f"设数列 b_n 满足分式递推 {score_suffix}，证明收敛并求极限。",
        "answer": "1",
        "proof_steps": ["建立新不变区间", "证明单调有界", "求解并筛选固定点"],
        "first_step_prompt": "先尝试找到一个递推前后都成立的范围。",
        "structure_level": "S2",
        "reasoning_level": "M2",
        "teaching_goal": "T1",
        "structure_type": f"rational_recurrence_{score_suffix}",
        "relation_form": "explicit_recurrence",
        "function_family": f"rational_{score_suffix}",
        "mathematical_object": "实数列",
        "strategy_chain": ["不变区间", "固定点"],
        "key_strategy": "重建不变区间",
        "key_changes": ["函数族变为分式", "符号分析需重建"],
        "new_reasoning_step": "重新确定分式递推的不变区间。",
        "source_type": "ai_original_variation",
    }


def _review(candidate_id: str, score: int) -> dict:
    """中文：构造通过硬规则的独立复核结果。 English: Builds an independent review that passes every hard rule."""

    return {
        "candidate_id": candidate_id,
        "accepted": True,
        "mathematical_correctness": "passed",
        "condition_completeness": "passed",
        "structure_target_met": True,
        "reasoning_target_met": True,
        "teaching_goal_met": True,
        "parameter_only_change": False,
        "source_proof_directly_reusable": False,
        "naturalness_score": score,
        "knowledge_alignment_score": score,
        "proof_rigor_score": score,
        "difficulty_fit_score": score,
        "teaching_value_score": score,
        "issues": [],
        "verification_summary": "数学正确且符合目标。",
    }


if __name__ == "__main__":
    unittest.main()
