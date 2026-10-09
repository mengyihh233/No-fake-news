"""Optional screenshots with every browser request serviced by the safe HTTP layer."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
from pathlib import Path
from uuid import uuid4

from .models import Evidence, Screenshot
from .i18n import tr
from .providers import now
from .security import ServiceError, pinned_request


CAPTURE_DIR = Path(__file__).resolve().parents[1] / "runtime" / "captures"


def screenshot_status(language: str = "zh-CN") -> dict:
    available = importlib.util.find_spec("playwright") is not None
    return {"package_installed": available, "browser_checked": False,
            "note": tr("截图需安装可选依赖 playwright，并运行 python -m playwright install chromium。页面脚本与外部子资源被禁用。", "Screenshots require the optional playwright package and python -m playwright install chromium. Page scripts and external subresources are disabled.", "スクリーンショットには任意依存 playwright と python -m playwright install chromium が必要です。ページスクリプトと外部リソースは無効です。", language)}


async def capture_sources(evidence: list[Evidence], language: str = "zh-CN") -> list[str]:
    if not screenshot_status()["package_installed"]:
        return [tr("网页截图未执行：未安装 playwright；运行 pip install playwright 和 python -m playwright install chromium。", "Screenshots were not captured: playwright is not installed. Run pip install playwright and python -m playwright install chromium.", "スクリーンショットは取得していません。playwright が未インストールです。pip install playwright と python -m playwright install chromium を実行してください。", language)]
    from playwright.async_api import async_playwright, Error as PlaywrightError
    limitations = []
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(java_script_enabled=False, service_workers="block", viewport={"width": 1365, "height": 900})
                # No browser-owned network request is ever allowed through. The one document
                # request uses DNS-pinned HTTP. Subresources are blocked to bound costs and SSRF.
                async def route_request(route):
                    if route.request.resource_type != "document" or route.request.method != "GET":
                        await route.abort()
                        return
                    try:
                        fetched = await pinned_request(route.request.url, redirects=4, timeout=12)
                        if fetched.status_code >= 400:
                            await route.abort()
                        else:
                            await route.fulfill(status=fetched.status_code, body=fetched.content,
                                                content_type=fetched.content_type or "text/html",
                                                headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-src 'none'"})
                    except ServiceError:
                        await route.abort()
                await context.route("**/*", route_request)
                for item in evidence[:3]:
                    page = await context.new_page()
                    try:
                        await page.goto(item.url, wait_until="domcontentloaded", timeout=16_000)
                        name = uuid4().hex + ".png"
                        path = CAPTURE_DIR / name
                        await page.screenshot(path=str(path), full_page=False, timeout=5000)
                        item.screenshots.append(Screenshot(url="/captures/" + name, captured_at=now(),
                                                            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), source_url=item.url))
                    except PlaywrightError:
                        limitations.append(tr(f"来源 {item.id} 截图失败（访问限制、网络或页面渲染错误）。", f"Screenshot failed for {item.id} (access restriction, network, or page-rendering error).", f"{item.id} のスクリーンショット取得に失敗しました（アクセス制限、ネットワーク、または描画エラー）。", language))
                    finally:
                        await page.close()
                await context.close()
            finally:
                await browser.close()
    except (PlaywrightError, OSError):
        limitations.append(tr("网页截图未执行：Chromium 无法启动或未安装；运行 python -m playwright install chromium。", "Screenshots were not captured: Chromium is unavailable or could not start. Run python -m playwright install chromium.", "スクリーンショットは取得していません。Chromium がないか起動できません。python -m playwright install chromium を実行してください。", language))
    if any(item.screenshots for item in evidence):
        limitations.append(tr("截图是检索时的页面视图（禁用脚本和外部样式/图片），布局可能与原站不同；截图不独立证明内容真实。", "Screenshots show the page at retrieval time with scripts and external styles/images disabled. Layout may differ from the original site; a screenshot does not independently establish truth.", "スクリーンショットは取得時点の表示です。スクリプトと外部スタイル・画像を無効にしているため、元サイトと異なる場合があります。画像だけで内容の真実性は証明できません。", language))
    return limitations
