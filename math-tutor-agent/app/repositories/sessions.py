import sqlite3
from pathlib import Path

from app.domain.schemas import TutoringSession
from app.repositories.base import SessionVersionConflict


class InMemorySessionRepository:
    """中文：定义“in·memory·会话·仓储”类，封装该职责相关的数据与行为。
    English: Defines the in memory session repository class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Development repository. Replace with a persistent adapter before multi-worker deployment.
    """

    def __init__(self) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self._sessions: dict[str, TutoringSession] = {}

    def save(self, session: TutoringSession) -> TutoringSession:
        """中文：处理“保存”相关操作。
        English: Handles the save operation.
        """
        existing = self._sessions.get(session.id)
        if existing is None:
            if session.version != 0:
                raise SessionVersionConflict(session.id, session.version, None)
            session.version = 1
        else:
            if existing.version != session.version:
                raise SessionVersionConflict(session.id, session.version, existing.version)
            session.version += 1
        self._sessions[session.id] = session.model_copy(deep=True)
        return session

    def get(self, session_id: str) -> TutoringSession | None:
        """中文：处理“获取”相关操作。
        English: Handles the get operation.
        """
        session = self._sessions.get(session_id)
        return session.model_copy(deep=True) if session is not None else None

    def list(self, student_user_id: str) -> list[TutoringSession]:
        """中文：处理“列出”相关操作。
        English: Handles the list operation.
        """
        return sorted(
            (item for item in self._sessions.values() if item.student_user_id == student_user_id),
            key=lambda item: item.updated_at,
            reverse=True,
        )

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        return None


class SqliteSessionRepository:
    """中文：定义“sqlite·会话·仓储”类，封装该职责相关的数据与行为。
    English: Defines the sqlite session repository class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, database_url: str) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        if not database_url.startswith("sqlite:///"):
            raise ValueError("The prototype repository currently supports sqlite:/// URLs only")
        database_path = Path(database_url.removeprefix("sqlite:///")).expanduser()
        self.database_path = database_path if database_path.is_absolute() else Path.cwd() / database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        """中文：处理“connect”相关操作。
        English: Handles the connect operation.
        """
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        """中文：处理“initialize”相关操作。
        English: Handles the initialize operation.
        """
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tutoring_sessions (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, session: TutoringSession) -> TutoringSession:
        """中文：处理“保存”相关操作。
        English: Handles the save operation.
        """
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM tutoring_sessions WHERE id = ?",
                (session.id,),
            ).fetchone()
            actual_version = (
                TutoringSession.model_validate_json(row["payload"]).version if row else None
            )
            if row is None:
                if session.version != 0:
                    raise SessionVersionConflict(session.id, session.version, None)
                session.version = 1
                connection.execute(
                    "INSERT INTO tutoring_sessions (id, payload, updated_at) VALUES (?, ?, ?)",
                    (session.id, session.model_dump_json(), session.updated_at.isoformat()),
                )
            else:
                if actual_version != session.version:
                    raise SessionVersionConflict(session.id, session.version, actual_version)
                session.version += 1
                connection.execute(
                    "UPDATE tutoring_sessions SET payload = ?, updated_at = ? WHERE id = ?",
                    (session.model_dump_json(), session.updated_at.isoformat(), session.id),
                )
        return session

    def get(self, session_id: str) -> TutoringSession | None:
        """中文：处理“获取”相关操作。
        English: Handles the get operation.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM tutoring_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return TutoringSession.model_validate_json(row["payload"]) if row else None

    def list(self, student_user_id: str) -> list[TutoringSession]:
        """中文：处理“列出”相关操作。
        English: Handles the list operation.
        """
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM tutoring_sessions ORDER BY updated_at DESC").fetchall()
        sessions = [TutoringSession.model_validate_json(row["payload"]) for row in rows]
        return [item for item in sessions if item.student_user_id == student_user_id]

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        return None
