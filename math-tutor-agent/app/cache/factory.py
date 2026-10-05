from app.cache.base import RuntimeCache
from app.cache.noop import NoOpRuntimeCache
from app.cache.redis_runtime import RedisRuntimeCache
from app.core.config import settings
from app.core.redis import get_redis_client


def build_runtime_cache() -> RuntimeCache:
    if not settings.redis_enabled:
        return NoOpRuntimeCache()

    return RedisRuntimeCache(
        client=get_redis_client(),
        key_prefix=settings.redis_key_prefix,
        session_ttl_seconds=settings.redis_session_ttl_seconds,
        idempotency_ttl_seconds=settings.redis_idempotency_ttl_seconds,
        lock_ttl_seconds=settings.redis_lock_ttl_seconds,
        lock_wait_seconds=settings.redis_lock_wait_seconds,
        coordination_fail_closed=settings.redis_coordination_fail_closed,
    )
