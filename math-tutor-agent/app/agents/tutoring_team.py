import json
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from app.agents.problem_understanding import ProblemUnderstandingAgent
from app.agents.learning_record import LearningRecordAgent
from app.agents.solution_analysis import SolutionAnalysisAgent
from app.agents.solution_verification import SolutionVerificationAgent
from app.core.product_scope import MVP_GRADE_BAND, MVP_SUBJECT_CODE
from app.domain.schemas import (
    AgentArtifact,
    LearnerProfile,
    Message,
    TutoringSession,
)
from app.domain.guidance import (
    AttemptVerificationStatus,
    BarrierType,
    GuidanceDecision,
    GuidancePolicy,
    GuidanceState,
    SolutionGraph,
)
from app.domain.learner import (
    EvidenceBackedObservation,
    LearnerEvidence,
    LearnerState,
    MisconceptionHypothesis,
)
from app.domain.knowledge import (
    KnowledgeFilters,
    KnowledgeQuery,
    RetrievalProblemStructure,
    RetrievedTeachingContext,
)
from app.domain.student_history import StudentHistoryQuery
from app.domain.tutoring import (
    HintLevel,
    TutorAction,
    TutorReply,
    TutorSourceReference,
    TutoringStatus,
)
from app.prompts.policies import (
    LEARNER_DIAGNOSIS_PROMPT,
    TUTOR_REPLY_PROMPT,
)
from app.providers.llm import LLMProvider, llm_provider
from app.providers.knowledge import DisabledKnowledgeRetriever, KnowledgeRetriever
from app.providers.student_history import (
    DisabledStudentHistoryRetriever,
    StudentHistoryRetriever,
)
from app.retrieval.decision import OnDemandRetrievalPolicy, RetrievalDecision


def bounded_number(value: object, default: float, minimum: float, maximum: float) -> float:
    """中文：处理“bounded·number”相关操作。
    English: Handles the bounded number operation.
    """
    try:
        return max(minimum, min(float(value), maximum))
    except (TypeError, ValueError):
        return default


def bounded_integer(value: object, default: int, minimum: int, maximum: int) -> int:
    """中文：处理“bounded·integer”相关操作。
    English: Handles the bounded integer operation.
    """
    return int(bounded_number(value, default, minimum, maximum))


def _compact_text(value: object, limit: int = 500) -> str:
    """中文：处理“compact·text”相关操作。
    English: Handles the compact text operation.
    """
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _has_meaningful_attempt(message: str) -> bool:
    """中文：处理“has·meaningful·attempt”相关操作。
    English: Handles the has meaningful attempt operation.
    """
    text = _compact_text(message)
    if not text:
        return False
    request_terms = (
        "不会", "不知道", "不确定", "卡住", "提示", "怎么做",
        "直接告诉", "完整答案", "完整讲解", "看解法", "标准解法", "详细解法",
    )
    mathematical_evidence = bool(
        re.search(r"[0-9=+\-−×÷*/^]", text)
        or any(term in text for term in (
            "因为", "所以", "因此", "可得", "由", "设", "代入", "展开", "移项",
            "证明", "我先", "得到", "相等", "平行", "垂直", "大于", "小于",
        ))
    )
    if any(term in text for term in request_terms) and not mathematical_evidence:
        return False
    return mathematical_evidence


class LearnerDiagnosisAgent:
    """中文：定义“learner·diagnosis·智能体”类，封装该职责相关的数据与行为。
    English: Defines the learner diagnosis agent class and encapsulates data and behavior for that responsibility.
    """
    name = "learner_diagnosis"

    def __init__(self, provider: LLMProvider) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.provider = provider

    def run(self, message: str, solution: dict, verification: dict) -> dict:
        """中文：处理“执行”相关操作。
        English: Handles the run operation.
        """
        reliable_solution = solution if verification.get("passed") else {}
        result = self.provider.complete_json(
            LEARNER_DIAGNOSIS_PROMPT,
            json.dumps({
                "student_message": message,
                "solution_context": reliable_solution,
                "verification_summary": {
                    "passed": bool(verification.get("passed")),
                    "coverage": verification.get("coverage", "none"),
                },
            }, ensure_ascii=False),
        ) or {}
        return self._normalize(message, reliable_solution, result).model_dump(mode="json")

    def _normalize(
        self,
        message: str,
        reliable_solution: dict,
        result: dict,
    ) -> LearnerState:
        """中文：处理“规范化”相关操作。
        English: Handles the normalize operation.
        """
        observed_work = _compact_text(message, 5000)
        meaningful = _has_meaningful_attempt(observed_work)
        attempt_kind = self._attempt_kind(observed_work, reliable_solution, meaningful)
        evidence = self._evidence(result.get("evidence"), observed_work)
        if not evidence:
            evidence = [LearnerEvidence(
                id="e1",
                quote=observed_work[:160],
                observation=(
                    "本轮提供了可检查的数学表达或推理。"
                    if meaningful
                    else "本轮表达了求助或疑问，尚未提供可检查的数学步骤。"
                ),
                supports="attempt" if meaningful else "uncertainty",
            )]

        verified_matches = self._verified_matches(observed_work, reliable_solution)
        match_evidence_id: str | None = None
        if verified_matches:
            match_evidence_id = "e_verified_match"
            evidence.append(LearnerEvidence(
                id=match_evidence_id,
                quote=observed_work[:160],
                observation="本轮文本包含与已校验解法一致的结果。",
                supports="mastery",
            ))

        mastery_evidence_ids = {
            item.id for item in evidence if item.supports in {"mastery", "attempt"}
        }
        misconception_evidence_ids = {
            item.id for item in evidence
            if item.supports in {"misconception", "attempt"}
        }
        mastered = self._observations(
            result.get("mastered_points"),
            mastery_evidence_ids,
        )
        deterministic_mastery = self._matching_mastery(
            verified_matches,
            match_evidence_id,
        )
        descriptions = {item.description for item in mastered}
        mastered.extend(
            item for item in deterministic_mastery
            if item.description not in descriptions
        )
        hypotheses = self._hypotheses(
            result.get("misconception_hypotheses"),
            misconception_evidence_ids,
        )
        uncertainties = self._safe_strings(result.get("uncertainties"), 8)
        if not reliable_solution:
            uncertainties = list(dict.fromkeys([
                *uncertainties,
                "当前没有通过校验的标准解法，不能据此判断本轮答案正误。",
            ]))
        if not meaningful:
            uncertainties = list(dict.fromkeys([
                *uncertainties,
                "本轮没有可检查的数学步骤，无法判断具体知识点掌握情况。",
            ]))

        possible_misconception = (
            hypotheses[0].description if hypotheses else "需要追问"
        )
        follow_up = _compact_text(result.get("follow_up_question"), 300)
        if not follow_up or self._contains_trait_label(follow_up):
            follow_up = (
                "你能写出刚才想到的第一步，并说明依据吗？"
                if not meaningful
                else "你能说明这一步使用了哪个条件或公式吗？"
            )
        confidence = bounded_number(result.get("confidence"), 0.45, 0, 0.85)
        if not meaningful:
            confidence = min(confidence, 0.45)
        solution_step_count = self._solution_step_count(reliable_solution)
        next_solution_step_index = (
            bounded_integer(
                result.get("next_solution_step_index"),
                1,
                1,
                solution_step_count,
            )
            if solution_step_count and result.get("next_solution_step_index") is not None
            else None
        )
        return LearnerState(
            observed_work=observed_work,
            attempt_kind=attempt_kind,
            has_meaningful_attempt=meaningful,
            evidence=evidence,
            mastered_points=mastered,
            misconception_hypotheses=hypotheses,
            uncertainties=uncertainties,
            possible_misconception=possible_misconception,
            next_hint_level=bounded_integer(
                result.get("next_hint_level"), 1, 1, 3
            ),
            next_solution_step_index=next_solution_step_index,
            follow_up_question=follow_up,
            confidence=confidence,
        )

    @staticmethod
    def _solution_step_count(solution: dict) -> int:
        """中文：返回推荐解法中可定位步骤的数量。
        English: Returns the number of addressable steps in the recommended solution.
        """
        methods = solution.get("methods") if isinstance(solution.get("methods"), list) else []
        recommended_id = solution.get("recommended_method_id")
        method = next(
            (
                item for item in methods
                if isinstance(item, dict) and item.get("id") == recommended_id
            ),
            {},
        )
        steps = method.get("steps") if isinstance(method.get("steps"), list) else []
        if not steps and isinstance(solution.get("steps"), list):
            steps = solution["steps"]
        return len(steps)

    @staticmethod
    def _evidence(value: object, message: str) -> list[LearnerEvidence]:
        """中文：处理“evidence”相关操作。
        English: Handles the evidence operation.
        """
        if not isinstance(value, list):
            return []
        normalized_message = _compact_text(message, 5000)
        evidence: list[LearnerEvidence] = []
        for position, item in enumerate(value[:8], start=1):
            if not isinstance(item, dict):
                continue
            quote = _compact_text(item.get("quote"), 160)
            observation = _compact_text(item.get("observation"), 300)
            supports = _compact_text(item.get("supports"), 30)
            if (
                not quote
                or quote not in normalized_message
                or not observation
                or LearnerDiagnosisAgent._contains_trait_label(observation)
            ):
                continue
            if supports not in {"attempt", "mastery", "misconception", "uncertainty"}:
                supports = "uncertainty"
            evidence.append(LearnerEvidence(
                id=f"e{position}",
                quote=quote,
                observation=observation,
                supports=supports,
            ))
        return evidence

    @staticmethod
    def _observations(
        value: object,
        evidence_ids: set[str],
    ) -> list[EvidenceBackedObservation]:
        """中文：处理“observations”相关操作。
        English: Handles the observations operation.
        """
        if not isinstance(value, list):
            return []
        observations: list[EvidenceBackedObservation] = []
        for item in value[:8]:
            if not isinstance(item, dict):
                continue
            description = _compact_text(item.get("description"), 300)
            linked = [
                str(identifier) for identifier in item.get("evidence_ids", [])
                if str(identifier) in evidence_ids
            ] if isinstance(item.get("evidence_ids"), list) else []
            if (
                description
                and linked
                and not LearnerDiagnosisAgent._contains_trait_label(description)
            ):
                observations.append(EvidenceBackedObservation(
                    description=description,
                    evidence_ids=list(dict.fromkeys(linked)),
                ))
        return observations

    @staticmethod
    def _hypotheses(
        value: object,
        evidence_ids: set[str],
    ) -> list[MisconceptionHypothesis]:
        """中文：处理“hypotheses”相关操作。
        English: Handles the hypotheses operation.
        """
        if not isinstance(value, list):
            return []
        hypotheses: list[MisconceptionHypothesis] = []
        for item in value[:6]:
            if not isinstance(item, dict):
                continue
            description = _compact_text(item.get("description"), 300)
            linked = [
                str(identifier) for identifier in item.get("evidence_ids", [])
                if str(identifier) in evidence_ids
            ] if isinstance(item.get("evidence_ids"), list) else []
            if (
                description
                and linked
                and not LearnerDiagnosisAgent._contains_trait_label(description)
            ):
                hypotheses.append(MisconceptionHypothesis(
                    description=description,
                    evidence_ids=list(dict.fromkeys(linked)),
                    barrier_type=(
                        item.get("barrier_type")
                        if item.get("barrier_type") in {
                            "knowledge_gap",
                            "strategy_selection",
                            "expression_transformation",
                            "execution_error",
                            "alternative_valid_path",
                            "uncertain",
                        }
                        else "uncertain"
                    ),
                    missing_evidence=LearnerDiagnosisAgent._safe_strings(
                        item.get("missing_evidence"), 4
                    ),
                    confidence=bounded_number(
                        item.get("confidence"), 0.45, 0, 0.8
                    ),
                ))
        return hypotheses

    @staticmethod
    def _matching_mastery(
        matches: list[str],
        evidence_id: str | None,
    ) -> list[EvidenceBackedObservation]:
        """中文：处理“matching·掌握度”相关操作。
        English: Handles the matching mastery operation.
        """
        if not matches or evidence_id is None:
            return []
        return [EvidenceBackedObservation(
            description=description,
            evidence_ids=[evidence_id],
        ) for description in matches]

    @staticmethod
    def _verified_matches(message: str, solution: dict) -> list[str]:
        """中文：处理“verified·matches”相关操作。
        English: Handles the verified matches operation.
        """
        if not solution:
            return []
        normalized_message = re.sub(r"\s+", "", message).lower()
        matches: list[str] = []
        answer = re.sub(r"\s+", "", str(solution.get("answer") or "")).lower()
        answer_candidates = [answer]
        if "=" in answer:
            answer_candidates.append(answer.rsplit("=", 1)[-1])
        if any(candidate and candidate in normalized_message for candidate in answer_candidates):
            matches.append(
                "本轮给出的结果与已校验答案一致；这只确认结果，不单独证明方法已经掌握。"
            )
        method = HintTeachingAgent._selected_method(solution)
        steps = method.get("steps") if isinstance(method.get("steps"), list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            result = re.sub(r"\s+", "", str(step.get("result") or "")).lower()
            if result and result in normalized_message:
                matches.append("本轮写出了与已校验解法一致的中间结果。")
                break
        return matches

    @staticmethod
    def _attempt_kind(message: str, solution: dict, meaningful: bool) -> str:
        """中文：处理“attempt·kind”相关操作。
        English: Handles the attempt kind operation.
        """
        if not meaningful:
            return "question" if "?" in message or "？" in message else "help_request"
        if any(term in message for term in ("证明", "因为", "所以")):
            return "proof_argument"
        normalized_message = re.sub(r"\s+", "", message).lower()
        answer = re.sub(r"\s+", "", str(solution.get("answer") or "")).lower()
        answer_candidates = [answer]
        if "=" in answer:
            answer_candidates.append(answer.rsplit("=", 1)[-1])
        if any(candidate and candidate in normalized_message for candidate in answer_candidates):
            return "final_answer"
        return "partial_work"

    @staticmethod
    def _safe_strings(value: object, limit: int) -> list[str]:
        """中文：处理“safe·strings”相关操作。
        English: Handles the safe strings operation.
        """
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(
            text for item in value[:limit]
            if (text := _compact_text(item, 300))
            and not LearnerDiagnosisAgent._contains_trait_label(text)
        ))

    @staticmethod
    def _contains_trait_label(text: str) -> bool:
        """中文：处理“contains·trait·label”相关操作。
        English: Handles the contains trait label operation.
        """
        return any(term in text for term in (
            "能力差", "能力弱", "基础差", "数学不好", "不擅长",
            "笨", "粗心", "不认真", "懒", "没天赋", "聪明",
        ))


class HintTeachingAgent:
    """中文：定义“提示·教学·智能体”类，封装该职责相关的数据与行为。
    English: Defines the hint teaching agent class and encapsulates data and behavior for that responsibility.
    """
    name = "hint_teaching"

    def __init__(self, provider: LLMProvider) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.provider = provider

    def start(self, session: TutoringSession, problem: dict) -> TutorReply:
        """中文：处理“启动”相关操作。
        English: Handles the start operation.
        """
        if problem["needs_clarification"]:
            return TutorReply(action=TutorAction.CLARIFY, text=problem["clarification"], confidence=0.88)
        return TutorReply(
            action=TutorAction.DIAGNOSE,
            text=f"我先确认一下题意：{session.question.strip()}\n这道题要我们求什么？你觉得第一步可以从哪里开始？",
            understanding_check="你可以写下第一步，或者告诉我现在最不确定的地方。",
            confidence=0.8,
        )

    def respond(
        self,
        session: TutoringSession,
        message: str,
        diagnosis: dict,
        solution: dict,
        verified: bool,
        retrieved_context: dict | None = None,
        student_history_context: dict | None = None,
        intent: str = "answer",
        problem: dict | None = None,
        guidance: dict | None = None,
    ) -> TutorReply:
        """中文：处理“respond”相关操作。
        English: Handles the respond operation.
        """
        if session.status == TutoringStatus.COMPLETED and solution.get("steps"):
            may_show_completed_solution = (
                verified
                and (
                    session.attempts > 0
                    or session.hint_level >= HintLevel.LOCAL_STEP
                )
            )
            return TutorReply(
                action=TutorAction.SUMMARIZE,
                text="这道题已经结束了。你可以先复述自己使用的关键关系，再决定是否回看完整步骤。",
                hint_level=(HintLevel.FULL_EXPLANATION if may_show_completed_solution else None),
                hint_stage=("full_explanation" if may_show_completed_solution else None),
                solution_steps=(solution["steps"] if may_show_completed_solution else []),
                can_show_full_solution=bool(may_show_completed_solution),
                confidence=0.8 if may_show_completed_solution else 0.65,
            )

        requested_solution = self._requested_full_solution(message)
        may_show_full = (
            verified
            and bool(solution.get("steps"))
            and (session.attempts > 0 or session.hint_level >= HintLevel.LOCAL_STEP)
        )
        if requested_solution and may_show_full:
            session.hint_level = HintLevel.FULL_EXPLANATION
            generated = self._generate(
                session,
                message,
                diagnosis,
                solution,
                HintLevel.FULL_EXPLANATION,
                True,
                retrieved_context,
                student_history_context,
                guidance,
            )
            return TutorReply(
                action=TutorAction.EXPLAIN,
                text=generated.get("text", "可以，我们一起看完整思路。下面按步骤展开，每一步都可以停下来问我。"),
                hint_level=HintLevel.FULL_EXPLANATION,
                hint_stage="full_explanation",
                solution_steps=solution["steps"],
                understanding_check=generated.get("understanding_check"),
                can_show_full_solution=True,
                confidence=0.86,
            )

        guidance = guidance or {}
        teaching_action = guidance.get("teaching_action")
        if teaching_action == "ask_diagnostic_question":
            question = _compact_text(
                guidance.get("next_action") or diagnosis.get("follow_up_question"),
                300,
            )
            return TutorReply(
                action=TutorAction.DIAGNOSE,
                text="我还缺少一条能判断你卡点的证据，先只确认这一件事。",
                understanding_check=question or "你能写下刚才想到的第一步，并说明依据吗？",
                confidence=0.72,
            )
        if teaching_action == "verify_attempt":
            goal = _compact_text(guidance.get("current_goal_title"), 240)
            question = _compact_text(
                diagnosis.get("follow_up_question") or guidance.get("next_action"),
                300,
            )
            return TutorReply(
                action=TutorAction.CHECK_ATTEMPT,
                text=(
                    f"你的本轮输入已经推进到“{goal}”。"
                    "我现在还不能把这一步判成正确或错误，需要补齐它的数学依据。"
                ),
                understanding_check=question or "这一步使用了哪个条件、公式或等价变形？",
                confidence=0.7,
            )
        if teaching_action == "continue_exploration":
            goal = _compact_text(guidance.get("current_goal_title"), 240)
            mastered = diagnosis.get("mastered_points")
            confirmed = ""
            if isinstance(mastered, list) and mastered and isinstance(mastered[0], dict):
                confirmed = _compact_text(mastered[0].get("description"), 240)
            return TutorReply(
                action=TutorAction.CHECK_ATTEMPT,
                text=(
                    f"这一步已有校验依据：{confirmed}"
                    if confirmed
                    else "这一步已有与校验解法一致的证据，可以继续向前。"
                ),
                understanding_check=(
                    f"现在只处理当前目标“{goal}”。你准备建立哪条关系？"
                    if goal else "接下来你准备建立哪条关系？"
                ),
                confidence=0.82,
            )
        if teaching_action == "reflect_on_strategy":
            return TutorReply(
                action=TutorAction.SUMMARIZE,
                text=(
                    "你的最终结果与已校验答案一致，解题目标已经完成。"
                    "现在不会再回到开头，请用自己的话提炼这道题的关键突破口。"
                ),
                understanding_check=_compact_text(
                    guidance.get("next_action"), 300
                ) or "哪一步改变了题目的结构，使后续推导能够继续？",
                confidence=0.88,
            )

        if intent == "ask_hint" and (not verified or not solution.get("steps")):
            delivery_level = min(
                max(int(session.hint_level) + 1, int(HintLevel.DIRECTION)),
                int(HintLevel.LOCAL_STEP),
            )
            text, understanding_check = self._unverified_scaffold_hint(
                problem or {}, delivery_level
            )
            session.hint_level = max(session.hint_level, delivery_level)
            return TutorReply(
                action=TutorAction.HINT,
                text=text,
                hint_level=delivery_level,
                hint_stage=self._stage(delivery_level),
                understanding_check=understanding_check,
                can_show_full_solution=False,
                confidence=max(0.5, 0.61 - delivery_level * 0.03),
            )

        if not verified or not solution.get("steps"):
            return TutorReply(
                action=TutorAction.CLARIFY,
                text="我还不能可靠地确认这道题的解法。你能补充题目里的图、条件，或告诉我你目前试过什么吗？",
                confidence=0.4,
            )

        current_scaffold_level = min(session.hint_level, HintLevel.LOCAL_STEP)
        diagnosed_level = bounded_integer(
            diagnosis.get("next_hint_level"), 1, 1, HintLevel.LOCAL_STEP
        )
        has_diagnostic_evidence = bool(
            diagnosis.get("has_meaningful_attempt")
            and (
                diagnosis.get("mastered_points")
                or diagnosis.get("misconception_hypotheses")
            )
        )
        policy_level = guidance.get("hint_level")
        if isinstance(policy_level, int):
            next_level = max(1, min(policy_level, HintLevel.LOCAL_STEP))
        else:
            next_level = max(
                1,
                min(
                    max(
                        current_scaffold_level + 1,
                        diagnosed_level if has_diagnostic_evidence else 1,
                    ),
                    HintLevel.LOCAL_STEP,
                ),
            )
        session.hint_level = max(session.hint_level, int(next_level))
        delivery_level = int(next_level)
        can_show_after_reply = (
            verified
            and bool(solution.get("steps"))
            and (
                session.attempts > 0
                or session.hint_level >= HintLevel.LOCAL_STEP
            )
        )
        stage = self._stage(delivery_level)
        selected_step_index = self._selected_step_index(solution, diagnosis)
        fallback_text, fallback_check = self._fallback_hint(
            solution,
            delivery_level,
            diagnosis,
        )
        generated = self._generate(
            session,
            message,
            diagnosis,
            solution,
            delivery_level,
            False,
            retrieved_context,
            student_history_context,
            guidance,
        )
        text = generated.get("text", fallback_text)
        if self._violates_hint_boundary(
            text, solution, delivery_level, selected_step_index
        ):
            text = fallback_text
        if self._violates_hint_boundary(
            text, solution, delivery_level, selected_step_index
        ):
            text = self._generic_hint(delivery_level)
        check = generated.get("understanding_check", fallback_check)
        if self._violates_hint_boundary(
            check, solution, delivery_level, selected_step_index
        ):
            check = fallback_check
        if self._violates_hint_boundary(
            check, solution, delivery_level, selected_step_index
        ):
            check = "请写出你准备进行的下一步，我来帮你检查。"
        return TutorReply(
            action=TutorAction.HINT,
            text=text,
            hint_level=delivery_level,
            hint_stage=stage,
            understanding_check=check,
            can_show_full_solution=can_show_after_reply,
            confidence=0.76,
        )

    def _generate(
        self,
        session: TutoringSession,
        message: str,
        diagnosis: dict,
        solution: dict,
        hint_level: int,
        reveal_solution: bool,
        retrieved_context: dict | None = None,
        student_history_context: dict | None = None,
        guidance: dict | None = None,
    ) -> dict:
        """中文：处理“生成”相关操作。
        English: Handles the generate operation.
        """
        return self.provider.complete_json(
            TUTOR_REPLY_PROMPT,
            json.dumps({
                "grade": session.profile.grade,
                "question": session.question,
                "student_message": message,
                "learner_state": diagnosis,
                "guidance_decision": guidance or {},
                "teaching_context": self._teaching_context(
                    solution, hint_level, diagnosis
                ),
                "retrieved_teaching_context": retrieved_context or {},
                "student_history_context": student_history_context or {},
                "hint_level": hint_level,
                "hint_contract": self._stage(hint_level),
                "may_reveal_full_solution": reveal_solution,
            }, ensure_ascii=False),
        ) or {}

    @staticmethod
    def is_meaningful_attempt(message: str) -> bool:
        """中文：处理“is·meaningful·attempt”相关操作。
        English: Handles the is meaningful attempt operation.
        """
        return _has_meaningful_attempt(message)

    @staticmethod
    def _requested_full_solution(message: str) -> bool:
        """中文：处理“requested·full·解答”相关操作。
        English: Handles the requested full solution operation.
        """
        return any(word in message for word in (
            "直接告诉", "完整答案", "完整讲解", "看解法", "标准解法", "详细解法",
        ))

    @staticmethod
    def _stage(level: int) -> str:
        """中文：处理“stage”相关操作。
        English: Handles the stage operation.
        """
        return {
            HintLevel.DIRECTION: "direction",
            HintLevel.KEY_RELATION: "key_relation",
            HintLevel.LOCAL_STEP: "local_step",
            HintLevel.FULL_EXPLANATION: "full_explanation",
        }.get(HintLevel(level), "direction")

    @staticmethod
    def _selected_method(solution: dict) -> dict:
        """中文：处理“selected·method”相关操作。
        English: Handles the selected method operation.
        """
        methods = solution.get("methods") if isinstance(solution.get("methods"), list) else []
        recommended_id = solution.get("recommended_method_id")
        return next(
            (
                method for method in methods
                if isinstance(method, dict) and method.get("id") == recommended_id
            ),
            {},
        )

    def _teaching_context(
        self,
        solution: dict,
        level: int,
        diagnosis: dict | None = None,
    ) -> dict:
        """中文：处理“教学·context”相关操作。
        English: Handles the teaching context operation.
        """
        if level == HintLevel.FULL_EXPLANATION:
            return solution
        breakthroughs = solution.get("key_breakthroughs")
        breakthroughs = breakthroughs if isinstance(breakthroughs, list) else []
        first_breakthrough = breakthroughs[0] if breakthroughs else {}
        base = {
            "knowledge_points": solution.get("knowledge_points", []),
            "common_misconceptions": solution.get("common_misconceptions", []),
            "current_focus": {
                "next_solution_step_index": self._selected_step_index(
                    solution, diagnosis or {}
                ),
                "mastered_points": (diagnosis or {}).get("mastered_points", []),
                "misconception_hypotheses": (
                    diagnosis or {}
                ).get("misconception_hypotheses", []),
                "follow_up_question": (diagnosis or {}).get("follow_up_question"),
            },
        }
        if level == HintLevel.DIRECTION:
            base["direction"] = {
                "title": first_breakthrough.get("title"),
                "hint_question": first_breakthrough.get("hint_question"),
            }
        elif level == HintLevel.KEY_RELATION:
            base["key_relation"] = first_breakthrough
        else:
            base["local_step"] = self._local_step(
                solution,
                self._selected_step_index(solution, diagnosis or {}),
            )
        return base

    def _fallback_hint(
        self,
        solution: dict,
        level: int,
        diagnosis: dict | None = None,
    ) -> tuple[str, str]:
        """中文：处理“fallback·提示”相关操作。
        English: Handles the fallback hint operation.
        """
        breakthroughs = solution.get("key_breakthroughs")
        breakthroughs = breakthroughs if isinstance(breakthroughs, list) else []
        breakthrough = breakthroughs[0] if breakthroughs else {}
        if level == HintLevel.DIRECTION:
            text = breakthrough.get("hint_question") or "先判断这道题最适合从哪个已知条件开始。"
            return text, "你先说说准备处理哪个条件？"
        if level == HintLevel.KEY_RELATION:
            text = breakthrough.get("description") or "找出已知条件和目标之间最直接的数学关系。"
            return text, "你能把这个关系写成式子或一句推理吗？"
        diagnosis = diagnosis or {}
        local_step = self._local_step(
            solution,
            self._selected_step_index(solution, diagnosis),
        )
        statement = local_step.get("statement") or "先完成推荐方法中的当前小步。"
        result = local_step.get("result")
        hypotheses = diagnosis.get("misconception_hypotheses")
        hypotheses = hypotheses if isinstance(hypotheses, list) else []
        mastered = diagnosis.get("mastered_points")
        mastered = mastered if isinstance(mastered, list) else []
        mastered_description = next(
            (
                _compact_text(item.get("description"), 200)
                for item in mastered
                if isinstance(item, dict) and item.get("description")
            ),
            "",
        )
        text = f"{statement}"
        if result and not hypotheses:
            text = f"{text}，这一小步得到 {result}。"
        if mastered_description:
            text = f"你已经完成了：{mastered_description}。现在继续检查：{text}"
        follow_up = _compact_text(diagnosis.get("follow_up_question"), 300)
        return text, follow_up or "接下来你觉得应该处理哪一项？"

    def _local_step(self, solution: dict, step_index: int = 1) -> dict:
        """中文：处理“local·step”相关操作。
        English: Handles the local step operation.
        """
        method = self._selected_method(solution)
        steps = method.get("steps") if isinstance(method.get("steps"), list) else []
        if not steps:
            return {}
        selected_index = max(1, min(step_index, len(steps))) - 1
        if not isinstance(steps[selected_index], dict):
            return {}
        step = dict(steps[selected_index])
        if len(steps) == 1:
            step.pop("result", None)
        return step

    @classmethod
    def _selected_step_index(cls, solution: dict, diagnosis: dict) -> int:
        """中文：根据学情诊断选择本轮需要处理的解法步骤。
        English: Selects the solution step to address from the learner diagnosis.
        """
        method = cls._selected_method(solution)
        steps = method.get("steps") if isinstance(method.get("steps"), list) else []
        if not steps and isinstance(solution.get("steps"), list):
            steps = solution["steps"]
        if not steps:
            return 1
        return bounded_integer(
            diagnosis.get("next_solution_step_index"),
            1,
            1,
            len(steps),
        )

    @staticmethod
    def _contains_final_answer(text: object, answer: object) -> bool:
        """中文：处理“contains·final·答案”相关操作。
        English: Handles the contains final answer operation.
        """
        normalized_text = re.sub(r"\s+", "", str(text or "")).lower()
        normalized_answer = re.sub(r"\s+", "", str(answer or "")).lower()
        candidates = [normalized_answer]
        if "=" in normalized_answer:
            candidates.append(normalized_answer.rsplit("=", 1)[-1])
        return any(candidate and candidate in normalized_text for candidate in candidates)

    @classmethod
    def _violates_hint_boundary(
        cls,
        text: object,
        solution: dict,
        level: int,
        selected_step_index: int = 1,
    ) -> bool:
        """中文：处理“violates·提示·boundary”相关操作。
        English: Handles the violates hint boundary operation.

        原有说明 / Existing notes:
        Reject model text that copies later verified steps into levels 1-3.
        """
        if level >= HintLevel.FULL_EXPLANATION:
            return False
        if cls._contains_final_answer(text, solution.get("answer")):
            return True

        normalized_text = cls._normalized_math_text(text)
        if not normalized_text:
            return False
        steps = cls._solution_step_fragments(solution)
        forbidden_steps = (
            steps
            if level <= HintLevel.KEY_RELATION
            else steps[max(1, selected_step_index):]
        )
        if any(
            fragment and fragment in normalized_text
            for step in forbidden_steps
            for fragment in step
        ):
            return True
        step_markers = sum(
            marker in normalized_text
            for marker in ("第一步", "第二步", "第三步", "然后", "接着", "最后")
        )
        return step_markers >= 2

    @classmethod
    def _solution_step_fragments(cls, solution: dict) -> list[list[str]]:
        """中文：处理“解答·step·fragments”相关操作。
        English: Handles the solution step fragments operation.
        """
        method = cls._selected_method(solution)
        raw_steps = method.get("steps") if isinstance(method.get("steps"), list) else []
        if not raw_steps:
            raw_steps = solution.get("steps") if isinstance(solution.get("steps"), list) else []
        fragments: list[list[str]] = []
        for raw in raw_steps:
            values = raw.values() if isinstance(raw, dict) else (raw,)
            normalized = [
                cls._normalized_math_text(value)
                for value in values
                if isinstance(value, (str, int, float))
            ]
            # Short words such as “移项” are too common to identify copied steps.
            fragments.append([value for value in normalized if len(value) >= 5])
        return fragments

    @staticmethod
    def _normalized_math_text(value: object) -> str:
        """中文：处理“normalized·math·text”相关操作。
        English: Handles the normalized math text operation.
        """
        return re.sub(r"[\s，。；：、,.!?！？;:]", "", str(value or "")).lower()

    @staticmethod
    def _generic_hint(level: int) -> str:
        """中文：处理“generic·提示”相关操作。
        English: Handles the generic hint operation.
        """
        if level == HintLevel.DIRECTION:
            return "先选一个与目标最接近的已知条件，说说你为什么想从它开始。"
        if level == HintLevel.KEY_RELATION:
            return "回忆这个知识点最核心的定义或公式，先写出关系，不急着算结果。"
        return "先完成推荐路线中的第一小步，并停在这个中间结果。"

    @staticmethod
    def _unverified_scaffold_hint(problem: dict, level: int) -> tuple[str, str]:
        """中文：解法未通过校验时，仅依据已确认题意连续提供安全的 1–3 级提示。
        English: Provides safe levels 1–3 from confirmed problem facts while the solution remains unverified.
        """
        conditions = problem.get("known_conditions")
        conditions = conditions if isinstance(conditions, list) else []
        domain = next((
            _compact_text(item.get("statement"), 260)
            for item in conditions
            if isinstance(item, dict) and item.get("kind") == "domain"
        ), "")
        methods = problem.get("thinking_methods")
        methods = methods if isinstance(methods, list) else []
        method = next((
            _compact_text(item.get("method_name"), 80)
            for item in methods
            if isinstance(item, dict) and item.get("method_name")
        ), "")
        if level == HintLevel.DIRECTION:
            if domain and method:
                text = f"先把取值范围检查清楚：{domain}。再用“{method}”观察式子的整体结构，暂时不要展开完整求解。"
            elif domain:
                text = f"先把取值范围检查清楚：{domain}。暂时不要连续变形或求最终答案。"
            elif method:
                text = f"先用“{method}”观察已知条件与目标之间的连接，暂时只确定从哪里开始。"
            else:
                text = "先分别列出已经确认的条件和求解目标，再选出与目标最直接相关的一条条件作为起点。"
            return text, "先写出你准备检查的范围或结构，我再帮你确认这条方向。"

        if level == HintLevel.KEY_RELATION:
            if domain:
                text = f"关键约束是所有变形都必须保留原题的取值范围：{domain}。如果后面使用平方，得到的只能先当作候选解，最后还要代回原式。"
            elif method:
                text = f"关键关系是“{method}”过程中前后条件必须等价；先写出准备使用的定义、公式或等价关系，不急着计算。"
            else:
                text = "关键关系是每一步都要同时连接已知条件与求解目标，并检查变形前后的条件是否等价。"
            return text, "你能把这条约束写成一个条件或一句等价关系吗？"

        if domain:
            text = f"先完成一个局部步骤：把这些非负条件求交集并写成一个取值范围——{domain}。做到这里先停下，不继续求最终答案。"
        else:
            text = "先完成一个局部步骤：把刚才选定的关键关系写成式子，并只化简到第一个中间结果。"
        return text, "把这个局部结果写下来，我先帮你检查范围和等价性。"


class TeachingOrchestrator:
    """中文：定义“教学·编排器”类，封装该职责相关的数据与行为。
    English: Defines the teaching orchestrator class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Controls agent order and validates state transitions for the first runnable prototype.
    """

    def __init__(
        self,
        max_revision_attempts: int = 2,
        knowledge_retriever: KnowledgeRetriever | None = None,
        student_history_retriever: StudentHistoryRetriever | None = None,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.problem_agent = ProblemUnderstandingAgent(llm_provider)
        self.solution_agent = SolutionAnalysisAgent(llm_provider)
        self.verifier_agent = SolutionVerificationAgent(llm_provider)
        self.diagnosis_agent = LearnerDiagnosisAgent(llm_provider)
        self.tutor_agent = HintTeachingAgent(llm_provider)
        self.record_agent = LearningRecordAgent()
        self.knowledge_retriever = knowledge_retriever or DisabledKnowledgeRetriever()
        self.student_history_retriever = (
            student_history_retriever or DisabledStudentHistoryRetriever()
        )
        self.retrieval_policy = OnDemandRetrievalPolicy()
        self.guidance_policy = GuidancePolicy()
        self.max_revision_attempts = max(0, min(max_revision_attempts, 3))

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.knowledge_retriever.close()
        self.student_history_retriever.close()

    def create_session(
        self,
        question: str,
        subject: str,
        grade: str,
        run_id: str,
        student_user_id: str,
        knowledge_problem_id: str | None = None,
        llm_model_id: str | None = None,
    ) -> tuple[TutoringSession, TutorReply]:
        """中文：处理“创建·会话”相关操作。
        English: Handles the create session operation.
        """
        session = TutoringSession(
            student_user_id=student_user_id,
            knowledge_problem_id=knowledge_problem_id,
            llm_model_id=llm_model_id,
            question=question,
            profile=LearnerProfile(subject=subject, grade=grade),
        )
        understanding_decision = self.retrieval_policy.decide_problem_understanding(
            question,
            retriever_available=self.knowledge_retriever.available,
        )
        understanding_context = self._retrieve_if_needed(
            session,
            run_id,
            understanding_decision,
            text=question,
        )
        problem = self._invoke(
            session,
            run_id,
            self.problem_agent.name,
            "problem_spec",
            lambda: self.problem_agent.run(
                question,
                subject,
                grade,
                teaching_context=understanding_context,
            ),
            schema_version="2.0",
        )
        solution: dict = {}
        if not problem["needs_clarification"]:
            solution, _ = self._solve_verify_and_revise(
                session,
                run_id,
                question,
                problem,
                retrieval_already_used=understanding_decision.should_retrieve,
            )
            graph = self._ensure_solution_graph(session, run_id, solution)
        else:
            graph = SolutionGraph()
        reply = self.tutor_agent.start(session, problem)
        if graph.goals:
            initial_guidance = self._initial_guidance_decision(graph)
            self._append_guidance_decision(session, run_id, initial_guidance)
            reply = self._attach_guidance(reply, initial_guidance)
        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version="2.1",
            agent=self.tutor_agent.name,
            kind="tutor_reply",
            payload=reply.model_dump(mode="json"),
            confidence=reply.confidence,
        ))
        session.messages.extend([Message(role="student", content=question), Message(role="assistant", content=reply.text)])
        session.status = TutoringStatus.CLARIFYING if reply.action == TutorAction.CLARIFY else TutoringStatus.DIAGNOSING
        session.updated_at = datetime.now(timezone.utc)
        return session, reply

    def handle_turn(self, session: TutoringSession, message: str, intent: str, run_id: str) -> TutorReply:
        """中文：处理“处理·turn”相关操作。
        English: Handles the handle turn operation.
        """
        session.messages.append(Message(role="student", content=message))
        if session.status == TutoringStatus.CLARIFYING:
            return self._handle_clarification(session, message, run_id)

        solution = self._artifact(session, "solution_plan")
        verification = self._artifact(session, "verification_report")
        student_history_context = self._retrieve_student_history(
            session,
            run_id,
            solution,
        )
        previous_progress = self._latest_solution_progress(session)
        diagnosis = self._invoke(
            session,
            run_id,
            self.diagnosis_agent.name,
            "learner_state",
            lambda: self._preserve_solution_progress(
                self.diagnosis_agent.run(message, solution, verification),
                previous_progress,
            ),
            schema_version="2.0",
        )
        if diagnosis.get("has_meaningful_attempt"):
            session.attempts += 1

        graph = self._solution_graph(session, solution)
        if not any(artifact.kind == "solution_graph" for artifact in session.artifacts):
            session.artifacts.append(AgentArtifact(
                run_id=run_id,
                schema_version=graph.schema_version,
                agent="solution_graph_builder",
                kind="solution_graph",
                payload=graph.model_dump(mode="json"),
                confidence=0.9 if graph.goals else 0.4,
            ))
        previous_guidance = self._latest_guidance_decision(session)
        student_attempt, guidance = self.guidance_policy.decide(
            graph=graph,
            diagnosis=diagnosis,
            message=message,
            intent=intent,
            current_hint_level=int(session.hint_level),
            previous=previous_guidance,
        )
        reply_context: dict | None = None
        completion_trigger = self._completion_trigger(
            session,
            message,
            intent,
            verification,
        )
        if completion_trigger:
            guidance = guidance.model_copy(update={
                "state": GuidanceState.COMPLETED,
                "event": "SESSION_COMPLETED",
                "completed_goal_ids": [goal.id for goal in graph.goals],
                "teaching_action": "complete_session",
                "allowed_actions": ["save_learning_evidence"],
                "hint_level": None,
                "next_action": "进入思路复盘，并保存本轮真实学习证据。",
                "reason": f"会话满足结束条件：{completion_trigger}。",
            })
            previous_status = session.status
            session.status = TutoringStatus.COMPLETED
            may_show_completed_solution = (
                verification.get("passed")
                and (session.attempts > 0 or session.hint_level >= HintLevel.LOCAL_STEP)
            )
            if may_show_completed_solution:
                session.hint_level = HintLevel.FULL_EXPLANATION
            if session.record is None:
                session.record = self.record_agent.run(session, solution)
                session.artifacts.append(AgentArtifact(
                    run_id=run_id,
                    schema_version="2.0",
                    agent=self.record_agent.name,
                    kind="learning_record",
                    payload=session.record.model_dump(mode="json"),
                    confidence=0.85 if session.attempts else 0.65,
                ))
            session.artifacts.append(AgentArtifact(
                run_id=run_id,
                schema_version="1.0",
                agent="teaching_orchestrator",
                kind="session_event",
                payload={
                    "event": "solution_completed",
                    "trigger": completion_trigger,
                    "student_message": message,
                    "previous_status": previous_status.value,
                    "attempt_count": session.attempts,
                    "hint_level": int(session.hint_level),
                },
                confidence=1.0 if completion_trigger == "explicit_intent" else 0.9,
            ))
            reply = TutorReply(
                action=TutorAction.SUMMARIZE,
                text=self._completion_reply_text(solution, may_show_completed_solution),
                hint_level=(HintLevel.FULL_EXPLANATION if may_show_completed_solution else None),
                hint_stage=("full_explanation" if may_show_completed_solution else None),
                solution_steps=(solution.get("steps", []) if may_show_completed_solution else []),
                can_show_full_solution=bool(may_show_completed_solution),
                confidence=0.85 if verification.get("passed") else 0.45,
            )
            if may_show_completed_solution:
                reply_context = self._latest_agent_teaching_context(session)
        elif intent == "practice" or any(token in message for token in ("相似题", "练习一下")):
            # Normal runtime calls are intercepted by MathTutorAgentHarness and
            # create an isolated constrained-practice session. Keep this branch
            # free of fallback exercises for direct orchestrator adapters.
            session.status = TutoringStatus.EXPLAINING
            reply = TutorReply(
                action=TutorAction.CHECK_ATTEMPT,
                text="相似题需要由学习运行器根据年级、知识点、难度和已学范围创建独立会话。",
                confidence=1.0,
            )
        else:
            session.status = self._tutoring_status_for_guidance(guidance.state)
            hint_context: dict | None = None
            if guidance.teaching_action in {"deliver_hint", "remediate_prerequisite"}:
                hint_level = guidance.hint_level or self._next_retrieval_hint_level(
                    session,
                    message,
                    solution,
                    bool(verification.get("passed")),
                )
                hint_decision = self.retrieval_policy.decide_hint_teaching(
                    message,
                    intent,
                    retriever_available=self.knowledge_retriever.available,
                    has_verified_solution=bool(verification.get("passed")),
                )
                hint_context = self._retrieve_if_needed(
                    session,
                    run_id,
                    hint_decision,
                    # Keep student chat out of the shared retrieval cache. The
                    # decision uses the turn message; retrieval uses the exercise.
                    text=session.question,
                    problem=self._artifact(session, "problem_spec"),
                    solution=solution,
                    hint_level=hint_level,
                )
            reply_context = hint_context or self._latest_agent_teaching_context(session)
            reply = self.tutor_agent.respond(
                session,
                message,
                diagnosis,
                solution,
                verification.get("passed", False),
                retrieved_context=hint_context,
                student_history_context=student_history_context,
                intent=intent,
                problem=self._artifact(session, "problem_spec"),
                guidance=guidance.model_dump(mode="json"),
            )

        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version="1.0",
            agent="guidance_policy",
            kind="student_attempt",
            payload=student_attempt.model_dump(mode="json"),
            confidence=1.0 if student_attempt.verification_status != AttemptVerificationStatus.UNVERIFIED else 0.6,
        ))
        self._append_guidance_decision(session, run_id, guidance)
        reply = self._attach_guidance(reply, guidance)
        reply.sources = self._source_references(reply_context)

        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version="2.1",
            agent=self.tutor_agent.name,
            kind="tutor_reply",
            payload=reply.model_dump(mode="json"),
            confidence=reply.confidence,
        ))
        session.messages.append(Message(role="assistant", content=reply.text))
        session.updated_at = datetime.now(timezone.utc)
        return reply

    @staticmethod
    def _latest_solution_progress(session: TutoringSession) -> int | None:
        """中文：读取会话中已经确认的最远解法步骤，作为进度下限。
        English: Reads the furthest confirmed solution step as the progress floor.
        """
        progress_values: list[int] = []
        for artifact in session.artifacts:
            if artifact.kind != "learner_state":
                continue
            value = artifact.payload.get("next_solution_step_index")
            if isinstance(value, int) and value >= 1:
                progress_values.append(value)
        return max(progress_values) if progress_values else None

    @staticmethod
    def _preserve_solution_progress(diagnosis: dict, progress_floor: int | None) -> dict:
        """中文：防止只看当前一句话的诊断把已成立的解题进度拉回开头。
        English: Prevents a turn-local diagnosis from moving confirmed progress backwards.
        """
        if progress_floor is None:
            return diagnosis
        current = diagnosis.get("next_solution_step_index")
        if not isinstance(current, int) or current < progress_floor:
            diagnosis["next_solution_step_index"] = progress_floor
            diagnosis["progress_floor_applied"] = progress_floor
        return diagnosis

    @staticmethod
    def _completion_trigger(
        session: TutoringSession,
        message: str,
        intent: str,
        verification: dict,
    ) -> str | None:
        """中文：识别显式完成动作或学生自然表达的完成确认。
        English: Detects explicit completion actions and natural completion acknowledgements.
        """
        if intent == "complete":
            return "explicit_intent"

        normalized = re.sub(r"[\s，。！？、,.!?]", "", message).lower()
        completion_phrases = (
            "我懂了", "我已经懂了", "已经懂了", "我明白了", "我已经明白了",
            "已经明白了", "我会了", "我已经会了", "已经会了", "我做出来了",
            "做出来了", "解决了", "做完了", "完成了", "没问题了", "清楚了",
        )
        has_completion_acknowledgement = any(
            phrase in normalized for phrase in completion_phrases
        )
        has_prior_progress = (
            session.attempts > 0
            or session.hint_level >= HintLevel.LOCAL_STEP
        )
        if has_completion_acknowledgement and verification.get("passed") and has_prior_progress:
            return "completion_acknowledgement"
        prior_guidance = next(
            (
                artifact.payload for artifact in reversed(session.artifacts)
                if artifact.kind == "guidance_decision"
            ),
            {},
        )
        if (
            prior_guidance.get("state") == GuidanceState.REFLECTING
            and verification.get("passed")
            and _has_meaningful_attempt(message)
        ):
            return "reflection_completed"
        return None

    @staticmethod
    def _completion_reply_text(solution: dict, may_show_completed_solution: bool) -> str:
        """中文：生成与具体题目无关的完成回复，避免写死错误的知识点。
        English: Builds a problem-neutral completion reply without hard-coded concepts.
        """
        if may_show_completed_solution:
            answer = _compact_text(solution.get("answer"), 180)
            conclusion = f" 最终结论已记录：{answer}。" if answer else ""
            return (
                "你已经把这道题的关键步骤走通了，本轮解题现已结束。"
                f"{conclusion}接下来进入思路复盘，回看你的原思路、关键突破口和完整解法。"
            )
        return "本轮解题现已结束。接下来进入思路复盘，并保留你已经完成的步骤。"

    @staticmethod
    def _initial_guidance_decision(graph: SolutionGraph) -> GuidanceDecision:
        """中文：为新会话建立以第一个数学目标为中心的探索状态。
        English: Creates an exploration state centered on the first mathematical goal.
        """

        goal = graph.goals[0]
        return GuidanceDecision(
            state=GuidanceState.EXPLORING,
            event="SESSION_READY_FOR_EXPLORATION",
            current_goal_id=goal.id,
            current_goal_title=goal.title,
            current_goal_ordinal=goal.ordinal,
            total_goal_count=len(graph.goals),
            barrier_type=BarrierType.NONE,
            verification_status=AttemptVerificationStatus.UNVERIFIED,
            teaching_action="observe",
            allowed_actions=["invite_first_attempt"],
            next_action=f"先尝试完成当前数学目标：{goal.title}。",
            reason="题意和已校验解法已准备好，先保留学生独立探索空间。",
        )

    @staticmethod
    def _ensure_solution_graph(
        session: TutoringSession,
        run_id: str,
        solution: dict,
    ) -> SolutionGraph:
        """中文：从当前解法建立解题图并保存为会话工件。
        English: Builds a solution graph from the active solution and stores it as a session artifact.
        """

        graph = SolutionGraph.from_solution_plan(solution)
        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version=graph.schema_version,
            agent="solution_graph_builder",
            kind="solution_graph",
            payload=graph.model_dump(mode="json"),
            confidence=0.9 if graph.goals else 0.4,
        ))
        return graph

    @staticmethod
    def _solution_graph(session: TutoringSession, solution: dict) -> SolutionGraph:
        """中文：读取最近的解题图，缺失时从当前解法即时构建。
        English: Reads the latest solution graph or derives one from the active solution.
        """

        payload = next(
            (
                artifact.payload for artifact in reversed(session.artifacts)
                if artifact.kind == "solution_graph"
            ),
            None,
        )
        if isinstance(payload, dict):
            try:
                return SolutionGraph.model_validate(payload)
            except ValueError:
                pass
        return SolutionGraph.from_solution_plan(solution)

    @staticmethod
    def _latest_guidance_decision(session: TutoringSession) -> GuidanceDecision | None:
        """中文：读取上一轮规则状态机决策，作为进度下限。
        English: Reads the previous policy decision as the monotonic progress floor.
        """

        payload = next(
            (
                artifact.payload for artifact in reversed(session.artifacts)
                if artifact.kind == "guidance_decision"
            ),
            None,
        )
        if not isinstance(payload, dict):
            return None
        try:
            return GuidanceDecision.model_validate(payload)
        except ValueError:
            return None

    @staticmethod
    def _append_guidance_decision(
        session: TutoringSession,
        run_id: str,
        decision: GuidanceDecision,
    ) -> None:
        """中文：将状态迁移、原因和允许动作写入可审计会话工件。
        English: Stores the state transition, reason, and allowed actions as an auditable artifact.
        """

        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version="1.0",
            agent="guidance_policy",
            kind="guidance_decision",
            payload=decision.model_dump(mode="json"),
            confidence=(
                1.0
                if decision.verification_status != AttemptVerificationStatus.UNVERIFIED
                else 0.75
            ),
        ))

    @staticmethod
    def _attach_guidance(reply: TutorReply, decision: GuidanceDecision) -> TutorReply:
        """中文：把结构化引导状态附加到兼容的回复 DTO。
        English: Attaches structured guidance state to the backward-compatible reply DTO.
        """

        return reply.model_copy(update={
            "guidance_state": decision.state.value,
            "current_goal_id": decision.current_goal_id,
            "current_goal_title": decision.current_goal_title,
            "current_goal_ordinal": decision.current_goal_ordinal,
            "completed_goal_count": len(decision.completed_goal_ids),
            "total_goal_count": decision.total_goal_count,
            "obstacle_type": decision.barrier_type.value,
            "attempt_verification": decision.verification_status.value,
            "next_action": decision.next_action,
        })

    @staticmethod
    def _tutoring_status_for_guidance(state: GuidanceState) -> TutoringStatus:
        """中文：将教学状态机映射到现有会话状态，保持 REST DTO 兼容。
        English: Maps guidance states to existing session statuses while preserving REST compatibility.
        """

        if state in {GuidanceState.EXPLORING, GuidanceState.UNCERTAIN}:
            return TutoringStatus.DIAGNOSING
        if state in {GuidanceState.BLOCKED, GuidanceState.REMEDIATING, GuidanceState.GUIDED}:
            return TutoringStatus.HINTING
        if state == GuidanceState.VERIFYING:
            return TutoringStatus.CHECKING_ATTEMPT
        if state in {GuidanceState.REFLECTING, GuidanceState.TRANSFER_TEST}:
            return TutoringStatus.EXPLAINING
        if state == GuidanceState.COMPLETED:
            return TutoringStatus.COMPLETED
        return TutoringStatus.DIAGNOSING

    def _handle_clarification(
        self,
        session: TutoringSession,
        message: str,
        run_id: str,
    ) -> TutorReply:
        """中文：处理“处理·clarification”相关操作。
        English: Handles the handle clarification operation.
        """
        session.question = f"{session.question.strip()}\n补充信息：{message.strip()}"
        understanding_decision = self.retrieval_policy.decide_problem_understanding(
            session.question,
            retriever_available=self.knowledge_retriever.available,
        )
        understanding_context = self._retrieve_if_needed(
            session,
            run_id,
            understanding_decision,
            text=session.question,
        )
        problem = self._invoke(
            session,
            run_id,
            self.problem_agent.name,
            "problem_spec",
            lambda: self.problem_agent.run(
                session.question,
                session.profile.subject,
                session.profile.grade,
                teaching_context=understanding_context,
            ),
            schema_version="2.0",
        )
        solution: dict = {}
        if not problem["needs_clarification"]:
            solution, _ = self._solve_verify_and_revise(
                session,
                run_id,
                session.question,
                problem,
                retrieval_already_used=understanding_decision.should_retrieve,
            )

        reply = self.tutor_agent.start(session, problem)
        if solution:
            graph = self._ensure_solution_graph(session, run_id, solution)
            if graph.goals:
                initial_guidance = self._initial_guidance_decision(graph)
                self._append_guidance_decision(session, run_id, initial_guidance)
                reply = self._attach_guidance(reply, initial_guidance)
        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version="2.1",
            agent=self.tutor_agent.name,
            kind="tutor_reply",
            payload=reply.model_dump(mode="json"),
            confidence=reply.confidence,
        ))
        session.messages.append(Message(role="assistant", content=reply.text))
        session.status = (
            TutoringStatus.CLARIFYING
            if reply.action == TutorAction.CLARIFY
            else TutoringStatus.DIAGNOSING
        )
        session.updated_at = datetime.now(timezone.utc)
        return reply

    def _solve_verify_and_revise(
        self,
        session: TutoringSession,
        run_id: str,
        question: str,
        problem: dict,
        retrieval_already_used: bool = False,
    ) -> tuple[dict, dict]:
        """中文：处理“solve·校验·and·revise”相关操作。
        English: Handles the solve verify and revise operation.
        """
        solution_decision = self.retrieval_policy.decide_solution_analysis(
            question,
            problem,
            retriever_available=self.knowledge_retriever.available,
            retrieval_already_used=retrieval_already_used,
        )
        solution_context = self._retrieve_if_needed(
            session,
            run_id,
            solution_decision,
            text=question,
            problem=problem,
        )
        solution = self._invoke(
            session,
            run_id,
            self.solution_agent.name,
            "solution_plan",
            lambda: self.solution_agent.run(
                question,
                problem,
                teaching_context=solution_context,
            ),
            schema_version="2.1",
        )
        verification = self._invoke(
            session,
            run_id,
            self.verifier_agent.name,
            "verification_report",
            lambda: self._verification_with_revision_context(
                problem,
                solution,
                revision_attempt=0,
            ),
            schema_version="2.1",
        )

        for attempt in range(1, self.max_revision_attempts + 1):
            revision_context = verification.get("revision_context", {})
            if not revision_context.get("will_retry", False):
                break
            previous_solution = solution
            previous_verification = verification
            solution = self._invoke(
                session,
                run_id,
                self.solution_agent.name,
                "solution_plan",
                lambda attempt=attempt, previous_solution=previous_solution,
                previous_verification=previous_verification: self.solution_agent.revise(
                    question=question,
                    problem=problem,
                    current_solution=previous_solution,
                    verification=previous_verification,
                    attempt=attempt,
                    max_attempts=self.max_revision_attempts,
                ),
                schema_version="2.1",
            )
            verification = self._invoke(
                session,
                run_id,
                self.verifier_agent.name,
                "verification_report",
                lambda attempt=attempt, solution=solution: self._verification_with_revision_context(
                    problem,
                    solution,
                    revision_attempt=attempt,
                ),
                schema_version="2.1",
            )
        return solution, verification

    def _retrieve_if_needed(
        self,
        session: TutoringSession,
        run_id: str,
        decision: RetrievalDecision,
        *,
        text: str,
        problem: dict | None = None,
        solution: dict | None = None,
        hint_level: int | None = None,
    ) -> dict | None:
        """中文：处理“检索·if·needed”相关操作。
        English: Handles the retrieve if needed operation.
        """
        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version="1.0",
            agent="retrieval_decision",
            kind="retrieval_decision",
            payload=decision.as_payload(),
            status="completed" if decision.should_retrieve else "skipped",
            confidence=1.0,
        ))
        if not decision.should_retrieve:
            return None

        query = self._build_knowledge_query(
            session,
            decision,
            text=text,
            problem=problem or {},
            solution=solution or {},
            hint_level=hint_level,
        )
        started = perf_counter()
        try:
            context = self.knowledge_retriever.retrieve(query)
        except Exception as error:
            session.artifacts.append(AgentArtifact(
                run_id=run_id,
                schema_version="1.0",
                agent=self.knowledge_retriever.name,
                kind="retrieved_textbook_context",
                payload={
                    "status": "degraded",
                    "provider": self.knowledge_retriever.name,
                    "purpose": decision.purpose,
                    "reason_code": "provider_error",
                    "error_type": type(error).__name__,
                },
                status="failed",
                duration_ms=round((perf_counter() - started) * 1000),
                confidence=0.0,
            ))
            return None

        if context.query != query:
            session.artifacts.append(AgentArtifact(
                run_id=run_id,
                schema_version=context.schema_version,
                agent=self.knowledge_retriever.name,
                kind="retrieved_textbook_context",
                payload={
                    "status": "degraded",
                    "provider": self.knowledge_retriever.name,
                    "purpose": decision.purpose,
                    "reason_code": "retrieval_query_mismatch",
                },
                status="failed",
                duration_ms=round((perf_counter() - started) * 1000),
                confidence=0.0,
            ))
            return None

        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version=context.schema_version,
            agent=self.knowledge_retriever.name,
            kind="retrieved_textbook_context",
            payload=context.model_dump(mode="json"),
            status=(
                "completed"
                if context.status in {"success", "degraded"}
                else "skipped"
            ),
            duration_ms=round((perf_counter() - started) * 1000),
            confidence=1.0 if context.status == "success" else 0.5,
        ))
        return self._agent_teaching_context(context)

    @staticmethod
    def _agent_teaching_context(
        context: RetrievedTeachingContext,
    ) -> dict | None:
        """中文：处理“智能体·教学·context”相关操作。
        English: Handles the agent teaching context operation.
        """
        if context.diagnostics.selected_count <= 0:
            return None
        return context.to_agent_context().model_dump(mode="json")

    @staticmethod
    def _latest_agent_teaching_context(
        session: TutoringSession,
    ) -> dict | None:
        """中文：处理“latest·智能体·教学·context”相关操作。
        English: Handles the latest agent teaching context operation.
        """
        for artifact in reversed(session.artifacts):
            if artifact.kind not in {
                "retrieved_textbook_context",
                "retrieved_teaching_context",
            }:
                continue
            if artifact.payload.get("status") not in {"success", "degraded"}:
                continue
            try:
                context = RetrievedTeachingContext.model_validate(artifact.payload)
            except ValueError:
                continue
            agent_context = TeachingOrchestrator._agent_teaching_context(context)
            if agent_context:
                return agent_context
        return None

    def _retrieve_student_history(
        self,
        session: TutoringSession,
        run_id: str,
        solution: dict,
    ) -> dict | None:
        """中文：处理“检索·学生·历史”相关操作。
        English: Handles the retrieve student history operation.
        """
        if not self.student_history_retriever.available:
            return None
        knowledge_points = [
            _compact_text(item, 120)
            for item in solution.get("knowledge_points", [])
            if _compact_text(item, 120)
        ]
        if not knowledge_points:
            return None
        query = StudentHistoryQuery(
            student_user_id=session.student_user_id,
            purpose="hint_personalization",
            subject=MVP_SUBJECT_CODE,
            grade_band=MVP_GRADE_BAND,
            knowledge_points=knowledge_points,
        )
        started = perf_counter()
        try:
            context = self.student_history_retriever.retrieve(query)
        except Exception as error:
            session.artifacts.append(AgentArtifact(
                run_id=run_id,
                schema_version="1.0",
                agent=self.student_history_retriever.name,
                kind="retrieved_student_history",
                payload={
                    "data_scope": "student_private",
                    "status": "degraded",
                    "reason_code": "provider_error",
                    "error_type": type(error).__name__,
                },
                status="failed",
                duration_ms=round((perf_counter() - started) * 1000),
                confidence=0.0,
            ))
            return None
        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version=context.schema_version,
            agent=context.provider,
            kind="retrieved_student_history",
            payload=context.model_dump(mode="json"),
            status="completed" if context.status == "success" else "skipped",
            duration_ms=round((perf_counter() - started) * 1000),
            confidence=1.0 if context.status == "success" else 0.5,
        ))
        if context.status != "success":
            return None
        return context.to_agent_context().model_dump(mode="json")

    @staticmethod
    def _source_references(
        teaching_context: dict | None,
    ) -> list[TutorSourceReference]:
        """中文：处理“source·references”相关操作。
        English: Handles the source references operation.
        """
        if not teaching_context:
            return []
        groups = (
            ("concepts", "concept"),
            ("principles", "principle"),
            ("problem_patterns", "example_pattern"),
            ("solution_outlines", "worked_example"),
            ("error_patterns", "error_pattern"),
            ("hints", "hint"),
            ("source_facts", "source_fact"),
        )
        references: dict[tuple[str, str | None], dict] = {}
        for group_name, support_kind in groups:
            items = teaching_context.get(group_name, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                citation = item.get("citation")
                if not isinstance(citation, dict):
                    continue
                document_id = _compact_text(citation.get("document_id"), 100)
                title = _compact_text(citation.get("title"), 500)
                if not document_id or not title:
                    continue
                chunk_id = _compact_text(citation.get("chunk_id"), 100) or None
                key = (document_id, chunk_id)
                current = references.setdefault(key, {
                    "source_reference_id": (
                        _compact_text(citation.get("source_reference_id"), 100) or None
                    ),
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "title": title,
                    "version": _compact_text(citation.get("version"), 100) or None,
                    "source_url": citation.get("source_url"),
                    "locator": _compact_text(citation.get("locator"), 255) or None,
                    "supports": [],
                })
                if support_kind not in current["supports"]:
                    current["supports"].append(support_kind)
        return [
            TutorSourceReference.model_validate(item)
            for item in list(references.values())[:8]
        ]

    @staticmethod
    def _build_knowledge_query(
        session: TutoringSession,
        decision: RetrievalDecision,
        *,
        text: str,
        problem: dict,
        solution: dict,
        hint_level: int | None,
    ) -> KnowledgeQuery:
        """中文：处理“构建·知识·query”相关操作。
        English: Handles the build knowledge query operation.
        """
        conditions = [
            _compact_text(item.get("statement"), 1000)
            for item in problem.get("known_conditions", [])
            if isinstance(item, dict) and _compact_text(item.get("statement"), 1000)
        ]
        target = problem.get("target") if isinstance(problem.get("target"), dict) else {}
        target_summary = " ".join(
            part
            for part in (
                _compact_text(target.get("action"), 100),
                _compact_text(target.get("object"), 800),
            )
            if part
        ) or None
        methods = solution.get("methods") if isinstance(solution.get("methods"), list) else []
        method_names: list[str] = []
        step_texts: list[str] = []
        for method in methods:
            if not isinstance(method, dict):
                continue
            if name := _compact_text(method.get("name"), 1000):
                method_names.append(name)
            for step in method.get("steps", []):
                if not isinstance(step, dict):
                    continue
                if statement := _compact_text(step.get("statement"), 1000):
                    step_texts.append(statement)

        question_type = _compact_text(problem.get("question_type"), 80)
        knowledge_points = [
            _compact_text(item, 120)
            for item in solution.get("knowledge_points", [])
            if _compact_text(item, 120)
        ]
        return KnowledgeQuery(
            text=_compact_text(text, 4000),
            purpose=decision.purpose,
            filters=KnowledgeFilters(
                subject=MVP_SUBJECT_CODE,
                grade=None,
                grade_band=MVP_GRADE_BAND,
                knowledge_points=knowledge_points[:20],
                problem_types=[question_type] if question_type else [],
            ),
            hint_level=hint_level if decision.purpose == "hint_teaching" else None,
            problem_structure=RetrievalProblemStructure(
                condition_statements=conditions[:20],
                target_summary=target_summary,
                solution_methods=method_names[:10],
                solution_steps=step_texts[:20],
            ),
        )

    @staticmethod
    def _next_retrieval_hint_level(
        session: TutoringSession,
        message: str,
        solution: dict,
        verified: bool,
    ) -> int:
        """中文：处理“next·retrieval·提示·level”相关操作。
        English: Handles the next retrieval hint level operation.
        """
        may_show_full = (
            verified
            and bool(solution.get("steps"))
            and (session.attempts > 0 or session.hint_level >= HintLevel.LOCAL_STEP)
        )
        if HintTeachingAgent._requested_full_solution(message) and may_show_full:
            return int(HintLevel.FULL_EXPLANATION)
        return max(1, min(int(session.hint_level) + 1, int(HintLevel.LOCAL_STEP)))

    def _verification_with_revision_context(
        self,
        problem: dict,
        solution: dict,
        revision_attempt: int,
    ) -> dict:
        """中文：处理“校验·with·revision·context”相关操作。
        English: Handles the verification with revision context operation.
        """
        report = self.verifier_agent.run(problem, solution)
        revisable = self._is_revisable_failure(report)
        if report.get("passed"):
            termination_reason = "passed"
            will_retry = False
        elif not revisable:
            termination_reason = "not_revisable"
            will_retry = False
        elif revision_attempt >= self.max_revision_attempts:
            termination_reason = "limit_reached"
            will_retry = False
        else:
            termination_reason = "retryable_failure"
            will_retry = True
        report["revision_context"] = {
            "attempt": revision_attempt,
            "max_attempts": self.max_revision_attempts,
            "will_retry": will_retry,
            "exhausted": termination_reason == "limit_reached",
            "termination_reason": termination_reason,
        }
        return report

    def _is_revisable_failure(self, report: dict) -> bool:
        """中文：处理“is·revisable·failure”相关操作。
        English: Handles the is revisable failure operation.
        """
        if report.get("passed") or not self.solution_agent.provider.available:
            return False
        limitations = [str(item) for item in report.get("limitations", [])]
        if any("模型不可用" in item for item in limitations):
            return False
        if report.get("verifier_type") == "unverified" and not report.get("issues"):
            return False
        return True

    @staticmethod
    def _artifact(session: TutoringSession, kind: str) -> dict:
        """中文：处理“artifact”相关操作。
        English: Handles the artifact operation.
        """
        for artifact in reversed(session.artifacts):
            if artifact.kind == kind:
                return artifact.payload
        return {}

    @staticmethod
    def _invoke(
        session: TutoringSession,
        run_id: str,
        agent_name: str,
        kind: str,
        operation: Callable[[], dict],
        schema_version: str = "1.0",
    ) -> dict:
        """中文：处理“invoke”相关操作。
        English: Handles the invoke operation.
        """
        started = perf_counter()
        result = operation()
        duration_ms = round((perf_counter() - started) * 1000)
        confidence = bounded_number(result.get("confidence"), 0.7, 0, 1)
        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version=schema_version,
            agent=agent_name,
            kind=kind,
            payload=result,
            duration_ms=duration_ms,
            confidence=confidence,
        ))
        return result
