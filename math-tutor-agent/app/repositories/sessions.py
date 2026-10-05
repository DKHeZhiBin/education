import sqlite3
from pathlib import Path

from app.domain.schemas import TutoringSession
from app.repositories.base import SessionVersionConflict


class InMemorySessionRepository:
    """Development repository. Replace with a persistent adapter before multi-worker deployment."""

    def __init__(self) -> None:
        self._sessions: dict[str, TutoringSession] = {}

    def save(self, session: TutoringSession) -> TutoringSession:
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
        session = self._sessions.get(session_id)
        return session.model_copy(deep=True) if session is not None else None

    def list(self, student_user_id: str) -> list[TutoringSession]:
        return sorted(
            (item for item in self._sessions.values() if item.student_user_id == student_user_id),
            key=lambda item: item.updated_at,
            reverse=True,
        )

    def close(self) -> None:
        return None


class SqliteSessionRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("The prototype repository currently supports sqlite:/// URLs only")
        database_path = Path(database_url.removeprefix("sqlite:///")).expanduser()
        self.database_path = database_path if database_path.is_absolute() else Path.cwd() / database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM tutoring_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return TutoringSession.model_validate_json(row["payload"]) if row else None

    def list(self, student_user_id: str) -> list[TutoringSession]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM tutoring_sessions ORDER BY updated_at DESC").fetchall()
        sessions = [TutoringSession.model_validate_json(row["payload"]) for row in rows]
        return [item for item in sessions if item.student_user_id == student_user_id]

    def close(self) -> None:
        return None
