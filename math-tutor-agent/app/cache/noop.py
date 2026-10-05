from contextlib import contextmanager
from collections.abc import Iterator

from app.domain.schemas import TutoringSession
from app.harness.contracts import HarnessRunResult


class NoOpRuntimeCache:
    """Local/degraded adapter that keeps the Harness independent from Redis availability."""

    def get_session(self, session_id: str) -> TutoringSession | None:
        return None

    def set_session(self, session: TutoringSession) -> None:
        return None

    def delete_session(self, session_id: str) -> None:
        return None

    def get_run_result(self, session_id: str, client_turn_id: str) -> HarnessRunResult | None:
        return None

    def set_run_result(
        self,
        session_id: str,
        client_turn_id: str,
        result: HarnessRunResult,
    ) -> None:
        return None

    @contextmanager
    def lock_session(self, session_id: str) -> Iterator[None]:
        yield

    def close(self) -> None:
        return None
