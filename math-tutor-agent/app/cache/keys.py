from urllib.parse import quote


class RedisKeys:
    """中文：定义“Redis·keys”类，封装该职责相关的数据与行为。
    English: Defines the redis keys class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self, prefix: str) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.prefix = prefix.strip(":")

    @staticmethod
    def _part(value: str) -> str:
        """中文：处理“part”相关操作。
        English: Handles the part operation.
        """
        return quote(value, safe="-_")

    def session(self, session_id: str) -> str:
        """中文：处理“会话”相关操作。
        English: Handles the session operation.
        """
        return f"{self.prefix}:session:{self._part(session_id)}"

    def turn_result(self, session_id: str, client_turn_id: str) -> str:
        """中文：处理“turn·结果”相关操作。
        English: Handles the turn result operation.
        """
        return f"{self.prefix}:turn-result:{self._part(session_id)}:{self._part(client_turn_id)}"

    def turn_result_pattern(self, session_id: str) -> str:
        """中文：处理“turn·结果·pattern”相关操作。
        English: Handles the turn result pattern operation.
        """
        return f"{self.prefix}:turn-result:{self._part(session_id)}:*"

    def session_lock(self, session_id: str) -> str:
        """中文：处理“会话·lock”相关操作。
        English: Handles the session lock operation.
        """
        return f"{self.prefix}:lock:session:{self._part(session_id)}"

    def rag_index_generation(self, collection: str, index_version: str) -> str:
        """中文：处理“rag·索引·生成”相关操作。
        English: Handles the rag index generation operation.
        """
        return (
            f"{self.prefix}:rag:index-generation:"
            f"{self._part(collection)}:{self._part(index_version)}"
        )

    def rag_query(
        self,
        provider: str,
        cache_schema: str,
        knowledge_version: str,
        query_digest: str,
    ) -> str:
        """中文：处理“rag·query”相关操作。
        English: Handles the rag query operation.
        """
        return (
            f"{self.prefix}:rag:query:{self._part(provider)}:"
            f"{self._part(cache_schema)}:{self._part(knowledge_version)}:"
            f"{self._part(query_digest)}"
        )
