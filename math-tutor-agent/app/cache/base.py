from contextlib import AbstractContextManager
from typing import Protocol

from app.domain.schemas import TutoringSession
from app.harness.contracts import HarnessRunResult


class SessionLockBusy(Exception):
    """Raised when another worker is already changing the same session."""


class RuntimeCoordinationUnavailable(Exception):
    """Raised when strict Redis coordination cannot be guaranteed."""


class RuntimeCache(Protocol):
    def get_session(self, session_id: str) -> TutoringSession | None: ...

    def set_session(self, session: TutoringSession) -> None: ...

    def delete_session(self, session_id: str) -> None: ...

    def get_run_result(self, session_id: str, client_turn_id: str) -> HarnessRunResult | None: ...

    def set_run_result(
        self,
        session_id: str,
        client_turn_id: str,
        result: HarnessRunResult,
    ) -> None: ...

    def lock_session(self, session_id: str) -> AbstractContextManager[None]: ...

    def close(self) -> None: ...
