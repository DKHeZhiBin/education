from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, model_validator


def new_knowledge_id() -> str:
    return str(uuid4())


class KnowledgeSourceType(StrEnum):
    CURRICULUM_STANDARD = "curriculum_standard"
    TEXTBOOK = "textbook"
    TEACHER_GUIDE = "teacher_guide"
    PROBLEM_SET = "problem_set"
    PAPER = "paper"
    WEBSITE = "website"
    LOCAL_AUTHORING = "local_authoring"


class KnowledgeDocumentType(StrEnum):
    CURRICULUM = "curriculum"
    TEXTBOOK = "textbook"
    CHAPTER = "chapter"
    LESSON = "lesson"
    THEOREM = "theorem"
    EXAMPLE = "example"
    PROBLEM_SET = "problem_set"
    SOLUTION_MANUAL = "solution_manual"
    TEACHING_NOTE = "teaching_note"


class KnowledgeContentType(StrEnum):
    TEXT = "text"
    CODE = "code"
    CURRICULUM = "curriculum"
    CURRICULUM_STANDARD = "curriculum_standard"
    TEXTBOOK = "textbook"
    CHAPTER = "chapter"
    LESSON = "lesson"
    CONCEPT = "concept"
    DEFINITION = "definition"
    THEOREM = "theorem"
    FORMULA = "formula"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    PROBLEM = "problem"
    PROBLEM_STATEMENT = "problem_statement"
    PROBLEM_SET = "problem_set"
    SOLUTION = "solution"
    SOLUTION_MANUAL = "solution_manual"
    PROOF = "proof"
    HINT = "hint"
    MISCONCEPTION = "misconception"
    TEACHING_NOTE = "teaching_note"
    OTHER = "other"


class KnowledgeReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class KnowledgeLifecycleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    INDEXED = "indexed"
    FAILED = "failed"


class ProblemContentStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATING = "validating"
    REVISION_REQUIRED = "revision_required"
    QUARANTINED = "quarantined"
    APPROVED = "approved"
    INDEXED = "indexed"
    RETIRED = "retired"


class ProblemDerivationType(StrEnum):
    PARAMETER_CHANGE = "parameter_change"
    CONDITION_CHANGE = "condition_change"
    REPRESENTATION_CHANGE = "representation_change"
    CONTEXT_CHANGE = "context_change"
    METHOD_CHANGE = "method_change"
    ISOMORPHIC = "isomorphic"
    DIFFICULTY_CHANGE = "difficulty_change"


class ProblemCondition(BaseModel):
    statement: str = Field(min_length=1, max_length=1000)
    condition_type: Literal[
        "equation",
        "inequality",
        "domain",
        "parameter",
        "geometric",
        "context",
        "assumption",
        "other",
    ] = "other"
    normalized_expression: str | None = Field(default=None, max_length=1000)
    related_symbols: list[str] = Field(default_factory=list)


class ImplicitProblemCondition(ProblemCondition):
    inference_basis: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1)


class ProblemTarget(BaseModel):
    action: Literal[
        "solve",
        "prove",
        "calculate",
        "determine",
        "construct",
        "compare",
        "analyze",
        "explain",
        "other",
    ]
    target_object: str = Field(min_length=1, max_length=1000)
    expected_answer_type: str = Field(min_length=1, max_length=64)
    constraints: list[str] = Field(default_factory=list)


class ProblemDifficultyFactor(BaseModel):
    factor_type: Literal[
        "hidden_condition",
        "knowledge_combination",
        "transformation_depth",
        "method_selection",
        "construction",
        "case_analysis",
        "computational_complexity",
        "proof_chain",
        "abstraction",
        "modeling",
        "extraneous_root_risk",
        "other",
    ]
    level: int = Field(ge=1, le=5)
    rationale: str = Field(min_length=1, max_length=1000)
    related_knowledge_codes: list[str] = Field(default_factory=list)


class SourceReference(BaseModel):
    id: str = Field(default_factory=new_knowledge_id)
    source_type: KnowledgeSourceType
    title: str = Field(min_length=1, max_length=500)
    authors: list[str] = Field(default_factory=list)
    publisher: str | None = Field(default=None, max_length=255)
    canonical_url: HttpUrl | None = None
    external_id: str | None = Field(default=None, max_length=255)
    license_name: str = Field(min_length=1, max_length=100)
    rights_note: str | None = Field(default=None, max_length=1000)
    published_at: datetime | None = None
    accessed_at: datetime | None = None
    fingerprint: str = Field(min_length=64, max_length=64)


class CurriculumVersion(BaseModel):
    id: str = Field(default_factory=new_knowledge_id)
    source_reference_id: str
    authority: str = Field(min_length=1, max_length=255)
    region_code: str = Field(default="CN", max_length=32)
    subject: str = Field(default="math", max_length=32)
    grade_band: str = Field(max_length=32)
    name: str = Field(min_length=1, max_length=255)
    version_code: str = Field(min_length=1, max_length=80)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    status: KnowledgeLifecycleStatus = KnowledgeLifecycleStatus.ACTIVE


class KnowledgeDocument(BaseModel):
    id: str = Field(default_factory=new_knowledge_id)
    source_reference_id: str
    curriculum_version_id: str | None = None
    document_type: KnowledgeDocumentType
    document_key: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    version_label: str = Field(default="original", min_length=1, max_length=100)
    language: str = Field(default="zh-CN", max_length=16)
    subject: str = Field(default="math", max_length=32)
    grade_band: str | None = Field(default=None, max_length=32)
    grade_codes: list[str] = Field(default_factory=list)
    content_checksum: str = Field(min_length=64, max_length=64)
    review_status: KnowledgeReviewStatus = KnowledgeReviewStatus.UNREVIEWED
    lifecycle_status: KnowledgeLifecycleStatus = KnowledgeLifecycleStatus.DRAFT
    ingestion_status: IngestionStatus = IngestionStatus.PENDING
    knowledge_point_codes: list[str] = Field(default_factory=list)
    problem_types: list[str] = Field(default_factory=list)
    difficulty_factors: list[ProblemDifficultyFactor] = Field(default_factory=list)
    content_types: list[KnowledgeContentType] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_tags(self) -> KnowledgeDocument:
        _require_unique_tags("knowledge_point_codes", self.knowledge_point_codes)
        _require_unique_tags("grade_codes", self.grade_codes)
        _require_unique_tags("problem_types", self.problem_types)
        _require_unique_tags("content_types", self.content_types)
        return self


class DocumentChunk(BaseModel):
    id: str = Field(default_factory=new_knowledge_id)
    document_id: str
    curriculum_version_id: str | None = None
    ordinal: int = Field(ge=0)
    content: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    token_count: int = Field(ge=1)
    heading_path: list[str] = Field(default_factory=list)
    locator: str | None = Field(default=None, max_length=255)
    content_type: KnowledgeContentType = KnowledgeContentType.TEXT
    grade_band: str | None = Field(default=None, max_length=32)
    grade_codes: list[str] = Field(default_factory=list)
    knowledge_point_codes: list[str] = Field(default_factory=list)
    problem_types: list[str] = Field(default_factory=list)
    difficulty_factors: list[ProblemDifficultyFactor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_tags(self) -> DocumentChunk:
        _require_unique_tags("knowledge_point_codes", self.knowledge_point_codes)
        _require_unique_tags("grade_codes", self.grade_codes)
        _require_unique_tags("problem_types", self.problem_types)
        return self


class KnowledgeProblem(BaseModel):
    id: str = Field(default_factory=new_knowledge_id)
    source_reference_id: str
    document_id: str | None = None
    source_chunk_id: str | None = None
    curriculum_version_id: str | None = None
    external_id: str | None = Field(default=None, max_length=255)
    statement: str = Field(min_length=1)
    normalized_statement: str | None = None
    subject: str = Field(default="math", max_length=32)
    grade_band: str | None = Field(default=None, max_length=32)
    grade_codes: list[str] = Field(default_factory=list)
    problem_type: str = Field(max_length=64)
    content_type: KnowledgeContentType = KnowledgeContentType.PROBLEM
    difficulty: int = Field(ge=1, le=5)
    answer_type: str = Field(default="unknown", max_length=64)
    language: str = Field(default="zh-CN", max_length=16)
    content_hash: str = Field(min_length=64, max_length=64)
    review_status: KnowledgeReviewStatus = KnowledgeReviewStatus.UNREVIEWED
    explicit_conditions: list[ProblemCondition] = Field(default_factory=list)
    implicit_conditions: list[ImplicitProblemCondition] = Field(default_factory=list)
    target: ProblemTarget | None = None
    difficulty_factors: list[ProblemDifficultyFactor] = Field(default_factory=list)
    mother_problem_id: str | None = None
    generation_batch_id: str | None = None
    derivation_type: ProblemDerivationType | None = None
    derivation_note: str | None = Field(default=None, max_length=1000)
    content_status: ProblemContentStatus = ProblemContentStatus.CANDIDATE
    status_reason: str | None = Field(default=None, max_length=1000)
    revision_attempts: int = Field(default=0, ge=0)
    status_version: int = Field(default=1, ge=1)
    status_changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    knowledge_point_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mother_problem_relation(self) -> KnowledgeProblem:
        _require_unique_tags("knowledge_point_codes", self.knowledge_point_codes)
        _require_unique_tags("grade_codes", self.grade_codes)
        if self.mother_problem_id == self.id:
            raise ValueError("a problem cannot use itself as its mother problem")
        if (self.mother_problem_id is None) != (self.derivation_type is None):
            raise ValueError(
                "mother_problem_id and derivation_type must either both be set or both be null"
            )
        if self.content_status in {
            ProblemContentStatus.REVISION_REQUIRED,
            ProblemContentStatus.QUARANTINED,
            ProblemContentStatus.RETIRED,
        } and not self.status_reason:
            raise ValueError(f"status_reason is required for {self.content_status.value}")
        if self.content_status in {
            ProblemContentStatus.APPROVED,
            ProblemContentStatus.INDEXED,
        }:
            if self.target is None:
                raise ValueError("approved or indexed problems must have a structured target")
            if not (
                self.grade_band
                and self.grade_codes
                and self.knowledge_point_codes
                and self.problem_type
                and self.content_type
                and self.difficulty_factors
            ):
                raise ValueError(
                    "approved or indexed problems must have complete classification tags"
                )
        return self


def _require_unique_tags(name: str, values: list[Any]) -> None:
    normalized = [item.value if isinstance(item, StrEnum) else item for item in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must contain unique values")


class SolutionStepJustification(BaseModel):
    basis_type: Literal[
        "given_condition",
        "definition",
        "theorem",
        "formula",
        "algebraic_property",
        "previous_step",
        "calculation",
        "assumption",
        "other",
    ]
    statement: str = Field(min_length=1, max_length=1000)
    source_reference_id: str | None = None
    locator: str | None = Field(default=None, max_length=255)


class StructuredSolutionStep(BaseModel):
    step_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=1000)
    result: str = Field(min_length=1, max_length=2000)
    justifications: list[SolutionStepJustification] = Field(min_length=1)
    depends_on_step_ids: list[str] = Field(default_factory=list)
    condition_refs: list[str] = Field(default_factory=list)
    knowledge_point_codes: list[str] = Field(default_factory=list)


class SolutionBreakthrough(BaseModel):
    breakthrough_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=1000)
    why_it_matters: str = Field(min_length=1, max_length=1000)
    related_step_ids: list[str] = Field(default_factory=list)
    knowledge_point_codes: list[str] = Field(default_factory=list)
    hint_question: str | None = Field(default=None, max_length=1000)


class SolutionVerificationCheck(BaseModel):
    check_type: Literal[
        "symbolic_equivalence",
        "candidate_substitution",
        "constraint_satisfaction",
        "numeric_sampling",
        "answer_completeness",
        "proof_logic",
        "theorem_applicability",
        "other",
    ]
    status: Literal["passed", "failed", "not_run"]
    verifier: str = Field(min_length=1, max_length=100)
    covered_step_ids: list[str] = Field(default_factory=list)
    evidence: str | None = Field(default=None, max_length=2000)


class SolutionVerificationCoverage(BaseModel):
    level: Literal["none", "partial", "full"] = "none"
    covered_step_ids: list[str] = Field(default_factory=list)
    uncovered_step_ids: list[str] = Field(default_factory=list)
    checks: list[SolutionVerificationCheck] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)


class KnowledgeSolution(BaseModel):
    id: str = Field(default_factory=new_knowledge_id)
    problem_id: str
    source_reference_id: str
    method_name: str = Field(min_length=1, max_length=255)
    solution_text: str = Field(min_length=1)
    final_answer: str | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    review_status: KnowledgeReviewStatus = KnowledgeReviewStatus.UNREVIEWED
    verification_status: Literal["unverified", "partial", "verified", "failed"] = "unverified"
    steps: list[StructuredSolutionStep] = Field(default_factory=list)
    key_breakthroughs: list[SolutionBreakthrough] = Field(default_factory=list)
    verification_coverage: SolutionVerificationCoverage = Field(
        default_factory=SolutionVerificationCoverage
    )
    is_preferred: bool = False
    language: str = Field(default="zh-CN", max_length=16)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_structured_solution(self) -> KnowledgeSolution:
        step_ids = [step.step_id for step in self.steps]
        sequences = [step.sequence for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("solution step ids must be unique")
        if len(sequences) != len(set(sequences)):
            raise ValueError("solution step sequences must be unique")
        if sequences and sorted(sequences) != list(range(1, len(sequences) + 1)):
            raise ValueError("solution step sequences must be contiguous and start at 1")

        step_sequence = {step.step_id: step.sequence for step in self.steps}
        for step in self.steps:
            for dependency in step.depends_on_step_ids:
                if dependency not in step_sequence:
                    raise ValueError(f"unknown step dependency: {dependency}")
                if step_sequence[dependency] >= step.sequence:
                    raise ValueError("a solution step may only depend on an earlier step")

        breakthrough_ids = [item.breakthrough_id for item in self.key_breakthroughs]
        if len(breakthrough_ids) != len(set(breakthrough_ids)):
            raise ValueError("solution breakthrough ids must be unique")
        for item in self.key_breakthroughs:
            unknown = set(item.related_step_ids) - set(step_ids)
            if unknown:
                raise ValueError(f"breakthrough references unknown steps: {sorted(unknown)}")

        covered = set(self.verification_coverage.covered_step_ids)
        uncovered = set(self.verification_coverage.uncovered_step_ids)
        if covered & uncovered:
            raise ValueError("covered and uncovered solution steps must not overlap")
        unknown_coverage = (covered | uncovered) - set(step_ids)
        if unknown_coverage:
            raise ValueError(f"verification references unknown steps: {sorted(unknown_coverage)}")
        for check in self.verification_coverage.checks:
            unknown = set(check.covered_step_ids) - set(step_ids)
            if unknown:
                raise ValueError(f"verification check references unknown steps: {sorted(unknown)}")
        evidenced = set().union(
            *(
                set(check.covered_step_ids)
                for check in self.verification_coverage.checks
                if check.status == "passed"
            )
        )
        if not covered.issubset(evidenced):
            raise ValueError("every covered step must be supported by a passed check")

        if self.verification_status == "unverified":
            if self.verification_coverage.level != "none":
                raise ValueError("unverified solutions must use verification coverage level none")
            if covered or uncovered or self.verification_coverage.checks:
                raise ValueError("unverified solutions cannot claim step coverage or checks")
        if self.verification_status == "partial":
            if not self.steps:
                raise ValueError("partially verified solutions must contain structured steps")
            if self.verification_coverage.level != "partial":
                raise ValueError("partial solutions must use verification coverage level partial")
            if not covered or covered | uncovered != set(step_ids):
                raise ValueError("partial coverage must classify every step and cover at least one")
            if not self.verification_coverage.limitations:
                raise ValueError("partial coverage must explain its limitations")
            if not self.verification_coverage.checks:
                raise ValueError("partial coverage must contain verification checks")
            if any(check.status == "failed" for check in self.verification_coverage.checks):
                raise ValueError("partial verification cannot contain a failed check")
        if self.verification_status == "verified":
            if not self.steps:
                raise ValueError("verified solutions must contain structured steps")
            if self.verification_coverage.level != "full":
                raise ValueError("verified solutions must have full verification coverage")
            if covered != set(step_ids) or uncovered:
                raise ValueError("full verification coverage must cover every solution step")
            if not self.verification_coverage.checks:
                raise ValueError("verified solutions must contain verification checks")
            if any(check.status != "passed" for check in self.verification_coverage.checks):
                raise ValueError("verified solutions may only contain passed verification checks")
        if self.verification_status == "failed" and not any(
            check.status == "failed" for check in self.verification_coverage.checks
        ):
            raise ValueError("failed solutions must contain at least one failed verification check")
        return self


class KnowledgeFilters(BaseModel):
    """Portable metadata filters understood by every retriever implementation."""

    subject: str = "math"
    grade: str | None = None
    grade_band: str | None = None
    grade_codes: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    problem_types: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    difficulty_sources: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    curriculum_version: str | None = None
    curriculum_version_id: str | None = None
    language: str = "zh-CN"


RetrievalStructureText = Annotated[str, Field(min_length=1, max_length=1000)]


class RetrievalProblemStructure(BaseModel):
    condition_statements: list[RetrievalStructureText] = Field(
        default_factory=list, max_length=20
    )
    target_summary: str | None = Field(default=None, min_length=1, max_length=1000)
    solution_methods: list[RetrievalStructureText] = Field(
        default_factory=list, max_length=10
    )
    solution_steps: list[RetrievalStructureText] = Field(
        default_factory=list, max_length=20
    )


class KnowledgeQuery(BaseModel):
    """Provider-neutral retrieval request created by the orchestration layer."""

    text: str = Field(min_length=1, max_length=4000)
    purpose: Literal[
        "problem_understanding",
        "solution_analysis",
        "hint_teaching",
        "source_lookup",
    ]
    filters: KnowledgeFilters = Field(default_factory=KnowledgeFilters)
    top_k: int = Field(default=5, ge=1, le=20)
    hint_level: int | None = Field(default=None, ge=1, le=4)
    problem_structure: RetrievalProblemStructure = Field(
        default_factory=RetrievalProblemStructure
    )

    @model_validator(mode="after")
    def validate_hint_scope(self) -> KnowledgeQuery:
        if self.purpose == "hint_teaching" and self.hint_level is None:
            raise ValueError("hint_teaching query requires hint_level")
        if self.purpose != "hint_teaching" and self.hint_level is not None:
            raise ValueError("hint_level is only valid for hint_teaching")
        return self


class KnowledgeCitation(BaseModel):
    source_reference_id: str | None = None
    document_id: str
    chunk_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    version: str | None = Field(default=None, max_length=100)
    source_url: HttpUrl | None = None
    locator: str | None = Field(default=None, max_length=255)


class RetrievedKnowledge(BaseModel):
    """Provider-internal candidate; this raw excerpt must never enter an Agent payload."""

    chunk_id: str
    content: str = Field(min_length=1, max_length=2000)
    score: float = Field(ge=0, le=1)
    content_type: str = Field(min_length=1, max_length=40)
    citation: KnowledgeCitation
    tags: dict[str, Any] = Field(default_factory=dict)


CompactText = Annotated[str, Field(min_length=1, max_length=300)]
CompactCode = Annotated[str, Field(min_length=1, max_length=120)]


class RetrievedConcept(BaseModel):
    concept_code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    definition_summary: str = Field(min_length=1, max_length=600)
    notation: list[CompactText] = Field(default_factory=list, max_length=8)
    prerequisites: list[CompactCode] = Field(default_factory=list, max_length=8)
    disclosure_level: int = Field(default=1, ge=1, le=4)
    score: float = Field(ge=0, le=1)
    citation: KnowledgeCitation


class RetrievedPrinciple(BaseModel):
    principle_key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    statement_summary: str = Field(min_length=1, max_length=700)
    formula: str | None = Field(default=None, max_length=500)
    applicability_conditions: list[CompactText] = Field(default_factory=list, max_length=8)
    common_constraints: list[CompactText] = Field(default_factory=list, max_length=8)
    disclosure_level: int = Field(default=2, ge=1, le=4)
    score: float = Field(ge=0, le=1)
    citation: KnowledgeCitation

    @model_validator(mode="after")
    def validate_formula_disclosure(self) -> RetrievedPrinciple:
        if self.formula is not None and self.disclosure_level < 2:
            raise ValueError("formula requires disclosure level 2 or above")
        return self


class RetrievedProblemPattern(BaseModel):
    problem_id: str
    structure_summary: str = Field(min_length=1, max_length=700)
    condition_schema: list[CompactText] = Field(default_factory=list, max_length=10)
    target_schema: str = Field(min_length=1, max_length=400)
    method_names: list[CompactText] = Field(default_factory=list, max_length=5)
    knowledge_point_codes: list[CompactCode] = Field(default_factory=list, max_length=12)
    difficulty_factors: list[CompactText] = Field(default_factory=list, max_length=8)
    disclosure_level: int = Field(default=1, ge=1, le=4)
    score: float = Field(ge=0, le=1)
    citation: KnowledgeCitation

    @model_validator(mode="after")
    def validate_method_disclosure(self) -> RetrievedProblemPattern:
        if self.method_names and self.disclosure_level < 2:
            raise ValueError("method names require disclosure level 2 or above")
        return self


class RetrievedSolutionStep(BaseModel):
    step_key: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=1, le=20)
    action_summary: str = Field(min_length=1, max_length=600)
    justification_summary: str = Field(min_length=1, max_length=600)
    result_summary: str | None = Field(default=None, max_length=700)


class RetrievedSolutionOutline(BaseModel):
    solution_id: str
    problem_id: str
    method_name: str = Field(min_length=1, max_length=255)
    strategy_summary: str = Field(min_length=1, max_length=800)
    key_breakthroughs: list[CompactText] = Field(default_factory=list, max_length=5)
    steps: list[RetrievedSolutionStep] = Field(default_factory=list, max_length=10)
    final_answer: str | None = Field(default=None, max_length=700)
    verification_level: Literal["partial", "full"]
    disclosure_level: Literal[4] = 4
    score: float = Field(ge=0, le=1)
    citation: KnowledgeCitation

    @model_validator(mode="after")
    def validate_verified_answer(self) -> RetrievedSolutionOutline:
        if self.final_answer is not None and self.verification_level != "full":
            raise ValueError("final answer requires full verification")
        return self


class RetrievedErrorPattern(BaseModel):
    pattern_code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    observable_signals: list[CompactText] = Field(min_length=1, max_length=8)
    diagnostic_question: str = Field(min_length=1, max_length=500)
    remediation_goal: str = Field(min_length=1, max_length=600)
    related_step_key: str | None = Field(default=None, max_length=64)
    disclosure_level: int = Field(default=1, ge=1, le=4)
    score: float = Field(ge=0, le=1)
    citation: KnowledgeCitation


class RetrievedHint(BaseModel):
    hint_blueprint_id: str
    solution_id: str
    solution_step_key: str | None = Field(default=None, max_length=64)
    error_pattern_code: str | None = Field(default=None, max_length=120)
    hint_level: int = Field(ge=1, le=4)
    hint_stage: Literal[
        "direction",
        "key_relation",
        "local_step",
        "full_explanation",
    ]
    content: str = Field(min_length=1, max_length=1000)
    understanding_check: str = Field(min_length=1, max_length=500)
    review_status: Literal["approved"] = "approved"
    score: float = Field(ge=0, le=1)
    citation: KnowledgeCitation

    @model_validator(mode="after")
    def validate_level_stage(self) -> RetrievedHint:
        stage_by_level = {
            1: "direction",
            2: "key_relation",
            3: "local_step",
            4: "full_explanation",
        }
        if self.hint_stage != stage_by_level[self.hint_level]:
            raise ValueError("hint level and stage do not match")
        if self.hint_level == 3 and not self.solution_step_key:
            raise ValueError("level 3 hint requires solution_step_key")
        return self


class RetrievedSourceFact(BaseModel):
    fact_type: Literal[
        "definition",
        "curriculum_requirement",
        "theorem",
        "formula",
        "provenance",
        "other",
    ]
    summary: str = Field(min_length=1, max_length=800)
    score: float = Field(ge=0, le=1)
    citation: KnowledgeCitation


class RetrievalDiagnostics(BaseModel):
    latency_ms: int | None = Field(default=None, ge=0)
    index_version: str | None = Field(default=None, max_length=100)
    candidate_count: int = Field(default=0, ge=0)
    selected_count: int = Field(default=0, ge=0)
    truncated: bool = False
    cache_hit: bool = False
    knowledge_version: str | None = Field(default=None, max_length=160)


class AgentTeachingContext(BaseModel):
    """The only RAG object that may be serialized into an Agent prompt."""

    schema_version: Literal["1.0"] = "1.0"
    purpose: Literal[
        "problem_understanding",
        "solution_analysis",
        "hint_teaching",
        "source_lookup",
    ]
    hint_level: int | None = Field(default=None, ge=1, le=4)
    concepts: list[RetrievedConcept] = Field(default_factory=list, max_length=8)
    principles: list[RetrievedPrinciple] = Field(default_factory=list, max_length=8)
    problem_patterns: list[RetrievedProblemPattern] = Field(default_factory=list, max_length=5)
    solution_outlines: list[RetrievedSolutionOutline] = Field(default_factory=list, max_length=3)
    error_patterns: list[RetrievedErrorPattern] = Field(default_factory=list, max_length=6)
    hints: list[RetrievedHint] = Field(default_factory=list, max_length=4)
    source_facts: list[RetrievedSourceFact] = Field(default_factory=list, max_length=8)
    limitations: list[CompactText] = Field(default_factory=list, max_length=8)


class RetrievedTeachingContext(BaseModel):
    """Validated, bounded teaching facts produced from raw retrieval candidates."""

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["success", "no_results", "disabled", "degraded"]
    provider: str = Field(min_length=1, max_length=80)
    query: KnowledgeQuery
    concepts: list[RetrievedConcept] = Field(default_factory=list, max_length=8)
    principles: list[RetrievedPrinciple] = Field(default_factory=list, max_length=8)
    problem_patterns: list[RetrievedProblemPattern] = Field(default_factory=list, max_length=5)
    solution_outlines: list[RetrievedSolutionOutline] = Field(default_factory=list, max_length=3)
    error_patterns: list[RetrievedErrorPattern] = Field(default_factory=list, max_length=6)
    hints: list[RetrievedHint] = Field(default_factory=list, max_length=4)
    source_facts: list[RetrievedSourceFact] = Field(default_factory=list, max_length=8)
    limitations: list[CompactText] = Field(default_factory=list, max_length=8)
    diagnostics: RetrievalDiagnostics = Field(default_factory=RetrievalDiagnostics)
    max_context_chars: int = Field(default=12000, ge=1000, le=24000)
    context_char_count: int = Field(default=0, ge=0)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_agent_boundary(self) -> RetrievedTeachingContext:
        groups = (
            self.concepts,
            self.principles,
            self.problem_patterns,
            self.solution_outlines,
            self.error_patterns,
            self.hints,
            self.source_facts,
        )
        has_content = any(groups)
        if self.status == "success" and not has_content:
            raise ValueError("successful retrieval must contain structured teaching content")
        if self.status in {"disabled", "no_results"} and has_content:
            raise ValueError(f"{self.status} retrieval cannot contain teaching content")

        purpose = self.query.purpose
        if purpose == "problem_understanding" and (
            self.solution_outlines or self.error_patterns or self.hints or self.source_facts
        ):
            raise ValueError("problem understanding received disallowed content groups")
        if purpose == "solution_analysis" and (self.hints or self.source_facts):
            raise ValueError("solution analysis received disallowed content groups")
        if purpose == "hint_teaching" and self.source_facts:
            raise ValueError("hint teaching cannot receive source lookup facts")
        if purpose == "source_lookup" and any(groups[:-1]):
            raise ValueError("source lookup may only return source_facts")
        if purpose != "hint_teaching" and self.hints:
            raise ValueError("hint blueprints are only valid for hint teaching")

        if purpose == "hint_teaching":
            hint_level = self.query.hint_level
            if hint_level is None:
                raise ValueError("hint teaching requires hint_level")
            disclosed = [
                *self.concepts,
                *self.principles,
                *self.problem_patterns,
                *self.solution_outlines,
                *self.error_patterns,
            ]
            if any(item.disclosure_level > hint_level for item in disclosed):
                raise ValueError("retrieved item exceeds the requested hint level")
            if any(item.hint_level != hint_level for item in self.hints):
                raise ValueError("retrieved hint must match the requested hint level")
            if hint_level < 4 and self.solution_outlines:
                raise ValueError("levels 1-3 cannot receive solution outlines")

        agent_context = self.to_agent_context()
        content_chars = len(agent_context.model_dump_json())
        if content_chars > self.max_context_chars:
            raise ValueError(
                f"structured teaching context exceeds {self.max_context_chars} characters"
            )
        self.context_char_count = content_chars
        selected_count = sum(len(group) for group in groups)
        if self.diagnostics.selected_count == 0:
            self.diagnostics.selected_count = selected_count
        elif self.diagnostics.selected_count != selected_count:
            raise ValueError("diagnostic selected_count does not match structured content")
        if self.diagnostics.candidate_count == 0:
            self.diagnostics.candidate_count = selected_count
        elif self.diagnostics.candidate_count < selected_count:
            raise ValueError("candidate_count cannot be smaller than selected_count")
        return self

    def to_agent_context(self) -> AgentTeachingContext:
        """Drop query, provider diagnostics, and every raw retrieval candidate."""
        return AgentTeachingContext(
            purpose=self.query.purpose,
            hint_level=self.query.hint_level,
            concepts=self.concepts,
            principles=self.principles,
            problem_patterns=self.problem_patterns,
            solution_outlines=self.solution_outlines,
            error_patterns=self.error_patterns,
            hints=self.hints,
            source_facts=self.source_facts,
            limitations=self.limitations,
        )
