import json
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from app.agents.problem_understanding import ProblemUnderstandingAgent
from app.agents.solution_analysis import SolutionAnalysisAgent
from app.agents.solution_verification import SolutionVerificationAgent
from app.domain.schemas import (
    AgentArtifact,
    LearningRecord,
    LearnerProfile,
    Message,
    TutoringSession,
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
from app.providers.llm import OpenAICompatibleProvider, llm_provider
from app.providers.knowledge import DisabledKnowledgeRetriever, KnowledgeRetriever
from app.retrieval.decision import OnDemandRetrievalPolicy, RetrievalDecision


def bounded_number(value: object, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(float(value), maximum))
    except (TypeError, ValueError):
        return default


def bounded_integer(value: object, default: int, minimum: int, maximum: int) -> int:
    return int(bounded_number(value, default, minimum, maximum))


def _compact_text(value: object, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _has_meaningful_attempt(message: str) -> bool:
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
    name = "learner_diagnosis"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(self, message: str, solution: dict, verification: dict) -> dict:
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
            follow_up_question=follow_up,
            confidence=confidence,
        )

    @staticmethod
    def _evidence(value: object, message: str) -> list[LearnerEvidence]:
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
        if not matches or evidence_id is None:
            return []
        return [EvidenceBackedObservation(
            description=description,
            evidence_ids=[evidence_id],
        ) for description in matches]

    @staticmethod
    def _verified_matches(message: str, solution: dict) -> list[str]:
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
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(
            text for item in value[:limit]
            if (text := _compact_text(item, 300))
            and not LearnerDiagnosisAgent._contains_trait_label(text)
        ))

    @staticmethod
    def _contains_trait_label(text: str) -> bool:
        return any(term in text for term in (
            "能力差", "能力弱", "基础差", "数学不好", "不擅长",
            "笨", "粗心", "不认真", "懒", "没天赋", "聪明",
        ))


class HintTeachingAgent:
    name = "hint_teaching"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def start(self, session: TutoringSession, problem: dict) -> TutorReply:
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
    ) -> TutorReply:
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

        if not verified or not solution.get("steps"):
            return TutorReply(
                action=TutorAction.CLARIFY,
                text="我还不能可靠地确认这道题的解法。你能补充题目里的图、条件，或告诉我你目前试过什么吗？",
                confidence=0.4,
            )

        current_scaffold_level = min(session.hint_level, HintLevel.LOCAL_STEP)
        next_level = max(1, min(current_scaffold_level + 1, HintLevel.LOCAL_STEP))
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
        fallback_text, fallback_check = self._fallback_hint(solution, delivery_level)
        generated = self._generate(
            session,
            message,
            diagnosis,
            solution,
            delivery_level,
            False,
            retrieved_context,
        )
        text = generated.get("text", fallback_text)
        if self._contains_final_answer(text, solution.get("answer")):
            text = fallback_text
        if self._contains_final_answer(text, solution.get("answer")):
            text = self._generic_hint(delivery_level)
        check = generated.get("understanding_check", fallback_check)
        if self._contains_final_answer(check, solution.get("answer")):
            check = fallback_check
        if self._contains_final_answer(check, solution.get("answer")):
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
    ) -> dict:
        return self.provider.complete_json(
            TUTOR_REPLY_PROMPT,
            json.dumps({
                "grade": session.profile.grade,
                "question": session.question,
                "student_message": message,
                "learner_state": diagnosis,
                "teaching_context": self._teaching_context(solution, hint_level),
                "retrieved_teaching_context": retrieved_context or {},
                "hint_level": hint_level,
                "hint_contract": self._stage(hint_level),
                "may_reveal_full_solution": reveal_solution,
            }, ensure_ascii=False),
        ) or {}

    @staticmethod
    def is_meaningful_attempt(message: str) -> bool:
        return _has_meaningful_attempt(message)

    @staticmethod
    def _requested_full_solution(message: str) -> bool:
        return any(word in message for word in (
            "直接告诉", "完整答案", "完整讲解", "看解法", "标准解法", "详细解法",
        ))

    @staticmethod
    def _stage(level: int) -> str:
        return {
            HintLevel.DIRECTION: "direction",
            HintLevel.KEY_RELATION: "key_relation",
            HintLevel.LOCAL_STEP: "local_step",
            HintLevel.FULL_EXPLANATION: "full_explanation",
        }.get(HintLevel(level), "direction")

    @staticmethod
    def _selected_method(solution: dict) -> dict:
        methods = solution.get("methods") if isinstance(solution.get("methods"), list) else []
        recommended_id = solution.get("recommended_method_id")
        return next(
            (
                method for method in methods
                if isinstance(method, dict) and method.get("id") == recommended_id
            ),
            {},
        )

    def _teaching_context(self, solution: dict, level: int) -> dict:
        if level == HintLevel.FULL_EXPLANATION:
            return solution
        breakthroughs = solution.get("key_breakthroughs")
        breakthroughs = breakthroughs if isinstance(breakthroughs, list) else []
        first_breakthrough = breakthroughs[0] if breakthroughs else {}
        base = {
            "knowledge_points": solution.get("knowledge_points", []),
            "common_misconceptions": solution.get("common_misconceptions", []),
        }
        if level == HintLevel.DIRECTION:
            base["direction"] = {
                "title": first_breakthrough.get("title"),
                "hint_question": first_breakthrough.get("hint_question"),
            }
        elif level == HintLevel.KEY_RELATION:
            base["key_relation"] = first_breakthrough
        else:
            base["local_step"] = self._local_step(solution)
        return base

    def _fallback_hint(self, solution: dict, level: int) -> tuple[str, str]:
        breakthroughs = solution.get("key_breakthroughs")
        breakthroughs = breakthroughs if isinstance(breakthroughs, list) else []
        breakthrough = breakthroughs[0] if breakthroughs else {}
        if level == HintLevel.DIRECTION:
            text = breakthrough.get("hint_question") or "先判断这道题最适合从哪个已知条件开始。"
            return text, "你先说说准备处理哪个条件？"
        if level == HintLevel.KEY_RELATION:
            text = breakthrough.get("description") or "找出已知条件和目标之间最直接的数学关系。"
            return text, "你能把这个关系写成式子或一句推理吗？"
        local_step = self._local_step(solution)
        statement = local_step.get("statement") or "先完成推荐方法中的第一小步。"
        result = local_step.get("result")
        text = f"{statement}"
        if result:
            text = f"{text}，这一小步得到 {result}。"
        return text, "接下来你觉得应该处理哪一项？"

    def _local_step(self, solution: dict) -> dict:
        method = self._selected_method(solution)
        steps = method.get("steps") if isinstance(method.get("steps"), list) else []
        if not steps or not isinstance(steps[0], dict):
            return {}
        step = dict(steps[0])
        if len(steps) == 1:
            step.pop("result", None)
        return step

    @staticmethod
    def _contains_final_answer(text: object, answer: object) -> bool:
        normalized_text = re.sub(r"\s+", "", str(text or "")).lower()
        normalized_answer = re.sub(r"\s+", "", str(answer or "")).lower()
        candidates = [normalized_answer]
        if "=" in normalized_answer:
            candidates.append(normalized_answer.rsplit("=", 1)[-1])
        return any(candidate and candidate in normalized_text for candidate in candidates)

    @staticmethod
    def _generic_hint(level: int) -> str:
        if level == HintLevel.DIRECTION:
            return "先选一个与目标最接近的已知条件，说说你为什么想从它开始。"
        if level == HintLevel.KEY_RELATION:
            return "回忆这个知识点最核心的定义或公式，先写出关系，不急着算结果。"
        return "先完成推荐路线中的第一小步，并停在这个中间结果。"


class LearningRecordAgent:
    name = "learning_record"

    def run(self, session: TutoringSession, diagnosis: dict, solution: dict) -> LearningRecord:
        return LearningRecord(
            subject=session.profile.subject,
            grade=session.profile.grade,
            question=session.question,
            learner_answer=diagnosis.get("observed_work", ""),
            error_reason=diagnosis.get("possible_misconception", "待进一步观察"),
            correct_approach="；".join(solution.get("steps", [])),
            knowledge_tags=solution.get("knowledge_points", []),
            difficulty=solution.get("difficulty", 2),
            mastery="待巩固",
        )


class TeachingOrchestrator:
    """Controls agent order and validates state transitions for the first runnable prototype."""

    def __init__(
        self,
        max_revision_attempts: int = 2,
        knowledge_retriever: KnowledgeRetriever | None = None,
    ) -> None:
        self.problem_agent = ProblemUnderstandingAgent(llm_provider)
        self.solution_agent = SolutionAnalysisAgent(llm_provider)
        self.verifier_agent = SolutionVerificationAgent(llm_provider)
        self.diagnosis_agent = LearnerDiagnosisAgent(llm_provider)
        self.tutor_agent = HintTeachingAgent(llm_provider)
        self.record_agent = LearningRecordAgent()
        self.knowledge_retriever = knowledge_retriever or DisabledKnowledgeRetriever()
        self.retrieval_policy = OnDemandRetrievalPolicy()
        self.max_revision_attempts = max(0, min(max_revision_attempts, 3))

    def close(self) -> None:
        self.knowledge_retriever.close()

    def create_session(
        self,
        question: str,
        subject: str,
        grade: str,
        run_id: str,
        student_user_id: str,
        knowledge_problem_id: str | None = None,
    ) -> tuple[TutoringSession, TutorReply]:
        session = TutoringSession(
            student_user_id=student_user_id,
            knowledge_problem_id=knowledge_problem_id,
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
        if not problem["needs_clarification"]:
            self._solve_verify_and_revise(
                session,
                run_id,
                question,
                problem,
                retrieval_already_used=understanding_decision.should_retrieve,
            )
        reply = self.tutor_agent.start(session, problem)
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
        session.messages.append(Message(role="student", content=message))
        if session.status == TutoringStatus.CLARIFYING:
            return self._handle_clarification(session, message, run_id)

        solution = self._artifact(session, "solution_plan")
        verification = self._artifact(session, "verification_report")
        diagnosis = self._invoke(
            session,
            run_id,
            self.diagnosis_agent.name,
            "learner_state",
            lambda: self.diagnosis_agent.run(message, solution, verification),
            schema_version="2.0",
        )
        if diagnosis.get("has_meaningful_attempt"):
            session.attempts += 1

        reply_context: dict | None = None
        if intent == "complete" or any(token in message for token in ("我懂了", "我会了", "做出来了")):
            session.status = TutoringStatus.COMPLETED
            session.record = self.record_agent.run(session, diagnosis, solution)
            session.artifacts.append(AgentArtifact(
                run_id=run_id,
                agent=self.record_agent.name,
                kind="learning_record",
                payload=session.record.model_dump(mode="json"),
                confidence=0.8,
            ))
            may_show_completed_solution = (
                verification.get("passed")
                and (session.attempts > 0 or session.hint_level >= HintLevel.LOCAL_STEP)
            )
            if may_show_completed_solution:
                session.hint_level = HintLevel.FULL_EXPLANATION
            reply = TutorReply(
                action=TutorAction.SUMMARIZE,
                text="太好了，你已经把关键思路走通了！这题用到的是分配律和一元一次方程。完成后可以在错题本里复习这道题。",
                hint_level=(HintLevel.FULL_EXPLANATION if may_show_completed_solution else None),
                hint_stage=("full_explanation" if may_show_completed_solution else None),
                solution_steps=(solution.get("steps", []) if may_show_completed_solution else []),
                can_show_full_solution=bool(may_show_completed_solution),
                confidence=0.85 if verification.get("passed") else 0.45,
            )
            if may_show_completed_solution:
                reply_context = self._latest_agent_teaching_context(session)
        elif intent == "practice" or any(token in message for token in ("相似题", "练习一下")):
            session.status = TutoringStatus.EXPLAINING
            reply = TutorReply(action=TutorAction.CHECK_ATTEMPT, text="试试这道相似题：2(x + 4) = 3x − 1。你可以先写出展开括号后的等式。", confidence=0.75)
        else:
            session.status = TutoringStatus.HINTING
            hint_level = self._next_retrieval_hint_level(
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
            )

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

    def _handle_clarification(
        self,
        session: TutoringSession,
        message: str,
        run_id: str,
    ) -> TutorReply:
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
        if not problem["needs_clarification"]:
            self._solve_verify_and_revise(
                session,
                run_id,
                session.question,
                problem,
                retrieval_already_used=understanding_decision.should_retrieve,
            )

        reply = self.tutor_agent.start(session, problem)
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
                kind="retrieved_teaching_context",
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

        session.artifacts.append(AgentArtifact(
            run_id=run_id,
            schema_version=context.schema_version,
            agent=self.knowledge_retriever.name,
            kind="retrieved_teaching_context",
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
        if context.diagnostics.selected_count <= 0:
            return None
        return context.to_agent_context().model_dump(mode="json")

    @staticmethod
    def _latest_agent_teaching_context(
        session: TutoringSession,
    ) -> dict | None:
        for artifact in reversed(session.artifacts):
            if artifact.kind != "retrieved_teaching_context":
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

    @staticmethod
    def _source_references(
        teaching_context: dict | None,
    ) -> list[TutorSourceReference]:
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

        subject = "math" if session.profile.subject in {"数学", "math"} else session.profile.subject
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
                subject=subject,
                grade=session.profile.grade,
                grade_band=session.profile.grade,
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
