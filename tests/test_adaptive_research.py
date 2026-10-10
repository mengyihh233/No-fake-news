import asyncio
from unittest.mock import AsyncMock

import pytest

from truth_backend import research as module
from truth_backend.budgets import DEPTH_BUDGETS
from truth_backend.deadlines import REQUEST_DEADLINE
from truth_backend.models import Analysis, Evidence, Plan, Report, ResearchRequest
from truth_backend.reports import validate_references
from truth_backend.security import ServiceError


def install_pipeline(monkeypatch, *, depth="brief", fail_extra=False, duplicated=False):
    plan = Plan(claims=[{"text": text, "kind": "fact"} for text in
                        ("Unmatched zeppelin archives", "Unmatched botanical census", "Unmatched ocean salinity")],
                queries=[{"query": "initial neutral search", "intent": "neutral"}], scope="Test records only")
    completion = AsyncMock(side_effect=[plan, Analysis(observations=[{
        "kind": "data", "text": "The extract lists an annual total; definitions need checking.",
        "claim_ids": ["C1"], "evidence_ids": ["E1"],
        "citations": [{"evidence_id": "E1", "quote": "Annual total was 20."}]}])])
    monkeypatch.setattr(module, "complete", completion)
    calls, fetched = [], []

    async def search(query, config, **kwargs):
        calls.append((query, kwargs))
        extra = query.startswith("Unmatched")
        if extra and fail_extra:
            raise ServiceError("upstream_error", "Test unavailable")
        number = len(calls)
        if duplicated:
            return [{"url": f"https://record.example/a?utm_source={number}#fragment", "title": "A record"}]
        host = "allowed.example" if kwargs else f"source{number}.example"
        return [{"url": f"https://{host}/record-{number}-{rank}", "title": "A record"} for rank in range(3)]

    async def fetch(row, index, query, **kwargs):
        fetched.append((row, kwargs))
        return Evidence(id=f"E{index}", title=row["title"], url=row["url"], publisher="records",
                        retrieved_at="2026-10-10T00:00:00Z", content_kind="full_text",
                        excerpt="Annual total was 20.", source_family="records", status="retrieved"), ""

    monkeypatch.setattr(module, "search_web", search)
    monkeypatch.setattr(module, "fetch_evidence", fetch)
    return calls, fetched, completion


def request(depth="brief", adaptive=True, **kwargs):
    return ResearchRequest(topic="Investigate original records", depth=depth, language="en", adaptive_search=adaptive,
                           ai={"model": "mock"}, search={"api_key": "mock-search-key"}, **kwargs)


@pytest.mark.parametrize("depth,extra", [("brief", 1), ("standard", 2), ("deep", 2)])
def test_optional_stage_obeys_search_fetch_and_analysis_budgets(monkeypatch, depth, extra):
    calls, fetched, completion = install_pipeline(monkeypatch, depth=depth)
    output = asyncio.run(module.research(request(depth)))
    budget = DEPTH_BUDGETS[depth]
    assert len(calls) == budget["max_queries"] + extra
    assert len(fetched) == len(output["evidence"]) == budget["max_sources"]
    assert completion.await_count == 2  # No extra planning/analysis model invocation.
    logs = [entry for entry in output["search_log"] if entry["round"] == "supplemental"]
    assert len(logs) == extra and all(entry["gap_claim_ids"] for entry in logs)
    assert sum(gap["attempted"] for gap in output["retrieval_gaps"]) == extra
    assert all(gap["reason"] == "no_keyword_match" for gap in output["retrieval_gaps"])
    assert output["schema_version"] == "1.1" and "summary" not in output
    assert output["observations"][0]["citations"][0]["verification"] == "exact_match"
    validate_references(Report.model_validate(output))


def test_disabled_stage_never_calls_extra_even_with_gaps(monkeypatch):
    calls, fetched, _ = install_pipeline(monkeypatch)
    output = asyncio.run(module.research(request(adaptive=False)))
    assert len(calls) == 4 and len(fetched) == 6
    assert output["retrieval_gaps"] and not any(gap["attempted"] for gap in output["retrieval_gaps"])
    assert all(entry["round"] == "initial" for entry in output["search_log"])


def test_failure_is_disclosed_and_cached_initial_results_fill_remaining_slots(monkeypatch):
    calls, fetched, _ = install_pipeline(monkeypatch, fail_extra=True)
    output = asyncio.run(module.research(request()))
    assert len(calls) == 5 and len(fetched) == 6
    assert len(output["search_log"]) == 4  # A failed search is never logged as a successful zero.
    assert output["retrieval_gaps"][0]["attempted"]
    assert any("failed" in limitation and "not a zero-result" in limitation for limitation in output["limitations"])


def test_preferred_domain_scope_applies_to_both_search_rounds(monkeypatch):
    calls, fetched, _ = install_pipeline(monkeypatch)
    output = asyncio.run(module.research(request(source_policy="preferred-only", sources=[{"url": "https://allowed.example/original"}])))
    assert len(calls) == 5 and all(kwargs["domains"] == ["allowed.example"] for _, kwargs in calls)
    assert all(item["url"].startswith("https://allowed.example/") for item in output["evidence"])
    assert fetched[0][0]["url"] == "https://allowed.example/original"


def test_tracking_url_duplicates_do_not_consume_repeated_fetch_slots(monkeypatch):
    calls, fetched, _ = install_pipeline(monkeypatch, duplicated=True)
    output = asyncio.run(module.research(request()))
    assert len(calls) == 5 and len(fetched) == len(output["evidence"]) == 1
    assert output["evidence"][0]["url"].endswith("utm_source=1#fragment")  # Original URL remains intact.


def test_no_spare_source_capacity_skips_extra_calls(monkeypatch):
    calls, fetched, _ = install_pipeline(monkeypatch)
    output = asyncio.run(module.research(request(sources=[{"url": f"https://explicit.example/{i}"} for i in range(6)])))
    assert len(calls) == 4 and len(fetched) == 6
    assert not any(gap["attempted"] for gap in output["retrieval_gaps"])
    assert any("capacity" in item for item in output["limitations"])


def test_cancellation_stops_supplemental_provider_tasks(monkeypatch):
    install_pipeline(monkeypatch, depth="standard")
    original = module.search_web
    started, cancelled = set(), set()

    async def slow(query, config, **kwargs):
        if not query.startswith("Unmatched"):
            return await original(query, config, **kwargs)
        started.add(query)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.add(query)
            raise

    monkeypatch.setattr(module, "search_web", slow)

    async def exercise():
        task = asyncio.create_task(module.research(request("standard")))
        for _ in range(100):
            if len(started) == 2:
                break
            await asyncio.sleep(0)
        assert len(started) == 2
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled == started

    asyncio.run(exercise())


def test_queued_request_deadline_can_skip_supplemental_stage(monkeypatch):
    calls, fetched, _ = install_pipeline(monkeypatch)

    async def exercise():
        token = REQUEST_DEADLINE.set(asyncio.get_running_loop().time() + 40)
        try:
            output = await module.research(request())
        finally:
            REQUEST_DEADLINE.reset(token)
        assert len(calls) == 4 and len(fetched) == 6
        assert not any(gap["attempted"] for gap in output["retrieval_gaps"])
        assert any("remaining time" in text for text in output["limitations"])
    asyncio.run(exercise())


def test_bounded_deadline_includes_queue_and_context_is_reset(monkeypatch):
    import app

    class Queue:
        async def __aenter__(self):
            assert REQUEST_DEADLINE.get() is not None  # Set before acquiring a slot.
        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(app, "busy", Queue())

    async def exercise():
        async def operation():
            remaining = REQUEST_DEADLINE.get() - asyncio.get_running_loop().time()
            assert 55 < remaining <= 60
            raise ServiceError("test_error", "Test")
        assert REQUEST_DEADLINE.get() is None
        with pytest.raises(ServiceError):
            await app.bounded(operation(), timeout_seconds=60)
        assert REQUEST_DEADLINE.get() is None
    asyncio.run(exercise())


def test_one_validation_repair_reuses_evidence_and_discloses_extra_call(monkeypatch):
    calls, _, completion = install_pipeline(monkeypatch)
    initial = list(completion.side_effect)
    invalid = Analysis(observations=[{"kind": "data", "text": "Missing quotation", "claim_ids": ["C1"], "evidence_ids": ["E1"]}])
    completion.side_effect = [initial[0], invalid, initial[1]]
    output = asyncio.run(module.research(request(adaptive=False)))
    assert len(calls) == 4 and completion.await_count == 3
    repaired_payload = completion.await_args_list[-1].args[2]
    assert repaired_payload["validation_repair"]["attempt"] == 1
    assert repaired_payload["require_exact_citations"] is True
    assert any("additional model call" in item for item in output["limitations"])
    assert output["observations"][0]["citations"]


def test_invalid_repair_is_never_returned_as_a_report(monkeypatch):
    _, _, completion = install_pipeline(monkeypatch)
    initial = list(completion.side_effect)
    invalid = Analysis(observations=[{"kind": "data", "text": "Wrong quotation", "claim_ids": ["C1"], "evidence_ids": ["E1"],
                                     "citations": [{"evidence_id": "E1", "quote": "Fabricated source text"}]}])
    completion.side_effect = [initial[0], invalid, invalid]
    with pytest.raises(ServiceError) as error:
        asyncio.run(module.research(request(adaptive=False)))
    assert error.value.code == "invalid_evidence_reference" and completion.await_count == 3


def test_provider_errors_do_not_trigger_validation_repair(monkeypatch):
    _, _, completion = install_pipeline(monkeypatch)
    initial = list(completion.side_effect)
    completion.side_effect = [initial[0], ServiceError("upstream_error", "Unavailable")]
    with pytest.raises(ServiceError):
        asyncio.run(module.research(request(adaptive=False)))
    assert completion.await_count == 2


def test_validation_repair_does_not_ignore_remaining_request_time(monkeypatch):
    _, _, completion = install_pipeline(monkeypatch)
    initial = list(completion.side_effect)
    invalid = Analysis(observations=[{"kind": "data", "text": "Missing quotation", "claim_ids": ["C1"], "evidence_ids": ["E1"]}])
    completion.side_effect = [initial[0], invalid]

    async def exercise():
        token = REQUEST_DEADLINE.set(asyncio.get_running_loop().time() + 40)
        try:
            with pytest.raises(ServiceError):
                await module.research(request(adaptive=False))
        finally:
            REQUEST_DEADLINE.reset(token)
        assert completion.await_count == 2
    asyncio.run(exercise())
