"""Exact excerpt matching only; these checks cannot establish semantic support."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping

from .models import Citation, Evidence, ExcerptMetadata, QuoteCitation, QuoteLocator
from .security import ServiceError


def reject(message: str) -> None:
    raise ServiceError("invalid_evidence_reference", message)


def excerpt_metadata(excerpt: str) -> ExcerptMetadata:
    return ExcerptMetadata(sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest())


def locate_quote(citation: QuoteCitation, evidence: Mapping[str, Evidence]) -> Citation:
    """Select the first exact occurrence and expose ambiguity instead of guessing."""
    item = evidence.get(citation.evidence_id)
    quote = citation.quote
    if item is None:
        reject("精确引文引用了不存在的证据 ID。")
    if not quote.strip() or "[REDACTED CREDENTIAL]" in quote:
        reject("精确引文必须是非空原文，不能引用凭据遮盖文本。")
    start = item.excerpt.find(quote)
    if start < 0:
        reject("精确引文未原样出现在已取得的证据摘录中；翻译、改写或空白归一化均不算原句匹配。")
    end = start + len(quote)
    count, cursor = 0, start
    while cursor >= 0:
        count += 1
        cursor = item.excerpt.find(quote, cursor + 1)
    locator = QuoteLocator(start=start, end=end, prefix=item.excerpt[max(0, start - 80):start],
                           suffix=item.excerpt[end:end + 80], excerpt_sha256=excerpt_metadata(item.excerpt).sha256,
                           match_count=count)
    return Citation(evidence_id=item.id, quote=quote, locator=locator,
                    verification="exact_match", semantic_support="unverified")


def validate_citations(citations: Iterable[QuoteCitation], evidence: Mapping[str, Evidence],
                       *, allowed_ids: Iterable[str] | None = None, required: bool = False,
                       stored: bool = False) -> list[Citation]:
    """Validate input quotes, or recheck stored locators against submitted extracts."""
    quotes = list(citations)
    if required and not quotes:
        reject("新分析的每条事实性内容必须提供至少一条精确原文引句。")
    allowed = set(allowed_ids) if allowed_ids is not None else set(evidence)
    seen: set[tuple[str, str]] = set()
    located = []
    for citation in quotes:
        key = (citation.evidence_id, citation.quote)
        if key in seen:
            reject("同一条分析不能重复列出相同证据的同一句引文。")
        seen.add(key)
        if citation.evidence_id not in allowed:
            reject("精确引文的证据 ID 不属于该条分析声明的依据。")
        actual = locate_quote(citation, evidence)
        if stored:
            locator = getattr(citation, "locator", None)
            verification = getattr(citation, "verification", None)
            if required and (locator is None or verification != "exact_match"):
                reject("1.1 报告缺少精确引文定位信息。")
            if locator is not None and locator != actual.locator:
                reject("精确引文定位、上下文、重复次数或摘录摘要与提交的原文不一致。")
            if verification == "exact_match" and locator is None:
                reject("原句匹配标记缺少可复核定位。")
        located.append(actual)
    return located
