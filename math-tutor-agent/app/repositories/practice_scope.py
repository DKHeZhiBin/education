from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.product_scope import MVP_GRADE_BAND, MVP_GRADE_LABEL, MVP_SUBJECT_CODE
from app.domain.practice import SimilarPracticeConstraints
from app.domain.schemas import TutoringSession
from app.domain.student_history import StudentHistoryQuery
from app.models import KnowledgePoint
from app.providers.student_history import StudentHistoryRetriever


KNOWLEDGE_ALIASES: dict[str, str] = {}


class PracticeScopeRepository:
    """中文：定义“练习·范围·仓储”类，封装该职责相关的数据与行为。
    English: Defines the practice scope repository class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Build a generation allowlist from the student's persisted learning evidence.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        student_history_retriever: StudentHistoryRetriever,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.session_factory = session_factory
        self.student_history_retriever = student_history_retriever

    def constraints_for(
        self,
        source: TutoringSession,
        *,
        target_difficulty: int,
    ) -> SimilarPracticeConstraints:
        """中文：处理“constraints·for”相关操作。
        English: Handles the constraints for operation.
        """
        solution = self._latest_payload(source, "solution_plan")
        raw_targets = [
            str(value).strip()
            for value in solution.get("knowledge_points", [])
            if str(value).strip()
        ]
        subject = MVP_SUBJECT_CODE
        with self.session_factory() as db:
            grade_band = MVP_GRADE_BAND
            target_codes = self._resolve_codes(db, raw_targets, subject, grade_band)
        history = self.student_history_retriever.retrieve(StudentHistoryQuery(
            student_user_id=source.student_user_id,
            purpose="practice_scope",
            subject=subject,
            grade_band=grade_band,
            limit=30,
        ))
        learned_codes = [
            item.knowledge_point_code
            for item in history.knowledge_history
        ]

        # The concept in the current teaching session is considered taught for
        # immediate consolidation even before the completion record is written.
        allowed = sorted(set(learned_codes) | set(target_codes))
        if not target_codes:
            raise ValueError("current session has no resolvable knowledge point")
        return SimilarPracticeConstraints(
            subject=subject,
            grade=MVP_GRADE_LABEL,
            grade_band=grade_band,
            target_difficulty=target_difficulty,
            target_knowledge_codes=target_codes,
            learned_knowledge_codes=sorted(set(learned_codes)),
            allowed_knowledge_codes=allowed,
        )

    @staticmethod
    def _resolve_codes(
        db: Session,
        values: list[str],
        subject: str,
        grade_band: str,
    ) -> list[str]:
        """中文：处理“解析·codes”相关操作。
        English: Handles the resolve codes operation.
        """
        result: list[str] = []
        for value in values:
            alias = KNOWLEDGE_ALIASES.get(value, value)
            point = db.scalar(select(KnowledgePoint).where(
                KnowledgePoint.active.is_(True),
                KnowledgePoint.subject == subject,
                KnowledgePoint.grade_band == grade_band,
                (KnowledgePoint.code == alias) | (KnowledgePoint.name == value),
            ))
            # A current-session label may not have been persisted yet. Keep a
            # namespaced token so it can still be enforced as an exact boundary.
            code = point.code if point is not None else f"session:{value}"
            if code not in result:
                result.append(code)
        return result

    @staticmethod
    def _latest_payload(source: TutoringSession, kind: str) -> dict:
        """中文：处理“latest·payload”相关操作。
        English: Handles the latest payload operation.
        """
        for artifact in reversed(source.artifacts):
            if artifact.kind == kind and artifact.status == "completed":
                return artifact.payload
        return {}
