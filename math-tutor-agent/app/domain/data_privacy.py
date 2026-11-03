from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class StudentDataExport(BaseModel):
    """中文：定义“学生·data·export”类，封装该职责相关的数据与行为。
    English: Defines the student data export class and encapsulates data and behavior for that responsibility.
    """
    format_version: Literal["1.0"] = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    account: dict[str, Any]
    student_profile: dict[str, Any]
    guardian_authorizations: list[dict[str, Any]] = Field(default_factory=list)
    learning_sessions: list[dict[str, Any]] = Field(default_factory=list)
    media_assets: list[dict[str, Any]] = Field(default_factory=list)
    content_issue_reports: list[dict[str, Any]] = Field(default_factory=list)
    stored_parent_reports: list[dict[str, Any]] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=lambda: [
        "password_hash",
        "access_tokens",
        "refresh_tokens",
        "account_action_tokens",
        "provider_api_keys",
        "internal_agent_artifacts",
    ])


class StudentAccountDeletionRequest(BaseModel):
    """中文：定义“学生·account·deletion·请求”类，封装该职责相关的数据与行为。
    English: Defines the student account deletion request class and encapsulates data and behavior for that responsibility.
    """
    current_password: str = Field(min_length=1, max_length=128)
    confirmation: Literal["DELETE_MY_ACCOUNT"]


class StudentAccountDeletionResult(BaseModel):
    """中文：定义“学生·account·deletion·结果”类，封装该职责相关的数据与行为。
    English: Defines the student account deletion result class and encapsulates data and behavior for that responsibility.
    """
    deleted_session_ids: list[str] = Field(default_factory=list)
    deleted_storage_keys: list[str] = Field(default_factory=list)
