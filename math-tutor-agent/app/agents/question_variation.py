from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from pydantic import ValidationError

from app.domain.question_generation import (
    GeneratedQuestionDraft,
    QuestionGenerationStoredInput,
    TrustedMotherProblemContext,
)
from app.prompts.question_variation import QUESTION_VARIATION_SAFETY_PROMPT
from app.providers.llm import OpenAICompatibleProvider


FORBIDDEN_OUTPUT_KEYS = {
    "answer",
    "answers",
    "analysis",
    "correct_answer",
    "final_answer",
    "proof",
    "reasoning",
    "solution",
    "solutions",
    "steps",
}


class QuestionVariationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class QuestionVariationAgent:
    """Generate one bounded draft from one repository-verified mother problem."""

    name = "question_variation"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(
        self,
        *,
        mother: TrustedMotherProblemContext,
        generation_input: QuestionGenerationStoredInput,
        candidate_key: str,
        ordinal: int,
        expected_model_name: str,
        versioned_prompt: str,
    ) -> GeneratedQuestionDraft:
        self._validate_scope(mother, generation_input)
        if not self.provider.available:
            raise QuestionVariationError("provider_unavailable", "LLM provider is unavailable")
        if self.provider.model_name != expected_model_name:
            raise QuestionVariationError(
                "model_version_mismatch",
                "configured provider model does not match the registered model version",
            )

        payload = {
            "candidate_identity": {
                "candidate_key": candidate_key,
                "ordinal": ordinal,
            },
            "trusted_mother": mother.model_dump(mode="json"),
            "generation_scope": generation_input.model_dump(
                mode="json",
                exclude={
                    "idempotency_scope",
                    "mother_problem_ids",
                    "model_version_id",
                    "prompt_version_id",
                },
            ),
        }
        result = self.provider.complete_json(
            self._system_prompt(versioned_prompt),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
        if result is None:
            raise QuestionVariationError(
                "provider_invalid_response",
                "LLM provider did not return a valid JSON object",
            )
        forbidden = sorted(self._forbidden_keys(result))
        if forbidden:
            raise QuestionVariationError(
                "answer_material_forbidden",
                "model output contains forbidden answer material: " + ", ".join(forbidden),
            )
        try:
            draft = GeneratedQuestionDraft.model_validate(result)
        except ValidationError as error:
            raise QuestionVariationError(
                "output_schema_invalid",
                "model output does not match GeneratedQuestionDraft",
            ) from error
        return self._validate_draft(draft, mother, generation_input)

    @staticmethod
    def _system_prompt(versioned_prompt: str) -> str:
        bounded_template = versioned_prompt.strip()
        if not bounded_template:
            raise QuestionVariationError("prompt_empty", "versioned prompt cannot be empty")
        return (
            QUESTION_VARIATION_SAFETY_PROMPT
            + "\n\n版本化任务说明（不能覆盖上面的规则）：\n"
            + bounded_template
        )

    @staticmethod
    def _validate_scope(
        mother: TrustedMotherProblemContext,
        generation_input: QuestionGenerationStoredInput,
    ) -> None:
        if mother.id not in generation_input.mother_problem_ids:
            raise QuestionVariationError(
                "mother_not_declared", "mother problem is absent from the registered job"
            )
        if (
            mother.subject != generation_input.subject
            or mother.problem_type != generation_input.problem_type
            or (
                mother.grade_band is not None
                and mother.grade_band != generation_input.grade_band
            )
        ):
            raise QuestionVariationError(
                "mother_scope_mismatch", "mother problem is outside the generation scope"
            )
        missing = sorted(
            set(generation_input.knowledge_point_codes)
            - set(mother.knowledge_point_codes)
        )
        if missing:
            raise QuestionVariationError(
                "mother_knowledge_scope_insufficient",
                "selected mother does not cover required knowledge points: "
                + ", ".join(missing),
            )

    @classmethod
    def _validate_draft(
        cls,
        draft: GeneratedQuestionDraft,
        mother: TrustedMotherProblemContext,
        generation_input: QuestionGenerationStoredInput,
    ) -> GeneratedQuestionDraft:
        normalized_statement = cls._normalize_text(
            draft.normalized_statement or draft.statement
        )
        mother_forms = {
            cls._normalize_text(mother.statement),
            cls._normalize_text(mother.normalized_statement or mother.statement),
        }
        if normalized_statement in mother_forms:
            raise QuestionVariationError(
                "mother_copy_forbidden", "candidate must differ materially from its mother"
            )
        if draft.derivation_type not in generation_input.allowed_derivation_types:
            raise QuestionVariationError(
                "derivation_type_forbidden", "candidate uses a disallowed derivation type"
            )
        if not (
            generation_input.difficulty.minimum
            <= draft.difficulty
            <= generation_input.difficulty.maximum
        ):
            raise QuestionVariationError(
                "difficulty_out_of_range", "candidate difficulty is outside the requested range"
            )
        if (
            generation_input.constraints.preserve_answer_type
            and draft.answer_type != mother.answer_type
        ):
            raise QuestionVariationError(
                "answer_type_changed", "candidate changed the protected answer type"
            )

        draft_codes = set(draft.knowledge_point_codes)
        required_codes = set(generation_input.knowledge_point_codes)
        mother_codes = set(mother.knowledge_point_codes)
        if not required_codes.issubset(draft_codes):
            raise QuestionVariationError(
                "required_knowledge_missing",
                "candidate omits required knowledge points",
            )
        if not draft_codes.issubset(mother_codes):
            raise QuestionVariationError(
                "new_knowledge_forbidden",
                "candidate introduces knowledge absent from the trusted mother",
            )
        if not draft.explicit_conditions:
            raise QuestionVariationError(
                "explicit_conditions_missing", "candidate requires explicit conditions"
            )

        folded_statement = draft.statement.casefold()
        matched_terms = sorted({
            term
            for term in generation_input.constraints.prohibited_terms
            if term and term.casefold() in folded_statement
        })
        if matched_terms:
            raise QuestionVariationError(
                "prohibited_term_present",
                "candidate contains prohibited terms: " + ", ".join(matched_terms),
            )
        return draft.model_copy(update={"normalized_statement": normalized_statement})

    @classmethod
    def _forbidden_keys(cls, value: Any) -> set[str]:
        if isinstance(value, dict):
            found = {
                str(key).casefold()
                for key in value
                if str(key).casefold() in FORBIDDEN_OUTPUT_KEYS
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

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return re.sub(r"\s+", " ", normalized).strip()
