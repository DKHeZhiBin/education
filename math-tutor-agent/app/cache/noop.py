from contextlib import contextmanager
from collections.abc import Iterator

from app.domain.schemas import TutoringSession
from app.harness.contracts import HarnessRunResult


class NoOpRuntimeCache:
    """中文：定义“no·op·runtime·缓存”类，封装该职责相关的数据与行为。
    English: Defines the no op runtime cache class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Local/degraded adapter that keeps the Harness independent from Redis availability.
    """

    def get_session(self, session_id: str) -> TutoringSession | None:
        """中文：处理“获取·会话”相关操作。
        English: Handles the get session operation.
        """
        return None

    def set_session(self, session: TutoringSession) -> None:
        """中文：处理“set·会话”相关操作。
        English: Handles the set session operation.
        """
        return None

    def delete_session(self, session_id: str) -> None:
        """中文：处理“删除·会话”相关操作。
        English: Handles the delete session operation.
        """
        return None

    def purge_session(self, session_id: str) -> None:
        """中文：处理“purge·会话”相关操作。
        English: Handles the purge session operation.
        """
        return None

    def get_run_result(self, session_id: str, client_turn_id: str) -> HarnessRunResult | None:
        """中文：处理“获取·执行·结果”相关操作。
        English: Handles the get run result operation.
        """
        return None

    def set_run_result(
        self,
        session_id: str,
        client_turn_id: str,
        result: HarnessRunResult,
    ) -> None:
        """中文：处理“set·执行·结果”相关操作。
        English: Handles the set run result operation.
        """
        return None

    @contextmanager
    def lock_session(self, session_id: str) -> Iterator[None]:
        """中文：处理“lock·会话”相关操作。
        English: Handles the lock session operation.
        """
        yield

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        return None
