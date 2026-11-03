from datetime import date, timedelta

from app.mcp_tools.contracts import ReviewScheduleResult


REVIEW_INTERVALS = (1, 3, 7, 14, 30, 60)
INITIAL_REVIEW_INTERVALS = {
    "to_review": 1,
    "reviewing": 3,
    "mastered": 14,
}


def calculate_initial_review_schedule(
    mastery_status: str,
    reference_date: date | None = None,
) -> ReviewScheduleResult:
    """中文：处理“计算·initial·复核·schedule”相关操作。
    English: Handles the calculate initial review schedule operation.

    原有说明 / Existing notes:
    Schedule the first review from the evidence-backed session outcome.
    """
    interval = INITIAL_REVIEW_INTERVALS.get(mastery_status)
    if interval is None:
        return ReviewScheduleResult(
            ok=False,
            mastery_status=mastery_status,
            review_count=0,
            error="未知的掌握状态",
        )
    start = reference_date or date.today()
    rationale = {
        "to_review": "本轮仍需巩固，次日安排首次复习",
        "reviewing": "本轮已有部分掌握，三日后安排首次复习",
        "mastered": "本轮证据较充分，两周后安排保持性复习",
    }[mastery_status]
    return ReviewScheduleResult(
        ok=True,
        mastery_status=mastery_status,
        review_count=0,
        interval_days=interval,
        next_review_date=start + timedelta(days=interval),
        rationale=rationale,
    )


def mastery_after_review(
    current_status: str,
    result: str,
    hint_level: int,
    independent_correct_streak: int,
) -> str:
    """中文：处理“掌握度·after·复核”相关操作。
    English: Handles the mastery after review operation.

    原有说明 / Existing notes:
    Derive a review state without turning one answer into a permanent label.
    """
    if result == "incorrect":
        return "to_review"
    if result == "partial" or hint_level > 0:
        return "reviewing"
    if current_status == "mastered" or independent_correct_streak >= 2:
        return "mastered"
    return "reviewing"


def calculate_review_schedule(
    mastery_status: str,
    review_count: int,
    last_result: str,
    reference_date: date | None = None,
) -> ReviewScheduleResult:
    """中文：处理“计算·复核·schedule”相关操作。
    English: Handles the calculate review schedule operation.

    原有说明 / Existing notes:
    Calculate the next review date from mastery state and the latest review result.
    """
    if mastery_status not in {"to_review", "reviewing", "mastered"}:
        return ReviewScheduleResult(
            ok=False,
            mastery_status=mastery_status,
            review_count=review_count,
            error="未知的掌握状态",
        )
    if last_result not in {"correct", "partial", "incorrect"}:
        return ReviewScheduleResult(
            ok=False,
            mastery_status=mastery_status,
            review_count=review_count,
            error="未知的复习结果",
        )
    if review_count < 0:
        return ReviewScheduleResult(
            ok=False,
            mastery_status=mastery_status,
            review_count=review_count,
            error="review_count 不能小于 0",
        )

    if last_result == "incorrect":
        interval = 1
        rationale = "本次仍未掌握，次日再次复习"
    elif last_result == "partial":
        interval = 3
        rationale = "本次部分正确，缩短复习间隔"
    else:
        index = min(review_count, len(REVIEW_INTERVALS) - 1)
        interval = REVIEW_INTERVALS[index]
        if mastery_status == "mastered":
            interval = max(interval, 14)
        rationale = "本次正确，按复习次数逐步拉长间隔"

    start = reference_date or date.today()
    return ReviewScheduleResult(
        ok=True,
        mastery_status=mastery_status,
        review_count=review_count,
        interval_days=interval,
        next_review_date=start + timedelta(days=interval),
        rationale=rationale,
    )
