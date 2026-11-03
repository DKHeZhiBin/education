from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.problem_image import FormulaStructureIssue, FormulaValidationStatus


@dataclass(frozen=True)
class FormulaStructureCheck:
    """中文：汇总公式结构状态、问题和参与检查的规范化公式。
    English: Summarizes formula status, issues, and normalized formulas checked.
    """

    status: FormulaValidationStatus
    issues: tuple[FormulaStructureIssue, ...]
    formulas: tuple[str, ...]


class FormulaStructureChecker:
    """中文：对 OCR 数学公式执行不依赖模型的确定性结构检查。
    English: Performs deterministic model-independent structural checks on OCR formulas.
    """

    _pairs = {"(": ")", "[": "]", "{": "}"}
    _closing = set(_pairs.values())
    _uncertain_markers = ("�", "□", "▢", "<?>", "[?]", "\\text{?}")

    def check(self, question_text: str, formulas: list[str] | tuple[str, ...]) -> FormulaStructureCheck:
        """中文：检查分隔符、成对符号、核心 LaTeX 命令和可疑占位符。
        English: Checks delimiters, paired symbols, core LaTeX commands, and uncertain placeholders.
        """
        normalized = tuple(dict.fromkeys(item.strip() for item in formulas if item.strip()))
        issues: list[FormulaStructureIssue] = []
        issues.extend(self._check_math_delimiters(question_text))
        for index, formula in enumerate(normalized):
            issues.extend(self._check_formula(formula, index))
        if len(normalized) < len([item for item in formulas if item.strip()]):
            issues.append(FormulaStructureIssue(
                code="duplicate_formula",
                severity="warning",
                message="识别结果中有重复公式，确认时已合并。",
            ))
        status: FormulaValidationStatus = "valid"
        if any(issue.severity == "error" for issue in issues):
            status = "invalid"
        elif issues:
            status = "needs_review"
        return FormulaStructureCheck(status=status, issues=tuple(issues), formulas=normalized)

    def extract_formulas(self, question_text: str) -> tuple[str, ...]:
        """中文：从学生修正后的正文中提取行内及块级 LaTeX 公式。
        English: Extracts inline and block LaTeX formulas from student-corrected text.
        """
        blocks = re.findall(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", question_text, re.DOTALL)
        without_blocks = re.sub(r"(?<!\\)\$\$.+?(?<!\\)\$\$", " ", question_text, flags=re.DOTALL)
        inline = re.findall(r"(?<!\\)\$(.+?)(?<!\\)\$", without_blocks, re.DOTALL)
        return tuple(item.strip() for item in (*blocks, *inline) if item.strip())

    def _check_math_delimiters(self, text: str) -> list[FormulaStructureIssue]:
        """中文：检查正文中的单美元和双美元公式边界是否闭合。
        English: Checks whether inline and block math delimiters in text are closed.
        """
        cleaned = re.sub(r"\\\$", "", text)
        block_count = len(re.findall(r"\$\$", cleaned))
        without_blocks = re.sub(r"\$\$", "", cleaned)
        issues: list[FormulaStructureIssue] = []
        if block_count % 2:
            issues.append(FormulaStructureIssue(
                code="unclosed_block_math",
                severity="error",
                message="题目中的块级公式 $$ 没有成对闭合。",
            ))
        if without_blocks.count("$") % 2:
            issues.append(FormulaStructureIssue(
                code="unclosed_inline_math",
                severity="error",
                message="题目中的行内公式 $ 没有成对闭合。",
            ))
        return issues

    def _check_formula(self, formula: str, index: int) -> list[FormulaStructureIssue]:
        """中文：检查一条 LaTeX 公式的主要结构约束。
        English: Checks the main structural constraints of one LaTeX formula.
        """
        issues: list[FormulaStructureIssue] = []
        stack: list[tuple[str, int]] = []
        escaped = False
        for position, character in enumerate(formula):
            if escaped:
                escaped = False
                continue
            if character == "\\":
                escaped = True
                continue
            if character in self._pairs:
                stack.append((character, position))
            elif character in self._closing:
                if not stack or self._pairs[stack[-1][0]] != character:
                    issues.append(self._formula_issue(
                        "mismatched_bracket", "error", index, "公式中存在无法配对的括号或花括号。"
                    ))
                    break
                stack.pop()
        if stack:
            issues.append(self._formula_issue(
                "unclosed_bracket", "error", index, "公式中存在未闭合的括号或花括号。"
            ))
        if len(re.findall(r"\\left\b", formula)) != len(re.findall(r"\\right\b", formula)):
            issues.append(self._formula_issue(
                "unbalanced_left_right", "error", index, "公式中的 \\left 与 \\right 数量不一致。"
            ))
        if re.search(r"\\frac\s*(?!\{)", formula):
            issues.append(self._formula_issue(
                "malformed_fraction", "error", index, "分数命令 \\frac 后缺少分子或分母结构。"
            ))
        if re.search(r"\\sqrt(?:\[[^\]]*\])?\s*(?!\{)", formula):
            issues.append(self._formula_issue(
                "ambiguous_root", "warning", index, "根式没有使用花括号标明完整被开方部分，请核对范围。"
            ))
        if any(marker in formula for marker in self._uncertain_markers):
            issues.append(self._formula_issue(
                "uncertain_ocr_symbol", "error", index, "公式包含 OCR 无法确认的占位符，请对照原图修正。"
            ))
        if re.search(r"(?<![<>=])={2,}(?!=)", formula) or "= =" in formula:
            issues.append(self._formula_issue(
                "suspicious_relation", "warning", index, "公式中出现重复等号，请确认关系符是否正确。"
            ))
        return issues

    @staticmethod
    def _formula_issue(code: str, severity: str, index: int, message: str) -> FormulaStructureIssue:
        """中文：创建带公式序号的结构问题对象。
        English: Creates a structure issue associated with a formula index.
        """
        return FormulaStructureIssue(
            code=code,
            severity=severity,
            formula_index=index,
            message=message,
        )


formula_structure_checker = FormulaStructureChecker()
