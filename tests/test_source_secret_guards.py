"""Offline request-wide privacy guards remain separate from origin-bound headers."""
import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote

import httpx
import pytest

from truth_backend import captures, providers, research, security
from truth_backend.models import Analysis, Evidence, Plan, ResearchRequest, SourceCredential
from truth_backend.security import Fetched, ServiceError
from truth_backend.source_access import credential_headers, headers_for_url, secret_strings


SECRET = "dummy-account-B-private-value"
GOOD_TEXT = "The original record uses a defined reporting period. " * 3


def offline_http(monkeypatch, handler):
    requests, resolved = [], []

    async def resolve(url, **kwargs):
        resolved.append(url)
        scheme, host, port = security.check_url_shape(url)
        return scheme, host, port, "93.184.216.34"

    def track(request):
        requests.append(request)
        return handler(request, len(requests))

    client = httpx.AsyncClient
    monkeypatch.setattr(security, "resolve_public", resolve)
    monkeypatch.setattr(security.httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(track), **kwargs))
    return requests, resolved


@pytest.mark.parametrize("encoded", [SECRET, SECRET.replace("-", "%2D"), quote(SECRET.replace("-", "%2D"), safe="")])
def test_unrelated_origin_secret_in_redirect_is_blocked_before_dns_or_request(monkeypatch, encoded):
    credentials = [SourceCredential(origin="https://account-b.example", kind="bearer", token=SECRET)]
    origins = credential_headers(credentials)
    known = secret_strings(credentials, origins)
    requests, resolved = offline_http(monkeypatch, lambda request, count: httpx.Response(
        302, headers={"location": "https://third-party.example/echo?token=" + encoded}))
    assert headers_for_url("https://public-a.example/start", origins) is None
    with pytest.raises(ServiceError) as error:
        asyncio.run(security.pinned_request("https://public-a.example/start", known_secrets=known, redirects=4))
    assert error.value.code == "credentials_in_public_input" and SECRET not in str(error.value)
    assert len(requests) == len(resolved) == 1
    assert "authorization" not in requests[0].headers and "cookie" not in requests[0].headers


def test_request_wide_guard_survives_header_drop_and_keeps_other_origin_credentials_private(monkeypatch):
    requests, resolved = offline_http(monkeypatch, lambda request, count: httpx.Response(302, headers={
        "location": "https://public-c.example/ordinary" if count == 1 else "https://third-party.example/?token=" + SECRET}))
    with pytest.raises(ServiceError):
        asyncio.run(security.pinned_request("https://account-a.example/start", headers={"Cookie": "session=dummy-A"},
                                            known_secrets=[SECRET], redirects=4))
    assert len(requests) == len(resolved) == 2
    assert requests[0].headers["cookie"] == "session=dummy-A"
    assert "cookie" not in requests[1].headers and "authorization" not in requests[1].headers
    assert all(SECRET not in str(request.url) and SECRET not in str(request.headers) for request in requests)


def test_plain_initial_url_with_another_origin_secret_never_resolves(monkeypatch):
    resolve = AsyncMock()
    monkeypatch.setattr(security, "resolve_public", resolve)
    with pytest.raises(ServiceError) as error:
        asyncio.run(security.pinned_request("https://public-a.example/?token=" + SECRET, known_secrets=[SECRET]))
    assert error.value.code == "credentials_in_public_input"
    resolve.assert_not_awaited()


def test_safe_uncredentialed_source_redirect_remains_usable_without_other_account_headers(monkeypatch):
    requests, _ = offline_http(monkeypatch, lambda request, count: httpx.Response(
        302, headers={"location": "https://public-c.example/final"}) if count == 1 else httpx.Response(200, text=GOOD_TEXT))
    result = asyncio.run(security.pinned_request("https://public-a.example/start", known_secrets=[SECRET], redirects=4))
    assert result.status_code == 200 and result.url == "https://public-c.example/final"
    assert len(requests) == 2
    assert all("authorization" not in request.headers and "cookie" not in request.headers for request in requests)


@pytest.mark.parametrize("leak_at", ["initial", "final"])
def test_fetch_guard_uses_all_request_secrets_even_without_source_headers(monkeypatch, leak_at):
    transport = AsyncMock(return_value=Fetched("https://public-a.example/final?token=" + SECRET,
                                               GOOD_TEXT.encode(), "text/plain", 200))
    monkeypatch.setattr(providers, "pinned_request", transport)
    row = {"url": "https://public-a.example/start" + ("?token=" + SECRET if leak_at == "initial" else ""),
           "title": "Original record", "snippet": "A fallback excerpt"}
    item, limitation = asyncio.run(providers.fetch_evidence(row, 1, language="en", known_secrets=[SECRET]))
    assert item is None and SECRET not in limitation
    if leak_at == "initial":
        transport.assert_not_awaited()
    else:
        assert transport.await_args.kwargs["headers"] is None
        assert SECRET in transport.await_args.kwargs["known_secrets"]


@pytest.mark.parametrize("leak_at", ["search_hit", "final_evidence"])
def test_research_excludes_secret_urls_before_analysis_and_screenshots(monkeypatch, leak_at):
    plan = Plan(claims=[{"text": "The record uses a stated period.", "kind": "fact"}],
                queries=[{"query": "record period", "intent": "neutral"}], scope="Defined records")
    analysis = Analysis(observations=[{"kind": "data", "text": "The reporting period needs checking.",
                                      "claim_ids": ["C1"], "evidence_ids": ["E1"],
                                      "citations": [{"evidence_id": "E1", "quote": GOOD_TEXT}]}])
    completion = AsyncMock(side_effect=[plan, analysis])
    monkeypatch.setattr(research, "complete", completion)
    monkeypatch.setattr(research, "resolve_search", lambda config, ai=None: config)
    bad_url = "https://public-a.example/bad" + ("?token=" + SECRET if leak_at == "search_hit" else "")
    searching = AsyncMock(return_value=[{"url": bad_url, "title": "Public record"}])
    monkeypatch.setattr(research, "search_web", searching)
    fetched = []

    async def fetch(row, index, query, **kwargs):
        fetched.append((row, kwargs))
        assert kwargs["headers"] is None
        assert SECRET in kwargs["known_secrets"]
        final = row["url"] + ("?echo=" + SECRET if row["url"].endswith("/bad") else "")
        return Evidence(id=f"E{index}", title=row["title"], url=final, publisher="public-a.example",
                        retrieved_at="2026-10-10T00:00:00Z", content_kind="full_text", excerpt=GOOD_TEXT,
                        source_family="public-a.example", status="retrieved"), ""

    monkeypatch.setattr(research, "fetch_evidence", fetch)
    screenshot = AsyncMock(return_value=[])
    monkeypatch.setattr(research, "capture_sources", screenshot)
    request = ResearchRequest(topic="Review public records", language="en", include_screenshots=True,
                              ai={"model": "mock"}, search={"api_key": "dummy-search-key"},
                              sources=[{"url": "https://public-a.example/good", "label": "Original source"}],
                              source_credentials=[{"origin": "https://account-b.example", "kind": "bearer", "token": SECRET}])
    output = asyncio.run(research.research(request))
    assert len(output["evidence"]) == 1 and output["evidence"][0]["url"].endswith("/good")
    assert SECRET not in json.dumps(output)
    assert len(fetched) == (1 if leak_at == "search_hit" else 2)
    for call in completion.await_args_list:
        assert SECRET not in json.dumps(call.args[2])
    for call in searching.await_args_list:
        assert SECRET not in call.args[0] and not call.kwargs
    assert [item.url for item in screenshot.await_args.args[0]] == ["https://public-a.example/good"]
    assert SECRET in screenshot.await_args.kwargs["known_secrets"]


def test_all_secret_sources_are_excluded_without_model_analysis_or_screenshots(monkeypatch):
    planning = AsyncMock(return_value=Plan(claims=[{"text": "A record exists", "kind": "fact"}],
                                          queries=[{"query": "record", "intent": "neutral"}], scope="Records"))
    monkeypatch.setattr(research, "complete", planning)
    monkeypatch.setattr(research, "resolve_search", lambda config, ai=None: config)
    monkeypatch.setattr(research, "search_web", AsyncMock(return_value=[{"url": "https://public-a.example/?token=" + SECRET}]))
    fetch, screenshot = AsyncMock(), AsyncMock()
    monkeypatch.setattr(research, "fetch_evidence", fetch)
    monkeypatch.setattr(research, "capture_sources", screenshot)
    with pytest.raises(ServiceError) as error:
        asyncio.run(research.research(ResearchRequest(topic="Public records", search={"api_key": "dummy-search"},
            include_screenshots=True, source_credentials=[{"origin": "https://account-b.example", "kind": "bearer", "token": SECRET}])))
    assert error.value.code == "no_search_results" and SECRET not in str(error.value)
    assert planning.await_count == 1
    fetch.assert_not_awaited()
    screenshot.assert_not_awaited()


def test_screenshot_refetch_blocks_new_secret_redirect_without_browser_network(monkeypatch, tmp_path):
    requests, _ = offline_http(monkeypatch, lambda request, count: httpx.Response(
        302, headers={"location": "https://third-party.example/?token=" + SECRET}))
    monkeypatch.setattr(captures, "screenshot_status", lambda: {"package_installed": True})
    monkeypatch.setattr(captures, "CAPTURE_DIR", tmp_path)

    class BrowserError(Exception):
        pass

    class Route:
        request = SimpleNamespace(resource_type="document", method="GET", url="https://public-a.example/source")
        aborted = False
        async def abort(self): self.aborted = True
        async def fulfill(self, **kwargs): pytest.fail("A secret redirect must not be rendered")

    route = Route()

    class Page:
        async def goto(self, *args, **kwargs):
            await context.callback(route)
            if route.aborted: raise BrowserError()
        async def screenshot(self, **kwargs): pytest.fail("A blocked document must not be saved")
        async def close(self): pass

    class Context:
        async def route(self, pattern, callback): self.callback = callback
        async def new_page(self): return Page()
        async def close(self): pass

    context = Context()
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())

    class Playwright:
        async def __aenter__(self): return SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        async def __aexit__(self, *args): pass

    module = ModuleType("playwright.async_api")
    module.async_playwright, module.Error = Playwright, BrowserError
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", module)
    evidence = Evidence(id="E1", title="Record", url="https://public-a.example/source", publisher="public-a.example",
                        retrieved_at="2026-10-10T00:00:00Z", content_kind="full_text", excerpt=GOOD_TEXT,
                        source_family="public-a.example", status="retrieved")
    limitations = asyncio.run(captures.capture_sources([evidence], language="en", known_secrets=[SECRET]))
    assert route.aborted and len(requests) == 1 and not evidence.screenshots
    assert not list(tmp_path.iterdir()) and SECRET not in json.dumps(limitations)
    assert "authorization" not in requests[0].headers and "cookie" not in requests[0].headers
    browser.close.assert_awaited_once()
