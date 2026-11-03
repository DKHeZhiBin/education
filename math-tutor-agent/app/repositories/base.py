from typing import Protocol

from app.domain.schemas import TutoringSession


class SessionVersionConflict(Exception):
    """中文：定义“会话·version·conflict”类，封装该职责相关的数据与行为。
    English: Defines the session version conflict class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, session_id: str, expected_version: int, actual_version: int | None) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.session_id = session_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(f"Session {session_id} version conflict")


class SessionRepository(Protocol):
    """中文：定义“会话·仓储”类，封装该职责相关的数据与行为。
    English: Defines the session repository class and encapsulates data and behavior for that responsibility.
    """
    def save(self, session: TutoringSession) -> TutoringSession:
        """中文：处理“保存”相关操作。
        English: Handles the save operation.
        """
        ...

    def get(self, session_id: str) -> TutoringSession | None:
        """中文：处理“获取”相关操作。
        English: Handles the get operation.
        """
        ...

    def list(self, student_user_id: str) -> list[TutoringSession]:
        """中文：处理“列出”相关操作。
        English: Handles the list operation.
        """
        ...

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        ...
