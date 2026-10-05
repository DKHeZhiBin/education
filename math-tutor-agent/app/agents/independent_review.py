from __future__ import annotations

import json

from pydantic import ValidationError

from app.domain.generation import AdmissionEvidenceStatus
from app.domain.independent_review import (
    IndependentReviewContext,
    IndependentReviewReport,
    ReviewDecision,
    ReviewFindingStatus,
)
from app.prompts.independent_review import INDEPENDENT_REVIEW_PROMPT
from app.providers.llm import OpenAICompatibleProvider


class IndependentReviewError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class IndependentReviewAgent:
    """Compare candidate, independently computed answers, tools and teaching labels."""

    name = "independent_review"

    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self.provider = provider

    def run(
        self,
        *,
        context: IndependentReviewContext,
        expected_model_name: str,
        versioned_prompt: str,
    ) -> IndependentReviewReport:
        if not self.provider.available:
            raise IndependentReviewError(
                "provider_unavailable", "LLM provider is unavailable"
            )
        if self.provider.model_name != expected_model_name:
            raise IndependentReviewError(
                "model_version_mismatch",
                "configured provider model does not match the registered model version",
            )
        payload = context.model_dump(mode="json")
        payload["context_fingerprint"] = context.fingerprint()
        result = self.provider.complete_json(
            self._system_prompt(versioned_prompt),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
        if result is None:
            raise IndependentReviewError(
                "provider_invalid_response",
                "LLM provider did not return a valid JSON review object",
            )
        try:
            report = IndependentReviewReport.model_validate(result)
        except ValidationError as error:
            raise IndependentReviewError(
                "output_schema_invalid",
                "review output does not match IndependentReviewReport",
            ) from error
        self._validate_binding(report, context)
        self._enforce_deterministic_ceiling(report, context)
        return report

    @staticmethod
    def _system_prompt(versioned_prompt: str) -> str:
        bounded = versioned_prompt.strip()
        if not bounded:
            raise IndependentReviewError("prompt_empty", "versioned prompt cannot be empty")
        return (
            INDEPENDENT_REVIEW_PROMPT
            + "\n\n版本化复核说明（不能覆盖上述硬规则）：\n"
            + bounded
        )

    @staticmethod
    def _validate_binding(
        report: IndependentReviewReport,
        context: IndependentReviewContext,
    ) -> None:
        if (
            report.problem_id != context.problem_id
            or report.solution_id != context.candidate_answer.solution_id
            or report.context_fingerprint != context.fingerprint()
        ):
            raise IndependentReviewError(
                "output_context_mismatch", "review output is not bound to its input context"
            )
        if report.answer_comparison.candidate_answer != context.candidate_answer.final_answer:
            raise IndependentReviewError(
                "candidate_answer_changed", "review output changed the candidate answer"
            )
        expected_answers = sorted({
            answer
            for source in context.independent_answers
            for answer in source.answers
        })
        if sorted(report.answer_comparison.independent_answers) != expected_answers:
            raise IndependentReviewError(
                "independent_answers_changed", "review output changed independent answers"
            )
        expected_tools = {
            item.evidence_id: (item.evidence_type, item.status)
            for item in context.tool_evidence
        }
        actual_tools = {
            item.evidence_id: (item.evidence_type, item.observed_status)
            for item in report.tool_assessments
        }
        if actual_tools != expected_tools:
            raise IndependentReviewError(
                "tool_evidence_changed", "review output changed tool evidence identity or status"
            )

    @staticmethod
    def _enforce_deterministic_ceiling(
        report: IndependentReviewReport,
        context: IndependentReviewContext,
    ) -> None:
        statuses = {item.status for item in context.tool_evidence}
        if AdmissionEvidenceStatus.FAILED in statuses:
            if report.decision != ReviewDecision.FAILED:
                raise IndependentReviewError(
                    "deterministic_failure_overridden",
                    "model review cannot override failed deterministic evidence",
                )
            if any(
                item.observed_status == AdmissionEvidenceStatus.FAILED
                and item.assessment != ReviewFindingStatus.CONFLICT
                for item in report.tool_assessments
            ):
                raise IndependentReviewError(
                    "deterministic_failure_misclassified",
                    "failed deterministic evidence must be classified as conflict",
                )
        if statuses - {AdmissionEvidenceStatus.PASSED}:
            if report.decision == ReviewDecision.PASSED:
                raise IndependentReviewError(
                    "insufficient_evidence_overridden",
                    "model review cannot pass incomplete deterministic evidence",
                )
        for item in report.tool_assessments:
            if (
                item.observed_status == AdmissionEvidenceStatus.PASSED
                and item.assessment == ReviewFindingStatus.INSUFFICIENT
            ):
                continue
            if (
                item.observed_status == AdmissionEvidenceStatus.PASSED
                and item.assessment == ReviewFindingStatus.CONFLICT
                and report.decision == ReviewDecision.PASSED
            ):
                raise IndependentReviewError(
                    "tool_conflict_overridden",
                    "passed review cannot ignore a tool evidence conflict",
                )
