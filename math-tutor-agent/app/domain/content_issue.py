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
    problem_id: str | None = Field(default=None, max_length=36)
    issue_type: ContentIssueType
    description: str = Field(min_length=3, max_length=2000)
    client_report_id: str = Field(min_length=1, max_length=64)


class ContentIssueReportView(BaseModel):
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
    report: ContentIssueReportView
    created: bool

