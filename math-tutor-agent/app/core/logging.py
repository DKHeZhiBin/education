from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import UTC, datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings


_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_session_id: ContextVar[str] = ContextVar("session_id", default="-")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_SESSION_PATH_PATTERN = re.compile(r"/sessions/([^/]+)")
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|cookie|password|refresh[_-]?token|secret|token)"
    r"(\s*[=:]\s*[\"']?)([^\s,;&\"']+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"(://[^:/\s]+:)([^@/\s]+)(@)")

_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_STRUCTURED_FIELDS = (
    "event",
    "request_method",
    "request_path",
    "status_code",
    "duration_ms",
    "run_id",
    "agent",
    "artifact_kinds",
    "session_status",
    "degraded",
    "degradation_code",
    "dependency",
    "operation",
    "cache_hit",
)


def redact_sensitive(value: object) -> str:
    """中文：隐藏日志文本中的令牌、密码、API Key 与连接串密码。
    English: Redacts tokens, passwords, API keys, and URL credentials from log text.
    """
    text = str(value)
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)
    return _URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]\3", text)


class SensitiveDataFilter(logging.Filter):
    """中文：在日志写入任何输出前统一清理敏感文本。
    English: Sanitizes sensitive text before a log record reaches any output.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """中文：清理消息及异常文本，同时允许该日志继续输出。
        English: Sanitizes message and exception text while allowing the record through.
        """
        record.msg = redact_sensitive(record.getMessage())
        record.args = ()
        return True


class RequestContextFilter(logging.Filter):
    """中文：为日志记录补充当前请求和辅导会话的关联标识。
    English: Adds current request and tutoring session correlation identifiers to records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """中文：写入缺失的 request_id 和 session_id 上下文字段。
        English: Supplies missing request_id and session_id context fields.
        """
        if not hasattr(record, "request_id"):
            record.request_id = _request_id.get()
        if not hasattr(record, "session_id"):
            record.session_id = _session_id.get()
        return True


class JsonLogFormatter(logging.Formatter):
    """中文：将应用日志转换为便于搜索和采集的单行 JSON。
    English: Formats application records as single-line JSON for search and collection.
    """

    def __init__(self, environment: str) -> None:
        """中文：保存运行环境名称并初始化 JSON 格式器。
        English: Stores the environment name and initializes the JSON formatter.
        """
        super().__init__()
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        """中文：输出包含时间、级别、关联 ID 和业务字段的 JSON 日志。
        English: Emits JSON with timestamp, level, correlation IDs, and business fields.
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": self.environment,
            "request_id": getattr(record, "request_id", "-"),
            "session_id": getattr(record, "session_id", "-"),
            "process_id": record.process,
        }
        for field in _STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        for key, value in record.__dict__.items():
            if key.startswith("log_") and key not in _STANDARD_RECORD_FIELDS:
                payload[key[4:]] = value
        if record.exc_info:
            payload["exception"] = redact_sensitive(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


class TextLogFormatter(logging.Formatter):
    """中文：为本地终端输出紧凑且可读的关联日志。
    English: Formats compact correlated logs for local terminal output.
    """

    def format(self, record: logging.LogRecord) -> str:
        """中文：将请求和会话标识附加到标准文本日志。
        English: Appends request and session identifiers to standard text logs.
        """
        timestamp = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        context = (
            f"request_id={getattr(record, 'request_id', '-')} "
            f"session_id={getattr(record, 'session_id', '-')}"
        )
        rendered = f"{timestamp} {record.levelname:<8} {record.name} {context} {record.getMessage()}"
        if record.exc_info:
            rendered = f"{rendered}\n{redact_sensitive(self.formatException(record.exc_info))}"
        return rendered


def _handler_filters(handler: logging.Handler) -> logging.Handler:
    """中文：为日志处理器安装请求上下文与敏感信息过滤器。
    English: Installs request-context and sensitive-data filters on a handler.
    """
    handler.addFilter(RequestContextFilter())
    handler.addFilter(SensitiveDataFilter())
    return handler


def configure_logging(config: Settings) -> None:
    """中文：配置控制台、应用文件和错误文件的统一日志输出。
    English: Configures unified console, application-file, and error-file logging.
    """
    level = getattr(logging, config.log_level)
    handlers: list[logging.Handler] = []

    if config.log_console_enabled:
        console = _handler_filters(logging.StreamHandler())
        console.setLevel(level)
        console.setFormatter(TextLogFormatter())
        handlers.append(console)

    if config.log_file_enabled:
        log_directory = Path(config.log_directory).expanduser()
        if not log_directory.is_absolute():
            log_directory = Path(__file__).resolve().parents[2] / log_directory
        log_directory.mkdir(parents=True, exist_ok=True)
        formatter: logging.Formatter = (
            JsonLogFormatter(config.app_env)
            if config.log_json_file
            else TextLogFormatter()
        )
        application_file = _handler_filters(RotatingFileHandler(
            log_directory / "app.log",
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding="utf-8",
        ))
        application_file.setLevel(level)
        application_file.setFormatter(formatter)
        handlers.append(application_file)

        error_file = _handler_filters(RotatingFileHandler(
            log_directory / "error.log",
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding="utf-8",
        ))
        error_file.setLevel(logging.ERROR)
        error_file.setFormatter(formatter)
        handlers.append(error_file)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    for handler in handlers:
        root.addHandler(handler)

    logging.captureWarnings(True)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").handlers.clear()
    logging.getLogger("uvicorn.error").propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if config.database_echo else logging.WARNING
    )


def configure_cli_logging() -> None:
    """中文：使用全局应用配置初始化命令行任务的统一日志。
    English: Initializes unified logging for CLI jobs from global application settings.
    """
    from app.core.config import settings

    configure_logging(settings)


def _header(scope: Scope, name: bytes) -> str | None:
    """中文：从 ASGI 请求中读取指定请求头。
    English: Reads one named header from an ASGI request scope.
    """
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _correlation_id(scope: Scope) -> str:
    """中文：复用合法客户端请求 ID，缺失时生成新的关联 ID。
    English: Reuses a valid client request ID or creates a new correlation ID.
    """
    supplied = _header(scope, b"x-request-id")
    if supplied and _REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return str(uuid4())


class RequestLoggingMiddleware:
    """中文：记录 HTTP 请求结果、耗时、错误及跨层关联 ID。
    English: Logs HTTP outcomes, latency, errors, and cross-layer correlation IDs.
    """

    def __init__(self, app: ASGIApp, config: Settings) -> None:
        """中文：保存下游应用和请求日志策略。
        English: Stores the downstream application and request logging policy.
        """
        self.app = app
        self.config = config
        self.logger = logging.getLogger("app.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """中文：为一次 HTTP 请求建立上下文并记录最终处理结果。
        English: Establishes context for one HTTP request and records its final outcome.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _correlation_id(scope)
        path = scope.get("path", "")
        session_match = _SESSION_PATH_PATTERN.search(path)
        session_id = session_match.group(1) if session_match else "-"
        request_token: Token[str] = _request_id.set(request_id)
        session_token: Token[str] = _session_id.set(session_id)
        started = perf_counter()
        status_code = 500
        response_started = False
        failed = False

        async def send_with_request_id(message: Message) -> None:
            """中文：在响应头中返回本次请求的关联 ID。
            English: Returns this request's correlation ID in the response headers.
            """
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                headers = list(message.get("headers", []))
                if not any(key.lower() == b"x-request-id" for key, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            failed = True
            self.logger.exception(
                "Unhandled request exception",
                extra={
                    "event": "http.request.failed",
                    "request_method": scope.get("method", ""),
                    "request_path": path,
                    "status_code": status_code,
                },
            )
            raise
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            is_health = path.startswith("/v1/health/")
            if not failed and (self.config.log_health_requests or not is_health):
                extra = {
                    "event": "http.request.completed",
                    "request_method": scope.get("method", ""),
                    "request_path": path,
                    "status_code": status_code if response_started else 499,
                    "duration_ms": duration_ms,
                    "log_slow": duration_ms >= self.config.log_slow_request_ms,
                }
                if status_code >= 500:
                    self.logger.error("HTTP request completed", extra=extra)
                elif status_code >= 400 or duration_ms >= self.config.log_slow_request_ms:
                    self.logger.warning("HTTP request completed", extra=extra)
                else:
                    self.logger.info("HTTP request completed", extra=extra)
            _session_id.reset(session_token)
            _request_id.reset(request_token)
