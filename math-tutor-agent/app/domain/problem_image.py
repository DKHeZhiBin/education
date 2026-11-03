from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ProblemImageStatus = Literal["pending", "processing", "ready", "failed"]
FormulaValidationStatus = Literal["not_checked", "valid", "needs_review", "invalid"]


class FormulaStructureIssue(BaseModel):
    """中文：描述公式结构检查发现的一项可定位问题。
    English: Describes one locatable issue found by formula structure validation.
    """

    code: str
    severity: Literal["warning", "error"]
    formula_index: int | None = Field(default=None, ge=0)
    message: str


class ConfirmProblemImageOCRRequest(BaseModel):
    """中文：接收学生核对并修正后的 OCR 题目与公式。
    English: Accepts OCR problem text and formulas reviewed and corrected by the student.
    """

    text: str = Field(min_length=1, max_length=20_000)
    formulas_latex: list[str] = Field(default_factory=list, max_length=50)


class ProblemImageUpload(BaseModel):
    """中文：定义“题目·图片·upload”类，封装该职责相关的数据与行为。
    English: Defines the problem image upload class and encapsulates data and behavior for that responsibility.
    """
    id: str
    status: ProblemImageStatus
    original_filename: str
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(ge=1)
    extracted_text: str | None = None
    error_code: str | None = None
    ocr_provider: str | None = None
    ocr_model: str | None = None
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    recognized_formulas: list[str] = Field(default_factory=list)
    formula_validation_status: FormulaValidationStatus = "not_checked"
    formula_validation_issues: list[FormulaStructureIssue] = Field(default_factory=list)
    student_confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    status_message: str
