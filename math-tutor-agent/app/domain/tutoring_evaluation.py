from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TutoringEvaluationTurn(BaseModel):
    """中文：定义端到端评估中的一轮学生输入。\n    English: Defines one student turn in an end-to-end tutoring evaluation.
    """

    id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    intent: Literal["answer", "ask_hint", "ask_solution", "complete"]


class TutoringStageOracle(BaseModel):
    """中文：定义某个流程阶段的冻结断言，只供评分器读取。\n    English: Defines frozen stage assertions that are visible only to the evaluator.
    """

    step_id: str = Field(min_length=1, max_length=80)
    expected_statuses: list[str] = Field(min_length=1, max_length=5)
    expected_actions: list[str] = Field(min_length=1, max_length=5)
    required_artifacts: list[str] = Field(default_factory=list, max_length=20)
    forbidden_artifacts: list[str] = Field(default_factory=list, max_length=20)
    required_reply_patterns: list[str] = Field(default_factory=list, max_length=20)
    forbidden_reply_patterns: list[str] = Field(default_factory=list, max_length=20)
    expected_hint_level: int | None = Field(default=None, ge=1, le=4)
    require_verification_passed: bool | None = None
    allowed_verification_coverage: list[Literal["none", "partial", "full"]] = Field(
        default_factory=list,
        max_length=3,
    )
    max_duration_ms: int = Field(default=60_000, ge=1000, le=600_000)
    answer_checkpoint: bool = False
    verification_honesty_checkpoint: bool = False
    hint_boundary_checkpoint: bool = False


class TutoringEvaluationInput(BaseModel):
    """中文：定义传给真实教学链路的输入，不包含参考答案。\n    English: Defines inputs passed to the live tutoring pipeline without oracle data.
    """

    question: str = Field(min_length=1, max_length=5000)
    subject: str = Field(default="数学", min_length=1, max_length=50)
    grade: str = Field(default="初中", min_length=1, max_length=50)
    turns: list[TutoringEvaluationTurn] = Field(default_factory=list, max_length=12)


class TutoringEvaluationCase(BaseModel):
    """中文：定义冻结的多 Agent 教学端到端评估案例。\n    English: Defines a frozen multi-agent tutoring end-to-end evaluation case.
    """

    id: str = Field(min_length=1, max_length=100)
    schema_version: Literal["1.0"] = "1.0"
    evaluation_only: Literal[True] = True
    split: Literal["tutoring_e2e_holdout"] = "tutoring_e2e_holdout"
    tags: list[str] = Field(min_length=1, max_length=20)
    input: TutoringEvaluationInput
    oracle: list[TutoringStageOracle] = Field(min_length=1, max_length=13)


class TutoringStageResult(BaseModel):
    """中文：记录单个教学阶段的输出、断言与失败原因。\n    English: Records one tutoring stage output, assertions, and failure reasons.
    """

    step_id: str
    passed: bool
    duration_ms: int
    status: str
    action: str
    hint_level: int | None = None
    artifact_kinds: list[str] = Field(default_factory=list)
    reply_text: str
    degraded: bool = False
    degradation_code: str | None = None
    failures: list[str] = Field(default_factory=list)
    answer_checkpoint_passed: bool | None = None
    verification_honesty_passed: bool | None = None
    hint_boundary_passed: bool | None = None


class TutoringCaseResult(BaseModel):
    """中文：汇总一个端到端案例的全部阶段结果。\n    English: Aggregates every stage result for one end-to-end case.
    """

    case_id: str
    passed: bool
    duration_ms: int
    stages: list[TutoringStageResult]
    error: str | None = None


class TutoringEvaluationMetrics(BaseModel):
    """中文：定义多 Agent 教学链路的核心质量指标。\n    English: Defines key quality metrics for the multi-agent tutoring pipeline.
    """

    case_pass_rate: float
    stage_pass_rate: float
    answer_correctness_rate: float | None = None
    verification_honesty_rate: float | None = None
    hint_leakage_rate: float | None = None
    timeout_rate: float


class TutoringEvaluationReport(BaseModel):
    """中文：定义可用于发布阻断的端到端评估报告。\n    English: Defines an end-to-end evaluation report suitable for release gating.
    """

    schema_version: Literal["1.0"] = "1.0"
    dataset_name: str
    dataset_sha256: str
    model_id: str
    prompt_version: str
    code_revision: str
    started_at: str
    finished_at: str
    metrics: TutoringEvaluationMetrics
    thresholds: dict[str, float]
    gate_status: Literal["passed", "blocked"]
    blockers: list[str] = Field(default_factory=list)
    cases: list[TutoringCaseResult]
