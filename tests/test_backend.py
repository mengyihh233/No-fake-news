import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app as application
from truth_backend import providers, research as research_module, security
from truth_backend.models import Analysis, Observation, Report, ResearchRequest, SummarizeRequest, TimelineItem
from truth_backend.reports import apply_analysis, public_report, validate_references
from truth_backend.security import Fetched, ServiceError
from truth_backend.source_access import credential_headers, headers_for_url, secret_strings, redact_source_secrets
from truth_backend.models import SourceCredential


def sample_report(mode="ai-summary"):
    return Report.model_validate({
        "schema_version": "1.0", "topic": "某项目的总量从 2020 年的 10 增长到 2021 年的 20。", "mode": mode,
        "generated_at": "2026-10-09T08:00:00Z", "scope": "限定统计口径", "limitations": [],
        "claims": [{"id": "C1", "text": "2021 年总量为 20。", "kind": "fact", "verdict": "有记录支持", "analysis": "条件性支持"}],
        "evidence": [{"id": "E1", "title": "原始年报", "url": "https://example.com/report", "publisher": "example.com",
                      "published_at": "2022-01-01", "retrieved_at": "2026-10-09T08:00:00Z", "source_type": "primary",
                      "content_kind": "full_text", "excerpt": "2020 年总量为 10；2021 年总量为 20。", "context": "报告定义见正文。",
                      "source_family": "example.com", "status": "retrieved", "claim_ids": ["C1"], "screenshots": []}],
        "links": [{"from": "E1", "to": "C1", "relation": "supports", "note": "裁决不能泄漏"}],
        "timeline": [], "charts": [], "comparisons": [],
        "reasoning": [{"id": "R1", "premise_ids": ["E1"], "claim_id": "C1", "text": "数值支持", "kind": "data"}],
        "questions": ["统计口径是否变化？"],
        "summary": {"text": "仅该年报支持命题。", "verdict": "有记录支持", "caveats": [], "evidence_ids": ["E1"]},
        "search_log": [],
    })


def analysis_data(mode="ai-summary"):
    return {
        "limitations": [], "evidence_annotations": [{"evidence_id": "E1", "claim_ids": ["C1"], "source_type": "primary", "context": "原始年报"}],
        "claim_assessments": [{"claim_id": "C1", "verdict": "有记录支持", "analysis": "数值取自 E1。"}],
        "links": [{"from": "E1", "to": "C1", "relation": "supports", "note": "数值吻合"}],
        "timeline": [], "charts": [{"title": "总量", "unit": "个", "kind": "bar", "points": [
            {"label": "2021", "value": 20, "evidence_ids": ["E1"], "source_quote": "2021 年总量为 20。"}], "note": "原始统计"}],
        "comparisons": [], "reasoning": [{"id": "R1", "premise_ids": ["E1"], "claim_id": "C1", "text": "记录提供总量", "kind": "data"}],
        "questions": [], "summary": {"text": "记录支持这一总量。", "verdict": "有记录支持", "caveats": [], "evidence_ids": ["E1"]},
    }


@pytest.fixture
def client():
    return TestClient(application.app, base_url="http://127.0.0.1")


def test_evidence_only_uses_allowlist_and_has_no_hidden_verdict():
    report = sample_report()
    output = public_report(report, "evidence-only")
    assert "summary" not in output and "reasoning" not in output
    assert set(output["claims"][0]) == {"id", "text", "kind"}
    assert output["links"][0]["relation"] == "relevant_to"
    assert "裁决不能泄漏" not in json.dumps(output, ensure_ascii=False)
    assert report.summary is not None  # export never mutates its input


def test_apply_analysis_does_not_store_verdict_or_reasoning_in_evidence_mode():
    report = sample_report("evidence-only")
    report.claims[0].verdict = report.claims[0].analysis = None
    report.summary, report.reasoning = None, []
    output = public_report(apply_analysis(report, Analysis.model_validate(analysis_data())))
    assert "summary" not in output and "reasoning" not in output
    assert "来源识别/语境提示" not in output["evidence"][0]["context"]
    assert output["charts"][0]["points"][0]["value"] == 20
    assert "source_quote" not in output["charts"][0]["points"][0]


def test_evidence_only_retains_neutral_observations_without_verdict_fields():
    data = analysis_data()
    data["observations"] = [{"kind": "logic", "text": "年度总量比较需要确认两个年份采用相同统计定义。",
                             "claim_ids": ["C1"], "evidence_ids": ["E1"]}]
    report = sample_report("evidence-only")
    output = public_report(apply_analysis(report, Analysis.model_validate(data)))
    assert output["observations"] == data["observations"]
    assert "reasoning" not in output and "summary" not in output
    assert set(output["claims"][0]) == {"id", "text", "kind"}
    validate_references(Report.model_validate(output))


@pytest.mark.parametrize("claim_ids,evidence_ids", [(["C999"], ["E1"]), (["C1"], ["E999"])])
def test_observations_cannot_reference_unknown_claim_or_evidence(claim_ids, evidence_ids):
    data = analysis_data()
    data["observations"] = [{"kind": "data", "text": "需核查口径。", "claim_ids": claim_ids, "evidence_ids": evidence_ids}]
    with pytest.raises(ServiceError):
        apply_analysis(sample_report(), Analysis.model_validate(data))


def test_report_observation_references_are_checked_on_import():
    report = sample_report()
    report.observations = [Observation(kind="history", text="历史记录范围需核查。", claim_ids=["C1"], evidence_ids=["E404"])]
    with pytest.raises(ServiceError):
        validate_references(report)


@pytest.mark.parametrize("mutation", [
    lambda data: data["links"][0].update({"from": "E999"}),
    lambda data: data["summary"].update({"evidence_ids": ["E999"]}),
    lambda data: data["reasoning"][0].update({"premise_ids": ["R2"]}),
    lambda data: data["claim_assessments"][0].update({"claim_id": "C99"}),
    lambda data: data["summary"].update({"text": "新 URL https://fabricated.example/news"}),
    lambda data: data["charts"][0]["points"][0].update({"value": 200}),
    lambda data: data["charts"][0]["points"][0].update({"source_quote": "这一句并不存在 20"}),
])
def test_fabricated_ids_urls_quotes_and_numbers_are_rejected(mutation):
    data = analysis_data()
    mutation(data)
    with pytest.raises(ServiceError):
        apply_analysis(sample_report(), Analysis.model_validate(data))


def test_model_cannot_replace_source_objects():
    data = analysis_data()
    data["evidence"] = [{"url": "https://fabricated.example/", "excerpt": "假摘录"}]
    with pytest.raises(ValidationError):
        Analysis.model_validate(data)


def test_missing_chart_value_remains_null_not_zero():
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    point["value"] = None
    point.pop("source_quote")
    output = public_report(apply_analysis(sample_report(), Analysis.model_validate(data)))
    assert output["charts"][0]["points"][0]["value"] is None


def test_derived_count_accepts_unique_exact_records_and_adds_completeness_caveat():
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    point.update({"value": 2, "source_quote": "", "calculation": {
        "operation": "count", "source_quotes": ["2020 年总量为 10", "2021 年总量为 20。"],
        "description": "统计 E1 摘录列出的两个年度总量记录，单位为年度记录条数，仅限该摘录且不代表其他年度。"}})
    output = public_report(apply_analysis(sample_report(), Analysis.model_validate(data)))
    assert output["charts"][0]["points"][0]["value"] == 2
    assert "不能证明资料覆盖全集" in output["limitations"][-1]
    validate_references(Report.model_validate(output))


@pytest.mark.parametrize("quotes,value", [
    (["2020 年总量为 10", "虚构年度记录"], 2),
    (["2020 年总量为 10", "2021 年总量为 20。"], 3),
    (["2020 年总量为 10", "2020 年总量为 10"], 2),
    ([""], 1),
    ([], 1),
])
def test_derived_count_rejects_forged_duplicate_and_miscounted_records(quotes, value):
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    point.update({"value": value, "source_quote": "", "calculation": {
        "operation": "count", "source_quotes": quotes, "description": "按 E1 摘录列出的年度记录条数计数，完整性待人工核查。"}})
    with pytest.raises(ServiceError):
        apply_analysis(sample_report(), Analysis.model_validate(data))


def test_empty_count_is_zero_observed_records_with_explicit_caveat():
    data = analysis_data()
    data["charts"][0]["points"][0].update({"value": 0, "source_quote": "", "calculation": {
        "operation": "count", "source_quotes": [], "description": "限定为本段 E1 所列 2020—2021 年资料中发生在 2019 年的记录数；未证实完整清单。"}})
    output = public_report(apply_analysis(sample_report(), Analysis.model_validate(data)))
    assert output["charts"][0]["points"][0]["value"] == 0
    assert "空清单的 0" in output["limitations"][-1]


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/a", "http://[::1]/", "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/", "http://192.168.1.1/", "file:///etc/passwd", "https://user:secret@example.com/",
    "https://example.com:8443/", "http://localhost/", "http://service.internal/", "http://2130706433/",
])
def test_ssrf_url_shape_blocked(url):
    with pytest.raises(ServiceError):
        security.check_url_shape(url)


def test_model_loopback_allowed_but_private_lan_is_not():
    assert security.check_url_shape("http://localhost:11434/v1", allow_loopback=True)
    with pytest.raises(ServiceError):
        security.check_url_shape("http://192.168.0.2:11434/v1", allow_loopback=True)


def test_dns_rebinding_to_private_is_blocked_even_for_ai(monkeypatch):
    loop = asyncio.new_event_loop()
    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]))
        with pytest.raises(ServiceError):
            await security.resolve_public("https://public.example.com/", allow_loopback=True)
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


def test_pinned_transport_uses_validated_ip_and_original_sni(monkeypatch):
    calls = []
    monkeypatch.setattr(security, "resolve_public", AsyncMock(return_value=("https", "example.com", 443, "93.184.216.34")))
    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="hello", headers={"content-type": "text/plain"})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(security.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    response = asyncio.run(security.pinned_request("https://example.com/article"))
    assert response.content == b"hello"
    assert calls[0].url.host == "93.184.216.34"
    assert calls[0].headers["host"] == "example.com"
    assert calls[0].extensions["sni_hostname"] == "example.com"


def test_redirect_to_metadata_is_blocked_before_request(monkeypatch):
    calls = []
    async def resolve(url, **kwargs):
        security.check_url_shape(url)
        return "https", "example.com", 443, "93.184.216.34"
    monkeypatch.setattr(security, "resolve_public", resolve)
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(security.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(ServiceError):
        asyncio.run(security.pinned_request("https://example.com/", redirects=4))
    assert len(calls) == 1


def test_provider_error_body_does_not_echo_key(monkeypatch):
    secret = "secret-do-not-echo"
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched("https://example.com", json.dumps({"error": secret}).encode(), "application/json", 401)))
    from truth_backend.models import AIConfig, Plan
    with pytest.raises(ServiceError) as error:
        asyncio.run(providers.complete(AIConfig(base_url="https://example.com/v1", api_key=secret, model="test"), "system", {}, Plan))
    assert "401" in error.value.message and secret not in error.value.message


def test_validation_error_does_not_echo_secret(client):
    response = client.post("/api/research", json={"topic": "test topic", "ai": {"api_key": {"secret": "do-not-echo"}}})
    assert response.status_code == 422
    assert "do-not-echo" not in response.text


def test_local_host_and_origin_guard(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 403
    assert client.post("/api/research", json={}, headers={"Origin": "https://attacker.example"}).status_code == 403


def test_research_missing_search_key_has_specific_error_and_never_demo(client, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    response = client.post("/api/research", json={"topic": "一个真实论题", "mode": "evidence-only"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_search_key"
    assert "evidence" not in response.json()


def test_demo_filters_mode_on_server(client, monkeypatch, tmp_path):
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "demo-report.json").write_text(sample_report().model_dump_json(by_alias=True), encoding="utf-8")
    monkeypatch.setattr(application, "ROOT", tmp_path)
    evidence_response = client.get("/api/demo?mode=evidence-only")
    summary_response = client.get("/api/demo?mode=ai-summary")
    assert evidence_response.status_code == summary_response.status_code == 200
    assert "summary" not in evidence_response.json() and "reasoning" not in evidence_response.json()
    assert summary_response.json()["summary"]["evidence_ids"] == ["E1"]


def test_capture_route_only_serves_allowed_image_names(client, monkeypatch, tmp_path):
    capture_dir = tmp_path / "examples" / "captures"
    capture_dir.mkdir(parents=True)
    name = "a" * 32 + ".jpg"
    (capture_dir / name).write_bytes(b"actual-image-data")
    (capture_dir / "secret.txt").write_text("not public", encoding="utf-8")
    monkeypatch.setattr(application, "ROOT", tmp_path)
    monkeypatch.setattr(application, "CAPTURE_DIR", tmp_path / "runtime" / "captures")
    response = client.get("/captures/" + name)
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert client.get("/captures/secret.txt").status_code == 404


def test_summarize_keeps_evidence_immutable_and_does_not_search(client, monkeypatch):
    monkeypatch.setattr(research_module, "complete", AsyncMock(return_value=Analysis.model_validate(analysis_data())))
    search = AsyncMock(side_effect=AssertionError("must not search"))
    monkeypatch.setattr(research_module, "search_web", search)
    original = sample_report("evidence-only")
    response = client.post("/api/summarize", json={"report": public_report(original), "ai": {"model": "mock"}})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mode"] == "ai-summary" and data["summary"]["evidence_ids"] == ["E1"]
    assert data["evidence"][0]["url"] == original.evidence[0].url
    assert data["evidence"][0]["excerpt"] == original.evidence[0].excerpt
    search.assert_not_called()
    validate_references(Report.model_validate(data))


def test_summarize_preserves_all_base_analysis_and_provides_it_to_model(client, monkeypatch):
    original = apply_analysis(sample_report("evidence-only"), Analysis.model_validate(analysis_data()))
    original.observations = [Observation(kind="data", text="E1 列出两个年度总量，统计口径是否连续仍需核实。",
                                         claim_ids=["C1"], evidence_ids=["E1"])]
    original.timeline = [TimelineItem(
        date="2021", title="年度记录", detail="E1 列出 2021 年度的记录。", evidence_ids=["E1"])]
    base = public_report(original)
    new_analysis = analysis_data()
    new_analysis["observations"] = [{"kind": "logic", "text": "替换旧观察", "claim_ids": ["C1"], "evidence_ids": ["E1"]}]
    new_analysis["timeline"] = []
    completion = AsyncMock(return_value=Analysis.model_validate(new_analysis))
    monkeypatch.setattr(research_module, "complete", completion)
    monkeypatch.setattr(research_module, "search_web", AsyncMock(side_effect=AssertionError("no new search")))
    response = client.post("/api/summarize", json={"report": base, "ai": {"model": "mock"}})
    assert response.status_code == 200, response.text
    output = response.json()
    for field in ("evidence", "observations", "timeline", "charts", "comparisons", "links", "questions", "search_log", "depth"):
        assert output[field] == base[field], field
    payload = completion.await_args.args[2]
    assert payload["prior_analysis"]["observations"] == base["observations"]
    assert payload["prior_analysis"]["charts"] == base["charts"]
    assert output["summary"] and output["claims"][0]["verdict"]


def test_mocked_research_pipeline_returns_real_schema_and_strips_verdict(client, monkeypatch):
    from truth_backend.models import Plan
    plan = Plan.model_validate({"claims": [{"text": "2021 年总量为 20。", "kind": "fact"}],
                                "queries": [{"query": "原始年报", "intent": "neutral"}], "scope": "限定统计口径"})
    monkeypatch.setattr(research_module, "complete", AsyncMock(side_effect=[plan, Analysis.model_validate(analysis_data())]))
    search = AsyncMock(return_value=[{"url": "https://example.com/report", "title": "原始年报", "snippet": "2021 年总量为 20。"}])
    monkeypatch.setattr(research_module, "search_web", search)
    monkeypatch.setattr(research_module, "fetch_evidence", AsyncMock(return_value=(sample_report().evidence[0], "")))
    response = client.post("/api/research", json={"topic": "2021 年总量为 20。", "mode": "evidence-only",
                                                "ai": {"model": "mock"}, "search": {"api_key": "secret-key"}})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["schema_version"] == "1.0" and len(data["search_log"]) == 4
    assert search.await_count == 4
    assert "summary" not in data and "reasoning" not in data
    assert "secret-key" not in response.text
    validate_references(Report.model_validate(data))


@pytest.mark.parametrize("depth,queries,sources,claims,excerpt_chars", [
    ("brief", 4, 6, 4, 1800), ("standard", 4, 12, 8, 3000), ("deep", 8, 24, 12, 4500),
])
def test_depth_executes_different_query_source_claim_and_excerpt_budgets(client, monkeypatch, depth, queries, sources, claims, excerpt_chars):
    from truth_backend.models import Plan
    plan = Plan.model_validate({"claims": [{"text": f"原子论断 {i}", "kind": "fact"} for i in range(12)],
                                "queries": [{"query": "弱模型仅提供一个查询", "intent": "neutral"}], "scope": "测试执行预算"})
    analysis = Analysis.model_validate({"observations": [{"kind": "data", "text": "各条记录的口径仍需核查。", "claim_ids": ["C1"], "evidence_ids": ["E1"]}]})
    completion = AsyncMock(side_effect=[plan, analysis])
    monkeypatch.setattr(research_module, "complete", completion)
    counter = 0
    async def fake_search(query, config):
        nonlocal counter
        counter += 1
        return [{"url": f"https://example.com/query-{counter}-{rank}", "title": f"record {counter}-{rank}"} for rank in range(3)]
    search = AsyncMock(side_effect=fake_search)
    monkeypatch.setattr(research_module, "search_web", search)
    fetch_calls = []
    async def fake_fetch(row, index, query, max_excerpt, **kwargs):
        fetch_calls.append((row, max_excerpt))
        evidence = sample_report().evidence[0].model_copy(update={"id": f"E{index}", "url": row["url"], "title": row["title"]})
        return evidence, ""
    monkeypatch.setattr(research_module, "fetch_evidence", fake_fetch)
    response = client.post("/api/research", json={"topic": "需完整核查的复杂论题", "depth": depth, "ai": {"model": "mock"}, "search": {"api_key": "mock-key"}})
    assert response.status_code == 200, response.text
    output = response.json()
    assert output["depth"] == depth and len(output["claims"]) == claims
    assert len(output["evidence"]) == sources and len(output["search_log"]) == queries
    assert search.await_count == queries and len(fetch_calls) == sources
    assert all(call[1] == excerpt_chars for call in fetch_calls)
    counts = {intent: sum(log["intent"] == intent for log in output["search_log"])
              for intent in ("neutral", "support", "counter", "actor_history")}
    assert set(counts.values()) == {2 if depth == "deep" else 1}
    assert len({item[0]["research_query"] for item in fetch_calls[:4]}) == 4
    assert completion.await_args_list[0].args[2]["budget"]["max_sources"] == sources
    validate_references(Report.model_validate(output))


@pytest.mark.parametrize("depth,seconds", [("brief", 150), ("standard", 180), ("deep", 360)])
def test_api_uses_depth_specific_execution_deadline(client, monkeypatch, depth, seconds):
    calls = []
    async def fake_bounded(operation, timeout_seconds=180):
        calls.append(timeout_seconds)
        return await operation
    monkeypatch.setattr(application, "bounded", fake_bounded)
    monkeypatch.setattr(application, "research", AsyncMock(return_value={"depth": depth}))
    response = client.post("/api/research", json={"topic": "测试深度时限", "depth": depth})
    assert response.status_code == 200 and calls == [seconds]


def test_health_reports_environment_base_url_and_real_depth_budgets(client, monkeypatch):
    monkeypatch.setenv("TRUTH_AI_BASE_URL", "http://127.0.0.1:11434/v1")
    health = client.get("/api/health").json()
    assert health["configured"]["ai_base_url"] is True
    assert health["depths"]["brief"]["max_sources"] == 6
    assert health["depths"]["deep"]["timeout_seconds"] == 360


def test_snippet_only_is_explicit_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(side_effect=ServiceError("network_error", "网络失败")))
    evidence, limitation = asyncio.run(providers.fetch_evidence({"url": "https://example.com/article", "title": "标题", "snippet": "搜索摘要内容", "raw_content": "", "published_at": None}, 1))
    assert evidence.status == "snippet_only" and evidence.content_kind == "snippet"
    assert evidence.excerpt == "搜索摘要内容" and limitation


def test_keyword_excerpts_select_relevant_original_text_over_navigation():
    relevant = "Apollo 11 completed its lunar landing on July 20, 1969."
    body = ("Navigation menu: About, Contact, Topics, Home.\n" * 100) + relevant + "\nNearby paragraph describes the mission definition.\n"
    excerpt, selected = providers.select_excerpt(body, "Apollo 11 lunar landing records")
    assert selected and relevant in excerpt
    assert "Nearby paragraph describes the mission definition." in excerpt
    assert len(excerpt) <= 3000


@pytest.mark.parametrize("max_excerpt", [1800, 3000, 4500])
def test_fetch_respects_actual_excerpt_character_budget(monkeypatch, max_excerpt):
    content = ("Neutral body without matching keywords. " * 350).encode()
    monkeypatch.setattr(providers, "pinned_request", AsyncMock(return_value=Fetched("https://example.com/article", content, "text/plain", 200)))
    evidence, _ = asyncio.run(providers.fetch_evidence({"url": "https://example.com/article", "title": "记录", "snippet": "", "raw_content": "", "published_at": None}, 1, max_excerpt=max_excerpt))
    assert max_excerpt - 1 <= len(evidence.excerpt) <= max_excerpt


def test_chinese_keyword_excerpts_are_verbatim_and_fallback_is_explicit():
    relevant = "该项工程在二零二一年成功完成月面着陆，并安全返航。"
    body = "导航栏目\n" * 1000 + relevant + "\n原文附有明确的任务定义。"
    excerpt, selected = providers.select_excerpt(body, "成功月面着陆的任务清单")
    assert selected and relevant in excerpt
    unmatched, selected = providers.select_excerpt(body, "unmatched-keyword")
    assert not selected and unmatched == body[:3000]


def test_json_fence_supported_and_malformed_rejected():
    assert providers.decode_json('```json\n{"a":1}\n```') == {"a": 1}
    with pytest.raises(ServiceError):
        providers.decode_json("not json")


@pytest.mark.parametrize("language,expected", [("en", "search API key"), ("ja", "検索 API キー"), ("zh-CN", "搜索 API Key")])
def test_errors_are_localized_without_echoing_request_secrets(client, monkeypatch, language, expected):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    response = client.post("/api/research", json={"topic": "A real topic", "language": language, "ai": {"api_key": "private-ai-secret"}})
    assert response.status_code == 400 and expected in response.json()["error"]["message"]
    assert "private-ai-secret" not in response.text


@pytest.mark.parametrize("language,expected", [("en", "Invalid request"), ("ja", "入力形式"), ("zh-CN", "输入结构")])
def test_validation_errors_honor_language_and_never_echo_secrets(client, language, expected):
    response = client.post("/api/research", json={"topic": "test topic", "language": language, "mode": "invalid", "ai": {"api_key": "private-secret"}})
    assert response.status_code == 422 and expected in response.json()["error"]["message"]
    assert "private-secret" not in response.text


@pytest.mark.parametrize("language,note", [("en", "Screenshots require"), ("ja", "スクリーンショットには"), ("zh-CN", "截图需")])
def test_health_localizes_status_and_exposes_supported_languages(client, language, note):
    data = client.get("/api/health?language=" + language).json()
    assert note in data["screenshots"]["note"]
    assert data["supported_languages"] == ["zh-CN", "en", "ja"]
    assert data["source_access"]["credentials_persisted"] is False


@pytest.mark.parametrize("language", ["en", "ja"])
def test_language_demo_reads_its_own_file_and_filters_mode(client, monkeypatch, tmp_path, language):
    directory = tmp_path / "examples"
    directory.mkdir()
    report = sample_report()
    report.language = language
    report.scope = "English demo scope" if language == "en" else "日本語のデモ範囲"
    (directory / f"demo-report.{language}.json").write_text(report.model_dump_json(by_alias=True), encoding="utf-8")
    monkeypatch.setattr(application, "ROOT", tmp_path)
    output = client.get("/api/demo?language=" + language).json()
    assert output["language"] == language and output["scope"] == report.scope
    assert "summary" not in output and "reasoning" not in output
    assert output["evidence"][0]["excerpt"] == report.evidence[0].excerpt
    (directory / f"demo-report.{language}.json").unlink()
    assert client.get("/api/demo?language=" + language).status_code == 500


@pytest.mark.parametrize("language,marker", [("en", "OUTPUT LANGUAGE"), ("ja", "出力言語"), ("zh-CN", "输出语言要求")])
def test_summary_language_is_explicit_without_translating_existing_sources(client, monkeypatch, language, marker):
    completion = AsyncMock(return_value=Analysis.model_validate(analysis_data()))
    monkeypatch.setattr(research_module, "complete", completion)
    report = sample_report("evidence-only")
    report.language = "zh-CN"
    original = public_report(report)
    response = client.post("/api/summarize", json={"report": original, "language": language, "ai": {"model": "mock"}})
    assert response.status_code == 200, response.text
    output = response.json()
    assert output["language"] == "zh-CN" and output["summary_language"] == language
    assert output["evidence"] == original["evidence"]
    assert marker in completion.await_args.args[1]
    assert completion.await_args.args[2]["language"] == language


@pytest.mark.parametrize("kind,expected_header", [("cookie", "Cookie"), ("bearer", "Authorization")])
def test_source_tokens_are_exact_origin_scoped(kind, expected_header):
    origins = credential_headers([SourceCredential(origin="https://example.com/", kind=kind, token="session-secret")])
    assert expected_header in headers_for_url("https://example.com/path", origins)
    for unrelated in ("https://other.example.com/path", "http://example.com/path", "https://example.com:80/path", "https://evil.example.org/path"):
        assert headers_for_url(unrelated, origins) is None


def test_basic_source_credentials_use_standard_header_only():
    import base64
    origins = credential_headers([SourceCredential(origin="https://example.com", kind="basic", username="account-user", password="account-pass")])
    expected = "Basic " + base64.b64encode(b"account-user:account-pass").decode()
    assert headers_for_url("https://example.com/data", origins) == {"Authorization": expected}


def test_individual_cookie_values_echoed_in_body_are_redacted():
    credentials = [SourceCredential(origin="https://example.com", kind="cookie", token='session=private-session-value; csrf="private-csrf-value"')]
    secrets = secret_strings(credentials, credential_headers(credentials))
    item = sample_report().evidence[0]
    item.excerpt = "Page echoed private-session-value and private-csrf-value."
    assert redact_source_secrets(item, secrets)
    assert "private-session-value" not in item.excerpt and "private-csrf-value" not in item.excerpt


@pytest.mark.parametrize("embedded", ["url", "label", "topic"])
def test_credential_strings_in_public_source_inputs_are_rejected_before_ai(client, monkeypatch, embedded):
    completion = AsyncMock()
    monkeypatch.setattr(research_module, "complete", completion)
    payload = {"topic": "Review a real topic", "language": "en", "search": {"api_key": "search-key"},
               "sources": [{"url": "https://example.com/source", "label": "Public source"}],
               "source_credentials": [{"origin": "https://example.com", "kind": "cookie", "token": "session=private-cookie-value"}]}
    if embedded == "topic":
        payload["topic"] += " private-cookie-value"
    elif embedded == "url":
        payload["sources"][0]["url"] += "?session=private%2Dcookie%2Dvalue"
    else:
        payload["sources"][0]["label"] = "private-cookie-value"
    response = client.post("/api/research", json=payload)
    assert response.status_code == 400 and response.json()["error"]["code"] == "credentials_in_public_input"
    assert "private-cookie-value" not in response.text
    completion.assert_not_called()


@pytest.mark.parametrize("credential", [
    {"origin": "http://example.com", "kind": "cookie", "token": "secret"},
    {"origin": "https://127.0.0.1", "kind": "bearer", "token": "secret"},
    {"origin": "https://169.254.169.254", "kind": "bearer", "token": "secret"},
    {"origin": "https://example.com/path", "kind": "cookie", "token": "secret"},
    {"origin": "https://example.com?session=secret", "kind": "cookie", "token": "secret"},
    {"origin": "https://example.com", "kind": "basic", "username": "user:name", "password": "secret"},
    {"origin": "https://example.com", "kind": "cookie", "token": "\nheader-injection"},
    {"origin": "https://example.com", "kind": "cookie", "token": "日本語の値"},
    {"origin": "https://example.com", "kind": "bearer", "token": ""},
])
def test_source_credentials_reject_unsafe_origins_and_header_injection(credential):
    with pytest.raises(ServiceError):
        credential_headers([SourceCredential.model_validate(credential)])


def test_source_credentials_survive_only_same_origin_redirect(monkeypatch):
    calls = []
    async def resolve(url, **kwargs):
        scheme, host, port = security.check_url_shape(url)
        return scheme, host, port, "93.184.216.34"
    monkeypatch.setattr(security, "resolve_public", resolve)
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(302, headers={"location": "https://example.com/second"})
        if len(calls) == 2:
            return httpx.Response(302, headers={"location": "https://other.example.org/final"})
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(security.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(security.pinned_request("https://example.com/start", headers={"Cookie": "session=private", "Authorization": "Bearer private"}, redirects=3))
    assert result.status_code == 200 and len(calls) == 3
    assert calls[0].headers["cookie"] == calls[1].headers["cookie"] == "session=private"
    assert calls[0].headers["authorization"] == calls[1].headers["authorization"] == "Bearer private"
    assert "cookie" not in calls[2].headers and "authorization" not in calls[2].headers


@pytest.mark.parametrize("kind", ["cookie", "bearer", "basic"])
@pytest.mark.parametrize("encoding", ["plain", "percent", "nested"])
def test_credential_in_redirect_url_is_blocked_before_any_egress(monkeypatch, kind, encoding):
    from urllib.parse import quote
    secret = "private-account-token"
    credential = SourceCredential(origin="https://example.com", kind=kind,
                                  username="account-user" if kind == "basic" else "",
                                  password=secret if kind == "basic" else "",
                                  token="session=" + secret if kind == "cookie" else secret if kind == "bearer" else "")
    headers = headers_for_url("https://example.com/start", credential_headers([credential]))
    encoded = secret if encoding == "plain" else secret.replace("-", "%2D")
    if encoding == "nested":
        encoded = quote(encoded, safe="")
    calls = []
    async def resolve(url, **kwargs):
        scheme, host, port = security.check_url_shape(url)
        return scheme, host, port, "93.184.216.34"
    monkeypatch.setattr(security, "resolve_public", resolve)
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://other.example.org/next?session=" + encoded})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(security.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(ServiceError) as error:
        asyncio.run(security.pinned_request("https://example.com/start", headers=headers, redirects=3))
    assert error.value.code == "credentials_in_public_input"
    assert secret not in error.value.message and len(calls) == 1


def test_credential_url_guard_survives_an_earlier_cross_origin_header_drop(monkeypatch):
    calls = []
    async def resolve(url, **kwargs):
        scheme, host, port = security.check_url_shape(url)
        return scheme, host, port, "93.184.216.34"
    monkeypatch.setattr(security, "resolve_public", resolve)
    def handler(request):
        calls.append(request)
        location = "https://other.example.org/ordinary" if len(calls) == 1 else "https://third.example.org/next?key=private-bearer-token"
        return httpx.Response(302, headers={"location": location})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(security.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(ServiceError):
        asyncio.run(security.pinned_request("https://example.com/start", headers={"Authorization": "Bearer private-bearer-token"}, redirects=3))
    assert len(calls) == 2 and "authorization" not in calls[1].headers


def test_final_evidence_url_with_credential_is_excluded_not_snippet_fallback(monkeypatch):
    secret = "private-session-token"
    mocked = AsyncMock(return_value=Fetched("https://example.com/final?session=" + secret,
                                           b"An original source record. " * 10, "text/plain", 200))
    monkeypatch.setattr(providers, "pinned_request", mocked)
    item, limitation = asyncio.run(providers.fetch_evidence(
        {"url": "https://example.com/start", "title": "Record", "snippet": "A search extract", "raw_content": "", "published_at": None}, 1,
        language="en", headers={"Cookie": "session=" + secret}))
    assert item is None and secret not in limitation
    assert "report output were blocked" in limitation


def test_initial_source_url_with_credential_is_blocked_before_request(monkeypatch):
    mocked = AsyncMock()
    monkeypatch.setattr(providers, "pinned_request", mocked)
    item, limitation = asyncio.run(providers.fetch_evidence(
        {"url": "https://example.com/start?key=private-bearer-token", "title": "Record", "snippet": "A search extract", "raw_content": "", "published_at": None}, 1,
        language="en", headers={"Authorization": "Bearer private-bearer-token"}))
    assert item is None and "private-bearer-token" not in limitation
    mocked.assert_not_called()


@pytest.mark.parametrize("provider", ["tavily", "brave"])
def test_preferred_only_search_uses_provider_domain_filters(monkeypatch, provider):
    from truth_backend.models import SearchConfig
    from urllib.parse import parse_qs
    mocked = AsyncMock(return_value=Fetched("https://search.example.org", b'{"results":[],"web":{"results":[]}}', "application/json", 200))
    monkeypatch.setattr(providers, "pinned_request", mocked)
    asyncio.run(providers.search_web("test research", SearchConfig(provider=provider, api_key="search-secret"), domains=["example.com", "other.org"]))
    if provider == "tavily":
        assert mocked.await_args.kwargs["json_body"]["include_domains"] == ["example.com", "other.org"]
    else:
        query = parse_qs(__import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(mocked.await_args.args[0]).query)["q"][0]
        assert "site:example.com OR site:other.org" in query


@pytest.mark.parametrize("policy", ["balanced", "preferred-only"])
def test_preferred_sources_and_credentials_are_isolated_from_ai_search_and_report(client, monkeypatch, policy):
    from truth_backend.models import Plan
    password = "never-send-account-password"
    account_user = "never-send-account-username"
    plan = Plan.model_validate({"claims": [{"text": "A record exists.", "kind": "fact"}], "queries": [{"query": "record", "intent": "neutral"}], "scope": "Defined records only."})
    analysis = Analysis.model_validate({"observations": [{"kind": "data", "text": "The record uses a stated reporting period.", "claim_ids": ["C1"], "evidence_ids": ["E1"]}]})
    completion = AsyncMock(side_effect=[plan, analysis])
    monkeypatch.setattr(research_module, "complete", completion)
    search = AsyncMock(return_value=[{"url": "https://other.example.org/independent", "title": "Independent record", "snippet": "Public evidence"}])
    monkeypatch.setattr(research_module, "search_web", search)
    fetch_calls = []
    async def fake_fetch(row, index, query, **kwargs):
        fetch_calls.append((row["url"], kwargs.get("headers")))
        item = sample_report().evidence[0].model_copy(update={"id": f"E{index}", "url": row["url"], "excerpt": "A source record. " + password})
        return item, ""
    monkeypatch.setattr(research_module, "fetch_evidence", fake_fetch)
    screenshots = AsyncMock(return_value=[])
    monkeypatch.setattr(research_module, "capture_sources", screenshots)
    response = client.post("/api/research", json={"topic": "Check a public record", "language": "en", "ai": {"model": "mock"},
        "search": {"api_key": "search-key"}, "sources": [{"url": "https://example.com/protected", "label": "Preferred record"}],
        "source_policy": policy, "source_credentials": [{"origin": "https://example.com", "kind": "basic", "username": account_user, "password": password}], "include_screenshots": True})
    assert response.status_code == 200, response.text
    output = response.json()
    assert output["preferred_sources"] == [{"url": "https://example.com/protected", "label": "Preferred record"}]
    assert output["source_policy"] == policy and output["language"] == "en"
    assert fetch_calls[0][0] == "https://example.com/protected" and fetch_calls[0][1]["Authorization"].startswith("Basic ")
    assert password not in response.text and account_user not in response.text and "source_credentials" not in output
    assert "[REDACTED CREDENTIAL]" in output["evidence"][0]["excerpt"]
    for call in completion.await_args_list:
        serialized = json.dumps(call.args[2])
        assert password not in serialized and account_user not in serialized and "Authorization" not in serialized
    for call in search.await_args_list:
        assert "source_credentials" not in json.dumps(call.kwargs)
        if policy == "preferred-only":
            assert call.kwargs["domains"] == ["example.com"]
    if policy == "balanced":
        assert fetch_calls[1][1] is None
        assert [item.id for item in screenshots.await_args.args[0]] == ["E2"]
    else:
        assert len(fetch_calls) == 1
        screenshots.assert_not_called()
        assert any("independent counter-evidence" in note for note in output["limitations"])


def test_preferred_only_requires_sources_and_validates_credentials_before_network(client, monkeypatch):
    completion = AsyncMock()
    monkeypatch.setattr(research_module, "complete", completion)
    response = client.post("/api/research", json={"topic": "A real topic", "language": "ja", "source_policy": "preferred-only"})
    assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_source_scope"
    response = client.post("/api/research", json={"topic": "A real topic", "language": "en", "source_credentials": [{"origin": "http://example.com", "kind": "bearer", "token": "private-source-token"}]})
    assert response.status_code == 400 and "private-source-token" not in response.text
    completion.assert_not_called()
