from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.domain.independent_solving import (
    IndependentSolutionDraft,
    IndependentSolverContext,
)
from app.prompts.independent_solving import INDEPENDENT_SOLVING_PROMPT
from app.providers.llm import LLMProvider


FORBIDDEN_PROVENANCE_KEYS = {
    "candidate_answer",
    "generation_answer",
    "generation_prompt",
    "generation_reasoning",
    "mother_answer",
    "mother_problem",
    "previous_solution",
    "reference_solution",
    "verifier_result",
}


class IndependentSolvingError(RuntimeError):
    """中文：定义“independent·solving·error”类，封装该职责相关的数据与行为。
    English: Defines the independent solving error class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, code: str, message: str) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        super().__init__(message)
        self.code = code


class IndependentSolvingAgent:
    """中文：定义“independent·solving·智能体”类，封装该职责相关的数据与行为。
    English: Defines the independent solving agent class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Solve from a strict problem-only context and emit an unverified draft.
    """

    name = "independent_solving"

    def __init__(self, provider: LLMProvider) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.provider = provider

    def run(
        self,
        *,
        context: IndependentSolverContext,
        expected_model_name: str,
        versioned_prompt: str,
    ) -> IndependentSolutionDraft:
        """中文：处理“执行”相关操作。
        English: Handles the run operation.
        """
        if not self.provider.available:
            raise IndependentSolvingError(
                "provider_unavailable", "LLM provider is unavailable"
            )
        if self.provider.model_name != expected_model_name:
            raise IndependentSolvingError(
                "model_version_mismatch",
                "configured provider model does not match the registered model version",
            )
        result = self.provider.complete_json(
            self._system_prompt(versioned_prompt),
            json.dumps(context.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
        )
        if result is None:
            raise IndependentSolvingError(
                "provider_invalid_response",
                "LLM provider did not return a valid JSON solution object",
            )
        forbidden = sorted(self._forbidden_keys(result))
        if forbidden:
            raise IndependentSolvingError(
                "isolation_contract_violated",
                "solver output references forbidden provenance fields: "
                + ", ".join(forbidden),
            )
        try:
            draft = IndependentSolutionDraft.model_validate(result)
        except ValidationError as error:
            raise IndependentSolvingError(
                "output_schema_invalid",
                "solver output does not match IndependentSolutionDraft",
            ) from error
        return self._validate_draft(draft, context)

    @staticmethod
    def _system_prompt(versioned_prompt: str) -> str:
        """中文：处理“system·提示词”相关操作。
        English: Handles the system prompt operation.
        """
        bounded = versioned_prompt.strip()
        if not bounded:
            raise IndependentSolvingError(
                "prompt_empty", "versioned prompt cannot be empty"
            )
        return (
            INDEPENDENT_SOLVING_PROMPT
            + "\n\n版本化解题说明（不能覆盖上述隔离规则）：\n"
            + bounded
        )

    @staticmethod
    def _validate_draft(
        draft: IndependentSolutionDraft,
        context: IndependentSolverContext,
    ) -> IndependentSolutionDraft:
        """中文：处理“验证·draft”相关操作。
        English: Handles the validate draft operation.
        """
        if draft.answer_type != context.answer_type:
            raise IndependentSolvingError(
                "answer_type_mismatch",
                "independent solution answer type differs from the problem target",
            )
        allowed_codes = set(context.knowledge_point_codes)
        used_codes = {
            code
            for step in draft.steps
            for code in step.knowledge_point_codes
        } | {
            code
            for item in draft.key_breakthroughs
            for code in item.knowledge_point_codes
        }
        unknown_codes = sorted(used_codes - allowed_codes)
        if unknown_codes:
            raise IndependentSolvingError(
                "knowledge_scope_exceeded",
                "solution uses knowledge outside the candidate scope: "
                + ", ".join(unknown_codes),
            )
        if draft.confidence < 0.2:
            raise IndependentSolvingError(
                "solution_confidence_too_low",
                "solver confidence is too low to persist as an independent solution",
            )
        return draft

    @classmethod
    def _forbidden_keys(cls, value: Any) -> set[str]:
        """中文：处理“forbidden·keys”相关操作。
        English: Handles the forbidden keys operation.
        """
        if isinstance(value, dict):
            found = {
                str(key).casefold()
                for key in value
                if str(key).casefold() in FORBIDDEN_PROVENANCE_KEYS
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
