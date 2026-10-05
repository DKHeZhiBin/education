from datetime import date, timedelta

from app.mcp_tools.contracts import ReviewScheduleResult


REVIEW_INTERVALS = (1, 3, 7, 14, 30, 60)


def calculate_review_schedule(
    mastery_status: str,
    review_count: int,
    last_result: str,
    reference_date: date | None = None,
) -> ReviewScheduleResult:
    """Calculate the next review date from mastery state and the latest review result."""
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
