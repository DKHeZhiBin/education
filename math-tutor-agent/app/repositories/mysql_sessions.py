from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.domain.schemas import (
    AgentArtifact as DomainAgentArtifact,
    LearnerProfile,
    LearningRecord as DomainLearningRecord,
    Message,
    TutoringSession,
)
from app.domain.tutoring import TutoringStatus
from app.models import (
    AgentArtifact,
    AgentRun,
    AgentRunStep,
    KnowledgePoint,
    LearningRecord,
    LearningRecordKnowledge,
    LearningSession,
    SessionMessage,
    StudentProfile,
)
from app.repositories.base import SessionVersionConflict


GRADE_TO_BAND = {
    "小学低年级": "primary_lower",
    "小学高年级": "primary_upper",
    "小学": "primary_upper",
    "初中": "middle",
    "高中": "high",
}
BAND_TO_GRADE = {
    "primary_lower": "小学低年级",
    "primary_upper": "小学高年级",
    "middle": "初中",
    "high": "高中",
}
SUBJECT_TO_CODE = {"数学": "math", "math": "math"}
CODE_TO_SUBJECT = {"math": "数学"}
MASTERY_TO_CODE = {"待巩固": "to_review", "巩固中": "reviewing", "已掌握": "mastered"}
CODE_TO_MASTERY = {value: key for key, value in MASTERY_TO_CODE.items()}


class MySQLSessionRepository:
    """Persists the complete tutoring-session aggregate in normalized MySQL tables."""

    def __init__(
        self,
        engine: Engine,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory

    def save(self, tutoring_session: TutoringSession) -> TutoringSession:
        next_version: int
        with self.session_factory.begin() as db:
            grade_band = self._grade_band(tutoring_session.profile.grade)
            if db.get(StudentProfile, tutoring_session.student_user_id) is None:
                raise ValueError("Tutoring session owner must be an existing student")

            values = self._session_values(tutoring_session, grade_band)
            if tutoring_session.version == 0:
                actual_version = db.scalar(select(LearningSession.version).where(
                    LearningSession.id == tutoring_session.id
                ))
                if actual_version is not None:
                    raise SessionVersionConflict(
                        tutoring_session.id,
                        tutoring_session.version,
                        actual_version,
                    )
                entity = LearningSession(
                    id=tutoring_session.id,
                    student_user_id=tutoring_session.student_user_id,
                    version=1,
                    started_at=self._to_mysql_datetime(tutoring_session.created_at),
                    **values,
                )
                db.add(entity)
                try:
                    db.flush()
                except IntegrityError as error:
                    raise SessionVersionConflict(
                        tutoring_session.id,
                        tutoring_session.version,
                        None,
                    ) from error
                next_version = 1
            else:
                expected_version = tutoring_session.version
                result = db.execute(
                    update(LearningSession)
                    .where(
                        LearningSession.id == tutoring_session.id,
                        LearningSession.student_user_id == tutoring_session.student_user_id,
                        LearningSession.version == expected_version,
                    )
                    .values(**values, version=LearningSession.version + 1)
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    row = db.execute(select(
                        LearningSession.student_user_id,
                        LearningSession.version,
                    ).where(LearningSession.id == tutoring_session.id)).one_or_none()
                    if row is not None and row.student_user_id != tutoring_session.student_user_id:
                        raise ValueError("Tutoring session ownership cannot be changed")
                    raise SessionVersionConflict(
                        tutoring_session.id,
                        expected_version,
                        row.version if row is not None else None,
                    )
                next_version = expected_version + 1
                entity = db.scalar(
                    self._aggregate_query().where(LearningSession.id == tutoring_session.id)
                )
                if entity is None:
                    raise SessionVersionConflict(
                        tutoring_session.id,
                        expected_version,
                        None,
                    )

            if tutoring_session.status == TutoringStatus.COMPLETED and entity.completed_at is None:
                entity.completed_at = self._to_mysql_datetime(tutoring_session.updated_at)

            self._sync_messages(entity, tutoring_session.messages)
            self._replace_agent_runs(db, entity, tutoring_session.artifacts)
            self._sync_learning_record(db, entity, tutoring_session.record)

        tutoring_session.version = next_version
        return tutoring_session

    @classmethod
    def _session_values(cls, tutoring_session: TutoringSession, grade_band: str) -> dict:
        problem_spec = next(
            (
                artifact.payload
                for artifact in reversed(tutoring_session.artifacts)
                if artifact.kind == "problem_spec"
            ),
            {},
        )
        return {
            "knowledge_problem_id": tutoring_session.knowledge_problem_id,
            "subject": SUBJECT_TO_CODE.get(
                tutoring_session.profile.subject,
                tutoring_session.profile.subject,
            ),
            "grade_band": grade_band,
            "question_text": tutoring_session.question,
            "normalized_question": problem_spec.get("normalized_question"),
            "status": tutoring_session.status.value,
            "hint_level": tutoring_session.hint_level,
            "attempt_count": tutoring_session.attempts,
            "updated_at": cls._to_mysql_datetime(tutoring_session.updated_at),
        }

    def get(self, session_id: str) -> TutoringSession | None:
        with self.session_factory() as db:
            entity = db.scalar(self._aggregate_query().where(LearningSession.id == session_id))
            return self._to_domain(entity) if entity is not None else None

    def list(self, student_user_id: str) -> list[TutoringSession]:
        with self.session_factory() as db:
            entities = db.scalars(
                self._aggregate_query()
                .where(LearningSession.student_user_id == student_user_id)
                .order_by(LearningSession.updated_at.desc())
            ).unique().all()
            return [self._to_domain(entity) for entity in entities]

    def close(self) -> None:
        self.engine.dispose()

    @staticmethod
    def _aggregate_query():
        return select(LearningSession).options(
            selectinload(LearningSession.messages),
            selectinload(LearningSession.student),
            selectinload(LearningSession.agent_runs)
            .selectinload(AgentRun.steps)
            .selectinload(AgentRunStep.artifacts),
            selectinload(LearningSession.learning_record)
            .selectinload(LearningRecord.knowledge_links)
            .selectinload(LearningRecordKnowledge.knowledge_point),
        )

    @staticmethod
    def _sync_messages(entity: LearningSession, messages: list[Message]) -> None:
        existing = {message.id: message for message in entity.messages}
        incoming_ids = {message.id for message in messages}
        entity.messages[:] = [message for message in entity.messages if message.id in incoming_ids]

        for sequence_no, domain_message in enumerate(messages, start=1):
            message = existing.get(domain_message.id)
            if message is None:
                message = SessionMessage(id=domain_message.id)
                entity.messages.append(message)
            message.sequence_no = sequence_no
            message.role = domain_message.role
            message.content = domain_message.content
            message.intent = domain_message.intent
            message.client_turn_id = domain_message.client_turn_id
            message.created_at = MySQLSessionRepository._to_mysql_datetime(
                domain_message.created_at
            )

    @staticmethod
    def _replace_agent_runs(
        db: Session,
        entity: LearningSession,
        artifacts: list[DomainAgentArtifact],
    ) -> None:
        if entity.agent_runs:
            entity.agent_runs.clear()
            db.flush()

        artifacts_by_run: dict[str, list[DomainAgentArtifact]] = defaultdict(list)
        for artifact in artifacts:
            artifacts_by_run[artifact.run_id].append(artifact)

        for run_id, run_artifacts in artifacts_by_run.items():
            duration_ms = sum(item.duration_ms for item in run_artifacts)
            run = AgentRun(
                id=run_id,
                trigger_type="session_turn",
                status="completed",
                max_agent_calls=max(1, len(run_artifacts)),
                agent_call_count=len(run_artifacts),
                duration_ms=duration_ms,
                started_at=MySQLSessionRepository._to_mysql_datetime(
                    min(item.created_at for item in run_artifacts)
                ),
                finished_at=MySQLSessionRepository._to_mysql_datetime(
                    max(item.created_at for item in run_artifacts)
                ),
            )
            entity.agent_runs.append(run)
            for step_no, domain_artifact in enumerate(run_artifacts, start=1):
                step = AgentRunStep(
                    step_no=step_no,
                    agent_name=domain_artifact.agent,
                    status=domain_artifact.status,
                    artifact_kind=domain_artifact.kind,
                    confidence=Decimal(str(domain_artifact.confidence)),
                    duration_ms=domain_artifact.duration_ms,
                    created_at=MySQLSessionRepository._to_mysql_datetime(
                        domain_artifact.created_at
                    ),
                )
                step.artifacts.append(AgentArtifact(
                    session_id=entity.id,
                    kind=domain_artifact.kind,
                    schema_version=domain_artifact.schema_version,
                    payload_json=domain_artifact.payload,
                    created_at=MySQLSessionRepository._to_mysql_datetime(
                        domain_artifact.created_at
                    ),
                ))
                run.steps.append(step)

    def _sync_learning_record(
        self,
        db: Session,
        entity: LearningSession,
        domain_record: DomainLearningRecord | None,
    ) -> None:
        if domain_record is None:
            if entity.learning_record is not None:
                entity.learning_record = None
            return

        record = entity.learning_record
        if record is None:
            record = LearningRecord(
                id=domain_record.id,
                student_user_id=entity.student_user_id,
                created_at=self._record_datetime(domain_record.date),
            )
            entity.learning_record = record

        record.question_snapshot = domain_record.question
        record.learner_answer = domain_record.learner_answer or None
        record.error_reason = domain_record.error_reason or None
        record.correct_approach = domain_record.correct_approach
        record.difficulty = domain_record.difficulty
        record.mastery_status = MASTERY_TO_CODE.get(domain_record.mastery, domain_record.mastery)
        record.review_count = domain_record.review_count

        if record.knowledge_links:
            record.knowledge_links.clear()
            db.flush()
        for tag in dict.fromkeys(domain_record.knowledge_tags):
            knowledge_point = self._get_or_create_knowledge_point(
                db,
                tag,
                entity.subject,
                entity.grade_band,
            )
            record.knowledge_links.append(LearningRecordKnowledge(
                knowledge_point=knowledge_point,
                relation_type="primary",
            ))

    @staticmethod
    def _get_or_create_knowledge_point(
        db: Session,
        name: str,
        subject: str,
        grade_band: str,
    ) -> KnowledgePoint:
        digest = sha256(f"{subject}:{grade_band}:{name}".encode("utf-8")).hexdigest()[:24]
        code = f"auto:{subject}:{grade_band}:{digest}"
        knowledge_point = db.scalar(select(KnowledgePoint).where(KnowledgePoint.code == code))
        if knowledge_point is None:
            knowledge_point = KnowledgePoint(
                subject=subject,
                grade_band=grade_band,
                code=code,
                name=name,
            )
            db.add(knowledge_point)
            db.flush()
        return knowledge_point

    @staticmethod
    def _to_domain(entity: LearningSession) -> TutoringSession:
        artifacts: list[DomainAgentArtifact] = []
        for run in sorted(entity.agent_runs, key=lambda item: item.started_at):
            for step in sorted(run.steps, key=lambda item: item.step_no):
                for artifact in step.artifacts:
                    artifacts.append(DomainAgentArtifact(
                        run_id=run.id,
                        schema_version=artifact.schema_version,
                        agent=step.agent_name,
                        kind=artifact.kind,
                        payload=artifact.payload_json,
                        status=step.status,
                        duration_ms=step.duration_ms,
                        confidence=float(step.confidence or 0),
                        created_at=MySQLSessionRepository._to_utc(artifact.created_at),
                    ))

        domain_record = None
        if entity.learning_record is not None:
            record = entity.learning_record
            domain_record = DomainLearningRecord(
                id=record.id,
                date=record.created_at.date().isoformat(),
                subject=CODE_TO_SUBJECT.get(entity.subject, entity.subject),
                grade=BAND_TO_GRADE.get(entity.grade_band, entity.grade_band),
                question=record.question_snapshot,
                learner_answer=record.learner_answer or "",
                error_reason=record.error_reason or "",
                correct_approach=record.correct_approach,
                knowledge_tags=[link.knowledge_point.name for link in record.knowledge_links],
                difficulty=record.difficulty,
                mastery=CODE_TO_MASTERY.get(record.mastery_status, record.mastery_status),
                review_count=record.review_count,
            )

        return TutoringSession(
            id=entity.id,
            version=entity.version,
            student_user_id=entity.student_user_id,
            knowledge_problem_id=entity.knowledge_problem_id,
            profile=LearnerProfile(
                grade=BAND_TO_GRADE.get(entity.grade_band, entity.grade_band),
                subject=CODE_TO_SUBJECT.get(entity.subject, entity.subject),
            ),
            question=entity.question_text,
            status=TutoringStatus(entity.status),
            hint_level=entity.hint_level,
            attempts=entity.attempt_count,
            messages=[
                Message(
                    id=message.id,
                    role=message.role,
                    content=message.content,
                    intent=message.intent,
                    client_turn_id=message.client_turn_id,
                    created_at=MySQLSessionRepository._to_utc(message.created_at),
                )
                for message in entity.messages
            ],
            artifacts=artifacts,
            record=domain_record,
            created_at=MySQLSessionRepository._to_utc(entity.started_at),
            updated_at=MySQLSessionRepository._to_utc(entity.updated_at),
        )

    @staticmethod
    def _grade_band(grade: str) -> str:
        return GRADE_TO_BAND.get(grade, grade if grade in BAND_TO_GRADE else "middle")

    @staticmethod
    def _to_mysql_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _record_datetime(value: str) -> datetime:
        return datetime.combine(date.fromisoformat(value), time.min)
