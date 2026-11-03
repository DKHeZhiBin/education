from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class GuidanceState(StrEnum):
    """中文：定义教学引导运行状态。
    English: Defines the runtime state of pedagogical guidance.
    """

    EXPLORING = "exploring"
    UNCERTAIN = "uncertain"
    BLOCKED = "blocked"
    REMEDIATING = "remediating"
    GUIDED = "guided"
    VERIFYING = "verifying"
    REFLECTING = "reflecting"
    TRANSFER_TEST = "transfer_test"
    COMPLETED = "completed"


class BarrierType(StrEnum):
    """中文：定义由本轮证据支持的认知障碍类型。
    English: Defines evidence-backed cognitive barrier types for the current turn.
    """

    NONE = "none"
    KNOWLEDGE_GAP = "knowledge_gap"
    STRATEGY_SELECTION = "strategy_selection"
    EXPRESSION_TRANSFORMATION = "expression_transformation"
    EXECUTION_ERROR = "execution_error"
    ALTERNATIVE_VALID_PATH = "alternative_valid_path"
    UNCERTAIN = "uncertain"


class AttemptVerificationStatus(StrEnum):
    """中文：定义学生本轮步骤的三态校验结果。
    English: Defines the tri-state verification result for a learner attempt.
    """

    VALID = "valid"
    INVALID = "invalid"
    UNVERIFIED = "unverified"


class MathematicalGoal(BaseModel):
    """中文：表示解题图中一个可独立判断是否完成的数学目标。
    English: Represents a mathematical goal with an independently checkable completion contract.
    """

    id: str
    ordinal: int = Field(ge=1)
    title: str
    prerequisite_goal_ids: list[str] = Field(default_factory=list)
    step_ids: list[str] = Field(default_factory=list)
    completion_contract: str


class PedagogicalStep(BaseModel):
    """中文：表示为完成数学目标而执行的教学关键步骤。
    English: Represents a pedagogical step used to satisfy a mathematical goal.
    """

    id: str
    method_id: str
    index: int = Field(ge=1)
    goal_id: str
    statement: str
    justification: str = ""
    result: str | None = None
    prerequisite_step_ids: list[str] = Field(default_factory=list)


class SolutionPath(BaseModel):
    """中文：表示解题图中一条允许采用的解法路径。
    English: Represents one allowed solution path in the solution graph.
    """

    id: str
    method_id: str
    name: str
    step_ids: list[str] = Field(default_factory=list)
    recommended: bool = False


class SolutionGraph(BaseModel):
    """中文：保存数学目标、步骤依赖以及可替代解法路径。
    English: Stores mathematical goals, step dependencies, and alternative solution paths.
    """

    schema_version: Literal["1.0"] = "1.0"
    recommended_path_id: str | None = None
    terminal_goal_id: str | None = None
    goals: list[MathematicalGoal] = Field(default_factory=list)
    steps: list[PedagogicalStep] = Field(default_factory=list)
    paths: list[SolutionPath] = Field(default_factory=list)

    @classmethod
    def from_solution_plan(cls, solution: dict) -> "SolutionGraph":
        """中文：把已校验解法计划投影为可追踪的解题图。
        English: Projects a verified solution plan into a traceable solution graph.
        """

        methods = solution.get("methods") if isinstance(solution.get("methods"), list) else []
        recommended_method_id = str(solution.get("recommended_method_id") or "")
        selected = next(
            (
                method for method in methods
                if isinstance(method, dict) and str(method.get("id") or "") == recommended_method_id
            ),
            next((method for method in methods if isinstance(method, dict)), None),
        )
        if selected is None:
            legacy_steps = solution.get("steps") if isinstance(solution.get("steps"), list) else []
            selected = {
                "id": "recommended",
                "name": "推荐解法",
                "steps": [
                    {"index": index, "statement": statement, "justification": ""}
                    for index, statement in enumerate(legacy_steps, start=1)
                ],
            }
            methods = [selected]
            recommended_method_id = "recommended"

        selected_steps = selected.get("steps") if isinstance(selected.get("steps"), list) else []
        if not selected_steps:
            return cls()

        goals: list[MathematicalGoal] = []
        for index, raw_step in enumerate(selected_steps, start=1):
            step = raw_step if isinstance(raw_step, dict) else {"statement": str(raw_step)}
            statement = cls._clean_text(step.get("statement")) or f"完成第 {index} 个关键步骤"
            result = cls._clean_text(step.get("result"))
            title = cls._safe_goal_title(statement, index)
            goal_id = f"goal-{index}"
            goals.append(MathematicalGoal(
                id=goal_id,
                ordinal=index,
                title=title[:240],
                prerequisite_goal_ids=([f"goal-{index - 1}"] if index > 1 else []),
                completion_contract=(
                    f"学生能建立并说明：{result}"
                    if result
                    else f"学生能完成并说明依据：{statement}"
                )[:500],
            ))

        all_steps: list[PedagogicalStep] = []
        paths: list[SolutionPath] = []
        for method_position, method_raw in enumerate(methods, start=1):
            if not isinstance(method_raw, dict):
                continue
            method_id = str(method_raw.get("id") or f"method-{method_position}")
            method_steps = method_raw.get("steps") if isinstance(method_raw.get("steps"), list) else []
            path_step_ids: list[str] = []
            previous_step_id: str | None = None
            for step_position, raw_step in enumerate(method_steps, start=1):
                step = raw_step if isinstance(raw_step, dict) else {"statement": str(raw_step)}
                step_id = f"{method_id}-step-{step_position}"
                goal_ordinal = min(step_position, len(goals))
                goal_id = f"goal-{goal_ordinal}"
                path_step_ids.append(step_id)
                all_steps.append(PedagogicalStep(
                    id=step_id,
                    method_id=method_id,
                    index=step_position,
                    goal_id=goal_id,
                    statement=cls._clean_text(step.get("statement")) or f"完成步骤 {step_position}",
                    justification=cls._clean_text(step.get("justification")),
                    result=cls._clean_text(step.get("result")) or None,
                    prerequisite_step_ids=([previous_step_id] if previous_step_id else []),
                ))
                goals[goal_ordinal - 1].step_ids.append(step_id)
                previous_step_id = step_id
            path_id = f"path-{method_id}"
            paths.append(SolutionPath(
                id=path_id,
                method_id=method_id,
                name=cls._clean_text(method_raw.get("name")) or f"解法 {method_position}",
                step_ids=path_step_ids,
                recommended=method_id == recommended_method_id,
            ))

        recommended_path = next((path.id for path in paths if path.recommended), None)
        return cls(
            recommended_path_id=recommended_path or (paths[0].id if paths else None),
            terminal_goal_id=goals[-1].id if goals else None,
            goals=goals,
            steps=all_steps,
            paths=paths,
        )

    @staticmethod
    def _clean_text(value: object) -> str:
        """中文：清理用于结构化解题图的短文本。
        English: Cleans short text used in the structured solution graph.
        """

        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _safe_goal_title(statement: str, index: int) -> str:
        """中文：从内部解法步骤生成不泄露数值结果的学生可见目标名。
        English: Derives a learner-visible goal title without exposing internal numeric results.
        """

        rules = (
            (("定义域", "取值范围", "边界条件"), "确定定义域与边界条件"),
            (("交点", "零点"), "确定关键点或零点关系"),
            (("单调",), "建立并说明单调性"),
            (("有界", "界"), "建立并说明有界性"),
            (("连续", "间断"), "判断连续性并说明依据"),
            (("极限", "收敛"), "建立极限或收敛结论"),
            (("导数", "求导", "微分"), "建立导数关系"),
            (("积分", "原函数"), "建立积分关系"),
            (("方程", "求解", "根"), "建立待求量满足的方程"),
            (("代入", "检验", "验证"), "检验候选结论是否满足原条件"),
            (("化简", "变形", "因式", "展开", "配方"), "完成当前等价变形"),
            (("证明", "结论"), "闭合当前证明目标"),
        )
        for keywords, title in rules:
            if any(keyword in statement for keyword in keywords):
                return title
        return f"完成第 {index} 个关键数学目标"


class StudentAttempt(BaseModel):
    """中文：保存学生原始行为及其可追溯解析，不覆盖原输入。
    English: Stores the raw learner action and traceable interpretation without overwriting the input.
    """

    raw_input: str
    input_type: Literal["math", "text", "math_and_text", "help_request"]
    intent: str
    candidate_goal_id: str | None = None
    candidate_step_index: int | None = Field(default=None, ge=1)
    attempt_kind: str = "other"
    has_meaningful_attempt: bool = False
    verification_status: AttemptVerificationStatus = AttemptVerificationStatus.UNVERIFIED
    evidence_ids: list[str] = Field(default_factory=list)


class GuidanceDecision(BaseModel):
    """中文：表示规则状态机为一轮辅导作出的唯一教学决策。
    English: Represents the single teaching decision produced by the deterministic guidance policy.
    """

    state: GuidanceState
    event: str
    current_goal_id: str | None = None
    current_goal_title: str = "当前数学目标"
    current_goal_ordinal: int = Field(default=1, ge=1)
    completed_goal_ids: list[str] = Field(default_factory=list)
    total_goal_count: int = Field(default=0, ge=0)
    barrier_type: BarrierType = BarrierType.UNCERTAIN
    verification_status: AttemptVerificationStatus = AttemptVerificationStatus.UNVERIFIED
    teaching_action: Literal[
        "observe",
        "ask_diagnostic_question",
        "continue_exploration",
        "deliver_hint",
        "remediate_prerequisite",
        "verify_attempt",
        "reflect_on_strategy",
        "offer_transfer_test",
        "complete_session",
    ]
    allowed_actions: list[str] = Field(default_factory=list)
    hint_level: int | None = Field(default=None, ge=1, le=4)
    next_action: str
    reason: str


class GuidancePolicy:
    """中文：根据解题进度和本轮证据执行确定性的教学状态转换。
    English: Applies deterministic teaching state transitions from progress and turn evidence.
    """

    def decide(
        self,
        *,
        graph: SolutionGraph,
        diagnosis: dict,
        message: str,
        intent: str,
        current_hint_level: int,
        previous: GuidanceDecision | None = None,
    ) -> tuple[StudentAttempt, GuidanceDecision]:
        """中文：生成学生行为对象和本轮唯一引导决策。
        English: Produces the learner attempt object and the single guidance decision for the turn.
        """

        total_goals = len(graph.goals)
        diagnosed_ordinal = self._bounded_ordinal(
            diagnosis.get("next_solution_step_index"), total_goals
        )
        previous_ordinal = previous.current_goal_ordinal if previous else 1
        current_ordinal = max(previous_ordinal, diagnosed_ordinal)
        current_ordinal = min(max(current_ordinal, 1), max(total_goals, 1))
        goal = graph.goals[current_ordinal - 1] if graph.goals else None
        verification_status = self._attempt_verification(diagnosis)
        attempt = StudentAttempt(
            raw_input=message,
            input_type=self._input_type(message, bool(diagnosis.get("has_meaningful_attempt"))),
            intent=intent,
            candidate_goal_id=goal.id if goal else None,
            candidate_step_index=current_ordinal if total_goals else None,
            attempt_kind=str(diagnosis.get("attempt_kind") or "other"),
            has_meaningful_attempt=bool(diagnosis.get("has_meaning_attempt") or diagnosis.get("has_meaningful_attempt")),
            verification_status=verification_status,
            evidence_ids=[
                str(item.get("id"))
                for item in diagnosis.get("evidence", [])
                if isinstance(item, dict) and item.get("id")
            ],
        )
        barrier = self._barrier_type(diagnosis, message, verification_status)
        completed_count = max(0, current_ordinal - 1) if total_goals else 0

        if intent == "ask_solution":
            return attempt, self._decision(
                GuidanceState.GUIDED, "STUDENT_REQUESTS_FULL_SOLUTION", goal,
                graph, completed_count, barrier, verification_status,
                "deliver_hint", ["show_verified_solution"], 4,
                "展示经过校验的完整讲解，并让学生复述关键关系。",
                "学生明确请求完整讲解；仍由完整解法展示条件控制是否放行。",
            )
        if intent == "ask_hint":
            level = min(max(current_hint_level + 1, 1), 3)
            state = GuidanceState.REMEDIATING if barrier == BarrierType.KNOWLEDGE_GAP else GuidanceState.GUIDED
            action = "remediate_prerequisite" if state == GuidanceState.REMEDIATING else "deliver_hint"
            return attempt, self._decision(
                state, "STUDENT_REQUESTS_HINT", goal, graph, completed_count,
                barrier, verification_status, action,
                ["deliver_scaffold", "wait_for_attempt"], level,
                "只展开当前目标所需的下一层提示，等待学生完成该目标。",
                "学生主动请求提示，提示等级由规则逐级提升。",
            )
        if attempt.attempt_kind == "final_answer" and verification_status == AttemptVerificationStatus.VALID:
            return attempt, self._decision(
                GuidanceState.REFLECTING, "TERMINAL_RESULT_MATCHED", goal,
                graph, total_goals, BarrierType.NONE, verification_status,
                "reflect_on_strategy", ["summarize_reasoning", "ask_reflection"], None,
                "说明关键突破口，并用自己的话复述为什么这条路径成立。",
                "本轮结果与已校验答案一致；先复盘方法，不再返回早期步骤。",
            )
        if verification_status == AttemptVerificationStatus.INVALID:
            level = min(max(int(diagnosis.get("next_hint_level") or 1), 1), 3)
            return attempt, self._decision(
                GuidanceState.BLOCKED, "ATTEMPT_INVALID", goal, graph,
                completed_count, barrier, verification_status, "deliver_hint",
                ["locate_local_error", "deliver_scaffold"], level,
                "只定位当前局部错误，修改后重新提交这一步。",
                "本轮证据支持局部错误；禁止跳到后续目标或泄露完整答案。",
            )
        if attempt.has_meaningful_attempt and verification_status == AttemptVerificationStatus.VALID:
            return attempt, self._decision(
                GuidanceState.EXPLORING, "GOAL_PROGRESS_CONFIRMED", goal,
                graph, completed_count, BarrierType.NONE, verification_status,
                "continue_exploration", ["acknowledge_progress", "ask_next_step"], None,
                f"继续完成当前数学目标：{goal.title if goal else '当前目标'}。",
                "本轮已有可核验进展；保持目标单调前进，不提升提示等级。",
            )
        if attempt.has_meaningful_attempt:
            return attempt, self._decision(
                GuidanceState.VERIFYING, "ATTEMPT_NEEDS_VERIFICATION", goal,
                graph, completed_count, barrier, verification_status,
                "verify_attempt", ["ask_justification", "check_constraints"], None,
                "补充这一步使用的条件、公式或等价变形依据。",
                "学生给出了可检查步骤，但当前证据不足以判定正确或错误。",
            )
        return attempt, self._decision(
            GuidanceState.UNCERTAIN, "DIAGNOSIS_EVIDENCE_INSUFFICIENT", goal,
            graph, completed_count, barrier, verification_status,
            "ask_diagnostic_question", ["ask_one_diagnostic_question"], None,
            str(diagnosis.get("follow_up_question") or "写下你想到的第一步，并说明依据。"),
            "本轮没有可检查的数学步骤；先用一个问题区分障碍类型。",
        )

    @staticmethod
    def _decision(
        state: GuidanceState,
        event: str,
        goal: MathematicalGoal | None,
        graph: SolutionGraph,
        completed_count: int,
        barrier: BarrierType,
        verification_status: AttemptVerificationStatus,
        teaching_action: str,
        allowed_actions: list[str],
        hint_level: int | None,
        next_action: str,
        reason: str,
    ) -> GuidanceDecision:
        """中文：构造经过统一边界约束的引导决策。
        English: Builds a guidance decision under one consistent boundary contract.
        """

        return GuidanceDecision(
            state=state,
            event=event,
            current_goal_id=goal.id if goal else None,
            current_goal_title=goal.title if goal else "当前数学目标",
            current_goal_ordinal=goal.ordinal if goal else 1,
            completed_goal_ids=[item.id for item in graph.goals[:completed_count]],
            total_goal_count=len(graph.goals),
            barrier_type=barrier,
            verification_status=verification_status,
            teaching_action=teaching_action,
            allowed_actions=allowed_actions,
            hint_level=hint_level,
            next_action=next_action,
            reason=reason,
        )

    @staticmethod
    def _bounded_ordinal(value: object, total: int) -> int:
        """中文：把诊断步骤限制在当前解题图范围内。
        English: Bounds a diagnosed step ordinal to the active solution graph.
        """

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 1
        return min(max(parsed, 1), max(total, 1))

    @staticmethod
    def _input_type(message: str, meaningful: bool) -> str:
        """中文：按原始输入内容确定学生行为输入类型。
        English: Determines the learner input type from the raw message.
        """

        if not meaningful:
            return "help_request"
        has_math = bool(re.search(r"[0-9=+\-−×÷*/^]|\\[a-zA-Z]+", message))
        has_text = bool(re.search(r"[\u4e00-\u9fffA-Za-z]", message))
        if has_math and has_text:
            return "math_and_text"
        return "math" if has_math else "text"

    @staticmethod
    def _attempt_verification(diagnosis: dict) -> AttemptVerificationStatus:
        """中文：从可追溯诊断证据计算学生步骤的三态校验结论。
        English: Derives a tri-state attempt result from traceable diagnosis evidence.
        """

        evidence = diagnosis.get("evidence") if isinstance(diagnosis.get("evidence"), list) else []
        if any(
            isinstance(item, dict)
            and item.get("supports") == "mastery"
            and "已校验" in str(item.get("observation") or "")
            for item in evidence
        ):
            return AttemptVerificationStatus.VALID
        hypotheses = diagnosis.get("misconception_hypotheses")
        if isinstance(hypotheses, list) and any(
            isinstance(item, dict) and float(item.get("confidence") or 0) >= 0.6
            for item in hypotheses
        ):
            return AttemptVerificationStatus.INVALID
        return AttemptVerificationStatus.UNVERIFIED

    @staticmethod
    def _barrier_type(
        diagnosis: dict,
        message: str,
        verification_status: AttemptVerificationStatus,
    ) -> BarrierType:
        """中文：根据本轮诊断文本归并认知障碍，不形成长期能力标签。
        English: Classifies the current barrier without creating a persistent ability label.
        """

        hypotheses = diagnosis.get("misconception_hypotheses")
        if isinstance(hypotheses, list):
            structured = next((
                str(item.get("barrier_type"))
                for item in hypotheses
                if isinstance(item, dict)
                and item.get("barrier_type") in {member.value for member in BarrierType}
                and item.get("barrier_type") != BarrierType.NONE
            ), None)
            if structured:
                return BarrierType(structured)
        descriptions = " ".join(
            str(item.get("description") or "")
            for item in hypotheses or []
            if isinstance(item, dict)
        )
        text = f"{descriptions} {message}"
        if verification_status == AttemptVerificationStatus.VALID and any(
            token in text for token in ("另一种", "换一种", "不同方法", "另外一种")
        ):
            return BarrierType.ALTERNATIVE_VALID_PATH
        if any(token in text for token in ("没学", "前置", "定义不清", "公式不清", "不知道定义", "不知道公式")):
            return BarrierType.KNOWLEDGE_GAP
        if any(token in text for token in ("想不到", "策略", "方法选择", "从哪里", "方向")):
            return BarrierType.STRATEGY_SELECTION
        if any(token in text for token in ("变形", "转换", "化简", "因式分解", "移项", "代数处理")):
            return BarrierType.EXPRESSION_TRANSFORMATION
        if any(token in text for token in ("计算", "符号", "漏项", "算错", "代错", "局部错误")):
            return BarrierType.EXECUTION_ERROR
        if verification_status == AttemptVerificationStatus.VALID:
            return BarrierType.NONE
        return BarrierType.UNCERTAIN
