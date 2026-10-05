from enum import IntEnum, StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class TutoringStatus(StrEnum):
    COLLECTING = "collecting"
    CLARIFYING = "clarifying"
    DIAGNOSING = "diagnosing"
    HINTING = "hinting"
    CHECKING_ATTEMPT = "checking_attempt"
    EXPLAINING = "explaining"
    COMPLETED = "completed"


class TutorAction(StrEnum):
    CLARIFY = "clarify"
    DIAGNOSE = "diagnose"
    HINT = "hint"
    CHECK_ATTEMPT = "check_attempt"
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"


class HintLevel(IntEnum):
    DIRECTION = 1
    KEY_RELATION = 2
    LOCAL_STEP = 3
    FULL_EXPLANATION = 4


class TutorSourceReference(BaseModel):
    """User-visible provenance for retrieved teaching claims and examples."""

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
    confidence: float = Field(ge=0, le=1)
