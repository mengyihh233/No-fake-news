import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app as application
from truth_backend import streaming
from truth_backend.progress import PROGRESS_CALLBACK, emit_progress
from truth_backend.models import ResearchRequest
from truth_backend.security import ServiceError
from starlette.requests import ClientDisconnect


async def unbounded(operation, timeout):
    return await operation


def decode(message):
    lines = message.splitlines()
    return lines[0].split(": ", 1)[1], json.loads(lines[1].split(": ", 1)[1])


def test_stream_exposes_progress_before_work_finishes_and_cancels_on_close():
    async def scenario():
        gate, started, stopped = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def operation():
            emit_progress("planning", 0, 1)
            started.set()
            try:
                await gate.wait()
            finally:
                stopped.set()

        iterator = streaming.research_events(operation, unbounded, 10, "en")
        assert not started.is_set()  # No detached work before stream consumption.
        assert decode(await anext(iterator))[1]["stage"] == "queued"
        assert started.is_set() and not stopped.is_set()
        assert decode(await anext(iterator))[1]["stage"] == "planning"
        await iterator.aclose()
        assert stopped.is_set()
        assert PROGRESS_CALLBACK.get() is None

    asyncio.run(scenario())


def test_success_has_one_terminal_result_and_json_escapes_newlines():
    async def operation():
        emit_progress("searching", 1, 4)
        return {"topic": "日本語\nevent: error", "evidence": [], "claims": []}

    async def scenario():
        return [decode(part) async for part in streaming.research_events(operation, unbounded, 10, "ja")]

    events = asyncio.run(scenario())
    assert [name for name, _ in events] == ["progress", "progress", "progress", "result"]
    assert events[-2][1] == {"stage": "complete", "completed": 1, "total": 1}
    assert events[-1][1]["topic"] == "日本語\nevent: error"


@pytest.mark.parametrize("language,word", [("en", "connection"), ("ja", "接続"), ("zh-CN", "网络")])
def test_service_errors_are_terminal_and_localized(language, word):
    async def operation():
        raise ServiceError("network_error", "网络连接失败或超时。")

    async def scenario():
        return [decode(part) async for part in streaming.research_events(operation, unbounded, 10, language)]

    events = asyncio.run(scenario())
    assert events[-1][0] == "error" and word in events[-1][1]["error"]["message"]
    assert not any(name == "result" or payload.get("stage") == "complete" for name, payload in events)


def test_unexpected_failure_never_streams_exception_text():
    async def operation():
        raise RuntimeError("dummy-private-provider-value")

    async def scenario():
        return [part async for part in streaming.research_events(operation, unbounded, 10, "en")]

    output = "".join(asyncio.run(scenario()))
    assert "internal_error" in output and "dummy-private-provider-value" not in output
    assert "event: result" not in output


def test_heartbeat_is_transport_only_and_does_not_cancel_work(monkeypatch):
    monkeypatch.setattr(streaming, "HEARTBEAT_SECONDS", 0.005)

    async def scenario():
        gate = asyncio.Event()

        async def operation():
            await gate.wait()
            return {"claims": [], "evidence": []}

        iterator = streaming.research_events(operation, unbounded, 10, "en")
        await anext(iterator)
        assert await anext(iterator) == ": keepalive\n\n"
        gate.set()
        remaining = [decode(part) async for part in iterator]
        assert remaining[-1][0] == "result"

    asyncio.run(scenario())


def test_slow_consumer_has_bounded_backlog_and_keeps_terminal_result():
    async def operation():
        for index in range(1000):
            emit_progress("reading", index, 1000)
        return {"claims": [], "evidence": []}

    async def scenario():
        return [decode(part) async for part in streaming.research_events(operation, unbounded, 10, "en")]

    events = asyncio.run(scenario())
    assert len(events) <= streaming.MAX_BUFFERED_EVENTS
    assert events[-1][0] == "result" and events[-2][1]["stage"] == "complete"


def test_concurrent_streams_keep_request_callbacks_isolated():
    async def consume(stage):
        async def operation():
            await asyncio.sleep(0)
            emit_progress(stage, 1, 2)
            await asyncio.sleep(0)
            return {"stage": stage}
        return [decode(part) async for part in streaming.research_events(operation, unbounded, 10, "en")]

    async def scenario():
        return await asyncio.gather(consume("searching"), consume("reading"))

    for events, stage in zip(asyncio.run(scenario()), ("searching", "reading")):
        assert [payload["stage"] for name, payload in events if name == "progress"] == ["queued", stage, "complete"]


def test_stream_timeout_cancels_operation_without_partial_result(monkeypatch):
    async def scenario():
        stopped = asyncio.Event()
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(2))

        async def operation():
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        events = [decode(part) async for part in streaming.research_events(operation, application.bounded, 0.005, "en")]
        assert stopped.is_set() and events[-1][1]["error"]["code"] == "research_timeout"
        assert not any(name == "result" for name, _ in events)

    asyncio.run(scenario())


def test_queued_timeout_closes_unstarted_coroutine(monkeypatch):
    async def scenario():
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(0))

        async def operation():
            pytest.fail("Queued work must not start")

        coroutine = operation()
        with pytest.raises(ServiceError):
            await application.bounded(coroutine, 0.005)
        assert coroutine.cr_frame is None

    asyncio.run(scenario())


def test_stream_route_keeps_local_guard_and_redacts_invalid_input(monkeypatch):
    operation = AsyncMock(return_value={"claims": [], "evidence": []})
    monkeypatch.setattr(application, "research", operation)
    with TestClient(application.app, base_url="http://127.0.0.1") as client:
        blocked = client.post("/api/research/stream", json={"topic": "Valid topic"}, headers={"Origin": "https://untrusted.example"})
        invalid = client.post("/api/research/stream", json={"topic": "x", "ai": {"api_key": "dummy-private-key"}})
        result = client.post("/api/research/stream", json={"topic": "Valid topic"})
    assert blocked.status_code == 403 and invalid.status_code == 422
    assert "dummy-private-key" not in invalid.text
    assert result.status_code == 200 and result.headers["content-type"].startswith("text/event-stream")
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["x-accel-buffering"] == "no"
    assert "event: result" in result.text and operation.await_count == 1


def test_real_pipeline_counts_reflect_queries_and_bounded_fetch_attempts(monkeypatch):
    from test_adaptive_research import install_pipeline, request
    from truth_backend import research
    calls, fetched, _ = install_pipeline(monkeypatch)
    events = []

    async def scenario():
        token = PROGRESS_CALLBACK.set(events.append)
        try:
            return await research.research(request())
        finally:
            PROGRESS_CALLBACK.reset(token)

    output = asyncio.run(scenario())
    assert len(calls) == 5 and len(fetched) == len(output["evidence"]) == 6
    for stage, count in (("planning", 1), ("searching", 4), ("supplemental_search", 1), ("reading", 6), ("analyzing", 1), ("checking", 1)):
        progress = [event for event in events if event["stage"] == stage]
        assert progress[-1]["completed"] == progress[-1]["total"] == count
        assert [event["completed"] for event in progress] == sorted(event["completed"] for event in progress)
    assert all(set(event) == {"stage", "completed", "total"} for event in events)


def test_asgi_disconnect_cancels_research_after_body_was_validated(monkeypatch):
    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()
        received = asyncio.Queue()
        body = json.dumps({"topic": "Offline cancellation check"}).encode()
        await received.put({"type": "http.request", "body": body, "more_body": False})
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(2))

        async def operation(request):
            started.set()
            emit_progress("planning", 0, 1)
            try:
                await asyncio.Event().wait()
            finally:
                # Real provider/page cleanup can itself await on disconnect.
                await asyncio.sleep(0.02)
                stopped.set()

        monkeypatch.setattr(application, "research", operation)
        sent = []

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
                 "http_version": "1.1", "method": "POST", "scheme": "http", "path": "/api/research/stream",
                 "raw_path": b"/api/research/stream", "query_string": b"", "root_path": "",
                 "headers": [(b"host", b"127.0.0.1"), (b"content-type", b"application/json")],
                 "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 80)}
        task = asyncio.create_task(application.app(scope, received.get, send))
        await asyncio.wait_for(started.wait(), 1)
        await received.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, 1)
        assert stopped.is_set()
        assert not any(b"event: result" in message.get("body", b"") for message in sent)

    asyncio.run(scenario())


@pytest.mark.parametrize("termination", ["disconnect", "send_error", "external_cancel"])
def test_response_exit_closes_suspended_generator_before_returning(monkeypatch, termination):
    """Cancellation at send, after yield, must not depend on generator GC timing."""
    async def scenario():
        started, stopped, sending = asyncio.Event(), asyncio.Event(), asyncio.Event()
        received = asyncio.Queue()
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(2))

        async def operation(request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.02)
                stopped.set()

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                sending.set()
                if termination == "send_error":
                    raise OSError("Offline disconnected transport")
                await asyncio.Event().wait()

        monkeypatch.setattr(application, "research", operation)
        response = await application.stream_research(ResearchRequest(topic="Offline suspended generator test"))
        # Retaining the iterator deliberately prevents finalization from masking
        # missing response-owned cleanup on a particular Python version.
        iterator = response.body_iterator
        before = set(asyncio.all_tasks())
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0" if termination == "disconnect" else "2.4"}}
        task = asyncio.create_task(response(scope, received.get, send))
        try:
            await asyncio.wait_for(started.wait(), 1)
            await asyncio.wait_for(sending.wait(), 1)
            if termination == "disconnect":
                await received.put({"type": "http.disconnect"})
                await asyncio.wait_for(task, 1)
            else:
                if termination == "external_cancel":
                    task.cancel()
                with pytest.raises(asyncio.CancelledError if termination == "external_cancel" else ClientDisconnect):
                    await asyncio.wait_for(task, 1)
            assert stopped.is_set()
            assert iterator.ag_frame is None
            assert not [candidate for candidate in asyncio.all_tasks() - before if not candidate.done()]
        finally:
            # Make the failing pre-fix regression safe for loop shutdown, while
            # the assertions above require cleanup before the response returns.
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await iterator.aclose()

    asyncio.run(scenario())
