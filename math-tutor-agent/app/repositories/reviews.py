from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.core.database import create_mysql_engine, create_session_factory
from app.domain.review import (
    ReviewAttemptRequest,
    ReviewKnowledgePoint,
    ReviewTask,
    ReviewTaskScope,
)
from app.mcp_tools.review_tools import calculate_review_schedule, mastery_after_review
from app.models import (
    LearningRecord,
    LearningRecordKnowledge,
    LearningSession,
    ReviewAttempt,
)


class ReviewTaskNotFound(LookupError):
    """中文：定义“复核·task·not·found”类，封装该职责相关的数据与行为。
    English: Defines the review task not found class and encapsulates data and behavior for that responsibility.
    """
    pass


class ReviewSessionInvalid(ValueError):
    """中文：定义“复核·会话·invalid”类，封装该职责相关的数据与行为。
    English: Defines the review session invalid class and encapsulates data and behavior for that responsibility.
    """
    pass


@dataclass(frozen=True)
class RecordedReviewAttempt:
    """中文：定义“recorded·复核·attempt”类，封装该职责相关的数据与行为。
    English: Defines the recorded review attempt class and encapsulates data and behavior for that responsibility.
    """
    attempt_id: str
    task: ReviewTask
    interval_days: int
    rationale: str


class ReviewRepository:
    """中文：定义“复核·仓储”类，封装该职责相关的数据与行为。
    English: Defines the review repository class and encapsulates data and behavior for that responsibility.
    """
    def __init__(
        self,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.engine = engine or create_mysql_engine()
        self.session_factory = session_factory or create_session_factory(self.engine)

    def list_tasks(
        self,
        student_user_id: str,
        *,
        scope: ReviewTaskScope,
        limit: int,
        now: datetime | None = None,
    ) -> list[ReviewTask]:
        """中文：处理“列出·tasks”相关操作。
        English: Handles the list tasks operation.
        """
        reference = self._naive_utc(now or datetime.now(timezone.utc))
        statement = (
            self._task_query()
            .where(
                LearningRecord.student_user_id == student_user_id,
                LearningRecord.next_review_at.is_not(None),
            )
            .order_by(LearningRecord.next_review_at, LearningRecord.created_at)
            .limit(limit)
        )
        if scope == "due":
            statement = statement.where(LearningRecord.next_review_at <= reference)
        elif scope == "upcoming":
            statement = statement.where(LearningRecord.next_review_at > reference)

        with self.session_factory() as db:
            records = db.scalars(statement).unique().all()
            return [self._task(record, reference) for record in records]

    def record_attempt(
        self,
        student_user_id: str,
        learning_record_id: str,
        request: ReviewAttemptRequest,
        *,
        reviewed_at: datetime | None = None,
    ) -> RecordedReviewAttempt:
        """中文：处理“记录·attempt”相关操作。
        English: Handles the record attempt operation.
        """
        reference = self._naive_utc(reviewed_at or datetime.now(timezone.utc))
        with self.session_factory.begin() as db:
            record = db.scalar(
                self._task_query()
                .where(
                    LearningRecord.id == learning_record_id,
                    LearningRecord.student_user_id == student_user_id,
                )
                .with_for_update()
            )
            if record is None:
                raise ReviewTaskNotFound(learning_record_id)

            if request.session_id is not None:
                review_session_owner = db.scalar(
                    select(LearningSession.student_user_id).where(
                        LearningSession.id == request.session_id
                    )
                )
                if review_session_owner != student_user_id:
                    raise ReviewSessionInvalid(request.session_id)

            correct_streak = self._independent_correct_streak(
                record.review_attempts,
                request.result,
                request.hint_level,
            )
            mastery_after = mastery_after_review(
                record.mastery_status,
                request.result,
                request.hint_level,
                correct_streak,
            )
            review_count = record.review_count + 1
            schedule = calculate_review_schedule(
                mastery_after,
                review_count,
                request.result,
                reference.date(),
            )
            if not schedule.ok or schedule.interval_days is None:
                raise ValueError(schedule.error or "无法计算下次复习时间")

            attempt = ReviewAttempt(
                learning_record_id=record.id,
                session_id=request.session_id,
                answer_text=request.answer_text,
                result=request.result,
                hint_level=request.hint_level,
                mastery_after=mastery_after,
                reviewed_at=reference,
            )
            db.add(attempt)
            record.review_count = review_count
            record.mastery_status = mastery_after
            record.next_review_at = reference + timedelta(days=schedule.interval_days)
            db.flush()

            return RecordedReviewAttempt(
                attempt_id=attempt.id,
                task=self._task(record, reference),
                interval_days=schedule.interval_days,
                rationale=schedule.rationale or "已安排下一次复习",
            )

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.engine.dispose()

    @staticmethod
    def _task_query():
        """中文：处理“task·query”相关操作。
        English: Handles the task query operation.
        """
        return select(LearningRecord).options(
            selectinload(LearningRecord.knowledge_links).selectinload(
                LearningRecordKnowledge.knowledge_point
            ),
            selectinload(LearningRecord.review_attempts),
        )

    @staticmethod
    def _task(record: LearningRecord, reference: datetime) -> ReviewTask:
        """中文：处理“task”相关操作。
        English: Handles the task operation.
        """
        if record.next_review_at is None:
            raise ValueError("复习记录缺少下次复习时间")
        return ReviewTask(
            learning_record_id=record.id,
            question=record.question_snapshot,
            learner_answer=record.learner_answer or "",
            error_reason=record.error_reason or "",
            correct_approach=record.correct_approach,
            difficulty=record.difficulty,
            mastery_status=record.mastery_status,
            review_count=record.review_count,
            due_at=ReviewRepository._aware_utc(record.next_review_at),
            status="due" if record.next_review_at <= reference else "upcoming",
            knowledge_points=[
                ReviewKnowledgePoint(
                    code=link.knowledge_point.code,
                    name=link.knowledge_point.name,
                    mistake_detected=link.mistake_detected,
                    mastery_status=link.mastery_status,
                )
                for link in record.knowledge_links
            ],
        )

    @staticmethod
    def _independent_correct_streak(
        attempts: list[ReviewAttempt],
        result: str,
        hint_level: int,
    ) -> int:
        """中文：处理“independent·correct·streak”相关操作。
        English: Handles the independent correct streak operation.
        """
        if result != "correct" or hint_level != 0:
            return 0
        streak = 1
        for attempt in sorted(
            attempts,
            key=lambda item: item.reviewed_at,
            reverse=True,
        ):
            if attempt.result != "correct" or attempt.hint_level != 0:
                break
            streak += 1
        return streak

    @staticmethod
    def _naive_utc(value: datetime) -> datetime:
        """中文：处理“naive·utc”相关操作。
        English: Handles the naive utc operation.
        """
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        """中文：处理“aware·utc”相关操作。
        English: Handles the aware utc operation.
        """
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
