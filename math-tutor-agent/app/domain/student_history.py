from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class StudentHistoryQuery(BaseModel):
    """中文：定义“学生·历史·query”类，封装该职责相关的数据与行为。
    English: Defines the student history query class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Private request whose owner id comes from the authenticated session.
    """

    data_scope: Literal["student_private"] = "student_private"
    student_user_id: str = Field(min_length=1, max_length=36)
    purpose: Literal["hint_personalization", "practice_scope"]
    subject: str = Field(min_length=1, max_length=24)
    grade_band: str = Field(min_length=1, max_length=24)
    knowledge_points: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=12, ge=1, le=30)


class StudentKnowledgeHistory(BaseModel):
    """中文：定义“学生·知识·历史”类，封装该职责相关的数据与行为。
    English: Defines the student knowledge history class and encapsulates data and behavior for that responsibility.
    """
    knowledge_point_code: str = Field(min_length=1, max_length=120)
    knowledge_point_name: str = Field(min_length=1, max_length=200)
    encounter_count: int = Field(ge=1)
    mistake_count: int = Field(ge=0)
    effective_attempt_count: int = Field(ge=0)
    highest_hint_level: int = Field(ge=0, le=4)
    latest_mastery_status: str = Field(min_length=1, max_length=20)
    latest_evidence: str | None = Field(default=None, max_length=500)
    last_practiced_at: datetime


class StudentHistoryAgentContext(BaseModel):
    """中文：定义“学生·历史·智能体·context”类，封装该职责相关的数据与行为。
    English: Defines the student history agent context class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Private, bounded projection allowed in a teaching prompt.
    """

    schema_version: Literal["1.0"] = "1.0"
    purpose: Literal["hint_personalization", "practice_scope"]
    knowledge_history: list[StudentKnowledgeHistory] = Field(default_factory=list, max_length=30)
    limitations: list[str] = Field(default_factory=list, max_length=4)


class RetrievedStudentHistory(BaseModel):
    """中文：定义“retrieved·学生·历史”类，封装该职责相关的数据与行为。
    English: Defines the retrieved student history class and encapsulates data and behavior for that responsibility.
    """
    schema_version: Literal["1.0"] = "1.0"
    data_scope: Literal["student_private"] = "student_private"
    status: Literal["success", "no_results", "disabled", "degraded"]
    provider: str = Field(min_length=1, max_length=80)
    query: StudentHistoryQuery
    knowledge_history: list[StudentKnowledgeHistory] = Field(default_factory=list, max_length=30)
    limitations: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_result(self) -> "RetrievedStudentHistory":
        """中文：处理“验证·结果”相关操作。
        English: Handles the validate result operation.
        """
        if self.status == "success" and not self.knowledge_history:
            raise ValueError("successful student history retrieval requires evidence")
        if self.status in {"no_results", "disabled"} and self.knowledge_history:
            raise ValueError(f"{self.status} student history cannot contain evidence")
        return self

    def to_agent_context(self) -> StudentHistoryAgentContext:
        """中文：处理“to·智能体·context”相关操作。
        English: Handles the to agent context operation.
        """
        return StudentHistoryAgentContext(
            purpose=self.query.purpose,
            knowledge_history=self.knowledge_history,
            limitations=self.limitations,
        )
