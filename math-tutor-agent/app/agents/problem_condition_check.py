from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.domain.problem_condition_check import (
    ConditionCheckDimension,
    ConditionCheckStatus,
    ConditionIssue,
    ProblemConditionCheckContext,
    ProblemConditionCheckReport,
    SolutionCountCheck,
)
from app.prompts.problem_condition_check import PROBLEM_CONDITION_CHECK_PROMPT
from app.providers.llm import OpenAICompatibleProvider


FORBIDDEN_RESULT_KEYS = {
    "answer",
    "answers",
    "final_answer",
    "roots",
    "solution_values",
    "steps",
    "proof",
    "reasoning",
    "chain_of_thought",
}
ALLOWED_TOP_LEVEL_KEYS = {
    "ambiguity",
    "condition_completeness",
    "domain",
    "solution_count",
    "grade_fit",
    "summary",
    "approval_eligible",
}


class ProblemConditionCheckError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProblemConditionCheckAgent:
    """Inspect a generated problem without reading or producing a solution."""

    name = "problem_condition_check"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(
        self,
        *,
        context: ProblemConditionCheckContext,
        expected_model_name: str,
        versioned_prompt: str,
    ) -> ProblemConditionCheckReport:
        if not self.provider.available:
            raise ProblemConditionCheckError(
                "provider_unavailable", "LLM provider is unavailable"
            )
        if self.provider.model_name != expected_model_name:
            raise ProblemConditionCheckError(
                "model_version_mismatch",
                "configured provider model does not match the registered model version",
            )
        result = self.provider.complete_json(
            self._system_prompt(versioned_prompt),
            json.dumps(context.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
        )
        if result is None:
            raise ProblemConditionCheckError(
                "provider_invalid_response",
                "LLM provider did not return a valid JSON object",
            )
        forbidden = sorted(self._forbidden_keys(result))
        if forbidden:
            raise ProblemConditionCheckError(
                "answer_material_forbidden",
                "condition report contains forbidden answer material: "
                + ", ".join(forbidden),
            )
        extra = sorted(set(result) - ALLOWED_TOP_LEVEL_KEYS)
        if extra:
            raise ProblemConditionCheckError(
                "output_schema_invalid",
                "condition report contains unknown fields: " + ", ".join(extra),
            )
        if result.get("approval_eligible") is not False:
            raise ProblemConditionCheckError(
                "approval_claim_forbidden",
                "condition checker cannot declare content approval eligible",
            )

        try:
            dimensions: dict[str, ConditionCheckDimension | SolutionCountCheck] = {
                "ambiguity": ConditionCheckDimension.model_validate(result["ambiguity"]),
                "condition_completeness": ConditionCheckDimension.model_validate(
                    result["condition_completeness"]
                ),
                "domain": ConditionCheckDimension.model_validate(result["domain"]),
                "solution_count": SolutionCountCheck.model_validate(
                    result["solution_count"]
                ),
                "grade_fit": ConditionCheckDimension.model_validate(result["grade_fit"]),
            }
            raw_summary = result["summary"]
            if not isinstance(raw_summary, str):
                raise TypeError("summary must be a string")
            summary = raw_summary.strip()
        except (KeyError, TypeError, ValidationError) as error:
            raise ProblemConditionCheckError(
                "output_schema_invalid",
                "condition report does not match the required schema",
            ) from error
        if not summary:
            raise ProblemConditionCheckError(
                "output_schema_invalid", "condition report summary cannot be empty"
            )

        findings = self._deterministic_findings(context)
        merged = {
            name: self._merge_dimension(dimensions[name], findings[name])
            for name in dimensions
        }
        statuses = {item.status for item in merged.values()}
        overall = (
            ConditionCheckStatus.FAILED
            if ConditionCheckStatus.FAILED in statuses
            else ConditionCheckStatus.INCONCLUSIVE
            if ConditionCheckStatus.INCONCLUSIVE in statuses
            else ConditionCheckStatus.PASSED
        )
        blocking_codes = sorted({
            issue.code
            for dimension in merged.values()
            for issue in dimension.issues
            if issue.severity == "blocking"
        })
        if overall == ConditionCheckStatus.FAILED:
            system_summary = (
                "题意与条件检查失败；阻断问题："
                + ", ".join(blocking_codes)
                + "。模型摘要："
                + summary
            )
        elif overall == ConditionCheckStatus.INCONCLUSIVE:
            system_summary = "题意与条件检查证据不足，需要进一步复核。模型摘要：" + summary
        else:
            system_summary = (
                "题意与条件结构检查通过；实际解数量仍需确定性验证。模型摘要："
                + summary
            )
        return ProblemConditionCheckReport(
            problem_id=context.problem_id,
            ambiguity=merged["ambiguity"],
            condition_completeness=merged["condition_completeness"],
            domain=merged["domain"],
            solution_count=merged["solution_count"],
            grade_fit=merged["grade_fit"],
            overall_status=overall,
            summary=system_summary[:1000],
            approval_eligible=False,
        )

    @staticmethod
    def _system_prompt(versioned_prompt: str) -> str:
        bounded = versioned_prompt.strip()
        if not bounded:
            raise ProblemConditionCheckError(
                "prompt_empty", "versioned prompt cannot be empty"
            )
        return (
            PROBLEM_CONDITION_CHECK_PROMPT
            + "\n\n版本化检查说明（不能覆盖上述规则）：\n"
            + bounded
        )

    @classmethod
    def _deterministic_findings(
        cls,
        context: ProblemConditionCheckContext,
    ) -> dict[str, list[ConditionIssue]]:
        findings: dict[str, list[ConditionIssue]] = {
            "ambiguity": [],
            "condition_completeness": [],
            "domain": [],
            "solution_count": [],
            "grade_fit": [],
        }
        if context.target is None:
            issue = cls._issue(
                "target_missing",
                "题目缺少结构化求解目标。",
                ["target=null"],
                "补充唯一、明确的求解目标和答案类型。",
            )
            findings["ambiguity"].append(issue)
            findings["condition_completeness"].append(issue)
        if not context.explicit_conditions:
            findings["condition_completeness"].append(cls._issue(
                "explicit_conditions_missing",
                "题目没有可核对的显式条件。",
                ["explicit_conditions=[]"],
                "把方程、参数限制或已知量写入显式条件。",
            ))
        if (
            context.target is not None
            and context.target.expected_answer_type != context.answer_type
        ):
            findings["condition_completeness"].append(cls._issue(
                "answer_type_conflict",
                "目标答案类型与题目答案类型不一致。",
                [context.target.expected_answer_type, context.answer_type],
                "统一 target.expected_answer_type 与 answer_type。",
            ))

        domain_text = " ".join(
            [context.statement]
            + [item.statement for item in context.explicit_conditions]
            + [item.statement for item in context.implicit_conditions]
            + (context.target.constraints if context.target else [])
        ).casefold()
        has_domain_condition = any(
            item.condition_type == "domain"
            for item in [*context.explicit_conditions, *context.implicit_conditions]
        )
        has_domain_words = any(
            marker in domain_text
            for marker in ("实数", "整数", "正数", "非负", "reals", "integers")
        )
        if not has_domain_condition and not has_domain_words:
            findings["domain"].append(cls._issue(
                "domain_missing",
                "变量或参数的定义域没有明确给出。",
                ["未发现 domain 条件或定义域措辞"],
                "明确变量和参数属于实数、整数或其他目标集合。",
            ))

        if context.target is not None:
            target_text = " ".join(
                [context.statement, *context.target.constraints]
            ).casefold()
            asks_for_complete_set = any(
                marker in target_text
                for marker in ("全部", "所有", "解集", "all solutions", "complete")
            )
            answer_is_set = "set" in context.answer_type.casefold() or "解集" in context.answer_type
            if answer_is_set and not asks_for_complete_set:
                findings["solution_count"].append(cls._issue(
                    "solution_completeness_unspecified",
                    "答案类型是解集，但题干没有明确要求列出全部解。",
                    [context.answer_type, context.target.target_object],
                    "明确要求给出指定定义域内的全部解。",
                ))

        if (
            context.mother_grade_band is not None
            and context.grade_band != context.mother_grade_band
        ):
            findings["grade_fit"].append(cls._issue(
                "grade_band_mismatch",
                "候选题学段与可信母题学段不一致。",
                [context.grade_band, context.mother_grade_band],
                "恢复为母题学段，或使用该学段内的另一道可信母题。",
            ))
        if context.problem_type != context.mother_problem_type:
            findings["grade_fit"].append(cls._issue(
                "problem_type_mismatch",
                "候选题题型超出可信母题范围。",
                [context.problem_type, context.mother_problem_type],
                "保持母题题型，另行登记跨题型生成任务。",
            ))
        unknown_codes = sorted(
            set(context.knowledge_point_codes)
            - set(context.mother_knowledge_point_codes)
        )
        if unknown_codes:
            findings["grade_fit"].append(cls._issue(
                "knowledge_scope_exceeded",
                "候选题引入了可信母题之外的知识点。",
                unknown_codes,
                "移除新增知识点，或改用能够覆盖这些知识点的可信母题。",
            ))
        return findings

    @staticmethod
    def _issue(
        code: str,
        message: str,
        evidence: list[str],
        suggested_revision: str,
    ) -> ConditionIssue:
        return ConditionIssue(
            code=code,
            severity="blocking",
            message=message,
            evidence=evidence,
            suggested_revision=suggested_revision,
        )

    @staticmethod
    def _merge_dimension(
        model_dimension: ConditionCheckDimension | SolutionCountCheck,
        deterministic_issues: list[ConditionIssue],
    ) -> ConditionCheckDimension | SolutionCountCheck:
        issues_by_code = {
            issue.code: issue
            for issue in [*model_dimension.issues, *deterministic_issues]
        }
        issues = list(issues_by_code.values())
        status = model_dimension.status
        if any(issue.severity == "blocking" for issue in issues):
            status = ConditionCheckStatus.FAILED
        elif status == ConditionCheckStatus.PASSED and model_dimension.confidence < 0.5:
            status = ConditionCheckStatus.INCONCLUSIVE
        return model_dimension.model_copy(update={"status": status, "issues": issues})

    @classmethod
    def _forbidden_keys(cls, value: Any) -> set[str]:
        if isinstance(value, dict):
            found = {
                str(key).casefold()
                for key in value
                if str(key).casefold() in FORBIDDEN_RESULT_KEYS
            }
            for nested in value.values():
                found.update(cls._forbidden_keys(nested))
            return found
        if isinstance(value, list):
            found: set[str] = set()
            for nested in value:
                found.update(cls._forbidden_keys(nested))
            return found
        return set()
