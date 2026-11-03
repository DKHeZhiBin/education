from enum import IntEnum, StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class TutoringStatus(StrEnum):
    """中文：定义“tutoring·状态”类，封装该职责相关的数据与行为。
    English: Defines the tutoring status class and encapsulates data and behavior for that responsibility.
    """
    COLLECTING = "collecting"
    CLARIFYING = "clarifying"
    DIAGNOSING = "diagnosing"
    HINTING = "hinting"
    CHECKING_ATTEMPT = "checking_attempt"
    EXPLAINING = "explaining"
    COMPLETED = "completed"


class TutorAction(StrEnum):
    """中文：定义“tutor·action”类，封装该职责相关的数据与行为。
    English: Defines the tutor action class and encapsulates data and behavior for that responsibility.
    """
    CLARIFY = "clarify"
    DIAGNOSE = "diagnose"
    HINT = "hint"
    CHECK_ATTEMPT = "check_attempt"
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"


class HintLevel(IntEnum):
    """中文：定义“提示·level”类，封装该职责相关的数据与行为。
    English: Defines the hint level class and encapsulates data and behavior for that responsibility.
    """
    DIRECTION = 1
    KEY_RELATION = 2
    LOCAL_STEP = 3
    FULL_EXPLANATION = 4


class TutorSourceReference(BaseModel):
    """中文：定义“tutor·source·reference”类，封装该职责相关的数据与行为。
    English: Defines the tutor source reference class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    User-visible provenance for retrieved teaching claims and examples.
    """

    source_reference_id: str | None = None
    document_id: str
    chunk_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    version: str | None = Field(default=None, max_length=100)
    source_url: HttpUrl | None = None
    locator: str | None = Field(default=None, max_length=255)
    supports: list[Literal[
        "concept",
        "principle",
        "example_pattern",
        "worked_example",
        "error_pattern",
        "hint",
        "source_fact",
    ]] = Field(default_factory=list, min_length=1)


class TutorReply(BaseModel):
    """中文：定义“tutor·reply”类，封装该职责相关的数据与行为。
    English: Defines the tutor reply class and encapsulates data and behavior for that responsibility.
    """
    action: TutorAction
    text: str
    hint_level: int | None = Field(default=None, ge=1, le=4)
    understanding_check: str | None = None
    solution_steps: list[str] = Field(default_factory=list)
    hint_stage: Literal[
        "direction",
        "key_relation",
        "local_step",
        "full_explanation",
    ] | None = None
    can_show_full_solution: bool = False
    sources: list[TutorSourceReference] = Field(default_factory=list, max_length=8)
    guidance_state: Literal[
        "exploring",
        "uncertain",
        "blocked",
        "remediating",
        "guided",
        "verifying",
        "reflecting",
        "transfer_test",
        "completed",
    ] | None = None
    current_goal_id: str | None = None
    current_goal_title: str | None = None
    current_goal_ordinal: int | None = Field(default=None, ge=1)
    completed_goal_count: int = Field(default=0, ge=0)
    total_goal_count: int = Field(default=0, ge=0)
    obstacle_type: Literal[
        "none",
        "knowledge_gap",
        "strategy_selection",
        "expression_transformation",
        "execution_error",
        "alternative_valid_path",
        "uncertain",
    ] | None = None
    attempt_verification: Literal["valid", "invalid", "unverified"] | None = None
    next_action: str | None = None
    confidence: float = Field(ge=0, le=1)
