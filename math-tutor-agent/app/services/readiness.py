import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from time import perf_counter

from sqlalchemy import text

from app.core.config import settings
from app.core.database import create_mysql_engine
from app.core.redis import get_redis_client
from app.providers.llm import llm_provider
from app.providers.knowledge import knowledge_retriever

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencyCheck:
    status: str
    required: bool
    latency_ms: int
    detail: str

    def as_dict(self) -> dict[str, str | bool | int]:
        return {
            "status": self.status,
            "required": self.required,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }


class ReadinessService:
    async def check(self) -> tuple[bool, dict]:
        mysql_task = self._run("mysql", True, self._check_mysql)
        redis_task = (
            self._run("redis", True, self._check_redis)
            if settings.redis_enabled
            else self._disabled(False, "disabled_by_configuration")
        )
        llm_task = (
            self._run(
                "llm",
                settings.llm_required_for_readiness,
                llm_provider.check_readiness,
            )
            if llm_provider.available
            else self._disabled(
                settings.llm_required_for_readiness,
                "not_configured",
            )
        )
        rag_task = (
            self._run(
                "rag",
                settings.rag_required_for_readiness,
                knowledge_retriever.check_readiness,
            )
            if settings.rag_enabled
            else self._disabled(False, "disabled_by_configuration")
        )
        mysql, redis, llm, rag = await asyncio.gather(
            mysql_task,
            redis_task,
            llm_task,
            rag_task,
        )
        checks = {"mysql": mysql, "redis": redis, "llm": llm, "rag": rag}
        ready = all(
            check.status == "ready"
            for check in checks.values()
            if check.required
        )
        degraded = any(check.status == "not_ready" for check in checks.values())
        return ready, {
            "status": "ready" if ready else "not_ready",
            "degraded": degraded,
            "checks": {name: check.as_dict() for name, check in checks.items()},
        }

    async def _run(
        self,
        name: str,
        required: bool,
        operation: Callable[[], tuple[bool, str]],
    ) -> DependencyCheck:
        started = perf_counter()
        try:
            ok, detail = await asyncio.wait_for(
                asyncio.to_thread(operation),
                timeout=settings.readiness_timeout_seconds,
            )
            status = "ready" if ok else "not_ready"
        except TimeoutError:
            status, detail = "not_ready", "timeout"
        except Exception:
            logger.warning("Dependency readiness check failed", extra={"dependency": name}, exc_info=True)
            status, detail = "not_ready", "check_failed"
        return DependencyCheck(
            status=status,
            required=required,
            latency_ms=round((perf_counter() - started) * 1000),
            detail=detail,
        )

    @staticmethod
    async def _disabled(required: bool, detail: str) -> DependencyCheck:
        return DependencyCheck(
            status="not_ready" if required else "disabled",
            required=required,
            latency_ms=0,
            detail=detail,
        )

    @staticmethod
    def _check_mysql() -> tuple[bool, str]:
        with create_mysql_engine().connect() as connection:
            value = connection.scalar(text("SELECT 1"))
        return value == 1, "query_ok" if value == 1 else "unexpected_result"

    @staticmethod
    def _check_redis() -> tuple[bool, str]:
        ok = bool(get_redis_client().ping())
        return ok, "ping_ok" if ok else "unexpected_result"


readiness_service = ReadinessService()
