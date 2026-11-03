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
from app.providers.ocr import ocr_provider
from app.providers.speech import asr_provider, tts_provider
from app.providers.knowledge import knowledge_retriever

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencyCheck:
    """中文：定义“dependency·检查”类，封装该职责相关的数据与行为。
    English: Defines the dependency check class and encapsulates data and behavior for that responsibility.
    """
    status: str
    required: bool
    latency_ms: int
    detail: str

    def as_dict(self) -> dict[str, str | bool | int]:
        """中文：处理“as·dict”相关操作。
        English: Handles the as dict operation.
        """
        return {
            "status": self.status,
            "required": self.required,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }


class ReadinessService:
    """中文：定义“就绪状态·服务”类，封装该职责相关的数据与行为。
    English: Defines the readiness service class and encapsulates data and behavior for that responsibility.
    """
    async def check(self) -> tuple[bool, dict]:
        """中文：处理“检查”相关操作。
        English: Handles the check operation.
        """
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
        ocr_task = (
            self._run(
                "ocr",
                settings.ocr_required_for_readiness,
                ocr_provider.check_readiness,
            )
            if ocr_provider.available
            else self._disabled(settings.ocr_required_for_readiness, "not_configured")
        )
        asr_task = (
            self._run("asr", settings.asr_required_for_readiness, asr_provider.check_readiness)
            if asr_provider.available
            else self._disabled(settings.asr_required_for_readiness, "not_configured")
        )
        tts_task = (
            self._run("tts", settings.tts_required_for_readiness, tts_provider.check_readiness)
            if tts_provider.available
            else self._disabled(settings.tts_required_for_readiness, "not_configured")
        )
        mysql, redis, llm, rag, ocr, asr, tts = await asyncio.gather(
            mysql_task,
            redis_task,
            llm_task,
            rag_task,
            ocr_task,
            asr_task,
            tts_task,
        )
        checks = {
            "mysql": mysql,
            "redis": redis,
            "llm": llm,
            "rag": rag,
            "ocr": ocr,
            "asr": asr,
            "tts": tts,
        }
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
        """中文：处理“执行”相关操作。
        English: Handles the run operation.
        """
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
        """中文：处理“disabled”相关操作。
        English: Handles the disabled operation.
        """
        return DependencyCheck(
            status="not_ready" if required else "disabled",
            required=required,
            latency_ms=0,
            detail=detail,
        )

    @staticmethod
    def _check_mysql() -> tuple[bool, str]:
        """中文：处理“检查·MySQL”相关操作。
        English: Handles the check mysql operation.
        """
        with create_mysql_engine().connect() as connection:
            value = connection.scalar(text("SELECT 1"))
        return value == 1, "query_ok" if value == 1 else "unexpected_result"

    @staticmethod
    def _check_redis() -> tuple[bool, str]:
        """中文：处理“检查·Redis”相关操作。
        English: Handles the check redis operation.
        """
        ok = bool(get_redis_client().ping())
        return ok, "ping_ok" if ok else "unexpected_result"


readiness_service = ReadinessService()
