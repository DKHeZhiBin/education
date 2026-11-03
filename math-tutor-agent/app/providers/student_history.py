from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.student_history import (
    RetrievedStudentHistory,
    StudentHistoryQuery,
    StudentKnowledgeHistory,
)
from app.models import KnowledgePoint, LearningRecord, LearningRecordKnowledge


@runtime_checkable
class StudentHistoryRetriever(Protocol):
    """中文：定义“学生·历史·retriever”类，封装该职责相关的数据与行为。
    English: Defines the student history retriever class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Private per-student retrieval boundary, separate from textbook RAG.
    """

    @property
    def name(self) -> str:
        """中文：处理“name”相关操作。
        English: Handles the name operation.
        """
        ...

    @property
    def available(self) -> bool:
        """中文：处理“available”相关操作。
        English: Handles the available operation.
        """
        ...

    def retrieve(self, query: StudentHistoryQuery) -> RetrievedStudentHistory:
        """中文：处理“检索”相关操作。
        English: Handles the retrieve operation.
        """
        ...

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        ...


class DisabledStudentHistoryRetriever:
    """中文：定义“disabled·学生·历史·retriever”类，封装该职责相关的数据与行为。
    English: Defines the disabled student history retriever class and encapsulates data and behavior for that responsibility.
    """
    name = "student_history_disabled"
    available = False

    def retrieve(self, query: StudentHistoryQuery) -> RetrievedStudentHistory:
        """中文：处理“检索”相关操作。
        English: Handles the retrieve operation.
        """
        return RetrievedStudentHistory(
            status="disabled",
            provider=self.name,
            query=query,
            limitations=["student history retrieval is disabled"],
        )

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        return None


class MySQLStudentHistoryRetriever:
    """中文：定义“my·sqlstudent·历史·retriever”类，封装该职责相关的数据与行为。
    English: Defines the my sqlstudent history retriever class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Read only structured learning evidence owned by exactly one student.
    """

    name = "mysql_student_history"
    available = True

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.session_factory = session_factory

    def retrieve(self, query: StudentHistoryQuery) -> RetrievedStudentHistory:
        """中文：处理“检索”相关操作。
        English: Handles the retrieve operation.
        """
        statement = (
            select(LearningRecordKnowledge, LearningRecord, KnowledgePoint)
            .join(LearningRecord, LearningRecord.id == LearningRecordKnowledge.learning_record_id)
            .join(KnowledgePoint, KnowledgePoint.id == LearningRecordKnowledge.knowledge_point_id)
            .where(
                LearningRecord.student_user_id == query.student_user_id,
                KnowledgePoint.subject == query.subject,
                KnowledgePoint.grade_band == query.grade_band,
                KnowledgePoint.active.is_(True),
            )
            .order_by(LearningRecord.created_at.desc())
            .limit(200)
        )
        if query.knowledge_points:
            statement = statement.where(or_(
                KnowledgePoint.code.in_(query.knowledge_points),
                KnowledgePoint.name.in_(query.knowledge_points),
            ))
        with self.session_factory() as db:
            rows = db.execute(statement).all()

        aggregated: dict[str, dict] = {}
        for link, record, point in rows:
            current = aggregated.get(point.code)
            if current is None:
                current = {
                    "knowledge_point_code": point.code,
                    "knowledge_point_name": point.name,
                    "encounter_count": 0,
                    "mistake_count": 0,
                    "effective_attempt_count": 0,
                    "highest_hint_level": 0,
                    "latest_mastery_status": link.mastery_status,
                    "latest_evidence": link.evidence,
                    "last_practiced_at": record.created_at,
                }
                aggregated[point.code] = current
            current["encounter_count"] += 1
            current["mistake_count"] += int(link.mistake_detected)
            current["effective_attempt_count"] += link.effective_attempt_count
            current["highest_hint_level"] = max(current["highest_hint_level"], link.hint_level)

        history = [
            StudentKnowledgeHistory.model_validate(item)
            for item in list(aggregated.values())[:query.limit]
        ]
        return RetrievedStudentHistory(
            status="success" if history else "no_results",
            provider=self.name,
            query=query,
            knowledge_history=history,
        )

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        return None
