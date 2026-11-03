from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.generation import GenerationBatchStatus
from app.domain.candidate_validation import CandidateValidationBatchResult
from app.domain.knowledge import (
    ImplicitProblemCondition,
    ProblemCondition,
    ProblemContentStatus,
    ProblemDerivationType,
    ProblemDifficultyFactor,
    ProblemTarget,
)
from app.core.product_scope import MVP_GRADE_BAND, is_mvp_scope


class QuestionGenerationStopReason(StrEnum):
    """中文：定义“问题·生成·停止·reason”类，封装该职责相关的数据与行为。
    English: Defines the question generation stop reason class and encapsulates data and behavior for that responsibility.
    """
    COMPLETED = "completed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    PERSISTENCE_FAILED = "persistence_failed"
    INTERNAL_ERROR = "internal_error"


class CandidateGenerationOutcome(StrEnum):
    """中文：定义“候选内容·生成·outcome”类，封装该职责相关的数据与行为。
    English: Defines the candidate generation outcome class and encapsulates data and behavior for that responsibility.
    """
    CANDIDATE_CREATED = "candidate_created"
    GENERATION_FAILED = "generation_failed"
    SKIPPED = "skipped"


MotherProblemId = Annotated[str, Field(min_length=1, max_length=36)]
KnowledgeCode = Annotated[str, Field(min_length=1, max_length=80)]
ErrorSummary = Annotated[str, Field(min_length=1, max_length=1000)]


class QuestionGenerationBudget(BaseModel):
    """中文：定义“问题·生成·budget”类，封装该职责相关的数据与行为。
    English: Defines the question generation budget class and encapsulates data and behavior for that responsibility.
    """
    max_execution_attempts: int = Field(default=3, ge=1, le=10)
    max_model_calls: int = Field(default=20, ge=1, le=10_000)
    max_revision_rounds: int = Field(default=2, ge=0, le=2)
    max_input_tokens: int = Field(default=100_000, ge=1, le=100_000_000)
    max_output_tokens: int = Field(default=50_000, ge=1, le=100_000_000)
    max_total_tokens: int = Field(default=150_000, ge=1, le=200_000_000)
    max_cost_minor_units: int = Field(default=10_000, ge=1, le=1_000_000_000)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    max_duration_seconds: int = Field(default=900, ge=1, le=86_400)
    max_candidates: int = Field(default=100, ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_token_limits(self) -> QuestionGenerationBudget:
        """中文：处理“验证·令牌·limits”相关操作。
        English: Handles the validate token limits operation.
        """
        if self.max_input_tokens > self.max_total_tokens:
            raise ValueError("max_input_tokens cannot exceed max_total_tokens")
        if self.max_output_tokens > self.max_total_tokens:
            raise ValueError("max_output_tokens cannot exceed max_total_tokens")
        return self


class QuestionGenerationUsage(BaseModel):
    """中文：定义“问题·生成·usage”类，封装该职责相关的数据与行为。
    English: Defines the question generation usage class and encapsulates data and behavior for that responsibility.
    """
    model_calls: int = Field(default=0, ge=0)
    revision_rounds: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_minor_units: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    candidates_attempted: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_total_tokens(self) -> QuestionGenerationUsage:
        """中文：处理“验证·total·tokens”相关操作。
        English: Handles the validate total tokens operation.
        """
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        return self

    def exhausted_reasons(self, budget: QuestionGenerationBudget) -> list[str]:
        """中文：处理“exhausted·reasons”相关操作。
        English: Handles the exhausted reasons operation.
        """
        checks = {
            "model_calls": self.model_calls >= budget.max_model_calls,
            "input_tokens": self.input_tokens >= budget.max_input_tokens,
            "output_tokens": self.output_tokens >= budget.max_output_tokens,
            "total_tokens": self.total_tokens >= budget.max_total_tokens,
            "cost": self.cost_minor_units >= budget.max_cost_minor_units,
            "duration": self.duration_ms >= budget.max_duration_seconds * 1000,
            "candidates": self.candidates_attempted >= budget.max_candidates,
        }
        return [name for name, exhausted in checks.items() if exhausted]

    def exceeded_reasons(self, budget: QuestionGenerationBudget) -> list[str]:
        """中文：处理“exceeded·reasons”相关操作。
        English: Handles the exceeded reasons operation.
        """
        checks = {
            "model_calls": self.model_calls > budget.max_model_calls,
            "revision_rounds": self.revision_rounds > budget.max_revision_rounds,
            "input_tokens": self.input_tokens > budget.max_input_tokens,
            "output_tokens": self.output_tokens > budget.max_output_tokens,
            "total_tokens": self.total_tokens > budget.max_total_tokens,
            "cost": self.cost_minor_units > budget.max_cost_minor_units,
            "duration": self.duration_ms > budget.max_duration_seconds * 1000,
            "candidates": self.candidates_attempted > budget.max_candidates,
        }
        return [name for name, exceeded in checks.items() if exceeded]

    def can_reserve(
        self,
        budget: QuestionGenerationBudget,
        *,
        model_calls: int = 0,
        revision_rounds: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_minor_units: int = 0,
        duration_ms: int = 0,
        candidates: int = 0,
    ) -> bool:
        """中文：处理“can·reserve”相关操作。
        English: Handles the can reserve operation.
        """
        values = (
            model_calls,
            revision_rounds,
            input_tokens,
            output_tokens,
            cost_minor_units,
            duration_ms,
            candidates,
        )
        if any(value < 0 for value in values):
            raise ValueError("budget reservation values cannot be negative")
        return all((
            self.model_calls + model_calls <= budget.max_model_calls,
            self.revision_rounds + revision_rounds <= budget.max_revision_rounds,
            self.input_tokens + input_tokens <= budget.max_input_tokens,
            self.output_tokens + output_tokens <= budget.max_output_tokens,
            self.total_tokens + input_tokens + output_tokens <= budget.max_total_tokens,
            self.cost_minor_units + cost_minor_units <= budget.max_cost_minor_units,
            self.duration_ms + duration_ms <= budget.max_duration_seconds * 1000,
            self.candidates_attempted + candidates <= budget.max_candidates,
        ))


class DifficultyRange(BaseModel):
    """中文：定义“difficulty·range”类，封装该职责相关的数据与行为。
    English: Defines the difficulty range class and encapsulates data and behavior for that responsibility.
    """
    minimum: int = Field(default=1, ge=1, le=5)
    maximum: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def validate_range(self) -> DifficultyRange:
        """中文：处理“验证·range”相关操作。
        English: Handles the validate range operation.
        """
        if self.minimum > self.maximum:
            raise ValueError("difficulty minimum cannot exceed maximum")
        return self


class QuestionGenerationConstraints(BaseModel):
    """中文：定义“问题·生成·constraints”类，封装该职责相关的数据与行为。
    English: Defines the question generation constraints class and encapsulates data and behavior for that responsibility.
    """
    domains: list[str] = Field(default_factory=lambda: ["reals"], min_length=1)
    preserve_answer_type: bool = True
    preserve_solution_count: bool = False
    require_unique_answer: bool = False
    require_programmatic_verification: bool = True
    allow_new_knowledge_points: bool = False
    prohibited_terms: list[str] = Field(default_factory=list, max_length=100)
    additional_instructions: str | None = Field(default=None, max_length=2000)


class QuestionGenerationSpec(BaseModel):
    """中文：定义“问题·生成·spec”类，封装该职责相关的数据与行为。
    English: Defines the question generation spec class and encapsulates data and behavior for that responsibility.
    """
    schema_version: Literal["1.0"] = "1.0"
    mother_problem_ids: list[MotherProblemId] = Field(min_length=1, max_length=100)
    requested_count: int = Field(ge=1, le=1000)
    subject: str = Field(default="math", min_length=1, max_length=32)
    grade_band: str = Field(min_length=1, max_length=32)
    topic_code: str = Field(min_length=1, max_length=80)
    problem_type: str = Field(min_length=1, max_length=64)
    knowledge_point_codes: list[KnowledgeCode] = Field(min_length=1, max_length=100)
    capability_point_codes: list[KnowledgeCode] = Field(default_factory=list, max_length=100)
    allowed_derivation_types: list[ProblemDerivationType] = Field(min_length=1)
    difficulty: DifficultyRange = Field(default_factory=DifficultyRange)
    language: str = Field(default="zh-CN", min_length=2, max_length=16)
    model_version_id: str = Field(min_length=1)
    prompt_version_id: str = Field(min_length=1)
    verifier_profile: str = Field(min_length=1, max_length=100)
    auto_validate: bool = False
    output_schema_version: str = Field(default="1.0", min_length=1, max_length=32)
    random_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    constraints: QuestionGenerationConstraints = Field(
        default_factory=QuestionGenerationConstraints
    )

    @model_validator(mode="after")
    def validate_spec(self) -> QuestionGenerationSpec:
        """中文：处理“验证·spec”相关操作。
        English: Handles the validate spec operation.
        """
        unique_fields = {
            "mother_problem_ids": self.mother_problem_ids,
            "knowledge_point_codes": self.knowledge_point_codes,
            "capability_point_codes": self.capability_point_codes,
            "allowed_derivation_types": self.allowed_derivation_types,
        }
        for name, values in unique_fields.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique values")
        if self.topic_code not in self.knowledge_point_codes:
            raise ValueError("topic_code must be included in knowledge_point_codes")
        return self


class QuestionGenerationStoredInput(QuestionGenerationSpec):
    """中文：定义“问题·生成·stored·input”类，封装该职责相关的数据与行为。
    English: Defines the question generation stored input class and encapsulates data and behavior for that responsibility.
    """
    idempotency_scope: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._:-]*$",
    )


class TrustedMotherProblemContext(BaseModel):
    """中文：定义“trusted·mother·题目·context”类，封装该职责相关的数据与行为。
    English: Defines the trusted mother problem context class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    The only problem context the variation agent is allowed to read.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=36)
    source_reference_id: str = Field(min_length=1, max_length=36)
    curriculum_version_id: str | None = Field(default=None, max_length=36)
    statement: str = Field(min_length=1, max_length=10_000)
    normalized_statement: str | None = Field(default=None, max_length=10_000)
    subject: str = Field(min_length=1, max_length=32)
    grade_band: str | None = Field(default=None, max_length=32)
    grade_codes: list[str] = Field(default_factory=list)
    problem_type: str = Field(min_length=1, max_length=64)
    content_type: str = Field(default="problem", min_length=1, max_length=40)
    difficulty: int = Field(ge=1, le=5)
    answer_type: str = Field(min_length=1, max_length=64)
    language: str = Field(min_length=2, max_length=16)
    explicit_conditions: list[ProblemCondition] = Field(default_factory=list)
    implicit_conditions: list[ImplicitProblemCondition] = Field(default_factory=list)
    target: ProblemTarget
    difficulty_factors: list[ProblemDifficultyFactor] = Field(default_factory=list)
    knowledge_point_codes: list[KnowledgeCode] = Field(min_length=1)
    content_status: ProblemContentStatus
    trusted_mother: Literal[True]

    @model_validator(mode="after")
    def validate_admission(self) -> TrustedMotherProblemContext:
        """中文：处理“验证·admission”相关操作。
        English: Handles the validate admission operation.
        """
        if self.content_status not in {
            ProblemContentStatus.APPROVED,
            ProblemContentStatus.INDEXED,
        }:
            raise ValueError("trusted mother must be approved or indexed")
        if len(self.knowledge_point_codes) != len(set(self.knowledge_point_codes)):
            raise ValueError("mother knowledge_point_codes must be unique")
        if self.grade_band != MVP_GRADE_BAND and not self.grade_codes:
            raise ValueError("trusted mother must have at least one grade code")
        if len(self.grade_codes) != len(set(self.grade_codes)):
            raise ValueError("mother grade_codes must be unique")
        return self


class QuestionGenerationJobInput(QuestionGenerationSpec):
    """中文：定义“问题·生成·任务·input”类，封装该职责相关的数据与行为。
    English: Defines the question generation job input class and encapsulates data and behavior for that responsibility.
    """
    idempotency_scope: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._:-]*$",
    )
    idempotency_key: str = Field(min_length=8, max_length=128)
    budget: QuestionGenerationBudget = Field(default_factory=QuestionGenerationBudget)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        """中文：处理“验证·idempotency·key”相关操作。
        English: Handles the validate idempotency key operation.
        """
        if value != value.strip():
            raise ValueError("idempotency_key cannot have leading or trailing whitespace")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("idempotency_key cannot contain control characters")
        return value

    @model_validator(mode="after")
    def validate_request_budget(self) -> QuestionGenerationJobInput:
        """中文：处理“验证·请求·budget”相关操作。
        English: Handles the validate request budget operation.
        """
        if not is_mvp_scope(self.subject, self.grade_band):
            raise ValueError("question generation is limited to math/university")
        if self.requested_count > self.budget.max_candidates:
            raise ValueError("requested_count cannot exceed budget.max_candidates")
        required_model_calls = self.requested_count * (4 if self.auto_validate else 1)
        if required_model_calls > self.budget.max_model_calls:
            raise ValueError(
                "max_model_calls must reserve generation plus condition, solving and review calls"
            )
        if self.auto_validate:
            raise ValueError(
                "university-calculus automatic validation is not configured; "
                "set auto_validate=false"
            )
        return self

    def request_hash(self) -> str:
        """中文：处理“请求·hash”相关操作。
        English: Handles the request hash operation.
        """
        payload = self.model_dump(
            mode="json",
            exclude={"idempotency_scope", "idempotency_key"},
        )
        return _canonical_hash(payload)

    def idempotency_key_hash(self) -> str:
        """中文：处理“idempotency·key·hash”相关操作。
        English: Handles the idempotency key hash operation.
        """
        return _canonical_hash({
            "scope": self.idempotency_scope,
            "key": self.idempotency_key,
        })

    def batch_key(self) -> str:
        """中文：处理“批次·key”相关操作。
        English: Handles the batch key operation.
        """
        return f"qgen-{self.idempotency_key_hash()}"

    def persistence_payload(self) -> dict:
        """中文：处理“persistence·payload”相关操作。
        English: Handles the persistence payload operation.
        """
        return self.model_dump(
            mode="json",
            exclude={"idempotency_key", "budget"},
        )


class GeneratedQuestionDraft(BaseModel):
    """中文：定义“generated·问题·draft”类，封装该职责相关的数据与行为。
    English: Defines the generated question draft class and encapsulates data and behavior for that responsibility.
    """
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=10_000)
    normalized_statement: str | None = Field(default=None, max_length=10_000)
    explicit_conditions: list[ProblemCondition] = Field(default_factory=list)
    implicit_conditions: list[ImplicitProblemCondition] = Field(default_factory=list)
    target: ProblemTarget
    difficulty: int = Field(ge=1, le=5)
    difficulty_factors: list[ProblemDifficultyFactor] = Field(default_factory=list)
    answer_type: str = Field(min_length=1, max_length=64)
    knowledge_point_codes: list[str] = Field(min_length=1)
    derivation_type: ProblemDerivationType
    derivation_note: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_structure(self) -> GeneratedQuestionDraft:
        """中文：处理“验证·structure”相关操作。
        English: Handles the validate structure operation.
        """
        if len(self.knowledge_point_codes) != len(set(self.knowledge_point_codes)):
            raise ValueError("knowledge_point_codes must be unique")
        if self.target.expected_answer_type != self.answer_type:
            raise ValueError("target expected_answer_type must match answer_type")
        return self


class QuestionGenerationCandidateResult(BaseModel):
    """中文：定义“问题·生成·候选内容·结果”类，封装该职责相关的数据与行为。
    English: Defines the question generation candidate result class and encapsulates data and behavior for that responsibility.
    """
    ordinal: int = Field(ge=0)
    candidate_key: str = Field(min_length=1, max_length=100)
    mother_problem_id: str
    outcome: CandidateGenerationOutcome
    draft: GeneratedQuestionDraft | None = None
    problem_id: str | None = None
    content_status: ProblemContentStatus | None = None
    failure_code: str | None = Field(default=None, max_length=64)
    failure_message: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_outcome(self) -> QuestionGenerationCandidateResult:
        """中文：处理“验证·outcome”相关操作。
        English: Handles the validate outcome operation.
        """
        if self.outcome == CandidateGenerationOutcome.CANDIDATE_CREATED:
            if (
                self.draft is None
                or self.problem_id is None
                or self.content_status is None
            ):
                raise ValueError(
                    "created candidates require a draft, problem_id and content status"
                )
            if self.failure_code is not None:
                raise ValueError("created candidates cannot have a failure_code")
        else:
            if self.failure_code is None:
                raise ValueError("failed or skipped candidates require a failure_code")
            if (
                self.draft is not None
                or self.problem_id is not None
                or self.content_status is not None
            ):
                raise ValueError("failed or skipped candidates cannot contain persisted content")
        return self


class QuestionGenerationJobOutput(BaseModel):
    """中文：定义“问题·生成·任务·output”类，封装该职责相关的数据与行为。
    English: Defines the question generation job output class and encapsulates data and behavior for that responsibility.
    """
    schema_version: Literal["1.0"] = "1.0"
    job_id: str
    generation_batch_id: str
    status: GenerationBatchStatus
    stop_reason: QuestionGenerationStopReason | None = None
    candidates: list[QuestionGenerationCandidateResult] = Field(default_factory=list)
    usage: QuestionGenerationUsage = Field(default_factory=QuestionGenerationUsage)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    errors: list[ErrorSummary] = Field(default_factory=list, max_length=100)
    validation: CandidateValidationBatchResult | None = None

    @model_validator(mode="after")
    def validate_output(self) -> QuestionGenerationJobOutput:
        """中文：处理“验证·output”相关操作。
        English: Handles the validate output operation.
        """
        ordinals = [candidate.ordinal for candidate in self.candidates]
        keys = [candidate.candidate_key for candidate in self.candidates]
        if len(ordinals) != len(set(ordinals)) or len(keys) != len(set(keys)):
            raise ValueError("candidate ordinals and keys must be unique")
        terminal = {
            GenerationBatchStatus.COMPLETED,
            GenerationBatchStatus.PARTIAL_FAILED,
            GenerationBatchStatus.FAILED,
            GenerationBatchStatus.CANCELLED,
        }
        if self.status in terminal and (self.finished_at is None or self.stop_reason is None):
            raise ValueError("terminal job output requires finished_at and stop_reason")
        if self.status not in terminal and self.finished_at is not None:
            raise ValueError("non-terminal job output cannot have finished_at")
        if self.status not in terminal and self.stop_reason is not None:
            raise ValueError("non-terminal job output cannot have a stop_reason")
        if (
            self.status == GenerationBatchStatus.COMPLETED
            and self.stop_reason != QuestionGenerationStopReason.COMPLETED
        ):
            raise ValueError("completed output requires completed stop_reason")
        if (
            self.status == GenerationBatchStatus.CANCELLED
            and self.stop_reason != QuestionGenerationStopReason.CANCELLED
        ):
            raise ValueError("cancelled output requires cancelled stop_reason")
        if self.status in {
            GenerationBatchStatus.PARTIAL_FAILED,
            GenerationBatchStatus.FAILED,
        } and self.stop_reason in {
            QuestionGenerationStopReason.COMPLETED,
            QuestionGenerationStopReason.CANCELLED,
        }:
            raise ValueError("failed output requires a failure stop_reason")
        if self.status in {
            GenerationBatchStatus.RUNNING,
            GenerationBatchStatus.PAUSED,
        } and self.started_at is None:
            raise ValueError("running or paused output requires started_at")
        return self


class QuestionGenerationJob(BaseModel):
    """中文：定义“问题·生成·任务”类，封装该职责相关的数据与行为。
    English: Defines the question generation job class and encapsulates data and behavior for that responsibility.
    """
    id: str
    generation_batch_id: str
    idempotency_key_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    input: QuestionGenerationStoredInput
    budget: QuestionGenerationBudget
    usage: QuestionGenerationUsage = Field(default_factory=QuestionGenerationUsage)
    output: QuestionGenerationJobOutput | None = None
    attempt_count: int = Field(default=0, ge=0)
    status_reason: str | None = Field(default=None, max_length=1000)
    last_error_code: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_identity_and_budget(self) -> QuestionGenerationJob:
        """中文：处理“验证·identity·and·budget”相关操作。
        English: Handles the validate identity and budget operation.
        """
        request_payload = self.input.model_dump(
            mode="json",
            exclude={"idempotency_scope"},
        )
        request_payload["budget"] = self.budget.model_dump(mode="json")
        if self.request_hash != _canonical_hash(request_payload):
            raise ValueError("request_hash does not match input")
        if self.output is not None:
            if self.output.job_id != self.id:
                raise ValueError("output job_id does not match job")
            if self.output.generation_batch_id != self.generation_batch_id:
                raise ValueError("output generation_batch_id does not match job")
            if self.output.usage != self.usage:
                raise ValueError("output usage does not match job usage")
            if len(self.output.candidates) > self.input.requested_count:
                raise ValueError("output candidates exceed requested_count")
            attempted_candidates = sum(
                candidate.outcome != CandidateGenerationOutcome.SKIPPED
                for candidate in self.output.candidates
            )
            if self.usage.candidates_attempted != attempted_candidates:
                raise ValueError(
                    "usage candidates_attempted does not match non-skipped output positions"
                )
            terminal = {
                GenerationBatchStatus.COMPLETED,
                GenerationBatchStatus.PARTIAL_FAILED,
                GenerationBatchStatus.FAILED,
                GenerationBatchStatus.CANCELLED,
            }
            if (
                self.output.status in terminal
                and len(self.output.candidates) != self.input.requested_count
            ):
                raise ValueError("terminal output must account for every requested position")
            mother_ids = set(self.input.mother_problem_ids)
            for candidate in self.output.candidates:
                if candidate.ordinal >= self.input.requested_count:
                    raise ValueError("candidate ordinal exceeds requested_count")
                if candidate.mother_problem_id not in mother_ids:
                    raise ValueError("candidate references an undeclared mother problem")
                expected_key = candidate_key(self.idempotency_key_hash, candidate.ordinal)
                if candidate.candidate_key != expected_key:
                    raise ValueError("candidate_key does not match job identity and ordinal")
            outcomes = {candidate.outcome for candidate in self.output.candidates}
            if self.output.status == GenerationBatchStatus.COMPLETED and outcomes != {
                CandidateGenerationOutcome.CANDIDATE_CREATED
            }:
                raise ValueError("completed output requires every candidate to be created")
            if self.output.status == GenerationBatchStatus.PARTIAL_FAILED and not (
                CandidateGenerationOutcome.CANDIDATE_CREATED in outcomes
                and outcomes
                & {
                    CandidateGenerationOutcome.GENERATION_FAILED,
                    CandidateGenerationOutcome.SKIPPED,
                }
            ):
                raise ValueError("partial_failed output requires success and failure/skip")
            if (
                self.output.status == GenerationBatchStatus.FAILED
                and CandidateGenerationOutcome.CANDIDATE_CREATED in outcomes
            ):
                raise ValueError("failed output cannot contain created candidates")
        exceeded = self.usage.exceeded_reasons(self.budget)
        if exceeded:
            raise ValueError(
                "job usage exceeds the configured budget: " + ", ".join(exceeded)
            )
        if self.attempt_count > self.budget.max_execution_attempts:
            raise ValueError("attempt_count exceeds max_execution_attempts")
        if self.usage.exhausted_reasons(self.budget) and self.output is None:
            raise ValueError("exhausted jobs require an output or stop decision")
        return self


class GenerationBatchStateMachine:
    """中文：定义“生成·批次·state·machine”类，封装该职责相关的数据与行为。
    English: Defines the generation batch state machine class and encapsulates data and behavior for that responsibility.
    """
    _transitions = {
        GenerationBatchStatus.PENDING: {
            GenerationBatchStatus.RUNNING,
            GenerationBatchStatus.CANCELLED,
        },
        GenerationBatchStatus.RUNNING: {
            GenerationBatchStatus.PAUSED,
            GenerationBatchStatus.COMPLETED,
            GenerationBatchStatus.PARTIAL_FAILED,
            GenerationBatchStatus.FAILED,
            GenerationBatchStatus.CANCELLED,
        },
        GenerationBatchStatus.PAUSED: {
            GenerationBatchStatus.RUNNING,
            GenerationBatchStatus.CANCELLED,
        },
    }

    @classmethod
    def transition(
        cls,
        current: GenerationBatchStatus,
        target: GenerationBatchStatus,
    ) -> GenerationBatchStatus:
        """中文：处理“transition”相关操作。
        English: Handles the transition operation.
        """
        if target == current:
            return current
        if target not in cls._transitions.get(current, set()):
            raise ValueError(f"invalid generation batch transition: {current} -> {target}")
        return target


def candidate_key(idempotency_key_hash: str, ordinal: int) -> str:
    """中文：处理“候选内容·key”相关操作。
    English: Handles the candidate key operation.
    """
    if ordinal < 0:
        raise ValueError("candidate ordinal cannot be negative")
    return f"qgc-{sha256(f'{idempotency_key_hash}:{ordinal}'.encode()).hexdigest()}"


def _canonical_hash(value: dict) -> str:
    """中文：处理“canonical·hash”相关操作。
    English: Handles the canonical hash operation.
    """
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()
