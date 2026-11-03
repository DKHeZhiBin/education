from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
    request_validation_exception_handler as default_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


TUTORING_API_PREFIX = "/v1/tutoring"


class TutoringAPIErrorResponse(BaseModel):
    """中文：定义“tutoring·apierror·响应”类，封装该职责相关的数据与行为。
    English: Defines the tutoring apierror response class and encapsulates data and behavior for that responsibility.
    """
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    retry_after_seconds: int | None = Field(default=None, ge=0, le=300)
    fields: list[dict[str, str]] | None = None


def tutoring_error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """中文：处理“tutoring·error”相关操作。
    English: Handles the tutoring error operation.
    """
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        **extra,
    }


async def normalized_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    """中文：处理“normalized·http·exception·handler”相关操作。
    English: Handles the normalized http exception handler operation.
    """
    if not request.url.path.startswith(TUTORING_API_PREFIX):
        return await default_http_exception_handler(request, exc)

    detail = exc.detail
    if isinstance(detail, dict) and all(
        key in detail for key in ("code", "message", "retryable")
    ):
        body = detail
    else:
        body = tutoring_error(
            _default_code(exc.status_code),
            str(detail) if isinstance(detail, str) else _default_message(exc.status_code),
            retryable=exc.status_code in {409, 429, 502, 503, 504},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=exc.headers,
    )


async def normalized_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """中文：处理“normalized·验证·exception·handler”相关操作。
    English: Handles the normalized validation exception handler operation.
    """
    if not request.url.path.startswith(TUTORING_API_PREFIX):
        return await default_validation_exception_handler(request, exc)

    fields = []
    for error in exc.errors():
        location = [str(item) for item in error.get("loc", ()) if item != "body"]
        fields.append({
            "field": ".".join(location) or "request",
            "type": str(error.get("type", "invalid")),
        })
    return JSONResponse(
        status_code=422,
        content=tutoring_error(
            "invalid_tutoring_request",
            "请求内容不完整或格式不正确，请检查后重试。",
            retryable=False,
            fields=fields,
        ),
    )


def _default_code(status_code: int) -> str:
    """中文：处理“default·code”相关操作。
    English: Handles the default code operation.
    """
    return {
        400: "invalid_request",
        401: "authentication_required",
        403: "tutoring_access_denied",
        404: "tutoring_resource_not_found",
        409: "tutoring_conflict",
        422: "invalid_tutoring_request",
        429: "rate_limited",
        502: "upstream_unavailable",
        503: "tutoring_service_unavailable",
        504: "upstream_timeout",
    }.get(status_code, "tutoring_request_failed")


def _default_message(status_code: int) -> str:
    """中文：处理“default·message”相关操作。
    English: Handles the default message operation.
    """
    return {
        401: "登录状态已失效，请重新登录。",
        403: "当前账号无权执行此操作。",
        404: "请求的学习资源不存在或已失效。",
        409: "学习会话状态已变化，请同步后重试。",
        422: "请求内容不完整或格式不正确。",
        429: "操作过于频繁，请稍后重试。",
        503: "学习服务暂时不可用，请稍后重试。",
    }.get(status_code, "学习请求处理失败，请稍后重试。")
