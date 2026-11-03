from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator

from fastapi import HTTPException

from app.api.errors import tutoring_error
from app.domain.auth import AuthenticatedUser
from app.domain.schemas import TurnRequest
from app.services.tutoring import tutoring_service


logger = logging.getLogger(__name__)


def encode_sse(event: str, data: dict, event_id: int | None = None) -> str:
    """中文：处理“encode·sse”相关操作。
    English: Handles the encode sse operation.
    """
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    serialized = json.dumps(
        {**data, "type": event},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    lines.extend(f"data: {line}" for line in serialized.splitlines() or [serialized])
    return "\n".join(lines) + "\n\n"


async def stream_turn(
    session_id: str,
    request: TurnRequest,
    actor: AuthenticatedUser,
) -> AsyncIterator[str]:
    """中文：处理“stream·turn”相关操作。
    English: Handles the stream turn operation.
    """
    event_id = 1
    yield "retry: 2000\n\n"
    yield encode_sse(
        "turn.started",
        {
            "client_turn_id": request.client_turn_id,
            "session_id": session_id,
            "stage": "accepted",
            "message": "本轮请求已接收。",
        },
        event_id,
    )
    event_id += 1
    yield encode_sse(
        "turn.progress",
        {
            "client_turn_id": request.client_turn_id,
            "stage": "reasoning",
            "message": "正在分析你的作答并准备下一步引导。",
        },
        event_id,
    )
    event_id += 1

    task = asyncio.create_task(asyncio.to_thread(
        tutoring_service.add_turn,
        session_id,
        request,
        actor,
    ))
    try:
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=10)
            except TimeoutError:
                yield ": keep-alive\n\n"

        result = task.result()
        yield encode_sse(
            "reply.started",
            {
                "client_turn_id": request.client_turn_id,
                "action": result.reply.action,
                "hint_level": result.reply.hint_level,
            },
            event_id,
        )
        event_id += 1
        for sequence, delta in enumerate(_reply_chunks(result.reply.text), start=1):
            yield encode_sse(
                "reply.delta",
                {
                    "client_turn_id": request.client_turn_id,
                    "sequence": sequence,
                    "delta": delta,
                },
                event_id,
            )
            event_id += 1
            await asyncio.sleep(0)
        if result.session.status.value == "completed":
            yield encode_sse(
                "session.completed",
                {
                    "client_turn_id": request.client_turn_id,
                    "session_id": result.session.id,
                    "status": result.session.status.value,
                    "next_route": f"/learn/{result.session.id}/feedback",
                },
                event_id,
            )
            event_id += 1
        yield encode_sse(
            "turn.completed",
            {
                "client_turn_id": request.client_turn_id,
                "result": result.model_dump(mode="json"),
            },
            event_id,
        )
    except asyncio.CancelledError:
        logger.warning(
            "SSE client disconnected before the turn completed",
            extra={
                "event": "sse.client.disconnected",
                "session_id": session_id,
                "log_client_turn_id": request.client_turn_id,
            },
        )
        raise
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else tutoring_error(
            "tutoring_request_failed",
            str(error.detail),
            retryable=error.status_code in {409, 429, 502, 503, 504},
        )
        yield encode_sse(
            "turn.error",
            {
                "client_turn_id": request.client_turn_id,
                "status": error.status_code,
                **detail,
            },
            event_id,
        )
    except Exception:
        logger.exception(
            "SSE turn failed after the stream was established",
            extra={
                "event": "sse.turn.failed",
                "session_id": session_id,
                "log_client_turn_id": request.client_turn_id,
            },
        )
        yield encode_sse(
            "turn.error",
            {
                "client_turn_id": request.client_turn_id,
                "status": 500,
                **tutoring_error(
                    "tutoring_stream_failed",
                    "流式回复暂时中断，请使用同一请求重试。",
                    retryable=True,
                ),
            },
            event_id,
        )


def _reply_chunks(text: str, max_chars: int = 72) -> list[str]:
    """中文：处理“reply·chunks”相关操作。
    English: Handles the reply chunks operation.
    """
    segments = re.findall(r".*?(?:[。！？；\n]+|$)", text, flags=re.DOTALL)
    chunks: list[str] = []
    pending = ""
    for segment in (item for item in segments if item):
        pending += segment
        while len(pending) > max_chars:
            chunks.append(pending[:max_chars])
            pending = pending[max_chars:]
        if pending.endswith(("。", "！", "？", "；", "\n")):
            chunks.append(pending)
            pending = ""
    if pending:
        chunks.append(pending)
    return chunks or [""]
