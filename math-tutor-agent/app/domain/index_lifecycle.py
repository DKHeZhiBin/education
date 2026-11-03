from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class IndexMaintenanceRequest(BaseModel):
    """中文：定义“索引·maintenance·请求”类，封装该职责相关的数据与行为。
    English: Defines the index maintenance request class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str = Field(min_length=1, max_length=36)
    trigger_type: Literal["retired", "revalidation", "version_update"]
    reason: str = Field(min_length=1, max_length=1000)
    replacement_problem_id: str | None = Field(default=None, max_length=36)
    expected_status_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_replacement(self) -> "IndexMaintenanceRequest":
        """中文：处理“验证·replacement”相关操作。
        English: Handles the validate replacement operation.
        """
        if self.trigger_type == "version_update":
            if not self.replacement_problem_id:
                raise ValueError(
                    "version_update requires replacement_problem_id"
                )
            if self.replacement_problem_id == self.problem_id:
                raise ValueError("version_update replacement must be a new problem")
        elif self.replacement_problem_id is not None:
            raise ValueError(
                "replacement_problem_id is only valid for version_update"
            )
        return self


class IndexMaintenanceJobView(BaseModel):
    """中文：定义“索引·maintenance·任务·view”类，封装该职责相关的数据与行为。
    English: Defines the index maintenance job view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    problem_id: str
    replacement_problem_id: str | None = None
    action: Literal["remove", "rebuild"]
    trigger_type: Literal["retired", "revalidation", "version_update"]
    reason: str
    expected_content_hash: str
    target_index_version: str
    point_ids: list[str]
    status: Literal[
        "pending",
        "deleting",
        "waiting_for_approval",
        "rebuilding",
        "completed",
        "failed",
        "cancelled",
    ]
    attempt_count: int
    last_error_code: str | None = None
    deletion_completed_at: datetime | None = None
    rebuild_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IndexMaintenanceRunSummary(BaseModel):
    """中文：定义“索引·maintenance·执行·summary”类，封装该职责相关的数据与行为。
    English: Defines the index maintenance run summary class and encapsulates data and behavior for that responsibility.
    """
    selected_count: int = 0
    completed_count: int = 0
    waiting_count: int = 0
    failed_job_ids: list[str] = Field(default_factory=list)
