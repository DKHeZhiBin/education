from contextlib import AbstractContextManager
from typing import Protocol

from app.domain.schemas import TutoringSession
from app.harness.contracts import HarnessRunResult


class SessionLockBusy(Exception):
    """中文：定义“会话·lock·busy”类，封装该职责相关的数据与行为。
    English: Defines the session lock busy class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Raised when another worker is already changing the same session.
    """


class RuntimeCoordinationUnavailable(Exception):
    """中文：定义“runtime·coordination·unavailable”类，封装该职责相关的数据与行为。
    English: Defines the runtime coordination unavailable class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Raised when strict Redis coordination cannot be guaranteed.
    """


class RuntimeCache(Protocol):
    """中文：定义“runtime·缓存”类，封装该职责相关的数据与行为。
    English: Defines the runtime cache class and encapsulates data and behavior for that responsibility.
    """
    def get_session(self, session_id: str) -> TutoringSession | None:
        """中文：处理“获取·会话”相关操作。
        English: Handles the get session operation.
        """
        ...

    def set_session(self, session: TutoringSession) -> None:
        """中文：处理“set·会话”相关操作。
        English: Handles the set session operation.
        """
        ...

    def delete_session(self, session_id: str) -> None:
        """中文：处理“删除·会话”相关操作。
        English: Handles the delete session operation.
        """
        ...

    def purge_session(self, session_id: str) -> None:
        """中文：处理“purge·会话”相关操作。
        English: Handles the purge session operation.
        """
        ...

    def get_run_result(self, session_id: str, client_turn_id: str) -> HarnessRunResult | None:
        """中文：处理“获取·执行·结果”相关操作。
        English: Handles the get run result operation.
        """
        ...

    def set_run_result(
        self,
        session_id: str,
        client_turn_id: str,
        result: HarnessRunResult,
    ) -> None:
        """中文：保存一次辅导执行结果。
        English: Stores the result of a tutoring run.
        """
        ...

    def lock_session(self, session_id: str) -> AbstractContextManager[None]:
        """中文：处理“lock·会话”相关操作。
        English: Handles the lock session operation.
        """
        ...

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        ...
