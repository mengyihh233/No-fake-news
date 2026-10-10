"""Bounded SSE transport with no persistent jobs, detached work, or paid retry."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from .i18n import error_message
from .progress import PROGRESS_CALLBACK, emit_progress
from .security import ServiceError


HEARTBEAT_SECONDS = 10
MAX_BUFFERED_EVENTS = 64


class ResearchStreamingResponse(StreamingResponse):
    """Own the research iterator's shutdown, including cancellation during send."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # The streaming consumer/task group has exited, so aclose cannot race
            # an active anext. A cancelled send can leave the iterator suspended
            # at yield; async-for alone does not close it or await its cleanup.
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                with anyio.CancelScope(shield=True):
                    await close()


def sse(event: str, data: dict) -> str:
    if event not in {"progress", "result", "error"}:
        raise ValueError("Invalid internal stream event")
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':'))}\n\n"


async def research_events(operation: Callable, bounded: Callable, timeout: float, language: str) -> AsyncIterator[str]:
    """Run only while this iterator is consumed; closing it cancels and awaits work."""
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=MAX_BUFFERED_EVENTS)

    def send(event, data):
        message = sse(event, data)
        if queue.full():
            # Keep the most recent progress under a slow client. Terminal messages
            # are never dropped, and no unbounded event history is retained.
            queue.get_nowait()
        queue.put_nowait((event, message))

    async def run():
        token = PROGRESS_CALLBACK.set(lambda data: send("progress", data))
        try:
            emit_progress("queued")
            result = await bounded(operation(), timeout)
            emit_progress("complete", 1, 1)
            send("result", result)
        except ServiceError as exc:
            send("error", {"error": {"code": exc.code, "message": error_message(exc.code, exc.message, language)}})
        except Exception:
            send("error", {"error": {"code": "internal_error", "message": error_message(
                "internal_error", "处理失败；请检查配置。未生成替代结果。", language)}})
        finally:
            PROGRESS_CALLBACK.reset(token)

    task = asyncio.create_task(run())
    try:
        while True:
            try:
                event, message = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield message
            if event in {"result", "error"}:
                break
    finally:
        # Starlette cancels its response scope on disconnect. Shield the awaited
        # shutdown so repeated scope cancellation cannot interrupt child cleanup.
        with anyio.CancelScope(shield=True):
            if not task.done() and not task.cancelling():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
