import json
import re
from typing import Any

from app.domain.problem import (
    ProblemAmbiguity,
    ProblemCondition,
    ProblemSpec,
    ProblemTarget,
    QuestionType,
    QuestionTypeCandidate,
)
from app.prompts.policies import PROBLEM_UNDERSTANDING_PROMPT
from app.providers.llm import OpenAICompatibleProvider


QUESTION_TYPES = {item.value: item for item in QuestionType}
TARGET_ACTION_CODES = {
    "solve",
    "calculate",
    "prove",
    "find",
    "compare",
    "determine",
    "simplify",
    "graph",
}
TARGET_ACTIONS = (
    ("证明", "prove"),
    ("求证", "prove"),
    ("求解", "solve"),
    ("计算", "calculate"),
    ("化简", "simplify"),
    ("判断", "determine"),
    ("比较", "compare"),
    ("作图", "graph"),
    ("画出", "graph"),
    ("解", "solve"),
    ("求", "find"),
)


def _bounded_confidence(value: object, default: float) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return default


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


class ProblemUnderstandingAgent:
    """Turns the raw exercise into a validated, non-solving ProblemSpec."""

    name = "problem_understanding"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(
        self,
        question: str,
        subject: str = "数学",
        grade_band: str = "未知",
        teaching_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback = self._rule_based_spec(question, subject, grade_band)
        result = self.provider.complete_json(
            PROBLEM_UNDERSTANDING_PROMPT,
            json.dumps({
                "question": question,
                "declared_subject": subject,
                "declared_grade_band": grade_band,
                "retrieved_teaching_context": teaching_context or {},
            }, ensure_ascii=False),
        )
        if not result:
            return fallback.model_dump(mode="json")
        return self._merge_provider_result(result, fallback).model_dump(mode="json")

    def _rule_based_spec(
        self,
        question: str,
        subject: str,
        grade_band: str,
    ) -> ProblemSpec:
        normalized = _clean_text(question)
        primary_type, evidence, type_confidence = self._classify(normalized)
        conditions = self._extract_conditions(normalized)
        target = self._extract_target(normalized, primary_type)
        ambiguities = self._detect_ambiguities(normalized, target)
        clarification_questions = [
            item.clarification_question
            for item in ambiguities
            if item.severity == "blocking"
        ]
        needs_clarification = bool(clarification_questions)
        confidence = 0.35 if needs_clarification else type_confidence
        return ProblemSpec(
            normalized_question=normalized,
            subject=subject,
            grade_band=grade_band,
            question_type=primary_type,
            question_type_candidates=[QuestionTypeCandidate(
                type=primary_type,
                confidence=type_confidence,
                evidence=evidence,
            )],
            known_conditions=conditions,
            target=target,
            ambiguities=ambiguities,
            needs_clarification=needs_clarification,
            clarification_questions=clarification_questions,
            clarification=clarification_questions[0] if clarification_questions else "",
            confidence=confidence,
        )

    def _merge_provider_result(self, result: dict[str, Any], fallback: ProblemSpec) -> ProblemSpec:
        normalized = _clean_text(result.get("normalized_question")) or fallback.normalized_question
        question_type = self._question_type(result.get("question_type"), fallback.question_type)
        candidates = self._parse_candidates(result.get("question_type_candidates"))
        if not candidates:
            candidates = fallback.question_type_candidates

        provider_conditions = self._parse_conditions(result.get("known_conditions"))
        conditions = list({
            item.statement: item
            for item in [*fallback.known_conditions, *provider_conditions]
        }.values())
        target = self._parse_target(result.get("target")) or fallback.target

        provider_ambiguities = self._parse_ambiguities(result.get("ambiguities"))
        fallback_ambiguities = fallback.ambiguities
        if target is not None:
            fallback_ambiguities = [
                item for item in fallback_ambiguities if item.kind != "missing_target"
            ]
        ambiguities = self._deduplicate_ambiguities(
            [*fallback_ambiguities, *provider_ambiguities]
        )
        provider_questions = self._string_list(result.get("clarification_questions"))
        blocking_questions = [
            item.clarification_question
            for item in ambiguities
            if item.severity == "blocking"
        ]
        questions = list(dict.fromkeys([*blocking_questions, *provider_questions]))
        needs_clarification = (
            _boolean(result.get("needs_clarification", False))
            or bool(blocking_questions)
        )
        clarification = _clean_text(result.get("clarification"))
        if needs_clarification and not clarification:
            clarification = questions[0] if questions else "题目信息还不完整，请补充缺失条件。"
        confidence = _bounded_confidence(result.get("confidence"), fallback.confidence)
        if needs_clarification:
            confidence = min(confidence, 0.49)

        return ProblemSpec(
            normalized_question=normalized,
            subject=_clean_text(result.get("subject")) or fallback.subject,
            grade_band=_clean_text(result.get("grade_band")) or fallback.grade_band,
            question_type=question_type,
            question_type_candidates=candidates,
            known_conditions=conditions,
            target=target,
            ambiguities=ambiguities,
            needs_clarification=needs_clarification,
            clarification_questions=questions,
            clarification=clarification,
            confidence=confidence,
        )

    @staticmethod
    def _classify(question: str) -> tuple[QuestionType, str, float]:
        rules = (
            (QuestionType.PROOF, ("证明", "求证"), "题目要求证明结论"),
            (QuestionType.CALCULUS, ("导数", "微分", "积分", "极限"), "包含微积分关键词"),
            (QuestionType.TRIGONOMETRY, ("正弦", "余弦", "正切", "sin", "cos", "tan"), "包含三角函数或三角恒等关系"),
            (QuestionType.ANALYTIC_GEOMETRY, ("椭圆", "双曲线", "抛物线", "轨迹", "坐标系"), "包含解析几何对象"),
            (QuestionType.COMBINATORICS, ("排列", "组合", "计数", "有多少种"), "包含组合计数任务"),
            (QuestionType.PROBABILITY, ("概率", "随机", "抽取", "掷"), "包含概率情境"),
            (QuestionType.STATISTICS, ("平均数", "中位数", "方差", "标准差", "频率"), "包含统计量"),
            (QuestionType.NUMBER_THEORY, ("质数", "素数", "整除", "最大公约数", "同余"), "包含数论性质"),
            (QuestionType.OPTIMIZATION, ("最大值", "最小值", "最优", "取值范围"), "要求极值或最优结果"),
            (QuestionType.SEQUENCE, ("数列", "通项", "等差", "等比"), "包含数列关键词"),
            (QuestionType.EQUATION_SYSTEM, ("方程组",), "题目要求处理方程组"),
            (QuestionType.GEOMETRY, ("三角形", "圆", "平行", "垂直", "角", "面积", "几何"), "包含几何对象或关系"),
            (QuestionType.FUNCTION, ("函数", "定义域", "值域", "图像", "单调"), "包含函数关键词"),
            (QuestionType.INEQUALITY, ("不等式", "≤", "≥"), "包含不等关系"),
        )
        for question_type, keywords, evidence in rules:
            if any(keyword in question for keyword in keywords):
                return question_type, evidence, 0.82
        if re.search(r"[A-Za-z]\s*(?:\^\s*2|[²])", question) and "=" in question:
            return QuestionType.QUADRATIC_EQUATION, "等式中包含未知量的二次项", 0.85
        if "=" in question and re.search(r"[A-Za-z]", question):
            nonlinear = bool(re.search(
                r"(?:[A-Za-z]\s*[A-Za-z]|√|根号|[A-Za-z]\s*/|/\s*[A-Za-z])",
                question,
            ))
            if nonlinear:
                return QuestionType.EQUATION, "包含未知量和等号，但规则无法确认方程次数", 0.6
            return QuestionType.LINEAR_EQUATION, "未知量只以一次形式出现在等式中", 0.78
        if any(word in question for word in ("每", "速度", "路程", "利润", "浓度", "工程", "人数")):
            return QuestionType.APPLICATION, "包含数量关系情境", 0.68
        if re.fullmatch(r"[\d\s.+\-−×÷*/()（）=]+[？?]?", question):
            return QuestionType.ARITHMETIC, "主要由数值和运算符组成", 0.8
        if any(word in question for word in ("代数式", "因式分解", "展开", "合并同类项")):
            return QuestionType.ALGEBRAIC_EXPRESSION, "要求处理代数表达式", 0.76
        return QuestionType.UNKNOWN, "规则无法可靠判定题型", 0.4

    @staticmethod
    def _extract_conditions(question: str) -> list[ProblemCondition]:
        conditions: list[ProblemCondition] = []
        segments = [item.strip(" ，。；;：:") for item in re.split(r"[。；;\n]", question)]
        for segment in segments:
            if not segment:
                continue
            has_relation = bool(re.search(r"(?:=|≤|≥|<|>|∥|⊥)", segment))
            condition_prefix = bool(re.search(r"(?:已知|若|设|给定|满足|其中)", segment))
            if not (has_relation or condition_prefix):
                continue
            kind = "relation" if has_relation else "text"
            if "=" in segment:
                kind = "equation"
            elif any(mark in segment for mark in ("≤", "≥", "<", ">")):
                kind = "inequality"
            elif any(mark in segment for mark in ("∥", "⊥")):
                kind = "geometric_relation"
            conditions.append(ProblemCondition(statement=segment, kind=kind))
        return list({item.statement: item for item in conditions}.values())

    @staticmethod
    def _extract_target(question: str, question_type: QuestionType) -> ProblemTarget | None:
        for chinese_action, action in TARGET_ACTIONS:
            match = re.search(
                rf"{chinese_action}(?:出|方程)?\s*([^。；;？?]+)",
                question,
            )
            if match:
                target_object = match.group(1).strip(" ：:")
                expected = {
                    "prove": "proof",
                    "solve": "solution_set",
                    "graph": "graph",
                    "determine": "boolean_with_reason",
                }.get(action, "expression_or_value")
                return ProblemTarget(
                    action=action,
                    object=target_object or "题目所问结论",
                    expected_answer_type=expected,
                )
        for marker, action in (("多少", "find"), ("几个", "find"), ("是否", "determine")):
            if marker in question:
                clause = next(
                    (
                        item.strip()
                        for item in re.split(r"[。；;？?]", question)
                        if marker in item
                    ),
                    question,
                )
                return ProblemTarget(
                    action=action,
                    object=clause,
                    expected_answer_type="value" if action == "find" else "boolean_with_reason",
                )
        if "=" in question and re.search(r"[A-Za-z]", question):
            return ProblemTarget(
                action="solve",
                object="方程中的未知量",
                expected_answer_type="value_or_solution_set",
                source="inferred",
            )
        if question_type == QuestionType.ARITHMETIC:
            return ProblemTarget(
                action="calculate",
                object="给定算式",
                expected_answer_type="value",
                source="inferred",
            )
        if question_type == QuestionType.ALGEBRAIC_EXPRESSION:
            return ProblemTarget(
                action="simplify",
                object="给定代数式",
                expected_answer_type="expression",
                source="inferred",
            )
        return None

    @staticmethod
    def _detect_ambiguities(question: str, target: ProblemTarget | None) -> list[ProblemAmbiguity]:
        ambiguities: list[ProblemAmbiguity] = []
        latest_supplement = (
            question.rpartition("补充信息：")[2].strip()
            if "补充信息：" in question
            else ""
        )
        if len(question) < 4:
            ambiguities.append(ProblemAmbiguity(
                kind="incomplete_statement",
                description="题干过短，无法形成完整数学任务。",
                clarification_question="请把完整题目发给我，包括所有数字、符号和问题。",
            ))
        diagram_was_described = bool(
            latest_supplement
            and re.search(
                r"(?:∠|°|厘米|米|长度|角度|半径|直径|平行|垂直|相交|[A-Z]{2,})",
                latest_supplement,
            )
        )
        if (
            any(marker in question for marker in ("如图", "见图", "下图", "图中"))
            and not diagram_was_described
        ):
            ambiguities.append(ProblemAmbiguity(
                kind="missing_diagram",
                description="题干引用了图形，但当前输入没有可解析的图形条件。",
                clarification_question="请上传题目图片，或把图中的点、线、角度和位置关系写出来。",
            ))
        mentions_options = any(marker in question for marker in ("选择", "选项", "下列"))
        has_options = bool(re.search(r"(?:^|\s)[A-DＡ-Ｄ][.．、:]", question))
        if mentions_options and not has_options:
            ambiguities.append(ProblemAmbiguity(
                kind="missing_options",
                description="题目提到选项，但没有提供完整选项。",
                clarification_question="请补充 A、B、C、D 等全部选项。",
            ))
        pairs = (("(", ")"), ("（", "）"), ("[", "]"), ("{", "}"))
        supplement_restates_expression = any(
            mark in latest_supplement for pair in pairs for mark in pair
        )
        delimiter_text = latest_supplement if supplement_restates_expression else question
        if any(delimiter_text.count(left) != delimiter_text.count(right) for left, right in pairs):
            ambiguities.append(ProblemAmbiguity(
                kind="unbalanced_delimiter",
                description="题目中的括号或分组符号不完整。",
                clarification_question="请确认题目中的括号范围并重新发送相关算式。",
            ))
        if target is None and len(question) >= 4:
            ambiguities.append(ProblemAmbiguity(
                kind="missing_target",
                description="可以识别部分题目信息，但没有明确要求求什么或证明什么。",
                clarification_question="这道题需要求、计算、判断还是证明什么？",
            ))
        return ambiguities

    @staticmethod
    def _question_type(value: object, default: QuestionType) -> QuestionType:
        normalized = _clean_text(value).lower()
        return QUESTION_TYPES.get(normalized, default)

    def _parse_candidates(self, value: object) -> list[QuestionTypeCandidate]:
        if not isinstance(value, list):
            return []
        candidates: list[QuestionTypeCandidate] = []
        for item in value:
            if isinstance(item, str):
                question_type = self._question_type(item, QuestionType.UNKNOWN)
                candidates.append(QuestionTypeCandidate(type=question_type, confidence=0.5))
            elif isinstance(item, dict):
                question_type = self._question_type(item.get("type"), QuestionType.UNKNOWN)
                candidates.append(QuestionTypeCandidate(
                    type=question_type,
                    confidence=_bounded_confidence(item.get("confidence"), 0.5),
                    evidence=_clean_text(item.get("evidence")),
                ))
        return candidates[:5]

    @staticmethod
    def _parse_conditions(value: object) -> list[ProblemCondition]:
        if not isinstance(value, list):
            return []
        conditions: list[ProblemCondition] = []
        for item in value:
            if isinstance(item, str) and _clean_text(item):
                conditions.append(ProblemCondition(statement=_clean_text(item)))
            elif isinstance(item, dict) and _clean_text(item.get("statement")):
                conditions.append(ProblemCondition(
                    statement=_clean_text(item.get("statement")),
                    kind=_clean_text(item.get("kind")) or "text",
                    source="inferred" if item.get("source") == "inferred" else "explicit",
                    confidence=_bounded_confidence(item.get("confidence"), 0.8),
                ))
        return conditions[:30]

    @staticmethod
    def _parse_target(value: object) -> ProblemTarget | None:
        if isinstance(value, str) and _clean_text(value):
            return ProblemTarget(action="find", object=_clean_text(value))
        if not isinstance(value, dict) or not _clean_text(value.get("object")):
            return None
        action = _clean_text(value.get("action")).lower()
        return ProblemTarget(
            action=action if action in TARGET_ACTION_CODES else "find",
            object=_clean_text(value.get("object")),
            expected_answer_type=_clean_text(value.get("expected_answer_type")) or "unknown",
            source="inferred" if value.get("source") == "inferred" else "explicit",
        )

    @staticmethod
    def _parse_ambiguities(value: object) -> list[ProblemAmbiguity]:
        if not isinstance(value, list):
            return []
        ambiguities: list[ProblemAmbiguity] = []
        for item in value:
            if isinstance(item, str) and _clean_text(item):
                description = _clean_text(item)
                ambiguities.append(ProblemAmbiguity(
                    kind="unspecified",
                    description=description,
                    clarification_question=f"请确认：{description}",
                ))
            elif isinstance(item, dict) and _clean_text(item.get("description")):
                description = _clean_text(item.get("description"))
                ambiguities.append(ProblemAmbiguity(
                    kind=_clean_text(item.get("kind")) or "unspecified",
                    description=description,
                    severity="warning" if item.get("severity") == "warning" else "blocking",
                    clarification_question=(
                        _clean_text(item.get("clarification_question"))
                        or f"请确认：{description}"
                    ),
                ))
        return ambiguities[:20]

    @staticmethod
    def _deduplicate_ambiguities(items: list[ProblemAmbiguity]) -> list[ProblemAmbiguity]:
        unique: dict[tuple[str, str], ProblemAmbiguity] = {}
        for item in items:
            unique[(item.kind, item.description)] = item
        return list(unique.values())

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [_clean_text(item) for item in value if _clean_text(item)][:10]
