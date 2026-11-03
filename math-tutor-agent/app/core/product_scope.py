"""Fixed product scope for the first university calculus MVP."""

from typing import Final


MVP_SUBJECT_CODE: Final = "math"
MVP_SUBJECT_LABEL: Final = "数学"
MVP_GRADE_BAND: Final = "university"
MVP_GRADE_LABEL: Final = "大学"
MVP_PRODUCT_NAME: Final = "大学高等数学"
MVP_DEFAULT_ROOT_CODE: Final = "UC.C1"


def is_mvp_scope(subject: str | None, grade_band: str | None) -> bool:
    """中文：判断内容是否属于大学高数 MVP。 English: Checks whether content belongs to the university-calculus MVP scope."""

    return subject == MVP_SUBJECT_CODE and grade_band == MVP_GRADE_BAND
