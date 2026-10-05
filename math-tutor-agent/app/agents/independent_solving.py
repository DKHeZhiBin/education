from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.domain.independent_solving import (
    IndependentSolutionDraft,
    IndependentSolverContext,
)
from app.prompts.independent_solving import INDEPENDENT_SOLVING_PROMPT
from app.providers.llm import OpenAICompatibleProvider


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
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class IndependentSolvingAgent:
    """Solve from a strict problem-only context and emit an unverified draft."""

    name = "independent_solving"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(
        self,
        *,
        context: IndependentSolverContext,
        expected_model_name: str,
        versioned_prompt: str,
    ) -> IndependentSolutionDraft:
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
