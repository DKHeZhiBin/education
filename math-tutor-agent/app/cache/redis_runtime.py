from collections.abc import Iterator
from contextlib import contextmanager
import logging

from pydantic import ValidationError
from redis import Redis
from redis.exceptions import LockError, RedisError

from app.cache.base import RuntimeCoordinationUnavailable, SessionLockBusy
from app.cache.keys import RedisKeys
from app.domain.schemas import TutoringSession
from app.harness.contracts import HarnessRunResult

logger = logging.getLogger(__name__)


class RedisRuntimeCache:
    """Cache, idempotency and distributed locking used at the Harness boundary."""

    def __init__(
        self,
        client: Redis,
        key_prefix: str,
        session_ttl_seconds: int,
        idempotency_ttl_seconds: int,
        lock_ttl_seconds: int,
        lock_wait_seconds: float,
        coordination_fail_closed: bool,
    ) -> None:
        self.client = client
        self.keys = RedisKeys(key_prefix)
        self.session_ttl_seconds = session_ttl_seconds
        self.idempotency_ttl_seconds = idempotency_ttl_seconds
        self.lock_ttl_seconds = lock_ttl_seconds
        self.lock_wait_seconds = lock_wait_seconds
        self.coordination_fail_closed = coordination_fail_closed

    def get_session(self, session_id: str) -> TutoringSession | None:
        key = self.keys.session(session_id)
        payload = self._get(key, "read session cache")
        if payload is None:
            return None
        try:
            return TutoringSession.model_validate_json(payload)
        except (ValidationError, ValueError):
            logger.warning("Ignoring invalid Redis session payload", extra={"session_id": session_id})
            self._delete(key, "delete invalid session cache")
            return None

    def set_session(self, session: TutoringSession) -> None:
        self._setex(
            self.keys.session(session.id),
            self.session_ttl_seconds,
            session.model_dump_json(),
            "write session cache",
        )

    def delete_session(self, session_id: str) -> None:
        self._delete(self.keys.session(session_id), "delete stale session cache")

    def get_run_result(self, session_id: str, client_turn_id: str) -> HarnessRunResult | None:
        key = self.keys.turn_result(session_id, client_turn_id)
        try:
            value = self.client.get(key)
            payload = value if isinstance(value, str) else None
        except RedisError as error:
            logger.warning("Redis operation failed: read idempotency result", exc_info=True)
            if self.coordination_fail_closed:
                raise RuntimeCoordinationUnavailable("Redis idempotency lookup unavailable") from error
            return None
        if payload is None:
            return None
        try:
            return HarnessRunResult.model_validate_json(payload)
        except (ValidationError, ValueError):
            logger.warning(
                "Ignoring invalid Redis idempotency payload",
                extra={"session_id": session_id, "client_turn_id": client_turn_id},
            )
            self._delete(key, "delete invalid idempotency result")
            if self.coordination_fail_closed:
                raise RuntimeCoordinationUnavailable("Redis idempotency result is invalid")
            return None

    def set_run_result(
        self,
        session_id: str,
        client_turn_id: str,
        result: HarnessRunResult,
    ) -> None:
        try:
            self.client.setex(
                self.keys.turn_result(session_id, client_turn_id),
                self.idempotency_ttl_seconds,
                result.model_dump_json(),
            )
        except RedisError:
            logger.error(
                "Redis idempotency write failed after the MySQL session transaction committed",
                extra={"session_id": session_id, "client_turn_id": client_turn_id},
                exc_info=True,
            )

    @contextmanager
    def lock_session(self, session_id: str) -> Iterator[None]:
        lock = self.client.lock(
            self.keys.session_lock(session_id),
            timeout=self.lock_ttl_seconds,
            blocking_timeout=self.lock_wait_seconds,
            thread_local=False,
        )
        try:
            acquired = lock.acquire()
        except RedisError as error:
            logger.warning(
                "Redis unavailable while acquiring session lock",
                extra={"session_id": session_id},
                exc_info=True,
            )
            if self.coordination_fail_closed:
                raise RuntimeCoordinationUnavailable("Redis session lock unavailable") from error
            yield
            return

        if not acquired:
            raise SessionLockBusy(session_id)

        try:
            yield
        finally:
            try:
                lock.release()
            except (LockError, RedisError):
                logger.warning(
                    "Unable to release Redis session lock",
                    extra={"session_id": session_id},
                    exc_info=True,
                )

    def close(self) -> None:
        try:
            self.client.close()
        except RedisError:
            logger.warning("Unable to close Redis client cleanly", exc_info=True)

    def _get(self, key: str, operation: str) -> str | None:
        try:
            value = self.client.get(key)
            return value if isinstance(value, str) else None
        except RedisError:
            logger.warning("Redis operation failed: %s", operation, exc_info=True)
            return None

    def _setex(self, key: str, ttl_seconds: int, value: str, operation: str) -> None:
        try:
            self.client.setex(key, ttl_seconds, value)
        except RedisError:
            logger.warning("Redis operation failed: %s", operation, exc_info=True)

    def _delete(self, key: str, operation: str) -> None:
        try:
            self.client.delete(key)
        except RedisError:
            logger.warning("Redis operation failed: %s", operation, exc_info=True)
