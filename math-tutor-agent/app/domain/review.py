from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ReviewResult = Literal["correct", "partial", "incorrect"]
ReviewTaskScope = Literal["due", "upcoming", "all"]


class ReviewKnowledgePoint(BaseModel):
    """中文：定义“复核·知识·point”类，封装该职责相关的数据与行为。
    English: Defines the review knowledge point class and encapsulates data and behavior for that responsibility.
    """
    code: str
    name: str
    mistake_detected: bool = False
    mastery_status: str


class ReviewTask(BaseModel):
    """中文：定义“复核·task”类，封装该职责相关的数据与行为。
    English: Defines the review task class and encapsulates data and behavior for that responsibility.
    """
    learning_record_id: str
    question: str
    learner_answer: str = ""
    error_reason: str = ""
    correct_approach: str
    difficulty: int = Field(ge=1, le=3)
    mastery_status: str
    review_count: int = Field(ge=0)
    due_at: datetime
    status: Literal["due", "upcoming"]
    knowledge_points: list[ReviewKnowledgePoint] = Field(default_factory=list)


class ReviewAttemptRequest(BaseModel):
    """中文：定义“复核·attempt·请求”类，封装该职责相关的数据与行为。
    English: Defines the review attempt request class and encapsulates data and behavior for that responsibility.
    """
    answer_text: str = Field(min_length=1, max_length=5000)
    result: ReviewResult
    hint_level: int = Field(default=0, ge=0, le=4)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)


class ReviewAttemptResponse(BaseModel):
    """中文：定义“复核·attempt·响应”类，封装该职责相关的数据与行为。
    English: Defines the review attempt response class and encapsulates data and behavior for that responsibility.
    """
    attempt_id: str
    task: ReviewTask
    interval_days: int = Field(ge=1)
    rationale: str
