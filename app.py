"""Run locally: python app.py (http://127.0.0.1:8000)."""
from __future__ import annotations

import asyncio
import ipaddress
import inspect
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from truth_backend.captures import CAPTURE_DIR, screenshot_status
from truth_backend.budgets import DEPTH_BUDGETS
from truth_backend.deadlines import REQUEST_DEADLINE
from truth_backend.models import Mode, Language, Report, ResearchRequest, SummarizeRequest, ReviewRequest
from truth_backend.i18n import SUPPORTED_LANGUAGES, error_message
from truth_backend.reports import public_report, validate_references
from truth_backend.research import research, summarize
from truth_backend.security import ServiceError
from truth_backend.local_config import load_local_config
from truth_backend.providers import resolve_search
from truth_backend.streaming import research_events
from truth_backend.review import review_report
from truth_backend.review_targets import REVIEW_CAPACITIES
from truth_backend.models import SearchConfig


ROOT = Path(__file__).resolve().parent
app = FastAPI(title="No fake news", version="0.3.0", docs_url="/api/docs", redoc_url=None)
busy = asyncio.Semaphore(2)


@app.middleware("http")
async def local_guard(request: Request, call_next):
    language = request.query_params.get("language")
    if language not in SUPPORTED_LANGUAGES:
        accepted = request.headers.get("accept-language", "").lower()
        language = "ja" if accepted.startswith("ja") else "en" if accepted.startswith("en") else "zh-CN"
    request.state.language = language
    def failure(code, message, status):
        return JSONResponse({"error": {"code": code, "message": error_message(code, message, request.state.language)}}, status_code=status)
    host_header = request.headers.get("host", "")
    try:
        host = urlsplit("//" + host_header).hostname
        valid_host = host in {"localhost", "127.0.0.1", "::1"} and "@" not in host_header and "/" not in host_header
    except ValueError:
        valid_host = False
    client_host = request.client.host if request.client else ""
    try:
        local_client = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        local_client = client_host == "testclient"
    if not valid_host or not local_client:
        return failure("local_only", "此服务只接受本机访问。", 403)
    origin = request.headers.get("origin")
    expected_origin = f"{request.url.scheme}://{host_header}"
    if origin and origin != expected_origin:
        return failure("origin_blocked", "已阻止跨站请求。", 403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        return failure("origin_blocked", "已阻止跨站请求。", 403)
    if request.method in {"POST", "PUT", "PATCH"}:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                return failure("body_too_large", "请求体超过 1 MB 上限。", 413)
        request._body = bytes(body)
        try:
            supplied_language = json.loads(body).get("language")
            if supplied_language in SUPPORTED_LANGUAGES:
                request.state.language = supplied_language
        except (ValueError, AttributeError, TypeError):
            pass
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    return response


@app.exception_handler(ServiceError)
async def service_error(_request, exc: ServiceError):
    return JSONResponse({"error": {"code": exc.code, "message": error_message(exc.code, exc.message, getattr(_request.state, "language", "zh-CN"))}}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_request, _exc):
    # FastAPI's default error includes input values (which can include API keys).
    return JSONResponse({"error": {"code": "invalid_request", "message": error_message("invalid_request", "输入结构或字段不符合要求，请检查主题、模式、模型设置及报告格式。", getattr(_request.state, "language", "zh-CN"))}}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(_request, _exc):
    return JSONResponse({"error": {"code": "internal_error", "message": error_message("internal_error", "处理失败；请重试并检查配置。未生成替代结果。", getattr(_request.state, "language", "zh-CN"))}}, status_code=500)


@app.get("/")
async def home():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/assets/{name}")
async def asset(name: str, request: Request):
    if name not in {"app.js", "styles.css", "i18n.js", "workspace.js", "workbench.css", "stream.js", "review.js"}:
        return JSONResponse({"error": {"code": "not_found", "message": error_message("not_found", "资源不存在。", request.state.language)}}, status_code=404)
    return FileResponse(ROOT / "frontend" / name)


@app.get("/captures/{name}")
async def capture(name: str, request: Request):
    import re
    if not re.fullmatch(r"[a-f0-9]{32}\.(?:png|jpg|webp)", name):
        return JSONResponse({"error": {"code": "not_found", "message": error_message("not_found", "截图不存在。", request.state.language)}}, status_code=404)
    path = CAPTURE_DIR / name
    if not path.is_file():
        path = ROOT / "examples" / "captures" / name
    if not path.is_file():
        return JSONResponse({"error": {"code": "not_found", "message": error_message("not_found", "截图不存在。", request.state.language)}}, status_code=404)
    media_type = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}[path.suffix]
    return FileResponse(path, media_type=media_type)


@app.get("/api/health")
async def health(language: Language = "zh-CN"):
    return {"status": "ok", "version": "0.3.0", "local_only": True,
            "search_providers": ["deepseek", "tavily", "brave"], "ai_protocol": "openai-chat-completions",
            "default_search_provider": os.getenv("TRUTH_SEARCH_PROVIDER", "tavily") if os.getenv("TRUTH_SEARCH_PROVIDER", "tavily") in {"deepseek", "tavily", "brave"} else "tavily",
            "configured": {"ai_base_url": bool(os.getenv("TRUTH_AI_BASE_URL")),
                           "ai_model": bool(os.getenv("TRUTH_AI_MODEL")), "ai_key": bool(os.getenv("TRUTH_AI_API_KEY")),
                           "tavily": bool(os.getenv("TAVILY_API_KEY")), "brave": bool(os.getenv("BRAVE_API_KEY")),
                           "deepseek": bool(resolve_search(SearchConfig(provider="deepseek")).api_key.get_secret_value())},
            "screenshots": screenshot_status(language), "max_screenshot_sources": 3, "supported_languages": SUPPORTED_LANGUAGES,
            "brand": "No fake news", "repository_name": "No-fake-news",
            "source_access": {"preferred_urls": True, "policies": ["balanced", "preferred-only"],
                              "credential_kinds": ["basic", "cookie", "bearer"], "credentials_persisted": False,
                              "authenticated_screenshots": False, "form_login": False},
            "max_sources": 24, "max_queries": 10, "depths": DEPTH_BUDGETS,
            "report_schema": "1.1", "supported_report_schemas": ["1.0", "1.1", "1.2"],
            "research_stream": True, "adaptive_search_default": False, "max_analysis_repair_calls": 1,
            "citation_review": {"modes": ["ai-summary"], "capacities": REVIEW_CAPACITIES,
                                "max_model_calls": 1, "timeout_seconds": 120}}


async def bounded(operation, timeout_seconds=180):
    token = REQUEST_DEADLINE.set(asyncio.get_running_loop().time() + timeout_seconds)
    started = False
    try:
        async with asyncio.timeout(timeout_seconds):
            async with busy:
                started = True
                return await operation
    except TimeoutError:
        raise ServiceError("research_timeout", f"处理超过 {timeout_seconds} 秒；未返回不完整或替代报告，请稍后重试。", 504) from None
    finally:
        REQUEST_DEADLINE.reset(token)
        if not started and inspect.iscoroutine(operation):
            operation.close()


async def bounded_connected(request: Request, factory, timeout_seconds=180):
    """Stop nonstreaming paid work when its client leaves, including queued work."""
    async def run():
        return await bounded(factory(), timeout_seconds)

    async def disconnected():
        # FastAPI and local_guard have consumed the validated request body.
        while True:
            if (await request.receive())["type"] == "http.disconnect":
                return

    operation = asyncio.create_task(run())
    listener = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait({operation, listener}, return_when=asyncio.FIRST_COMPLETED)
        if operation in done:
            return await operation
        # There is no connected client to receive a new public error payload.
        return Response(status_code=499)
    finally:
        # Starlette's cancellation scopes must not interrupt asynchronous cleanup.
        with anyio.CancelScope(shield=True):
            for task in (operation, listener):
                if not task.done() and not task.cancelling():
                    task.cancel()
            await asyncio.gather(operation, listener, return_exceptions=True)


@app.post("/api/research")
async def do_research(request: ResearchRequest, raw_request: Request):
    return await bounded_connected(raw_request, lambda: research(request), DEPTH_BUDGETS[request.depth]["timeout_seconds"])


@app.post("/api/research/stream")
async def stream_research(request: ResearchRequest):
    return StreamingResponse(
        research_events(lambda: research(request), bounded, DEPTH_BUDGETS[request.depth]["timeout_seconds"], request.language),
        media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.post("/api/summarize")
async def do_summarize(request: SummarizeRequest, raw_request: Request):
    return await bounded_connected(raw_request, lambda: summarize(request))


@app.post("/api/review")
async def do_review(request: ReviewRequest, raw_request: Request):
    return await bounded_connected(raw_request, lambda: review_report(request), 120)


@app.get("/api/demo")
async def demo(mode: Mode = "evidence-only", language: Language = "zh-CN"):
    try:
        filename = "demo-report.json" if language == "zh-CN" else f"demo-report.{language}.json"
        report = Report.model_validate(json.loads((ROOT / "examples" / filename).read_text(encoding="utf-8")))
        report.language = language
        if mode == "ai-summary" and report.summary:
            report.summary_language = language
        validate_references(report)
        return public_report(report, mode)
    except (OSError, ValueError):
        raise ServiceError("demo_unavailable", "演示报告缺失或结构无效。", 500) from None


if __name__ == "__main__":
    import uvicorn
    load_local_config(ROOT)
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("TRUTH_PORT", "8000")), access_log=False)
