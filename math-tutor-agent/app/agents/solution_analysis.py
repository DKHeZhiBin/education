import json
import re
from typing import Any

from app.domain.solution import (
    KeyBreakthrough,
    SolutionMethod,
    SolutionPlan,
    SolutionStep,
)
from app.prompts.policies import SOLUTION_ANALYSIS_PROMPT, SOLUTION_REVISION_PROMPT
from app.providers.llm import OpenAICompatibleProvider


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _string_list(value: object, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(
        text for item in value if (text := _clean_text(item))
    ))[:limit]


def _bounded_number(value: object, default: float) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return default


def _difficulty(value: object) -> int:
    try:
        return max(1, min(int(value), 3))
    except (TypeError, ValueError):
        return 2


class SolutionAnalysisAgent:
    """Builds alternative solution routes and teachable breakthrough points."""

    name = "solution_analysis"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(
        self,
        question: str,
        problem: dict | None = None,
        teaching_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        problem = problem or {}
        if problem.get("needs_clarification"):
            return self._empty_plan(
                "题目仍有阻断性歧义，必须先完成澄清。"
            ).model_dump(mode="json")

        if re.search(
            r"3\s*[（(]\s*x\s*[−-]\s*2\s*[）)]\s*=\s*2\s*x\s*\+\s*5",
            question,
            re.I,
        ):
            return self._demo_plan().model_dump(mode="json")

        result = self.provider.complete_json(
            SOLUTION_ANALYSIS_PROMPT,
            json.dumps({
                "raw_question": question,
                "problem_spec": problem,
                "retrieved_teaching_context": teaching_context or {},
            }, ensure_ascii=False),
        )
        if not result:
            return self._empty_plan(
                "当前规则未覆盖此题；配置模型服务后才能生成可靠的候选解法。"
            ).model_dump(mode="json")
        return self._normalize_result(result).model_dump(mode="json")

    def revise(
        self,
        question: str,
        problem: dict,
        current_solution: dict,
        verification: dict,
        attempt: int,
        max_attempts: int,
    ) -> dict[str, Any]:
        result = self.provider.complete_json(
            SOLUTION_REVISION_PROMPT,
            json.dumps({
                "raw_question": question,
                "problem_spec": problem,
                "current_solution": current_solution,
                "verification_report": verification,
                "revision_attempt": attempt,
                "max_revision_attempts": max_attempts,
            }, ensure_ascii=False),
        )
        if not result:
            plan = self._empty_plan(
                "解题修订模型不可用，未能生成新的候选解法。"
            )
        else:
            plan = self._normalize_result(result)
        plan.revision_attempt = attempt
        plan.revision_reason = self._revision_reason(verification)
        return plan.model_dump(mode="json")

    @staticmethod
    def _revision_reason(verification: dict) -> str:
        issues = _string_list(verification.get("issues"), 6)
        if issues:
            return "；".join(issues)
        limitations = _string_list(verification.get("limitations"), 6)
        if limitations:
            return "；".join(limitations)
        return _clean_text(verification.get("evidence")) or "上一版解法未通过校验"

    @staticmethod
    def _demo_plan() -> SolutionPlan:
        methods = [
            SolutionMethod(
                id="distribute_then_collect",
                name="先展开再整理",
                strategy_summary="先消去括号，再把未知数项和常数项分别整理。",
                applicability="适合熟悉分配律和移项的一元一次方程学习者。",
                steps=[
                    SolutionStep(
                        index=1,
                        statement="用分配律展开左边",
                        justification="括号外的 3 要乘括号内的每一项。",
                        result="3x − 6 = 2x + 5",
                    ),
                    SolutionStep(
                        index=2,
                        statement="两边同时减去 2x",
                        justification="等式两边进行相同运算，等式仍成立。",
                        result="x − 6 = 5",
                    ),
                    SolutionStep(
                        index=3,
                        statement="两边同时加 6",
                        justification="把未知数 x 单独留在一边。",
                        result="x = 11",
                    ),
                ],
                answer="x = 11",
                advantages=["步骤符合常见教材顺序", "每一步都便于独立校验"],
                limitations=["展开时容易漏乘括号内的负数项"],
                confidence=0.94,
            ),
            SolutionMethod(
                id="function_intersection",
                name="函数交点法",
                strategy_summary="把等号两边看成两个一次函数，方程的解就是两个图像交点的横坐标。",
                applicability="适合已经学习一次函数图像和交点意义的学生。",
                steps=[
                    SolutionStep(
                        index=1,
                        statement="分别定义等号两边对应的函数",
                        justification="两个表达式相等的位置就是两个函数图像的交点。",
                        result="y₁ = 3(x − 2)，y₂ = 2x + 5",
                    ),
                    SolutionStep(
                        index=2,
                        statement="求两个函数值之差",
                        justification="交点处 y₁ − y₂ = 0。",
                        result="y₁ − y₂ = 3x − 6 − (2x + 5) = x − 11",
                    ),
                    SolutionStep(
                        index=3,
                        statement="令函数值之差为 0",
                        justification="此时两个函数值相等。",
                        result="x = 11",
                    ),
                ],
                answer="x = 11",
                advantages=["展示方程与函数交点的联系", "适合解释解的几何意义"],
                limitations=["需要一次函数基础", "单纯计算时步骤更多"],
                confidence=0.88,
            ),
        ]
        breakthroughs = [
            KeyBreakthrough(
                id="expand_all_terms",
                title="括号外的数要乘每一项",
                description="把 3(x − 2) 正确展开为 3x − 6。",
                why_it_matters="一旦漏乘 −2，后面的方程即使操作正确也会得到错误答案。",
                hint_question="括号外的 3 分别要和括号里的哪两项相乘？",
                related_method_ids=["distribute_then_collect", "function_intersection"],
            ),
            KeyBreakthrough(
                id="preserve_equality",
                title="始终保持等式平衡",
                description="移项的本质是等式两边同时进行相同运算。",
                why_it_matters="这能解释符号为何变化，并减少机械移项造成的错误。",
                hint_question="如果想消去右边的 2x，等式两边应该同时做什么？",
                related_method_ids=["distribute_then_collect"],
            ),
        ]
        return SolutionAnalysisAgent._build_plan(
            methods=methods,
            recommended_method_id="distribute_then_collect",
            recommendation_reason="教材顺序清晰，分配律、整理和隔离未知数三个知识点界限明确。",
            breakthroughs=breakthroughs,
            verification_targets=[
                "3(x − 2) 与 3x − 6 等价",
                "x = 11 代回原方程后左右两边相等",
                "两种方法得到相同解集",
            ],
            assumptions=[],
            knowledge_points=["分配律", "等式性质", "一元一次方程", "合并同类项"],
            common_misconceptions=[
                "括号外的数没有乘到每一项",
                "把移项记成机械变号，却没有保持等式两边同做运算",
                "把 3x − 2x 错算成 0",
            ],
            difficulty=2,
            confidence=0.93,
        )

    def _normalize_result(self, result: dict[str, Any]) -> SolutionPlan:
        methods = self._parse_methods(result.get("methods"))
        if not methods:
            legacy_steps = self._parse_steps(result.get("steps"))
            if legacy_steps:
                methods = [SolutionMethod(
                    id="primary",
                    name="主要解法",
                    strategy_summary=_clean_text(result.get("strategy_summary")),
                    steps=legacy_steps,
                    answer=self._optional_text(result.get("answer")),
                    confidence=_bounded_number(result.get("confidence"), 0.6),
                )]

        if not methods:
            return self._empty_plan(
                _clean_text(result.get("note")) or "模型没有给出可校验的完整解法。"
            )

        requested_id = _clean_text(result.get("recommended_method_id"))
        method_ids = {method.id for method in methods}
        recommended_id = (
            requested_id
            if requested_id in method_ids
            else max(methods, key=lambda method: method.confidence).id
        )
        breakthroughs = self._parse_breakthroughs(
            result.get("key_breakthroughs"),
            method_ids,
        )
        if not breakthroughs:
            first_step = next(
                (method.steps[0] for method in methods if method.steps),
                None,
            )
            if first_step is not None:
                breakthroughs = [KeyBreakthrough(
                    id="starting_point",
                    title="确定第一步",
                    description=first_step.statement,
                    why_it_matters=first_step.justification,
                    hint_question="根据已知条件，第一步可以先处理什么？",
                    related_method_ids=[recommended_id],
                )]

        return self._build_plan(
            methods=methods,
            recommended_method_id=recommended_id,
            recommendation_reason=_clean_text(result.get("recommendation_reason")),
            breakthroughs=breakthroughs,
            verification_targets=_string_list(result.get("verification_targets")),
            assumptions=_string_list(result.get("assumptions")),
            knowledge_points=_string_list(result.get("knowledge_points")),
            common_misconceptions=_string_list(result.get("common_misconceptions")),
            difficulty=_difficulty(result.get("difficulty")),
            confidence=_bounded_number(result.get("confidence"), 0.6),
            note=_clean_text(result.get("note")),
        )

    def _parse_methods(self, value: object) -> list[SolutionMethod]:
        if not isinstance(value, list):
            return []
        methods: list[SolutionMethod] = []
        used_ids: set[str] = set()
        for position, item in enumerate(value[:4], start=1):
            if not isinstance(item, dict):
                continue
            steps = self._parse_steps(item.get("steps"))
            if not steps:
                continue
            method_id = self._safe_id(item.get("id"), f"method_{position}")
            while method_id in used_ids:
                method_id = f"{method_id}_{position}"
            used_ids.add(method_id)
            methods.append(SolutionMethod(
                id=method_id,
                name=_clean_text(item.get("name")) or f"解法 {position}",
                strategy_summary=_clean_text(item.get("strategy_summary")),
                applicability=_clean_text(item.get("applicability")),
                steps=steps,
                answer=self._optional_text(item.get("answer")),
                advantages=_string_list(item.get("advantages"), 8),
                limitations=_string_list(item.get("limitations"), 8),
                confidence=_bounded_number(item.get("confidence"), 0.6),
            ))
        return methods

    @staticmethod
    def _parse_steps(value: object) -> list[SolutionStep]:
        if not isinstance(value, list):
            return []
        steps: list[SolutionStep] = []
        for position, item in enumerate(value[:20], start=1):
            if isinstance(item, str) and _clean_text(item):
                steps.append(SolutionStep(
                    index=position,
                    statement=_clean_text(item),
                    justification="待独立校验",
                ))
            elif isinstance(item, dict):
                statement = _clean_text(item.get("statement") or item.get("content"))
                if not statement:
                    continue
                steps.append(SolutionStep(
                    index=position,
                    statement=statement,
                    justification=(
                        _clean_text(item.get("justification"))
                        or "待独立校验"
                    ),
                    result=SolutionAnalysisAgent._optional_text(item.get("result")),
                ))
        return steps

    @staticmethod
    def _parse_breakthroughs(
        value: object,
        method_ids: set[str],
    ) -> list[KeyBreakthrough]:
        if not isinstance(value, list):
            return []
        breakthroughs: list[KeyBreakthrough] = []
        for position, item in enumerate(value[:8], start=1):
            if not isinstance(item, dict):
                continue
            description = _clean_text(item.get("description"))
            if not description:
                continue
            related = [
                method_id
                for method_id in _string_list(item.get("related_method_ids"), 4)
                if method_id in method_ids
            ]
            breakthroughs.append(KeyBreakthrough(
                id=SolutionAnalysisAgent._safe_id(
                    item.get("id"),
                    f"breakthrough_{position}",
                ),
                title=_clean_text(item.get("title")) or f"关键点 {position}",
                description=description,
                why_it_matters=_clean_text(item.get("why_it_matters")),
                hint_question=(
                    _clean_text(item.get("hint_question"))
                    or "这里最关键的关系是什么？"
                ),
                related_method_ids=related,
            ))
        return breakthroughs

    @staticmethod
    def _build_plan(
        methods: list[SolutionMethod],
        recommended_method_id: str,
        recommendation_reason: str,
        breakthroughs: list[KeyBreakthrough],
        verification_targets: list[str],
        assumptions: list[str],
        knowledge_points: list[str],
        common_misconceptions: list[str],
        difficulty: int,
        confidence: float,
        note: str = "",
    ) -> SolutionPlan:
        selected = next(
            method for method in methods if method.id == recommended_method_id
        )
        method_answers = [
            re.sub(r"\s+", "", method.answer).lower()
            for method in methods
            if method.answer
        ]
        if len(method_answers) != len(methods) or not method_answers:
            answer_consistency = "unconfirmed"
        elif len(set(method_answers)) == 1:
            answer_consistency = "consistent"
        else:
            answer_consistency = "conflict"
            confidence = min(confidence, 0.4)
            verification_targets = list(dict.fromkeys([
                *verification_targets,
                "不同解法给出的答案不一致，必须逐条复核后才能采用",
            ]))
            note = (
                f"{note}；不同解法的答案存在冲突。".strip("；")
            )
        rendered_steps = [
            f"{step.statement}：{step.result}" if step.result else step.statement
            for step in selected.steps
        ]
        return SolutionPlan(
            recommended_method_id=recommended_method_id,
            recommendation_reason=recommendation_reason,
            methods=methods,
            answer_consistency=answer_consistency,
            key_breakthroughs=breakthroughs,
            verification_targets=verification_targets,
            assumptions=assumptions,
            knowledge_points=knowledge_points,
            common_misconceptions=common_misconceptions,
            difficulty=difficulty,
            confidence=confidence,
            note=note,
            steps=rendered_steps,
            answer=selected.answer,
            alternative_methods=[
                method.name for method in methods if method.id != recommended_method_id
            ],
        )

    @staticmethod
    def _empty_plan(note: str) -> SolutionPlan:
        return SolutionPlan(
            knowledge_points=["待识别"],
            confidence=0.25,
            note=note,
        )

    @staticmethod
    def _safe_id(value: object, default: str) -> str:
        candidate = re.sub(r"[^a-zA-Z0-9_-]+", "_", _clean_text(value)).strip("_")
        return candidate[:64] or default

    @staticmethod
    def _optional_text(value: object) -> str | None:
        text = _clean_text(value)
        return text or None
