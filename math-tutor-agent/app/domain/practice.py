from typing import Literal

from pydantic import BaseModel, Field, model_validator


StructureVariationLevel = Literal["S1", "S2", "S3", "S4"]
ReasoningVariationLevel = Literal["M1", "M2", "M3", "M4"]
MPRStructureRelationLevel = Literal["S1", "S2", "S3", "S4", "UNKNOWN"]
MPRReasoningRelationLevel = Literal["M1", "M2", "M3", "M4", "UNKNOWN"]
TeachingGoal = Literal["T1", "T2", "T3", "T4"]
PracticeDifficulty = Literal["easy", "medium", "hard", "easier", "same", "harder"]


class SimilarPracticeDifficultyProfile(BaseModel):
    """中文：将用户可见难度固定映射为 S/M/T 和候选预算。 English: Maps a learner-facing difficulty to fixed S/M/T targets and a candidate budget."""

    level: Literal["easy", "medium", "hard"]
    numeric_difficulty: int = Field(ge=1, le=3)
    structure_level: StructureVariationLevel
    reasoning_level: ReasoningVariationLevel
    teaching_goal: TeachingGoal
    candidate_count: int = Field(ge=1, le=3)
    quality_threshold: int = Field(ge=0, le=100)


class KnowledgeExamplePracticeRequest(BaseModel):
    """中文：学生从知识点例题发起相似练习的请求。 English: A learner request for similar practice from a knowledge-point example."""

    knowledge_point_code: str = Field(min_length=1, max_length=80)
    content_key: str = Field(min_length=1, max_length=80)
    difficulty: PracticeDifficulty = "medium"
    structure_level: StructureVariationLevel | None = None
    reasoning_level: ReasoningVariationLevel | None = None
    teaching_goal: TeachingGoal | None = None
    llm_model_id: str | None = Field(default=None, min_length=3, max_length=180)
    client_request_id: str = Field(min_length=1, max_length=64)

    def difficulty_profile(self) -> SimilarPracticeDifficultyProfile:
        """中文：由后端统一解析难度规则，避免前端组合出不一致的 S/M/T。 English: Resolves difficulty on the server so clients cannot create inconsistent S/M/T combinations."""

        canonical = {"easier": "easy", "same": "medium", "harder": "hard"}.get(
            self.difficulty,
            self.difficulty,
        )
        profiles = {
            "easy": SimilarPracticeDifficultyProfile(
                level="easy", numeric_difficulty=1,
                structure_level="S1", reasoning_level="M1", teaching_goal="T2",
                candidate_count=1, quality_threshold=72,
            ),
            "medium": SimilarPracticeDifficultyProfile(
                level="medium", numeric_difficulty=2,
                structure_level="S2", reasoning_level="M2", teaching_goal="T1",
                candidate_count=2, quality_threshold=78,
            ),
            "hard": SimilarPracticeDifficultyProfile(
                level="hard", numeric_difficulty=3,
                structure_level="S3", reasoning_level="M3", teaching_goal="T4",
                candidate_count=3, quality_threshold=82,
            ),
        }
        return profiles[canonical]


class MPRVariable(BaseModel):
    """中文：描述题目中的变量及其定义域。 English: Describes a problem variable and its domain."""

    symbol: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=120)
    domain: str = Field(min_length=1, max_length=300)


class MPRCondition(BaseModel):
    """中文：描述一个显式或隐含条件及其解题作用。 English: Describes an explicit or implicit condition and its role."""

    condition_type: Literal["explicit", "implicit"]
    expression: str = Field(min_length=1, max_length=1000)
    role: str = Field(min_length=1, max_length=500)


class MPRGoal(BaseModel):
    """中文：描述题目要求求解或证明的目标。 English: Describes the quantity or claim the problem asks to solve or prove."""

    goal_type: str = Field(min_length=1, max_length=100)
    expression: str = Field(min_length=1, max_length=1000)
    expected_result_type: str = Field(min_length=1, max_length=120)


class MPRCanonicalStructure(BaseModel):
    """中文：给出可用于结构比较的规范题型表示。 English: Provides a canonical problem representation for structural comparison."""

    structure_type: str = Field(min_length=1, max_length=100)
    relation_form: str = Field(min_length=1, max_length=100)
    function_family: str = Field(min_length=1, max_length=100)
    canonical_pattern: str = Field(min_length=1, max_length=1000)


class MPRStrategyStep(BaseModel):
    """中文：记录解题策略的一步及这一步的目的。 English: Records one strategy step and its purpose."""

    order: int = Field(ge=1, le=20)
    method: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=500)


class MPRVerification(BaseModel):
    """中文：记录数学表示当前已获得的验证覆盖。 English: Records the verification coverage currently available for an MPR."""

    status: Literal["pending", "passed", "failed", "partial"] = "pending"
    answer_status: Literal["unchecked", "passed", "failed", "inconclusive"] = "unchecked"
    proof_coverage: Literal["none", "partial", "full"] = "none"
    evidence_types: list[str] = Field(default_factory=list, max_length=10)
    summary: str = Field(default="待独立复核", max_length=1000)


class MPRCore(BaseModel):
    """中文：题目的数学问题表示，统一描述符号结构、思维策略、教学信息和验证状态。 English: A mathematical problem representation covering symbolic structure, strategy, pedagogy, and verification."""

    schema_version: Literal["1.0"] = "1.0"
    problem_id: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=5000)
    subject: str = Field(min_length=1, max_length=80)
    grade_band: str = Field(min_length=1, max_length=80)
    problem_type: str = Field(min_length=1, max_length=120)
    knowledge_points: list[str] = Field(min_length=1, max_length=30)
    prerequisite_knowledge: list[str] = Field(default_factory=list, max_length=30)
    mathematical_objects: list[str] = Field(min_length=1, max_length=20)
    variables: list[MPRVariable] = Field(default_factory=list, max_length=20)
    conditions: list[MPRCondition] = Field(min_length=1, max_length=30)
    goal: MPRGoal
    canonical_structure: MPRCanonicalStructure
    proof_obligations: list[str] = Field(min_length=1, max_length=30)
    primary_method: str = Field(min_length=1, max_length=200)
    secondary_methods: list[str] = Field(default_factory=list, max_length=20)
    strategy_steps: list[MPRStrategyStep] = Field(min_length=1, max_length=20)
    key_breakthrough: str = Field(min_length=1, max_length=1000)
    difficulty: int = Field(ge=1, le=3)
    common_errors: list[str] = Field(default_factory=list, max_length=20)
    hint_directions: list[str] = Field(default_factory=list, max_length=10)
    verification: MPRVerification = Field(default_factory=MPRVerification)


class MPRRelation(BaseModel):
    """中文：描述两道题之间的结构与思维变化；S/M 只属于关系，不属于单题。 English: Describes structural and reasoning changes between two problems; S/M belong to the relation, not either problem."""

    schema_version: Literal["1.0"] = "1.0"
    relation_type: Literal["variant_of"] = "variant_of"
    source_problem_id: str = Field(min_length=1, max_length=200)
    target_problem_id: str = Field(min_length=1, max_length=200)
    structure_level: MPRStructureRelationLevel
    reasoning_level: MPRReasoningRelationLevel
    transformations: list[str] = Field(min_length=1, max_length=20)
    preserved_methods: list[str] = Field(default_factory=list, max_length=20)
    changed_methods: list[str] = Field(default_factory=list, max_length=20)
    structure_evidence: str = Field(min_length=1, max_length=1000)
    reasoning_evidence: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1)
    review_status: Literal["accepted", "review_required", "rejected", "unknown"]

    @model_validator(mode="after")
    def validate_relation_decision(self) -> "MPRRelation":
        """中文：阻止不确定或低置信关系被标为已接受。 English: Prevents an uncertain or low-confidence relation from being accepted."""

        if self.source_problem_id == self.target_problem_id:
            raise ValueError("MPR relation source and target must be different")
        if self.review_status == "accepted":
            if "UNKNOWN" in {self.structure_level, self.reasoning_level}:
                raise ValueError("accepted MPR relation cannot use UNKNOWN levels")
            if self.confidence < 0.65:
                raise ValueError("accepted MPR relation confidence must be at least 0.65")
        return self


class SimilarPracticeCandidateReview(BaseModel):
    """中文：独立复核器对候选题、候选 MPR 和题间关系给出的结构化结论。 English: The independent reviewer's structured decision for a candidate, its MPR, and its relation to the source."""

    candidate_id: str = Field(min_length=1, max_length=80)
    accepted: bool
    mathematical_correctness: Literal["passed", "failed", "inconclusive"]
    condition_completeness: Literal["passed", "failed"]
    teaching_goal_met: bool
    parameter_only_change: bool
    source_proof_directly_reusable: bool
    naturalness_score: int = Field(ge=0, le=100)
    knowledge_alignment_score: int = Field(ge=0, le=100)
    proof_rigor_score: int = Field(ge=0, le=100)
    difficulty_fit_score: int = Field(ge=0, le=100)
    teaching_value_score: int = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list, max_length=5)
    verification_summary: str = Field(min_length=1, max_length=1000)
    candidate_mpr: MPRCore
    relation: MPRRelation

    @model_validator(mode="after")
    def validate_acceptance(self) -> "SimilarPracticeCandidateReview":
        """中文：确保数学失败、条件缺失或关系不确定时不能接受候选题。 English: Ensures a candidate cannot be accepted after math, condition, or relation uncertainty."""

        if self.accepted and (
            self.mathematical_correctness != "passed"
            or self.condition_completeness != "passed"
            or not self.teaching_goal_met
            or self.relation.review_status != "accepted"
        ):
            raise ValueError("accepted review must pass math, conditions, teaching, and MPR relation")
        return self


class MotherProblemAnalysis(BaseModel):
    """中文：保存母题 MPR 及用于受控变式的设计边界。 English: Stores the mother-problem MPR and controlled-variation boundaries."""

    mpr: MPRCore
    mechanical_routine_risk: list[str] = Field(min_length=1, max_length=20)
    mutable_dimensions: list[str] = Field(min_length=1, max_length=30)
    method_breaking_changes: list[str] = Field(min_length=1, max_length=30)
    migration_directions: list[str] = Field(min_length=1, max_length=30)

    @property
    def knowledge_points(self) -> list[str]:
        """中文：兼容既有变式规划代码读取知识点。 English: Exposes knowledge points for the existing variation planner."""
        return self.mpr.knowledge_points

    @property
    def prerequisite_knowledge(self) -> list[str]:
        """中文：兼容读取母题先修知识。 English: Exposes mother-problem prerequisites."""
        return self.mpr.prerequisite_knowledge

    @property
    def mathematical_objects(self) -> list[str]:
        """中文：兼容读取母题数学对象。 English: Exposes mother-problem mathematical objects."""
        return self.mpr.mathematical_objects

    @property
    def structure_type(self) -> str:
        """中文：兼容读取母题规范结构。 English: Exposes the canonical structure type."""
        return self.mpr.canonical_structure.structure_type

    @property
    def relation_form(self) -> str:
        """中文：兼容读取母题关系形式。 English: Exposes the canonical relation form."""
        return self.mpr.canonical_structure.relation_form

    @property
    def function_family(self) -> str:
        """中文：兼容读取母题函数族。 English: Exposes the canonical function family."""
        return self.mpr.canonical_structure.function_family

    @property
    def problem_goals(self) -> list[str]:
        """中文：兼容读取母题求解目标。 English: Exposes the mother-problem goal."""
        return [self.mpr.goal.expression]

    @property
    def proof_obligations(self) -> list[str]:
        """中文：兼容读取证明义务。 English: Exposes proof obligations."""
        return self.mpr.proof_obligations

    @property
    def strategies(self) -> list[str]:
        """中文：兼容读取主要及辅助策略。 English: Exposes primary and secondary strategies."""
        return [self.mpr.primary_method, *self.mpr.secondary_methods]

    @property
    def reasoning_steps(self) -> list[str]:
        """中文：兼容读取有序策略步骤。 English: Exposes ordered reasoning steps."""
        return [f"{step.method}：{step.purpose}" for step in self.mpr.strategy_steps]

    @property
    def key_breakthrough(self) -> str:
        """中文：兼容读取关键突破口。 English: Exposes the key breakthrough."""
        return self.mpr.key_breakthrough


class SimilarPracticeVariationPlan(BaseModel):
    """中文：定义一次相似题生成必须保留、必须改变和禁止采用的内容。 English: Defines what a similar-practice generation must preserve, change, and avoid."""

    preserve: list[str] = Field(min_length=1, max_length=30)
    change: list[str] = Field(min_length=1, max_length=30)
    prohibited_shortcuts: list[str] = Field(min_length=1, max_length=20)
    expected_new_reasoning: str = Field(min_length=1, max_length=1000)


class SimilarPracticeConstraints(BaseModel):
    """中文：定义“similar·练习·constraints”类，封装该职责相关的数据与行为。
    English: Defines the similar practice constraints class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    The hard boundary used to create an immediate practice problem.
    """

    subject: str
    grade: str
    grade_band: str
    target_difficulty: int = Field(ge=1, le=3)
    target_knowledge_codes: list[str] = Field(min_length=1)
    learned_knowledge_codes: list[str] = Field(default_factory=list)
    allowed_knowledge_codes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "SimilarPracticeConstraints":
        """中文：处理“验证·范围”相关操作。
        English: Handles the validate scope operation.
        """
        allowed = set(self.allowed_knowledge_codes)
        if not set(self.target_knowledge_codes).issubset(allowed):
            raise ValueError("target knowledge must be inside the allowed learning scope")
        if not set(self.learned_knowledge_codes).issubset(allowed):
            raise ValueError("learned knowledge must be inside the allowed learning scope")
        return self


class GeneratedSimilarPractice(BaseModel):
    """中文：定义“generated·similar·练习”类，封装该职责相关的数据与行为。
    English: Defines the generated similar practice class and encapsulates data and behavior for that responsibility.
    """
    question: str = Field(min_length=1, max_length=5000)
    answer: str = Field(min_length=1)
    first_step_prompt: str = Field(min_length=1, max_length=500)
    subject: str
    grade: str
    grade_band: str
    difficulty: int = Field(ge=1, le=3)
    knowledge_point_codes: list[str] = Field(min_length=1)
    generator: str
    structure_level: StructureVariationLevel = "S1"
    reasoning_level: ReasoningVariationLevel = "M1"
    teaching_goal: TeachingGoal = "T2"
    variation_summary: str = Field(default="参数与条件受控变化", min_length=1, max_length=2000)
    new_reasoning_step: str | None = Field(default=None, max_length=2000)
    structure_type: str | None = Field(default=None, max_length=100)
    relation_form: str | None = Field(default=None, max_length=100)
    function_family: str | None = Field(default=None, max_length=100)
    key_strategy: str | None = Field(default=None, max_length=200)
    verification_summary: str | None = Field(default=None, max_length=2000)
    source_type: Literal["ai_original_variation"] = "ai_original_variation"
    mother_analysis: MotherProblemAnalysis | None = None
    variation_plan: SimilarPracticeVariationPlan | None = None
    mother_mpr: MPRCore | None = None
    candidate_mpr: MPRCore | None = None
    mpr_relation: MPRRelation | None = None

    def public_context(self, source_session_id: str) -> dict:
        """中文：处理“public·context”相关操作。
        English: Handles the public context operation.

        原有说明 / Existing notes:
        Return auditable metadata without exposing the private answer.
        """
        return {
            "source_session_id": source_session_id,
            "subject": self.subject,
            "grade": self.grade,
            "grade_band": self.grade_band,
            "difficulty": self.difficulty,
            "knowledge_point_codes": self.knowledge_point_codes,
            "generator": self.generator,
            "structure_level": self.structure_level,
            "reasoning_level": self.reasoning_level,
            "teaching_goal": self.teaching_goal,
            "variation_summary": self.variation_summary,
            "new_reasoning_step": self.new_reasoning_step,
            "structure_type": self.structure_type,
            "relation_form": self.relation_form,
            "function_family": self.function_family,
            "key_strategy": self.key_strategy,
            "verification_summary": self.verification_summary,
            "source_type": self.source_type,
            "mother_analysis": (
                self.mother_analysis.model_dump(mode="json")
                if self.mother_analysis is not None
                else None
            ),
            "variation_plan": (
                self.variation_plan.model_dump(mode="json")
                if self.variation_plan is not None
                else None
            ),
            "mother_mpr": (
                self.mother_mpr.model_dump(mode="json")
                if self.mother_mpr is not None
                else None
            ),
            "candidate_mpr": (
                self.candidate_mpr.model_dump(mode="json")
                if self.candidate_mpr is not None
                else None
            ),
            "mpr_relation": (
                self.mpr_relation.model_dump(mode="json")
                if self.mpr_relation is not None
                else None
            ),
            "constraint_check": "passed",
        }
