from __future__ import annotations

import re
from typing import Any

from app.domain.schemas import KnowledgeLearningEvidence, LearningRecord, TutoringSession


class LearningRecordAgent:
    """中文：定义“学习·记录·智能体”类，封装该职责相关的数据与行为。
    English: Defines the learning record agent class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Build one evidence-backed record from the complete tutoring session.
    """

    name = "learning_record"

    def run(self, session: TutoringSession, solution: dict[str, Any]) -> LearningRecord:
        """中文：处理“执行”相关操作。
        English: Handles the run operation.
        """
        learner_states = self._learner_states(session)
        meaningful_states = [
            state for state in learner_states if state.get("has_meaningful_attempt") is True
        ]
        learner_answers = list(dict.fromkeys(
            answer
            for state in meaningful_states[-3:]
            if (answer := self._text(state.get("observed_work"), 1200))
        ))
        error_reason = self._error_reason(meaningful_states)
        error_category = self._error_category(meaningful_states, error_reason)
        knowledge_tags = self._string_list(solution.get("knowledge_points"), 20)
        mastered_evidence = any(
            isinstance(state.get("mastered_points"), list) and state["mastered_points"]
            for state in meaningful_states
        )

        mastery = self._mastery(session, mastered_evidence)
        return LearningRecord(
            subject=session.profile.subject,
            grade=session.profile.grade,
            question=session.question,
            learner_answer="\n".join(learner_answers),
            error_category=error_category,
            error_reason=error_reason,
            correct_approach=self._correct_approach(solution),
            knowledge_tags=knowledge_tags,
            knowledge_points=[
                KnowledgeLearningEvidence(
                    name=tag,
                    mistake_detected=error_category == "misconception",
                    error_category=(error_category if error_category == "misconception" else ""),
                    error_reason=(error_reason if error_category == "misconception" else ""),
                    hint_level=session.hint_level,
                    effective_attempt_count=session.attempts,
                    mastery=mastery,
                    evidence=self._knowledge_evidence(
                        tag,
                        meaningful_states,
                        error_reason,
                        error_category,
                        session,
                    ),
                )
                for tag in knowledge_tags
            ],
            difficulty=self._difficulty(solution.get("difficulty")),
            mastery=mastery,
            hint_level=session.hint_level,
            attempt_count=session.attempts,
        )

    @classmethod
    def _knowledge_evidence(
        cls,
        tag: str,
        states: list[dict[str, Any]],
        error_reason: str,
        error_category: str,
        session: TutoringSession,
    ) -> str:
        """中文：处理“知识·evidence”相关操作。
        English: Handles the knowledge evidence operation.
        """
        for state in reversed(states):
            for observation in state.get("mastered_points", []):
                if not isinstance(observation, dict):
                    continue
                description = cls._text(observation.get("description"), 500)
                if description and (tag in description or description in tag):
                    return description
        if error_category == "misconception":
            return error_reason
        return (
            f"本轮记录到 {session.attempts} 次有效尝试，"
            f"最高使用第 {session.hint_level} 级提示。"
        )

    @staticmethod
    def _learner_states(session: TutoringSession) -> list[dict[str, Any]]:
        """中文：处理“learner·states”相关操作。
        English: Handles the learner states operation.
        """
        return [
            artifact.payload
            for artifact in session.artifacts
            if artifact.kind == "learner_state" and isinstance(artifact.payload, dict)
        ]

    @classmethod
    def _error_reason(cls, states: list[dict[str, Any]]) -> str:
        """中文：处理“error·reason”相关操作。
        English: Handles the error reason operation.
        """
        for state in reversed(states):
            hypotheses = state.get("misconception_hypotheses")
            if isinstance(hypotheses, list):
                for hypothesis in hypotheses:
                    if not isinstance(hypothesis, dict):
                        continue
                    description = cls._text(hypothesis.get("description"), 500)
                    evidence_ids = hypothesis.get("evidence_ids")
                    if description and isinstance(evidence_ids, list) and evidence_ids:
                        return description
            possible = cls._text(state.get("possible_misconception"), 500)
            if possible and possible not in {"待进一步观察", "尚未形成可验证的错误证据"}:
                return possible
        if states:
            return "本次作答没有形成足够证据确认具体错因。"
        return "本次会话没有记录到可检查的独立作答步骤。"

    @staticmethod
    def _error_category(states: list[dict[str, Any]], reason: str) -> str:
        """中文：处理“error·category”相关操作。
        English: Handles the error category operation.
        """
        if "没有记录到" in reason:
            return "insufficient_attempt"
        if "没有形成足够证据" not in reason:
            return "misconception"
        kinds = {
            str(state.get("attempt_kind") or "")
            for state in states
        }
        if "proof_argument" in kinds:
            return "reasoning"
        if "partial_work" in kinds:
            return "procedure"
        if "final_answer" in kinds:
            return "answer_check"
        return "unclassified"

    @classmethod
    def _correct_approach(cls, solution: dict[str, Any]) -> str:
        """中文：处理“correct·approach”相关操作。
        English: Handles the correct approach operation.
        """
        methods = solution.get("methods") if isinstance(solution.get("methods"), list) else []
        recommended_id = cls._text(solution.get("recommended_method_id"), 100)
        selected = next(
            (
                method for method in methods
                if isinstance(method, dict) and str(method.get("id") or "") == recommended_id
            ),
            next((method for method in methods if isinstance(method, dict)), None),
        )
        parts: list[str] = []
        if isinstance(selected, dict):
            if strategy := cls._text(selected.get("strategy_summary"), 500):
                parts.append(strategy)
            steps = selected.get("steps") if isinstance(selected.get("steps"), list) else []
        else:
            steps = solution.get("steps") if isinstance(solution.get("steps"), list) else []
        for step in steps:
            if isinstance(step, dict):
                statement = cls._text(step.get("statement"), 500)
                result = cls._text(step.get("result"), 500)
                text = f"{statement}，得到 {result}" if statement and result else statement or result
            else:
                text = cls._text(step, 500)
            if text:
                parts.append(text)
        return "；".join(dict.fromkeys(parts)) or "本轮没有生成通过校验的结构化解题路线。"

    @staticmethod
    def _mastery(session: TutoringSession, mastered_evidence: bool) -> str:
        """中文：处理“掌握度”相关操作。
        English: Handles the mastery operation.
        """
        if session.attempts >= 2 and mastered_evidence and session.hint_level <= 1:
            return "已掌握"
        return "待巩固"

    @staticmethod
    def _difficulty(value: object) -> int:
        """中文：处理“difficulty”相关操作。
        English: Handles the difficulty operation.
        """
        try:
            return max(1, min(int(value), 3))
        except (TypeError, ValueError):
            return 2

    @classmethod
    def _string_list(cls, value: object, limit: int) -> list[str]:
        """中文：处理“string·列出”相关操作。
        English: Handles the string list operation.
        """
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(
            text for item in value[:limit] if (text := cls._text(item, 120))
        ))

    @staticmethod
    def _text(value: object, limit: int) -> str:
        """中文：处理“text”相关操作。
        English: Handles the text operation.
        """
        return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]
