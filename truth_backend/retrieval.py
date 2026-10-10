"""Bounded, transparent retrieval heuristics; no truth or entailment scoring."""
from __future__ import annotations

import re

from .i18n import tr
from .models import Claim, Evidence, RetrievalGap


STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "have", "has", "was", "were", "are",
    "for", "its", "into", "than", "which", "claim", "evidence", "data", "records",
    "是否", "一个", "相关", "可以", "需要", "进行", "资料", "记录", "数据", "报告", "论断",
    "问题", "核查", "统计", "情况", "其中", "结果", "期间", "以及", "认为", "する", "こと",
}


def keyword_terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-z][a-z0-9-]{2,}", text.casefold()))
    for phrase in re.findall(r"[\u3040-\u30ff\u3400-\u9fff]{2,}", text):
        terms.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    return terms - STOPWORDS


def matched_sources(claim: Claim, evidence: list[Evidence]) -> list[Evidence]:
    terms = keyword_terms(claim.text)
    if not terms:
        return []
    minimum = min(3, max(1, (len(terms) + 5) // 6))
    return [item for item in evidence if item.excerpt and item.status != "unavailable"
            and len(terms & keyword_terms(item.excerpt)) >= minimum]


def identify_retrieval_gaps(claims: list[Claim], evidence: list[Evidence], language="zh-CN") -> list[RetrievalGap]:
    gaps = []
    for claim in claims:
        matched = matched_sources(claim, evidence)
        families = {item.source_family for item in matched}
        if not matched:
            reason = "no_keyword_match"
        elif len(families) < 2:
            reason = "limited_families"
        else:
            continue
        suffix = tr(" 原始资料 完整记录 定义 口径", " original sources complete records definitions methodology",
                    " 原資料 完全な記録 定義 集計方法", language)
        query = " ".join((claim.text[:450] + suffix).split()[:75])[:600]
        gaps.append(RetrievalGap(claim_id=claim.id, reason=reason, query=query, attempted=False))
    # Fill missing material before expanding a single existing family.
    return sorted(gaps, key=lambda gap: (gap.reason != "no_keyword_match", int(gap.claim_id[1:])))
