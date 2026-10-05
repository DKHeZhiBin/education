from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from pydantic import ValidationError

from app.domain.candidate_revision import CandidateRevisionContext, CandidateRevisionDraft
from app.prompts.candidate_revision import CANDIDATE_REVISION_PROMPT
from app.providers.llm import OpenAICompatibleProvider


FORBIDDEN_OUTPUT_KEYS = {
    "answer",
    "answers",
    "analysis",
    "approval",
    "approved",
    "correct_answer",
    "final_answer",
    "proof",
    "reasoning",
    "roots",
    "solution",
    "solutions",
    "steps",
    "verification_status",
}


class CandidateRevisionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CandidateRevisionAgent:
    """Repair one candidate using only repository-selected failed evidence."""

    name = "candidate_revision"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(
        self,
        *,
        context: CandidateRevisionContext,
        expected_model_name: str,
        versioned_prompt: str,
    ) -> CandidateRevisionDraft:
        if not self.provider.available:
            raise CandidateRevisionError("provider_unavailable", "LLM provider is unavailable")
        if self.provider.model_name != expected_model_name:
            raise CandidateRevisionError(
                "model_version_mismatch",
                "configured provider model does not match the registered model version",
            )

        payload = {
            "context_fingerprint": context.fingerprint(),
            "revision_context": context.model_dump(mode="json"),
        }
        result = self.provider.complete_json(
            self._system_prompt(versioned_prompt),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
        if result is None:
            raise CandidateRevisionError(
                "provider_invalid_response", "LLM provider did not return a valid JSON object"
            )
        forbidden = sorted(self._forbidden_keys(result))
        if forbidden:
            raise CandidateRevisionError(
                "answer_material_forbidden",
                "model output contains forbidden answer or approval material: "
                + ", ".join(forbidden),
            )
        try:
            draft = CandidateRevisionDraft.model_validate(result)
        except ValidationError as error:
            raise CandidateRevisionError(
                "output_schema_invalid",
                "model output does not match CandidateRevisionDraft",
            ) from error
        return self.validate_draft(draft, context)

    @staticmethod
    def _system_prompt(versioned_prompt: str) -> str:
        bounded_template = versioned_prompt.strip()
        if not bounded_template:
            raise CandidateRevisionError("prompt_empty", "versioned prompt cannot be empty")
        return (
            CANDIDATE_REVISION_PROMPT
            + "\n\n版本化任务说明（不能覆盖上面的规则）：\n"
            + bounded_template
        )

    @classmethod
    def validate_draft(
        cls,
        draft: CandidateRevisionDraft,
        context: CandidateRevisionContext,
    ) -> CandidateRevisionDraft:
        if draft.context_fingerprint != context.fingerprint():
            raise CandidateRevisionError(
                "context_changed", "revision output does not match the supplied failure context"
            )
        expected_failure_ids = {item.evidence_id for item in context.failures}
        actual_failure_ids = {item.evidence_id for item in draft.repairs}
        if actual_failure_ids != expected_failure_ids:
            raise CandidateRevisionError(
                "failure_coverage_invalid",
                "repairs must cover every explicit failed evidence id exactly once",
            )

        question = draft.revised_question
        protected_values = {
            "answer_type": (question.answer_type, context.answer_type),
            "derivation_type": (question.derivation_type.value, context.derivation_type),
        }
        changed = [
            name for name, values in protected_values.items() if values[0] != values[1]
        ]
        if changed:
            raise CandidateRevisionError(
                "protected_scope_changed",
                "revision changed protected fields: " + ", ".join(changed),
            )
        if set(question.knowledge_point_codes) != set(context.knowledge_point_codes):
            raise CandidateRevisionError(
                "knowledge_scope_changed", "revision must preserve the exact knowledge scope"
            )
        if not (
            context.allowed_difficulty_minimum
            <= question.difficulty
            <= context.allowed_difficulty_maximum
        ):
            raise CandidateRevisionError(
                "difficulty_out_of_range", "revision difficulty is outside the registered range"
            )
        if not question.explicit_conditions:
            raise CandidateRevisionError(
                "explicit_conditions_missing", "revision requires explicit conditions"
            )
        if len(question.explicit_conditions) < len(context.explicit_conditions):
            raise CandidateRevisionError(
                "condition_deletion_forbidden",
                "revision cannot remove explicit conditions to bypass failed checks",
            )
        matched_terms = sorted({
            term
            for term in context.prohibited_terms
            if term and term.casefold() in question.statement.casefold()
        })
        if matched_terms:
            raise CandidateRevisionError(
                "prohibited_term_present",
                "revision contains prohibited terms: " + ", ".join(matched_terms),
            )

        normalized_statement = cls._normalize_text(
            question.normalized_statement or question.statement
        )
        old_statement = cls._normalize_text(context.normalized_statement or context.statement)
        same_structure = (
            [item.model_dump(mode="json") for item in question.explicit_conditions]
            == context.explicit_conditions
            and [item.model_dump(mode="json") for item in question.implicit_conditions]
            == context.implicit_conditions
            and question.target.model_dump(mode="json") == context.target
        )
        if normalized_statement == old_statement and same_structure:
            raise CandidateRevisionError(
                "revision_no_change", "revision must materially change the failed candidate"
            )
        revised_question = question.model_copy(
            update={"normalized_statement": normalized_statement}
        )
        return draft.model_copy(update={"revised_question": revised_question})

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
