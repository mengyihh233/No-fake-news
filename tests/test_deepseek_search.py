"""Native DeepSeek search contracts, with synthetic keys and no external requests."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from truth_backend import providers, research as research_module
from truth_backend.models import AIConfig, Analysis, Evidence, Plan, Report, ResearchRequest, SearchConfig
from truth_backend.reports import validate_references
from truth_backend.security import Fetched, ServiceError


@pytest.fixture(autouse=True)
def clean_search_environment(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "TRUTH_AI_BASE_URL", "TRUTH_AI_API_KEY", "TRUTH_AI_MODEL"):
        monkeypatch.delenv(name, raising=False)


def native_response():
    return {"content": [
        {"type": "thinking", "thinking": "Internal model narrative is never evidence."},
        {"type": "server_tool_use", "name": "web_search", "input": {"query": "test"}},
        {"type": "web_search_tool_result", "content": [
            {"type": "web_search_result", "url": "https://example.com/first", "title": "Original title", "page_age": "2026-01-01"},
            {"type": "web_search_result", "url": "https://example.com/second", "title": "Second title"},
        ]},
        {"type": "text", "text": "Unverified model answer that must not become a snippet.", "citations": [
            {"type": "web_search_result_location", "url": "https://example.com/first", "cited_text": "Original source quotation."},
        ]},
    ]}


def test_search_schema_accepts_native_provider_without_changing_default():
    assert SearchConfig().provider == "tavily"
    assert ResearchRequest(topic="A test claim", search={"provider": "deepseek"}).search.provider == "deepseek"


@pytest.mark.parametrize("explicit,deepseek_env,chat_env,expected", [
    ("search-test-key", "dedicated-test-key", "chat-test-key", "search-test-key"),
    ("", "dedicated-test-key", "chat-test-key", "dedicated-test-key"),
    ("", "", "chat-test-key", "chat-test-key"),
    ("", "", "", "request-test-key"),
])
def test_key_priority_is_explicit_then_dedicated_then_official_environment_then_request(monkeypatch, explicit, deepseek_env, chat_env, expected):
    monkeypatch.setenv("DEEPSEEK_API_KEY", deepseek_env)
    monkeypatch.setenv("TRUTH_AI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("TRUTH_AI_API_KEY", chat_env)
    ai = AIConfig(base_url="https://api.deepseek.com/v1", api_key="request-test-key")
    result = providers.resolve_search(SearchConfig(provider="deepseek", api_key=explicit), ai)
    assert result.api_key.get_secret_value() == expected


@pytest.mark.parametrize("base_url", [
    "https://third-party.example/v1", "https://api.deepseek.com.evil.example/v1",
    "http://api.deepseek.com/v1", "https://api.deepseek.com:8443/v1",
    "https://api.deepseek.com@evil.example/v1", "https://user@api.deepseek.com/v1",
    "http://localhost:11434/v1", "https://api.deepseek.com./v1",
])
def test_other_ai_origins_never_supply_deepseek_key(monkeypatch, base_url):
    monkeypatch.setenv("TRUTH_AI_BASE_URL", base_url)
    monkeypatch.setenv("TRUTH_AI_API_KEY", "other-provider-test-key")
    result = providers.resolve_search(SearchConfig(provider="deepseek"), AIConfig(base_url=base_url, api_key="request-other-key"))
    assert result.api_key.get_secret_value() == ""


def test_request_key_can_inherit_official_environment_base_url(monkeypatch):
    monkeypatch.setenv("TRUTH_AI_BASE_URL", "https://api.deepseek.com")
    result = providers.resolve_search(SearchConfig(provider="deepseek"), AIConfig(api_key="ephemeral-test-key"))
    assert result.api_key.get_secret_value() == "ephemeral-test-key"


def test_parser_joins_citations_but_never_uses_prose_or_inline_fabricated_snippet():
    payload = native_response()
    payload["content"][2]["content"][1]["snippet"] = "Unexpected inline model-written text"
    output = providers.parse_deepseek_search(payload)
    assert output[0] == {"url": "https://example.com/first", "title": "Original title",
                         "snippet": "Original source quotation.", "raw_content": "", "published_at": "2026-01-01"}
    assert output[1]["snippet"] == "" and output[1]["published_at"] is None
    assert "Unverified" not in json.dumps(output) and "Unexpected" not in json.dumps(output)


def test_parser_deduplicates_across_blocks_and_caps_three_valid_sources():
    payload = native_response()
    payload["content"].insert(0, {"type": "text", "citations": [
        {"url": "https://example.com/first", "cited_text": "First citation wins."}]})
    payload["content"].append({"type": "web_search_tool_result", "content": [
        {"type": "web_search_result", "url": "https://example.com/first", "title": "Duplicate"},
        {"type": "web_search_result", "url": "https://example.com/third"},
        {"type": "web_search_result", "url": "https://example.com/fourth"},
    ]})
    output = providers.parse_deepseek_search(payload)
    assert [row["url"] for row in output] == ["https://example.com/first", "https://example.com/second", "https://example.com/third"]
    assert output[0]["snippet"] == "First citation wins."


@pytest.mark.parametrize("payload", [
    {}, {"content": {}}, {"content": [None, {"type": "text", "text": "https://example.com/prose-link"}]},
    {"content": [{"type": "web_search_tool_result", "content": {"type": "web_search_tool_result_error", "error_code": "secret-test-key"}}]},
    {"content": [{"type": "web_search_tool_result", "content": []}, {"type": "text", "citations": "malformed"}]},
])
def test_missing_or_malformed_native_results_fail_without_echoing_provider_body(payload):
    with pytest.raises(ServiceError) as caught:
        providers.parse_deepseek_search(payload)
    assert caught.value.code == "invalid_search_output"
    assert "secret-test-key" not in caught.value.message
    assert "prose-link" not in caught.value.message


def test_empty_native_result_block_is_empty_search_not_prose_fallback():
    assert providers.parse_deepseek_search({"content": [
        {"type": "web_search_tool_result", "content": []},
        {"type": "text", "text": "https://example.com/a-link"},
    ]}) == []


def test_parser_skips_private_credentials_unsafe_ports_and_wrong_domain_urls():
    urls = ["http://127.0.0.1/a", "https://example.com:8443/a", "https://user:pass@example.com/a",
            "https://example.com/?key=synthetic%2Fsecret", "https://other.example/a", "https://example.com/valid"]
    payload = {"content": [{"type": "web_search_tool_result", "content": [
        {"type": "web_search_result", "url": url} for url in urls]}]}
    assert [row["url"] for row in providers.parse_deepseek_search(payload, domains=["example.com"], token="synthetic/secret")] == ["https://example.com/valid"]


def test_native_request_is_fixed_bounded_and_uses_only_verified_tool_fields(monkeypatch):
    transport = AsyncMock(return_value=Fetched(providers.DEEPSEEK_SEARCH_ENDPOINT, json.dumps(native_response()).encode(), "application/json", 200))
    monkeypatch.setattr(providers, "pinned_request", transport)
    output = asyncio.run(providers.search_web("A research query", SearchConfig(provider="deepseek", api_key="synthetic-api-key"), domains=["example.com"]))
    assert len(output) == 2
    args, kwargs = transport.call_args
    assert args == ("https://api.deepseek.com/anthropic/v1/messages",)
    assert kwargs["timeout"] == 65 and kwargs["redirects"] == 0 and kwargs["max_bytes"] == 1_000_000
    assert not kwargs.get("allow_loopback", False)
    assert kwargs["headers"]["x-api-key"] == "synthetic-api-key"
    assert kwargs["headers"]["Authorization"] == "Bearer synthetic-api-key"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    body = kwargs["json_body"]
    assert body["model"] == "deepseek-flash" and body["max_tokens"] == 2048
    assert body["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]
    assert "site:example.com" in body["messages"][0]["content"][0]["text"]
    assert "synthetic-api-key" not in json.dumps(body)
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_native_http_errors_retain_status_but_never_echo_key(monkeypatch, status):
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched(
        providers.DEEPSEEK_SEARCH_ENDPOINT, b'{"error":"secret-provider-key"}', "application/json", status)))
    with pytest.raises(ServiceError) as caught:
        asyncio.run(providers.search_web("query", SearchConfig(provider="deepseek", api_key="secret-provider-key")))
    assert caught.value.code == "provider_error" and f"HTTP {status}" in caught.value.message
    assert "secret-provider-key" not in caught.value.message


def test_missing_native_key_does_not_dispatch_network(monkeypatch):
    transport = AsyncMock()
    monkeypatch.setattr(providers, "pinned_request", transport)
    with pytest.raises(ServiceError) as caught:
        asyncio.run(providers.search_web("query", SearchConfig(provider="deepseek")))
    assert caught.value.code == "missing_search_key"
    transport.assert_not_awaited()


def test_research_reuses_request_official_ai_key_without_exposing_it_in_planner(monkeypatch):
    planning = AsyncMock(return_value=Plan(claims=[{"text": "A claim", "kind": "fact"}],
                                         queries=[{"query": "A claim records", "intent": "neutral"}], scope="Test scope"))
    searching = AsyncMock(return_value=[])
    monkeypatch.setattr(research_module, "complete", planning)
    monkeypatch.setattr(research_module, "search_web", searching)
    with pytest.raises(ServiceError) as caught:
        asyncio.run(research_module.research(ResearchRequest(
            topic="A test claim", search={"provider": "deepseek"},
            ai={"base_url": "https://api.deepseek.com/v1", "api_key": "ephemeral-synthetic-key", "model": "deepseek-flash"})))
    assert caught.value.code == "no_search_results"
    assert searching.await_count == 4
    for call in searching.call_args_list:
        assert call.args[1].provider == "deepseek"
        assert call.args[1].api_key.get_secret_value() == "ephemeral-synthetic-key"
    assert "ephemeral-synthetic-key" not in json.dumps(planning.call_args.args[2])
    assert "ephemeral-synthetic-key" not in caught.value.message


def test_complete_native_research_returns_valid_report_without_credentials(monkeypatch):
    planning = AsyncMock(return_value=Plan(claims=[{"text": "A claim", "kind": "fact"}],
                                         queries=[{"query": "A claim records", "intent": "neutral"}], scope="Test scope"))
    searching = AsyncMock(return_value=[{"url": "https://example.com/record", "title": "Original record", "snippet": "Original data."}])
    async def fetch(row, index, query, **kwargs):
        return Evidence(id=f"E{index}", title=row["title"], url=row["url"], publisher="example.com",
                        retrieved_at="2026-10-09T08:00:00Z", content_kind="snippet", excerpt=row["snippet"],
                        source_family="example.com", status="snippet_only", claim_ids=["C1"]), None
    async def analyze(report, ai):
        return report
    monkeypatch.setattr(research_module, "complete", planning)
    monkeypatch.setattr(research_module, "search_web", searching)
    monkeypatch.setattr(research_module, "fetch_evidence", fetch)
    monkeypatch.setattr(research_module, "analyze", analyze)
    output = asyncio.run(research_module.research(ResearchRequest(
        topic="A test claim", search={"provider": "deepseek"},
        ai={"base_url": "https://api.deepseek.com/v1", "api_key": "ephemeral-synthetic-key", "model": "deepseek-flash"})))
    validate_references(Report.model_validate(output))
    assert len(output["evidence"]) == 1 and len(output["search_log"]) == 4
    assert all(entry["provider"] == "deepseek" for entry in output["search_log"])
    assert "ephemeral-synthetic-key" not in json.dumps(output)
    assert "summary" not in output and "reasoning" not in output


def completion_transport(monkeypatch, schema):
    content = ({"claims": [{"text": "A test claim", "kind": "fact"}],
                "queries": [{"query": "Original records", "intent": "neutral"}], "scope": "Test scope"}
               if schema is Plan else
               {"observations": [{"kind": "logic", "text": "Comparable definitions are required.",
                                  "claim_ids": ["C1"], "evidence_ids": ["E1"]}]})
    envelope = {"choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps(content), "reasoning_content": "Internal reasoning must not enter the returned schema."}}]}
    transport = AsyncMock(return_value=Fetched("https://api.deepseek.com/v1/chat/completions",
                                               json.dumps(envelope).encode(), "application/json", 200))
    monkeypatch.setattr(providers, "pinned_request", transport)
    return transport


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro"])
@pytest.mark.parametrize("depth", ["brief", "standard", "deep"])
def test_official_planning_disables_thinking_and_bounds_output_for_every_depth(monkeypatch, model, depth):
    transport = completion_transport(monkeypatch, Plan)
    result = asyncio.run(providers.complete(
        AIConfig(base_url="https://api.deepseek.com/v1", api_key="synthetic-official-key", model=model),
        "Plan the evidence search.", {"topic": "A test claim", "depth": depth}, Plan))
    assert isinstance(result, Plan) and result.queries[0].query == "Original records"
    assert transport.call_args.args == ("https://api.deepseek.com/v1/chat/completions",)
    payload = transport.call_args.kwargs["json_body"]
    assert payload["model"] == model and payload["thinking"] == {"type": "disabled"}
    assert payload["max_tokens"] == 2048 and "reasoning_effort" not in payload
    assert "synthetic-official-key" not in json.dumps(payload)
    assert "Internal reasoning" not in result.model_dump_json()


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro"])
@pytest.mark.parametrize("depth,expected_effort", [("brief", "low"), ("standard", "high"), ("deep", "high"), (None, "high")])
def test_official_analysis_reserves_output_and_uses_depth_reasoning_budget(monkeypatch, model, depth, expected_effort):
    transport = completion_transport(monkeypatch, Analysis)
    data = {"evidence": [{"id": "E1", "excerpt": "Original evidence, unchanged."}]}
    if depth is not None:
        data["depth"] = depth
    result = asyncio.run(providers.complete(
        AIConfig(base_url="https://api.deepseek.com", api_key="synthetic-official-key", model=model),
        "Analyze only the supplied evidence.", data, Analysis))
    assert isinstance(result, Analysis) and result.observations[0].evidence_ids == ["E1"]
    payload = transport.call_args.kwargs["json_body"]
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == expected_effort and payload["max_tokens"] == 12000
    assert json.loads(payload["messages"][1]["content"]) == data
    assert "synthetic-official-key" not in json.dumps(payload)
    assert "Internal reasoning" not in result.model_dump_json()


@pytest.mark.parametrize("schema", [Plan, Analysis])
@pytest.mark.parametrize("base_url,model", [
    ("https://compatible.example/v1", "deepseek-flash"),
    ("https://api.deepseek.com.evil.example/v1", "deepseek-v4-pro"),
    ("http://localhost:11434/v1", "deepseek-flash"),
    ("https://api.deepseek.com/v1", "deepseek-chat"),
])
def test_provider_specific_thinking_fields_never_reach_other_compatible_endpoints_or_models(monkeypatch, schema, base_url, model):
    transport = completion_transport(monkeypatch, schema)
    result = asyncio.run(providers.complete(
        AIConfig(base_url=base_url, api_key="synthetic-own-key", model=model),
        "Return structured output.", {"topic": "A test claim", "depth": "brief"}, schema))
    assert isinstance(result, schema)
    assert transport.call_args.args == (base_url + "/chat/completions",)
    payload = transport.call_args.kwargs["json_body"]
    assert set(payload) == {"model", "messages", "stream"}
    assert not {"thinking", "reasoning_effort", "output_config", "max_tokens", "response_format"} & payload.keys()
    assert "synthetic-own-key" not in json.dumps(payload)


@pytest.mark.parametrize("default_url", ["https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions"])
@pytest.mark.parametrize("selected_url", ["", "https://api.deepseek.com/another/path",
                                           "https://api.deepseek.com:443/v1", "https://api.deepseek.com/v1/chat/completions"])
def test_ai_environment_key_is_inherited_only_within_the_same_origin(monkeypatch, default_url, selected_url):
    monkeypatch.setenv("TRUTH_AI_BASE_URL", default_url)
    monkeypatch.setenv("TRUTH_AI_API_KEY", "private-environment-test-key")
    resolved = providers.resolve_ai(AIConfig(base_url=selected_url))
    assert resolved.api_key.get_secret_value() == "private-environment-test-key"
    assert resolved.base_url == (selected_url or default_url)


@pytest.mark.parametrize("selected_url", [
    "https://third-party.example/v1", "https://api.deepseek.com.evil.example/v1",
    "http://api.deepseek.com/v1", "https://api.deepseek.com:8443/v1",
    "https://user@api.deepseek.com/v1", "https://user:password@api.deepseek.com/v1",
    "http://localhost:11434/v1", "https://api.deepseek.com:0/v1",
])
def test_ai_environment_key_is_never_inherited_by_another_or_invalid_origin(monkeypatch, selected_url):
    monkeypatch.setenv("TRUTH_AI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("TRUTH_AI_API_KEY", "private-environment-test-key")
    assert providers.resolve_ai(AIConfig(base_url=selected_url)).api_key.get_secret_value() == ""


def test_explicit_third_party_ai_key_is_used_without_environment_key(monkeypatch):
    monkeypatch.setenv("TRUTH_AI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("TRUTH_AI_API_KEY", "private-environment-test-key")
    transport = completion_transport(monkeypatch, Plan)
    asyncio.run(providers.complete(AIConfig(base_url="https://third-party.example/v1", api_key="explicit-own-key", model="other-model"),
                                   "Return a plan.", {"topic": "A test claim"}, Plan))
    assert transport.call_args.args == ("https://third-party.example/v1/chat/completions",)
    assert transport.call_args.kwargs["headers"]["Authorization"] == "Bearer explicit-own-key"
    assert "private-environment-test-key" not in str(transport.call_args)


def test_changing_public_ai_origin_without_explicit_key_fails_before_any_network_dispatch(monkeypatch):
    monkeypatch.setenv("TRUTH_AI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("TRUTH_AI_API_KEY", "private-environment-test-key")
    transport = AsyncMock()
    monkeypatch.setattr(providers, "pinned_request", transport)
    with pytest.raises(ServiceError) as caught:
        asyncio.run(providers.complete(AIConfig(base_url="https://third-party.example/v1", model="other-model"),
                                       "Return a plan.", {"topic": "A test claim"}, Plan))
    assert caught.value.code == "missing_ai_key"
    assert "private-environment-test-key" not in caught.value.message
    transport.assert_not_awaited()


def test_one_failed_search_cancels_and_drains_peers_before_returning_original_error(monkeypatch):
    planning = AsyncMock(return_value=Plan(
        claims=[{"text": "A test claim", "kind": "fact"}], scope="Test scope",
        queries=[{"query": query, "intent": intent} for query, intent in (
            ("fail-search", "neutral"), ("support-search", "support"),
            ("counter-search", "counter"), ("history-search", "actor_history"))]))
    fetch, analyze = AsyncMock(), AsyncMock()
    monkeypatch.setattr(research_module, "complete", planning)
    monkeypatch.setattr(research_module, "fetch_evidence", fetch)
    monkeypatch.setattr(research_module, "analyze", analyze)
    failure = ServiceError("provider_error", "Synthetic upstream failure", 502)
    async def scenario():
        all_started = asyncio.Event()
        started, cleaned = set(), set()
        async def search(query, config):
            started.add(query)
            if len(started) == 4:
                all_started.set()
            if query == "fail-search":
                await all_started.wait()
                raise failure
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                # Cleanup itself awaits: returning early after cancel() is insufficient.
                await asyncio.sleep(0)
                cleaned.add(query)
                raise
        monkeypatch.setattr(research_module, "search_web", search)
        with pytest.raises(ServiceError) as caught:
            await asyncio.wait_for(research_module.research(ResearchRequest(
                topic="A test claim", depth="brief", search={"provider": "deepseek", "api_key": "synthetic-key"})), timeout=1)
        assert caught.value is failure
        # Assert before asyncio.run closes its loop, which would cancel stragglers itself.
        assert cleaned == {"support-search", "counter-search", "history-search"}
        fetch.assert_not_awaited()
        analyze.assert_not_awaited()
    asyncio.run(scenario())


def test_cancelled_research_drains_active_searches_and_never_dispatches_queued_deep_queries(monkeypatch):
    planning = AsyncMock(return_value=Plan(claims=[{"text": "A test claim", "kind": "fact"}],
                                         queries=[{"query": "Original records", "intent": "neutral"}], scope="Test scope"))
    fetch, analyze = AsyncMock(), AsyncMock()
    monkeypatch.setattr(research_module, "complete", planning)
    monkeypatch.setattr(research_module, "fetch_evidence", fetch)
    monkeypatch.setattr(research_module, "analyze", analyze)
    async def scenario():
        first_batch_started = asyncio.Event()
        started, cleaned = set(), set()
        async def search(query, config):
            started.add(query)
            if len(started) == 4:
                first_batch_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await asyncio.sleep(0)
                cleaned.add(query)
                raise
        monkeypatch.setattr(research_module, "search_web", search)
        task = asyncio.create_task(research_module.research(ResearchRequest(
            topic="A test claim", depth="deep", search={"provider": "deepseek", "api_key": "synthetic-key"})))
        await asyncio.wait_for(first_batch_started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(started) == 4 and cleaned == started
        fetch.assert_not_awaited()
        analyze.assert_not_awaited()
    asyncio.run(scenario())
