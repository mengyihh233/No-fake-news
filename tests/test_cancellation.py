"""Offline ASGI and helper tests for disconnect-aware JSON endpoints."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app as application
from truth_backend.deadlines import REQUEST_DEADLINE
from truth_backend import research as research_module
from truth_backend.models import Evidence, Plan, Report, ResearchRequest
from truth_backend.security import ServiceError


def payload(path):
    if path == "/api/research":
        return {"topic": "Offline cancellation contract", "language": "en"}
    report = Report(schema_version="1.1", topic="Offline source review", mode="ai-summary",
                    generated_at="2026-10-10T00:00:00Z", scope="Test only",
                    claims=[{"id": "C1", "text": "A record exists", "kind": "fact"}], evidence=[])
    return {"report": report.model_dump(by_alias=True), "language": "en"}


def scope(path):
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1", "method": "POST", "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"host", b"127.0.0.1"), (b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 80)}


ROUTES = [("/api/research", "research"), ("/api/summarize", "summarize"), ("/api/review", "review_report")]


@pytest.mark.parametrize("path,operation_name", ROUTES)
def test_complete_asgi_body_then_disconnect_cancels_and_awaits_async_cleanup(monkeypatch, path, operation_name):
    async def scenario():
        started, cleaned = asyncio.Event(), asyncio.Event()
        received = asyncio.Queue()
        await received.put({"type": "http.request", "body": json.dumps(payload(path)).encode(), "more_body": False})

        async def operation(request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.02)
                cleaned.set()

        monkeypatch.setattr(application, operation_name, operation)
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(2))
        sent = []

        async def send(message): sent.append(message)

        before = set(asyncio.all_tasks())
        task = asyncio.create_task(application.app(scope(path), received.get, send))
        await asyncio.wait_for(started.wait(), 1)
        await received.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, 1)
        assert cleaned.is_set()
        assert not [candidate for candidate in asyncio.all_tasks() - before if not candidate.done()]
        assert all(message.get("status") != 200 for message in sent)
        assert all(not message.get("body") for message in sent)

    asyncio.run(scenario())


@pytest.mark.parametrize("path,operation_name", ROUTES)
@pytest.mark.parametrize("fail", [False, True])
def test_json_success_and_safe_provider_error_keep_existing_contract(monkeypatch, path, operation_name, fail):
    calls = []

    async def operation(request):
        calls.append(request)
        if fail:
            raise ServiceError("network_error", "网络连接失败或超时。")
        return {"schema_version": "1.1", "topic": "Offline result", "evidence": []}

    monkeypatch.setattr(application, operation_name, operation)
    with TestClient(application.app, base_url="http://127.0.0.1") as client:
        response = client.post(path, json=payload(path))
    assert len(calls) == 1
    if fail:
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "network_error"
        assert "connection" in response.json()["error"]["message"]
    else:
        assert response.status_code == 200 and response.json()["topic"] == "Offline result"
        assert response.headers["content-type"].startswith("application/json")


def receive_monitor():
    queue, closed = asyncio.Queue(), asyncio.Event()

    async def receive():
        try:
            return await queue.get()
        finally:
            closed.set()

    return SimpleNamespace(receive=receive), queue, closed


def test_queue_timeout_closes_unstarted_operation_and_stops_disconnect_listener(monkeypatch):
    async def scenario():
        request, _, listener_closed = receive_monitor()
        created = []
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(0))

        async def operation(): pytest.fail("Queued operation must not start")

        def factory():
            coroutine = operation()
            created.append(coroutine)
            return coroutine

        before = set(asyncio.all_tasks())
        with pytest.raises(ServiceError) as error:
            await application.bounded_connected(request, factory, 0.005)
        assert error.value.code == "research_timeout"
        assert len(created) == 1 and created[0].cr_frame is None
        assert listener_closed.is_set() and REQUEST_DEADLINE.get() is None
        assert not [candidate for candidate in asyncio.all_tasks() - before if not candidate.done()]

    asyncio.run(scenario())


def test_disconnect_while_queued_returns_empty_499_without_starting_work(monkeypatch):
    async def scenario():
        request, queue, listener_closed = receive_monitor()
        created = []
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(0))

        async def operation(): pytest.fail("Disconnected queued work must not start")

        def factory():
            coroutine = operation()
            created.append(coroutine)
            return coroutine

        await queue.put({"type": "http.disconnect"})
        response = await application.bounded_connected(request, factory, 60)
        assert response.status_code == 499 and response.body == b""
        assert len(created) == 1 and created[0].cr_frame is None
        assert listener_closed.is_set()

    asyncio.run(scenario())


@pytest.mark.parametrize("queued", [False, True])
def test_external_request_task_cancel_waits_cleanup_and_has_no_orphan_tasks(monkeypatch, queued):
    async def scenario():
        request, _, listener_closed = receive_monitor()
        started, cleaned, factory_called = asyncio.Event(), asyncio.Event(), asyncio.Event()
        created = []
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(0 if queued else 2))

        async def operation():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.02)
                cleaned.set()

        def factory():
            factory_called.set()
            coroutine = operation()
            created.append(coroutine)
            return coroutine

        before = set(asyncio.all_tasks())
        task = asyncio.create_task(application.bounded_connected(request, factory, 60))
        await asyncio.wait_for(factory_called.wait() if queued else started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert listener_closed.is_set() and created[0].cr_frame is None
        assert cleaned.is_set() is (not queued)
        assert started.is_set() is (not queued)
        assert not [candidate for candidate in asyncio.all_tasks() - before if not candidate.done()]

    asyncio.run(scenario())


def test_active_deadline_cancels_and_waits_operation_cleanup_before_error(monkeypatch):
    async def scenario():
        request, _, listener_closed = receive_monitor()
        cleaned = asyncio.Event()
        monkeypatch.setattr(application, "busy", asyncio.Semaphore(2))

        async def operation():
            try:
                assert REQUEST_DEADLINE.get() is not None
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.02)
                cleaned.set()

        with pytest.raises(ServiceError) as error:
            await application.bounded_connected(request, operation, 0.005)
        assert error.value.code == "research_timeout" and cleaned.is_set() and listener_closed.is_set()
        assert REQUEST_DEADLINE.get() is None

    asyncio.run(scenario())


@pytest.mark.parametrize("phase,expected_active", [("initial_search", 4), ("reading", 4), ("supplemental_search", 2)])
def test_research_cancellation_awaits_every_child_async_cleanup(monkeypatch, phase, expected_active):
    """One child exits early; its peers must not be cancelled again mid-cleanup."""
    async def scenario():
        started, cleaned = set(), set()
        all_started = asyncio.Event()
        plan = Plan(claims=[{"text": "Offline source comparison", "kind": "fact"}],
                    queries=[{"query": "offline original records", "intent": "neutral"}], scope="Offline only")
        planning, analysis = AsyncMock(return_value=plan), AsyncMock()
        monkeypatch.setattr(research_module, "complete", planning)
        monkeypatch.setattr(research_module, "analyze", analysis)
        monkeypatch.setattr(research_module, "resolve_search", lambda config, ai: config)
        monkeypatch.setattr(research_module, "identify_retrieval_gaps", lambda *args: [
            SimpleNamespace(query=f"supplemental offline query {index}", claim_id="C1", attempted=False)
            for index in range(2)])

        async def pending_child():
            index = len(started)
            started.add(index)
            if len(started) == expected_active:
                all_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                # The first child's early completion makes ordinary gather raise
                # while its siblings are still closing their asynchronous resources.
                await asyncio.sleep(0 if index == 0 else 0.03)
                cleaned.add(index)

        searches, reads = [], []

        async def search(query, config, **kwargs):
            searches.append(query)
            if phase == "initial_search" or (phase == "supplemental_search" and query.startswith("supplemental")):
                await pending_child()
            return [{"url": f"https://source{len(searches)}.example/record", "title": "Offline record"}]

        async def fetch(row, index, query, **kwargs):
            reads.append(row["url"])
            if phase == "reading":
                await pending_child()
            return Evidence(id=f"E{index}", title=row["title"], url=row["url"], publisher="Offline",
                            retrieved_at="2026-10-10T00:00:00Z", content_kind="full_text",
                            excerpt="An offline record exists.", source_family="Offline", status="retrieved"), ""

        monkeypatch.setattr(research_module, "search_web", search)
        monkeypatch.setattr(research_module, "fetch_evidence", fetch)
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(research_module.research(ResearchRequest(
            topic="Offline cancellation audit", depth="standard", language="en",
            adaptive_search=phase == "supplemental_search", search={"api_key": "dummy-search"})))
        await asyncio.wait_for(all_started.wait(), 1)
        reads_at_cancel = len(reads)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        # Check before asyncio.run cancels anything remaining on loop shutdown.
        assert cleaned == started == set(range(expected_active))
        assert len(reads) == reads_at_cancel
        assert len(searches) == (6 if phase == "supplemental_search" else 4)
        if phase == "initial_search":
            assert not reads
        analysis.assert_not_awaited()
        assert planning.await_count == 1
        assert not [candidate for candidate in asyncio.all_tasks() - before if not candidate.done()]

    asyncio.run(scenario())
