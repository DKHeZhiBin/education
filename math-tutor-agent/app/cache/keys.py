from urllib.parse import quote


class RedisKeys:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix.strip(":")

    @staticmethod
    def _part(value: str) -> str:
        return quote(value, safe="-_")

    def session(self, session_id: str) -> str:
        return f"{self.prefix}:session:{self._part(session_id)}"

    def turn_result(self, session_id: str, client_turn_id: str) -> str:
        return f"{self.prefix}:turn-result:{self._part(session_id)}:{self._part(client_turn_id)}"

    def session_lock(self, session_id: str) -> str:
        return f"{self.prefix}:lock:session:{self._part(session_id)}"

    def rag_index_generation(self, collection: str, index_version: str) -> str:
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
        return (
            f"{self.prefix}:rag:query:{self._part(provider)}:"
            f"{self._part(cache_schema)}:{self._part(knowledge_version)}:"
            f"{self._part(query_digest)}"
        )
