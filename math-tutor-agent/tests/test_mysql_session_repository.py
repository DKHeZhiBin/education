import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.domain.schemas import Message, TutoringSession
from app.models import LearningSession, StudentProfile, User
from app.repositories.base import SessionVersionConflict
from app.repositories.mysql_sessions import MySQLSessionRepository


RUN_MYSQL_TESTS = os.getenv("RUN_MYSQL_INTEGRATION_TESTS") == "1"


@unittest.skipUnless(RUN_MYSQL_TESTS, "set RUN_MYSQL_INTEGRATION_TESTS=1 to run MySQL integration tests")
class MySQLSessionRepositoryTests(unittest.TestCase):
    """中文：使用真实 MySQL 验证会话仓储和乐观锁边界。
    English: Uses real MySQL to verify session repository and optimistic locking boundaries.
    """

    def setUp(self) -> None:
        """中文：创建独立测试学生和仓储实例。
        English: Creates an isolated test student and repository instance.
        """
        database_url = os.getenv("MYSQL_TEST_DATABASE_URL", settings.database_url)
        if settings.app_env != "development" and "MYSQL_TEST_DATABASE_URL" not in os.environ:
            self.fail("MYSQL_TEST_DATABASE_URL is required outside development")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )
        self.repository = MySQLSessionRepository(self.engine, self.session_factory)
        self.student_id = str(uuid4())
        self.session_ids: set[str] = set()
        with self.session_factory.begin() as db:
            db.add(User(
                id=self.student_id,
                email=f"repository-test-{self.student_id}@example.invalid",
                password_hash="not-a-login-credential",
                role="student",
                account_status="active",
                token_version=1,
            ))
            db.add(StudentProfile(
                user_id=self.student_id,
                display_name="Repository Test Student",
                grade_band="middle",
                current_grade=8,
                preferred_explanation_style="balanced",
            ))

    def tearDown(self) -> None:
        """中文：按外键顺序清理本测试创建的数据。
        English: Removes data created by the test in foreign-key-safe order.
        """
        with self.session_factory.begin() as db:
            if self.session_ids:
                db.execute(delete(LearningSession).where(LearningSession.id.in_(self.session_ids)))
            db.execute(delete(StudentProfile).where(StudentProfile.user_id == self.student_id))
            db.execute(delete(User).where(User.id == self.student_id))
        self.repository.close()

    def test_save_get_and_list_round_trip(self) -> None:
        """中文：新会话保存后可以按 ID 和学生列表完整读回。
        English: A new session can be read back by ID and student list after saving.
        """
        session = self._session()
        saved = self.repository.save(session)
        loaded = self.repository.get(session.id)
        listed = self.repository.list(self.student_id)

        self.assertEqual(saved.version, 1)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.question, session.question)
        self.assertEqual(loaded.messages[0].client_turn_id, "turn-1")
        self.assertIn(session.id, {item.id for item in listed})

    def test_update_increments_version_and_rejects_stale_write(self) -> None:
        """中文：更新增加版本号，旧版本写入触发乐观锁冲突。
        English: An update increments the version and a stale write raises a conflict.
        """
        session = self.repository.save(self._session())
        stale = session.model_copy(deep=True)
        session.messages.append(Message(
            role="student",
            content="我先尝试移项。",
            intent="answer",
            client_turn_id="turn-2",
        ))
        updated = self.repository.save(session)

        self.assertEqual(updated.version, 2)
        with self.assertRaises(SessionVersionConflict) as raised:
            self.repository.save(stale)
        self.assertEqual(raised.exception.expected_version, 1)
        self.assertEqual(raised.exception.actual_version, 2)

    def test_existing_session_owner_cannot_be_changed(self) -> None:
        """中文：已保存会话不能通过更新转移给其他学生。
        English: A persisted session cannot be reassigned to another student by update.
        """
        session = self.repository.save(self._session())
        session.student_user_id = str(uuid4())
        with self.assertRaises(ValueError):
            self.repository.save(session)

    def _session(self) -> TutoringSession:
        """中文：创建带客户端轮次 ID 的最小会话聚合。
        English: Creates a minimal session aggregate with a client turn ID.
        """
        session = TutoringSession(
            student_user_id=self.student_id,
            question="解方程 x² - 5x + 6 = 0",
            messages=[Message(
                role="student",
                content="解方程 x² - 5x + 6 = 0",
                intent="answer",
                client_turn_id="turn-1",
            )],
        )
        self.session_ids.add(session.id)
        return session


if __name__ == "__main__":
    unittest.main()
