from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.knowledge import ProblemContentStatus


class CandidateValidationStage(StrEnum):
    """中文：定义“候选内容·验证·stage”类，封装该职责相关的数据与行为。
    English: Defines the candidate validation stage class and encapsulates data and behavior for that responsibility.
    """
    CONDITION_CHECK = "condition_check"
    INDEPENDENT_SOLVING = "independent_solving"
    SYMBOLIC_VERIFICATION = "symbolic_verification"
    NUMERIC_VERIFICATION = "numeric_verification"
    DUPLICATE_DETECTION = "duplicate_detection"
    LEAKAGE_DETECTION = "leakage_detection"
    INDEPENDENT_REVIEW = "independent_review"
    ADMISSION = "admission"
    INDEX_SYNC = "index_sync"


class CandidateValidationStep(BaseModel):
    """中文：定义“候选内容·验证·step”类，封装该职责相关的数据与行为。
    English: Defines the candidate validation step class and encapsulates data and behavior for that responsibility.
    """
    stage: CandidateValidationStage
    status: str
    evidence_ids: list[str] = Field(default_factory=list)
    detail: str | None = None


class CandidateValidationResult(BaseModel):
    """中文：定义“候选内容·验证·结果”类，封装该职责相关的数据与行为。
    English: Defines the candidate validation result class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str
    initial_status: ProblemContentStatus
    final_status: ProblemContentStatus
    solution_id: str | None = None
    steps: list[CandidateValidationStep] = Field(default_factory=list)
    model_calls: int = Field(default=0, ge=0)
    error_code: str | None = None
    error_detail: str | None = None


class CandidateValidationBatchResult(BaseModel):
    """中文：定义“候选内容·验证·批次·结果”类，封装该职责相关的数据与行为。
    English: Defines the candidate validation batch result class and encapsulates data and behavior for that responsibility.
    """
    generation_batch_id: str
    verifier_profile: str
    total_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    model_calls: int = Field(default=0, ge=0)
    results: list[CandidateValidationResult] = Field(default_factory=list)
