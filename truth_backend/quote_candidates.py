"""Deterministic original-text fragments for model-selected quote references."""
from __future__ import annotations

import re

from .models import Evidence


def quote_candidates(evidence: list[Evidence]) -> list[dict[str, str]]:
    """Partition the displayed extract without rewriting or joining omitted text.

    IDs locate candidate fragments, not verified semantic support. Source text is
    still rechecked after model selection. Privacy and omission markers are not
    original material and cannot be selected as quoted evidence.
    """
    catalog = []
    for source in evidence:
        text = source.excerpt
        cursor, number = 0, 0
        exclusions = list(re.finditer(r"\[…\]|\[REDACTED CREDENTIAL\]", text))
        spans = []
        for marker in exclusions:
            spans.append((cursor, marker.start()))
            cursor = marker.end()
        spans.append((cursor, len(text)))
        for left, right in spans:
            while left < right:
                end = min(left + 700, right)
                if end < right:
                    boundaries = list(re.finditer(r"[.!?。！？；;](?:\s|$)|\n", text[left + 240:end]))
                    if boundaries:
                        end = left + 240 + boundaries[-1].end()
                    else:
                        space = text.rfind(" ", left + 240, end)
                        if space >= 0:
                            end = space + 1
                fragment = text[left:end]
                if fragment.strip():
                    number += 1
                    catalog.append({"quote_id": f"{source.id}Q{number}", "evidence_id": source.id, "quote": fragment})
                left = end
    return catalog
