from functools import lru_cache

from redis import Redis

from app.core.config import settings


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """中文：处理“获取·Redis·客户端”相关操作。
    English: Handles the get redis client operation.

    原有说明 / Existing notes:
    Return the process-wide Redis client and its shared connection pool.
    """
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        max_connections=settings.redis_max_connections,
        health_check_interval=30,
    )
