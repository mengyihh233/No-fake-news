"""Conservative URL deduplication and provisional source-family grouping."""
from __future__ import annotations

import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from .models import Evidence


TRACKING_KEYS = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}


def canonical_url_key(url: str) -> str:
    """Used for deduplication only; the recorded/fetched URL stays unchanged."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if ":" in host:
        host = "[" + host + "]"
    port = parts.port
    if port is not None and port != (443 if parts.scheme.lower() == "https" else 80):
        host += ":" + str(port)
    # Preserve substantive query values and order; do not guess that IDs are tracking.
    query = []
    for fragment in parts.query.split("&"):
        key = unquote_plus(fragment.partition("=")[0]).lower()
        if not key.startswith("utm_") and key not in TRACKING_KEYS:
            query.append(fragment)
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", "&".join(query), ""))


def normalized_excerpt(text: str) -> str:
    return " ".join(text.casefold().split())


def shingles(text: str) -> set[tuple[str, ...]]:
    tokens = re.findall(r"[a-z0-9]+|[\u3040-\u30ff\u3400-\u9fff]", text.casefold())
    return {tuple(tokens[index:index + 5]) for index in range(max(0, len(tokens) - 4))}


def group_source_families(evidence: list[Evidence]) -> None:
    """Group domains, byte-identical responses, and very similar long extracts.

    This estimates dependence. It cannot establish authorship or independent reporting.
    Never group empty/short boilerplate solely by textual similarity.
    """
    parents = list(range(len(evidence)))
    methods = ["domain"] * len(evidence)
    rank = {"domain": 0, "near_duplicate": 1, "exact_excerpt": 2, "exact_content": 3}

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def join(left, right, method):
        a, b = find(left), find(right)
        if a != b:
            parents[max(a, b)] = min(a, b)
        for index in (left, right):
            if rank[method] > rank[methods[index]]:
                methods[index] = method

    texts = [normalized_excerpt(item.excerpt) for item in evidence]
    fingerprints = [shingles(text) if len(text) >= 500 else set() for text in texts]
    for left, first in enumerate(evidence):
        host = (urlsplit(first.url).hostname or "").removeprefix("www.")
        for right in range(left + 1, len(evidence)):
            second = evidence[right]
            other_host = (urlsplit(second.url).hostname or "").removeprefix("www.")
            if host == other_host:
                join(left, right, "domain")
            # Fingerprints are assigned by retrieval, never by the AI planner.
            if first.content_sha256 and first.content_sha256 == second.content_sha256:
                join(left, right, "exact_content")
            elif len(texts[left]) >= 180 and texts[left] == texts[right]:
                join(left, right, "exact_excerpt")
            elif min(len(fingerprints[left]), len(fingerprints[right])) >= 60:
                intersection = len(fingerprints[left] & fingerprints[right])
                union = len(fingerprints[left] | fingerprints[right])
                if intersection / union >= 0.90:
                    join(left, right, "near_duplicate")
    for index, item in enumerate(evidence):
        group = [other for other in range(len(evidence)) if find(other) == find(index)]
        first = evidence[min(group)]
        item.source_family = (urlsplit(first.url).hostname or first.source_family).removeprefix("www.")
        item.source_family_method = methods[index]
        item.source_family_evidence_ids = [evidence[other].id for other in group if other != index]
