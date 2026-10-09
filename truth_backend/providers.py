from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from .models import AIConfig, Evidence, SearchConfig
from .i18n import tr, error_message
from .security import ServiceError, check_url_shape, pinned_request, sensitive_header_values, check_url_for_secrets


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_ai(config: AIConfig) -> AIConfig:
    return AIConfig(
        base_url=config.base_url or os.getenv("TRUTH_AI_BASE_URL", "https://api.openai.com/v1"),
        api_key=config.api_key.get_secret_value() or os.getenv("TRUTH_AI_API_KEY", ""),
        model=config.model or os.getenv("TRUTH_AI_MODEL", ""),
    )


def resolve_search(config: SearchConfig) -> SearchConfig:
    env = "TAVILY_API_KEY" if config.provider == "tavily" else "BRAVE_API_KEY"
    return SearchConfig(provider=config.provider, api_key=config.api_key.get_secret_value() or os.getenv(env, ""))


def provider_error(provider: str, status: int) -> ServiceError:
    explanation = {
        400: "请求不被接受，请检查模型名称、兼容接口及参数。",
        401: "鉴权失败，请检查 API Key。", 403: "权限不足或服务不可用。",
        404: "接口或模型不存在，请检查 Base URL 与模型名称。",
        429: "触发速率限制或额度不足。",
    }.get(status, "服务请求失败，请稍后重试。")
    return ServiceError("provider_error", f"{provider} 返回 HTTP {status}：{explanation}", 502)


def decode_json(content: str) -> dict:
    if not isinstance(content, str) or len(content) > 250_000:
        raise ServiceError("invalid_model_output", "AI 输出为空或超出长度限制。")
    content = content.strip()
    if content.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", content, flags=re.IGNORECASE)
        if match:
            content = match.group(1)
    try:
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise ServiceError("invalid_model_output", "AI 未返回要求的 JSON 对象；请使用支持 JSON 指令的模型。") from None


async def complete(config: AIConfig, system: str, data: dict, schema: type[BaseModel]) -> BaseModel:
    config = resolve_ai(config)
    if not config.model:
        raise ServiceError("missing_ai_model", "请填写 AI 模型名称，或设置 TRUTH_AI_MODEL。", 400)
    endpoint = config.base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    check_url_shape(endpoint, allow_loopback=True)
    if not config.api_key.get_secret_value() and urlsplit(endpoint).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ServiceError("missing_ai_key", "请填写 AI API Key，或设置 TRUTH_AI_API_KEY。本机兼容服务可留空。", 400)
    headers = {"Content-Type": "application/json"}
    if config.api_key.get_secret_value():
        headers["Authorization"] = "Bearer " + config.api_key.get_secret_value()
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system + "\n仅输出一个 JSON 对象，遵守以下 JSON Schema：\n" + json.dumps(schema.model_json_schema(), ensure_ascii=False)},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ],
        "stream": False,
    }
    response = await pinned_request(endpoint, method="POST", headers=headers, json_body=payload,
                                    allow_loopback=True, max_bytes=1_000_000, timeout=65)
    if response.status_code >= 400:
        raise provider_error("AI 供应商", response.status_code)
    try:
        envelope = json.loads(response.content)
        content = envelope["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ServiceError("invalid_model_output", "AI 供应商响应不符合 chat/completions 协议。") from None
    try:
        return schema.model_validate(decode_json(content))
    except ValidationError:
        # Validation errors contain raw input, which may include confidential prompt data.
        raise ServiceError("invalid_model_output", "AI JSON 结构不符合报告规范，未生成替代内容。请重试或更换模型。") from None


async def search_web(query: str, config: SearchConfig, domains: list[str] | None = None) -> list[dict]:
    config = resolve_search(config)
    if not config.api_key.get_secret_value():
        raise ServiceError("missing_search_key", f"请填写 {config.provider.title()} 搜索 API Key；联网研究需要真实搜索服务。", 400)
    token = config.api_key.get_secret_value()
    if config.provider == "tavily":
        response = await pinned_request(
            "https://api.tavily.com/search", method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json_body={"query": query, "max_results": 3, "search_depth": "basic", "include_answer": False,
                       "include_raw_content": "text", **({"include_domains": domains} if domains else {})}, timeout=20, max_bytes=1_000_000,
        )
    else:
        import urllib.parse
        if domains:
            scope = " (" + " OR ".join("site:" + domain for domain in domains) + ")"
            if len(scope) > 500:
                raise ServiceError("invalid_source_scope", "指定来源域名过长，无法放入 Brave 的搜索查询上限。", 400)
            query = query[:600 - len(scope)] + scope
        params = urllib.parse.urlencode({"q": query, "count": 3, "extra_snippets": "true"})
        response = await pinned_request(
            "https://api.search.brave.com/res/v1/web/search?" + params,
            headers={"X-Subscription-Token": token, "Accept": "application/json"}, timeout=20,
        )
    if response.status_code >= 400:
        raise provider_error(config.provider.title(), response.status_code)
    try:
        data = json.loads(response.content)
        results = data.get("results", []) if config.provider == "tavily" else data.get("web", {}).get("results", [])
        if not isinstance(results, list):
            raise ValueError
        output = []
        for row in results[:3]:
            if not isinstance(row, dict) or not isinstance(row.get("url"), str):
                continue
            output.append({
                "url": row["url"], "title": str(row.get("title") or "")[:1000],
                "snippet": str(row.get("content") or row.get("description") or "")[:5000],
                "raw_content": str(row.get("raw_content") or "")[:16000],
                "published_at": str(row["published_date"])[:100] if row.get("published_date") else None,
            })
        return output
    except (ValueError, AttributeError, TypeError):
        raise ServiceError("invalid_search_output", "搜索供应商响应格式无效。") from None


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        elif tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def extract_text(content: bytes, content_type: str) -> str:
    if "html" not in content_type and "text/plain" not in content_type and "xhtml" not in content_type:
        raise ServiceError("unsupported_content", "此版本只提取 HTML / 纯文本正文；PDF、音视频需人工查阅。")
    # HTTP bodies are commonly UTF-8; honor declared encodings without executing content.
    match = re.search(r"charset=[\"']?([\w-]+)", content_type, re.I)
    encoding = match.group(1) if match else "utf-8"
    try:
        decoded = content.decode(encoding, errors="replace")
    except LookupError:
        decoded = content.decode("utf-8", errors="replace")
    if "html" in content_type:
        parser = TextExtractor()
        parser.feed(decoded)
        decoded = " ".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", decoded)
    return re.sub(r"\n\s*\n+", "\n", text).strip()[:16000]


def select_excerpt(text: str, query: str = "", max_length: int = 3000) -> tuple[str, bool]:
    """Choose unchanged, relevant paragraphs deterministically, with nearby context.

    This is retrieval, not an AI rewrite. It cannot establish document completeness.
    """
    if len(text) <= max_length or not query.strip():
        return text[:max_length], False
    stopwords = {"the", "and", "for", "with", "from", "this", "that", "are", "was", "has", "have",
                 "evidence", "official", "support", "counter", "primary", "history", "data", "records"}
    terms = {term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}|\d{4}", query) if term.lower() not in stopwords}
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        for width in (2, 3, 4):
            terms.update(phrase[i:i + width] for i in range(max(0, len(phrase) - width + 1)))
    if not terms:
        return text[:max_length], False
    parts = []
    for paragraph in re.split(r"\n+|(?<=[。！？!?；;])|(?<=\.)\s+(?=[A-Z])", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        # Bound long tables or paragraphs while retaining original character sequences.
        parts.extend(paragraph[i:i + 700] for i in range(0, len(paragraph), 700))
    scores = []
    for index, paragraph in enumerate(parts):
        lower = paragraph.lower()
        hits = sum(min(len(term), 8) for term in terms if term in lower)
        if hits:
            # Very short link labels are rarely enough context to support a fact.
            scores.append((hits * (1 if len(paragraph) >= 45 else 0.25), index))
    if not scores:
        return text[:max_length], False
    selected, budget = set(), 0
    for _score, index in sorted(scores, key=lambda row: (-row[0], row[1])):
        nearby = {i for i in (index - 1, index, index + 1) if 0 <= i < len(parts)}
        addition = nearby - selected
        cost = sum(len(parts[i]) + 5 for i in addition)
        if budget + cost > max_length:
            addition = {index} - selected
            cost = sum(len(parts[i]) + 5 for i in addition)
        if addition and budget + cost <= max_length:
            selected.update(addition)
            budget += cost
    if not selected:
        return text[:max_length], False
    # Ellipses explicitly identify non-contiguous extracts, never synthesized prose.
    chunks = []
    previous = -2
    for index in sorted(selected):
        if chunks and index != previous + 1:
            chunks.append("[…]")
        chunks.append(parts[index])
        previous = index
    return "\n".join(chunks)[:max_length], True


async def fetch_evidence(row: dict, index: int, query: str = "", max_excerpt: int = 3000, language: str = "zh-CN", headers: dict[str, str] | None = None) -> tuple[Evidence | None, str]:
    secrets = sensitive_header_values(headers)
    try:
        check_url_shape(row["url"])
        check_url_for_secrets(row["url"], secrets)
    except ServiceError:
        return None, tr("一个搜索结果的 URL 不满足公网访问策略，已排除。", "A search result URL violated the public-network policy and was excluded.", "公開ネットワークのポリシーに合わない検索結果 URL を除外しました。", language)
    text = row.get("raw_content") or row.get("snippet") or ""
    kind = "search_extract" if row.get("raw_content") else "snippet"
    status = "snippet_only" if text else "unavailable"
    context = tr("正文未直接访问；仅保留搜索供应商提供的摘录，不能视为全文核验。", "The source body was not accessed directly. Only the search provider's extract is retained; this is not full-text verification.", "本文には直接アクセスしていません。検索プロバイダーの抜粋のみ保持しており、全文を検証したことにはなりません。", language)
    final_url = row["url"]
    limitation = ""
    try:
        fetched = await pinned_request(row["url"], redirects=4, timeout=12, max_bytes=1_500_000, headers=headers)
        check_url_for_secrets(fetched.url, secrets)
        if fetched.status_code >= 400:
            raise ServiceError("source_http_error", f"来源返回 HTTP {fetched.status_code}。")
        extracted = extract_text(fetched.content, fetched.content_type)
        if len(extracted) < 80:
            raise ServiceError("empty_text", "正文不足 80 字符，可能需要脚本、登录或人工访问。")
        text, kind, status, final_url = extracted, "full_text", "retrieved", fetched.url
        context = tr(f"直接抓取页面文字（最多 16,000 字符）；展示摘录最多 {max_excerpt:,} 字符。未绕过付费墙、登录或访问限制。", f"Page text was retrieved directly (up to 16,000 characters); the displayed extract is limited to {max_excerpt:,} characters. Paywalls, login, and access controls were not bypassed.", f"ページ本文を直接取得しました（最大 16,000 文字）。表示する抜粋は最大 {max_excerpt:,} 文字です。有料壁、ログイン、アクセス制限は回避していません。", language)
    except ServiceError as exc:
        if exc.code == "credentials_in_public_input":
            return None, tr(f"来源 E{index} 的 URL 或重定向含已知凭据，已阻止访问和输出。", f"Source E{index} contained a known credential in a URL or redirect; access and report output were blocked.", f"情報源 E{index} の URL またはリダイレクトに既知の認証情報が含まれるため、アクセスとレポート出力をブロックしました。", language)
        if exc.code == "unsafe_url":
            return None, tr(f"来源 E{index} 解析或重定向到非公网目标，已排除。", f"Source E{index} resolved or redirected to a non-public target and was excluded.", f"情報源 E{index} は非公開アドレスに解決またはリダイレクトされたため、除外しました。", language)
        detail = error_message(exc.code, exc.message, language)
        limitation = tr(f"来源 E{index} 未取得可用正文：{detail}", f"Source E{index}: usable body text was not retrieved. {detail}", f"情報源 E{index}：利用可能な本文を取得できませんでした。{detail}", language)
        context += " " + detail
    host = urlsplit(final_url).hostname or "未知"
    excerpt, selected = select_excerpt(text, query, max_length=max_excerpt)
    if selected:
        context += tr(" 服务器按主题/查询关键词选取原文片段并保留邻近语境，[…] 表示不连续；关键词摘录仍可能遗漏限定条件，需打开原文复核。", " The server selected original passages using topic/query keywords and nearby context. […] marks omitted passages; qualifications may still be missing, so check the original page.", " サーバーがテーマ・検索語に基づいて原文と周辺文脈を選びました。[…] は省略箇所です。限定条件が欠ける可能性があるため、原ページを確認してください。", language)
    elif len(text) > max_excerpt:
        context += tr(f" 未定位到可靠关键词片段，展示正文前 {max_excerpt:,} 字符，可能包含导航或无关内容。", f" No reliable keyword passage was located. The first {max_excerpt:,} body characters are shown and may include navigation or unrelated text.", f"適切なキーワード箇所が見つからなかったため、本文の先頭 {max_excerpt:,} 文字を表示しています。ナビゲーションや無関係な内容を含む場合があります。", language)
    evidence = Evidence(
        id=f"E{index}", title=row.get("title") or tr("无标题", "Untitled", "無題", language), url=final_url, publisher=host,
        published_at=row.get("published_at"), retrieved_at=now(), content_kind=kind,
        excerpt=excerpt, context=context, source_family=host.removeprefix("www."), status=status,
    )
    # The analysis receives precisely the stored excerpt; unshown text cannot justify its chart.
    return evidence, limitation
