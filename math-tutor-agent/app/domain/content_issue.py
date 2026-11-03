from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ContentIssueType = Literal[
    "incorrect_answer",
    "incorrect_question",
    "incorrect_hint",
    "ambiguous_content",
    "answer_conflict",
    "other",
]


class StudentContentIssueRequest(BaseModel):
    """中文：定义“学生·内容·issue·请求”类，封装该职责相关的数据与行为。
    English: Defines the student content issue request class and encapsulates data and behavior for that responsibility.
    """
    problem_id: str | None = Field(default=None, max_length=36)
    issue_type: ContentIssueType
    description: str = Field(min_length=3, max_length=2000)
    client_report_id: str = Field(min_length=1, max_length=64)


class ContentIssueReportView(BaseModel):
    """中文：定义“内容·issue·报告·view”类，封装该职责相关的数据与行为。
    English: Defines the content issue report view class and encapsulates data and behavior for that responsibility.
    """
    id: str
    problem_id: str
    session_id: str | None = None
    reporter_user_id: str | None = None
    source: Literal["student_report", "runtime_answer_conflict"]
    issue_type: ContentIssueType
    description: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: Literal[
        "received",
        "revalidation_queued",
        "validating",
        "resolved",
        "dismissed",
    ]
    maintenance_job_id: str | None = None
    created_at: datetime
    updated_at: datetime


class RuntimeContentIssueResult(BaseModel):
    """中文：定义“runtime·内容·issue·结果”类，封装该职责相关的数据与行为。
    English: Defines the runtime content issue result class and encapsulates data and behavior for that responsibility.
    """
    report: ContentIssueReportView
    created: bool

