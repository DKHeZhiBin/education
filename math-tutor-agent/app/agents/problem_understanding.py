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
    ThinkingMethodCandidate,
)
from app.prompts.policies import PROBLEM_UNDERSTANDING_PROMPT
from app.providers.llm import LLMProvider


QUESTION_TYPES = {item.value: item for item in QuestionType}
METHOD_CATALOG = {
    "equivalent-transform": ("transformation", "转化与化归", "等价转化"),
    "middle-substitute": ("transformation", "转化与化归", "换元法"),
    "reduce-degree": ("transformation", "转化与化归", "降次与结构简化"),
    "representation-transform": ("transformation", "转化与化归", "表示转换"),
    "whole-structure": ("whole-local", "整体与局部", "整体结构识别"),
    "classify-by-sign": ("case-analysis", "分类讨论", "按符号分类"),
    "classify-by-parameter": ("case-analysis", "分类讨论", "按参数分类"),
    "boundary-degeneration": ("case-analysis", "分类讨论", "边界与退化检查"),
    "function-graph": ("number-shape", "数形结合", "函数图像分析"),
    "coordinate-method": ("number-shape", "数形结合", "坐标化"),
    "zero-intersection": ("function-equation", "函数与方程", "零点与交点"),
    "monotonicity-analysis": ("function-equation", "函数与方程", "单调性分析"),
    "special-case-exploration": ("special-general", "特殊与一般", "特例探索"),
    "counterexample-check": ("special-general", "特殊与一般", "反例检验"),
    "auxiliary-line": ("construction-correspondence", "构造与对应", "辅助线构造"),
    "pairing-mapping": ("construction-correspondence", "构造与对应", "配对与映射"),
    "successive-approximation": ("limit-approximation", "极限与逼近", "逐次逼近"),
}
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
    """中文：处理“bounded·confidence”相关操作。
    English: Handles the bounded confidence operation.
    """
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return default


def _boolean(value: object) -> bool:
    """中文：处理“boolean”相关操作。
    English: Handles the boolean operation.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _clean_text(value: object) -> str:
    """中文：处理“clean·text”相关操作。
    English: Handles the clean text operation.
    """
    return re.sub(r"\s+", " ", str(value or "")).strip()


class ProblemUnderstandingAgent:
    """中文：定义“题目·understanding·智能体”类，封装该职责相关的数据与行为。
    English: Defines the problem understanding agent class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Turns the raw exercise into a validated, non-solving ProblemSpec.
    """

    name = "problem_understanding"

    def __init__(self, provider: LLMProvider) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.provider = provider

    def run(
        self,
        question: str,
        subject: str = "数学",
        grade_band: str = "未知",
        teaching_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """中文：处理“执行”相关操作。
        English: Handles the run operation.
        """
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
        """中文：处理“rule·based·spec”相关操作。
        English: Handles the rule based spec operation.
        """
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
            thinking_methods=self._classify_thinking_methods(normalized),
            needs_clarification=needs_clarification,
            clarification_questions=clarification_questions,
            clarification=clarification_questions[0] if clarification_questions else "",
            confidence=confidence,
        )

    def _merge_provider_result(self, result: dict[str, Any], fallback: ProblemSpec) -> ProblemSpec:
        """中文：处理“merge·提供方·结果”相关操作。
        English: Handles the merge provider result operation.
        """
        normalized = _clean_text(result.get("normalized_question")) or fallback.normalized_question
        question_type = self._question_type(result.get("question_type"), fallback.question_type)
        # 中文：确定性规则已识别出非线性结构时，不接受模型把它降级成一次方程。
        # English: Do not let the model downgrade a deterministically detected nonlinear equation to linear.
        if (
            fallback.question_type == QuestionType.EQUATION
            and question_type == QuestionType.LINEAR_EQUATION
        ):
            question_type = fallback.question_type
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
        thinking_methods = self._merge_thinking_methods(
            self._parse_thinking_methods(result.get("thinking_methods")),
            fallback.thinking_methods,
        )
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
            thinking_methods=thinking_methods,
            needs_clarification=needs_clarification,
            clarification_questions=questions,
            clarification=clarification,
            confidence=confidence,
        )

    @staticmethod
    def _classify_thinking_methods(question: str) -> list[ThinkingMethodCandidate]:
        """中文：用确定性结构信号给出保守的方法分类。
        English: Uses deterministic structural signals for conservative method classification.
        """
        candidates: list[ThinkingMethodCandidate] = []
        if ("√" in question or "根号" in question) and "=" in question:
            candidates.append(ThinkingMethodCandidate(
                category_id="transformation",
                category_name="转化与化归",
                method_id="equivalent-transform",
                method_name="等价转化",
                role="primary",
                evidence="方程含多个根式，需要在定义域内通过移项、有理化或平方等保持条件的变形推进。",
                confidence=0.88,
            ))
            candidates.append(ThinkingMethodCandidate(
                category_id="whole-local",
                category_name="整体与局部",
                method_id="whole-structure",
                method_name="整体结构识别",
                role="related",
                evidence="等式两侧由多个根式差组成，可先把根式差视为整体并比较结构。",
                confidence=0.76,
            ))
        elif re.search(r"[A-Za-z]\s*(?:\^\s*[34]|[³⁴])", question) and "=" in question:
            candidates.append(ThinkingMethodCandidate(
                category_id="transformation", category_name="转化与化归",
                method_id="reduce-degree", method_name="降次与结构简化", role="primary",
                evidence="方程含高次幂结构，可先寻找低次整体。", confidence=0.8,
            ))
        if not candidates and ("绝对值" in question or "|" in question):
            candidates.append(ThinkingMethodCandidate(
                category_id="case-analysis", category_name="分类讨论",
                method_id="classify-by-sign", method_name="按符号分类", role="primary",
                evidence="绝对值表达式需要按内部式子的符号分界讨论。", confidence=0.85,
            ))
        return candidates

    @staticmethod
    def _parse_thinking_methods(value: object) -> list[ThinkingMethodCandidate]:
        """中文：校验模型返回的方法分类并限制到正式目录。
        English: Validates model classifications against the published method catalog.
        """
        if not isinstance(value, list):
            return []
        parsed: list[ThinkingMethodCandidate] = []
        primary_used = False
        for item in value[:3]:
            if not isinstance(item, dict):
                continue
            method_id = _clean_text(item.get("method_id"))
            catalog = METHOD_CATALOG.get(method_id)
            if not catalog:
                continue
            category_id, category_name, method_name = catalog
            requested_role = _clean_text(item.get("role"))
            role = "primary" if requested_role == "primary" and not primary_used else "related"
            primary_used = primary_used or role == "primary"
            parsed.append(ThinkingMethodCandidate(
                category_id=category_id,
                category_name=category_name,
                method_id=method_id,
                method_name=method_name,
                role=role,
                evidence=_clean_text(item.get("evidence")) or "模型识别到对应结构信号。",
                confidence=_bounded_confidence(item.get("confidence"), 0.6),
            ))
        if parsed and not primary_used:
            parsed[0].role = "primary"
        return parsed

    @staticmethod
    def _merge_thinking_methods(
        provider_items: list[ThinkingMethodCandidate],
        fallback_items: list[ThinkingMethodCandidate],
    ) -> list[ThinkingMethodCandidate]:
        """中文：合并模型与确定性分类，并保留一个主方法。
        English: Merges model and deterministic classifications with one primary method.
        """
        merged: dict[str, ThinkingMethodCandidate] = {}
        for item in [*provider_items, *fallback_items]:
            current = merged.get(item.method_id)
            if current is None or item.confidence > current.confidence:
                merged[item.method_id] = item.model_copy()
        ordered = list(merged.values())[:3]
        for index, item in enumerate(ordered):
            item.role = "primary" if index == 0 else "related"
        return ordered

    @staticmethod
    def _classify(question: str) -> tuple[QuestionType, str, float]:
        """中文：处理“classify”相关操作。
        English: Handles the classify operation.
        """
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
        if "=" in question and re.search(r"\^\s*(?:\{[^}]*[A-Za-z]|[^\s=]*[A-Za-z])", question):
            return QuestionType.EQUATION, "未知量出现在指数中，属于非线性指数方程", 0.9
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
        """中文：处理“extract·conditions”相关操作。
        English: Handles the extract conditions operation.
        """
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
        """中文：处理“extract·target”相关操作。
        English: Handles the extract target operation.
        """
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
        """中文：处理“detect·ambiguities”相关操作。
        English: Handles the detect ambiguities operation.
        """
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
        """中文：处理“问题·type”相关操作。
        English: Handles the question type operation.
        """
        normalized = _clean_text(value).lower()
        return QUESTION_TYPES.get(normalized, default)

    def _parse_candidates(self, value: object) -> list[QuestionTypeCandidate]:
        """中文：处理“解析·candidates”相关操作。
        English: Handles the parse candidates operation.
        """
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
        """中文：处理“解析·conditions”相关操作。
        English: Handles the parse conditions operation.
        """
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
        """中文：处理“解析·target”相关操作。
        English: Handles the parse target operation.
        """
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
        """中文：处理“解析·ambiguities”相关操作。
        English: Handles the parse ambiguities operation.
        """
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
        """中文：处理“deduplicate·ambiguities”相关操作。
        English: Handles the deduplicate ambiguities operation.
        """
        unique: dict[tuple[str, str], ProblemAmbiguity] = {}
        for item in items:
            unique[(item.kind, item.description)] = item
        return list(unique.values())

    @staticmethod
    def _string_list(value: object) -> list[str]:
        """中文：处理“string·列出”相关操作。
        English: Handles the string list operation.
        """
        if not isinstance(value, list):
            return []
        return [_clean_text(item) for item in value if _clean_text(item)][:10]
