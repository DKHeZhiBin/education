from typing import Protocol

from app.domain.schemas import TutoringSession


class SessionVersionConflict(Exception):
    def __init__(self, session_id: str, expected_version: int, actual_version: int | None) -> None:
        self.session_id = session_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(f"Session {session_id} version conflict")


class SessionRepository(Protocol):
    def save(self, session: TutoringSession) -> TutoringSession: ...

    def get(self, session_id: str) -> TutoringSession | None: ...

    def list(self, student_user_id: str) -> list[TutoringSession]: ...

    def close(self) -> None: ...
