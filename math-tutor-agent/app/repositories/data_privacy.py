from __future__ import annotations

from datetime import timezone

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.domain.data_privacy import StudentAccountDeletionResult, StudentDataExport
from app.models import (
    AccountActionToken,
    ContentIssueReport,
    GuardianStudentLink,
    LearningRecord,
    LearningRecordKnowledge,
    LearningSession,
    MediaAsset,
    ParentReport,
    RefreshSession,
    StudentProfile,
    User,
)


class StudentDataNotFound(LookupError):
    """中文：定义“学生·data·not·found”类，封装该职责相关的数据与行为。
    English: Defines the student data not found class and encapsulates data and behavior for that responsibility.
    """
    pass


class StudentDataRepository:
    """中文：定义“学生·data·仓储”类，封装该职责相关的数据与行为。
    English: Defines the student data repository class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, engine: Engine, session_factory: sessionmaker[Session]) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.engine = engine
        self.session_factory = session_factory

    def export(self, student_user_id: str) -> StudentDataExport:
        """中文：处理“export”相关操作。
        English: Handles the export operation.
        """
        with self.session_factory() as db:
            user = db.get(User, student_user_id)
            profile = db.get(StudentProfile, student_user_id)
            if user is None or profile is None or user.role != "student":
                raise StudentDataNotFound(student_user_id)
            sessions = db.scalars(
                select(LearningSession)
                .where(LearningSession.student_user_id == student_user_id)
                .options(
                    selectinload(LearningSession.messages),
                    selectinload(LearningSession.learning_record)
                    .selectinload(LearningRecord.knowledge_links)
                    .selectinload(LearningRecordKnowledge.knowledge_point),
                    selectinload(LearningSession.learning_record)
                    .selectinload(LearningRecord.review_attempts),
                )
                .order_by(LearningSession.started_at)
            ).unique().all()
            links = db.scalars(select(GuardianStudentLink).where(
                GuardianStudentLink.student_user_id == student_user_id
            )).all()
            media = db.scalars(select(MediaAsset).where(
                MediaAsset.owner_user_id == student_user_id
            ).order_by(MediaAsset.created_at)).all()
            reports = db.scalars(select(ParentReport).where(
                ParentReport.student_user_id == student_user_id
            ).order_by(ParentReport.period_start)).all()
            issues = db.scalars(select(ContentIssueReport).where(
                ContentIssueReport.reporter_user_id == student_user_id
            ).order_by(ContentIssueReport.created_at)).all()

            return StudentDataExport(
                account={
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "account_status": user.account_status,
                    "email_verified_at": self._iso(user.email_verified_at),
                    "created_at": self._iso(user.created_at),
                    "updated_at": self._iso(user.updated_at),
                },
                student_profile={
                    "display_name": profile.display_name,
                    "grade_band": profile.grade_band,
                    "preferred_explanation_style": profile.preferred_explanation_style,
                    "created_at": self._iso(profile.created_at),
                    "updated_at": self._iso(profile.updated_at),
                },
                guardian_authorizations=[{
                    "id": link.id,
                    "guardian_user_id": link.guardian_user_id,
                    "relationship": link.relationship_type,
                    "status": link.status,
                    "consented_at": self._iso(link.consented_at),
                    "created_at": self._iso(link.created_at),
                } for link in links],
                learning_sessions=[self._session_export(item) for item in sessions],
                media_assets=[{
                    "id": item.id,
                    "session_id": item.session_id,
                    "media_type": item.media_type,
                    "original_filename": item.original_filename,
                    "mime_type": item.mime_type,
                    "size_bytes": item.size_bytes,
                    "content_sha256": item.content_sha256,
                    "processing_status": item.processing_status,
                    "extracted_text": item.extracted_text,
                    "error_code": item.error_code,
                    "expires_at": self._iso(item.expires_at),
                    "created_at": self._iso(item.created_at),
                } for item in media],
                content_issue_reports=[{
                    "id": item.id,
                    "problem_id": item.problem_id,
                    "session_id": item.session_id,
                    "issue_type": item.issue_type,
                    "description": item.description,
                    "status": item.status,
                    "created_at": self._iso(item.created_at),
                    "updated_at": self._iso(item.updated_at),
                } for item in issues],
                stored_parent_reports=[{
                    "id": item.id,
                    "period_type": item.period_type,
                    "period_start": item.period_start.isoformat(),
                    "period_end": item.period_end.isoformat(),
                    "metrics": item.metrics_json,
                    "content_markdown": item.content_markdown,
                    "status": item.status,
                    "generated_at": self._iso(item.generated_at),
                } for item in reports],
            )

    def deletion_targets(self, student_user_id: str) -> StudentAccountDeletionResult:
        """中文：处理“deletion·targets”相关操作。
        English: Handles the deletion targets operation.
        """
        with self.session_factory() as db:
            profile = db.get(StudentProfile, student_user_id)
            if profile is None:
                raise StudentDataNotFound(student_user_id)
            return StudentAccountDeletionResult(
                deleted_session_ids=list(db.scalars(select(LearningSession.id).where(
                    LearningSession.student_user_id == student_user_id
                ))),
                deleted_storage_keys=list(db.scalars(select(MediaAsset.storage_key).where(
                    MediaAsset.owner_user_id == student_user_id
                ))),
            )

    def delete_student_data(self, student_user_id: str) -> StudentAccountDeletionResult:
        """中文：处理“删除·学生·data”相关操作。
        English: Handles the delete student data operation.
        """
        with self.session_factory.begin() as db:
            user = db.get(User, student_user_id, with_for_update=True)
            profile = db.get(StudentProfile, student_user_id)
            if user is None or profile is None or user.role != "student":
                raise StudentDataNotFound(student_user_id)
            session_ids = list(db.scalars(select(LearningSession.id).where(
                LearningSession.student_user_id == student_user_id
            )))
            storage_keys = list(db.scalars(select(MediaAsset.storage_key).where(
                MediaAsset.owner_user_id == student_user_id
            )))

            db.execute(update(ContentIssueReport).where(
                ContentIssueReport.reporter_user_id == student_user_id
            ).values(reporter_user_id=None))
            db.execute(delete(ParentReport).where(
                ParentReport.student_user_id == student_user_id
            ))
            db.execute(delete(LearningSession).where(
                LearningSession.student_user_id == student_user_id
            ))
            db.execute(delete(MediaAsset).where(
                MediaAsset.owner_user_id == student_user_id
            ))
            db.execute(delete(GuardianStudentLink).where(
                GuardianStudentLink.student_user_id == student_user_id
            ))
            db.execute(delete(AccountActionToken).where(
                AccountActionToken.user_id == student_user_id
            ))
            db.execute(delete(RefreshSession).where(
                RefreshSession.user_id == student_user_id
            ))
            db.execute(delete(StudentProfile).where(
                StudentProfile.user_id == student_user_id
            ))

            now = self._naive_now()
            user.email = f"deleted+{student_user_id}@invalid.local"
            user.password_hash = "deleted"
            user.account_status = "deleted"
            user.token_version += 1
            user.last_login_at = None
            user.email_verified_at = None
            user.deleted_at = now
            return StudentAccountDeletionResult(
                deleted_session_ids=session_ids,
                deleted_storage_keys=storage_keys,
            )

    @classmethod
    def _session_export(cls, session: LearningSession) -> dict:
        """中文：处理“会话·export”相关操作。
        English: Handles the session export operation.
        """
        record = session.learning_record
        return {
            "id": session.id,
            "subject": session.subject,
            "grade_band": session.grade_band,
            "question": session.question_text,
            "status": session.status,
            "hint_level": session.hint_level,
            "attempt_count": session.attempt_count,
            "started_at": cls._iso(session.started_at),
            "completed_at": cls._iso(session.completed_at),
            "messages": [{
                "role": message.role,
                "content": message.content,
                "intent": message.intent,
                "created_at": cls._iso(message.created_at),
            } for message in session.messages],
            "learning_record": None if record is None else {
                "id": record.id,
                "question": record.question_snapshot,
                "learner_answer": record.learner_answer,
                "error_category": record.error_category,
                "error_reason": record.error_reason,
                "correct_approach": record.correct_approach,
                "difficulty": record.difficulty,
                "mastery_status": record.mastery_status,
                "review_count": record.review_count,
                "next_review_at": cls._iso(record.next_review_at),
                "knowledge_points": [{
                    "code": link.knowledge_point.code,
                    "name": link.knowledge_point.name,
                    "relation_type": link.relation_type,
                    "evidence": link.evidence,
                    "mistake_detected": link.mistake_detected,
                    "error_category": link.error_category,
                    "hint_level": link.hint_level,
                    "effective_attempt_count": link.effective_attempt_count,
                    "mastery_status": link.mastery_status,
                } for link in record.knowledge_links],
                "review_attempts": [{
                    "answer_text": attempt.answer_text,
                    "result": attempt.result,
                    "hint_level": attempt.hint_level,
                    "mastery_after": attempt.mastery_after,
                    "reviewed_at": cls._iso(attempt.reviewed_at),
                } for attempt in record.review_attempts],
            },
        }

    @staticmethod
    def _iso(value) -> str | None:
        """中文：处理“iso”相关操作。
        English: Handles the iso operation.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _naive_now():
        """中文：处理“naive·now”相关操作。
        English: Handles the naive now operation.
        """
        from datetime import datetime

        return datetime.now(timezone.utc).replace(tzinfo=None)
