"""Stable review targets and snapshot checks; never an entailment verifier."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from itertools import zip_longest

from .citations import validate_citations
from .i18n import tr
from .models import Citation, Report
from .security import ServiceError


REVIEW_CAPACITIES = {"brief": 12, "standard": 24, "deep": 40}
REVIEW_INPUT_CHARACTER_LIMIT = 120_000


@dataclass
class ReviewTarget:
    target_id: str
    statement: dict
    citations: list[Citation]
    context: list[dict[str, str]]

    def hash_payload(self) -> dict:
        return {"target_id": self.target_id, "statement": self.statement,
                "citations": [citation.model_dump() for citation in self.citations], "context": self.context}


def canonical_numbers(value):
    """Make 20 and 20.0 identical across Python/JavaScript report round trips."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        text = format(Decimal(str(value)), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text == "-0" else text
    if isinstance(value, dict):
        return {key: canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical_numbers(item) for item in value]
    return value


def target_sha256(target: ReviewTarget) -> str:
    serialized = json.dumps(canonical_numbers(target.hash_payload()), ensure_ascii=False,
                            sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def all_review_targets(report: Report) -> list[ReviewTarget]:
    """Summary first, then round-robin categories; retain original quote order."""
    sources = {item.id: item for item in report.evidence}

    def target(identifier, item, extra=None):
        citations = item.citations
        if not citations or any(citation.verification != "exact_match" or citation.locator is None for citation in citations):
            return None
        content = item.model_dump(exclude={"citations"})
        if extra:
            content = {**extra, "point": content}
        statement = {"report_topic": report.topic, "report_scope": report.scope, "content": content}
        context = [{"evidence_id": eid, "title": sources[eid].title, "context": sources[eid].context,
                    "excerpt": sources[eid].excerpt}
                   for eid in dict.fromkeys(citation.evidence_id for citation in citations)]
        return ReviewTarget(identifier, statement, citations, context)

    categories = [[], [], [], [], [], []]
    for index, item in enumerate(report.observations, 1):
        categories[0].append(target(f"observation:{index}", item))
    for item in report.claims:
        if item.verdict or item.analysis:
            categories[1].append(target(f"claim:{item.id}", item))
    for index, item in enumerate(report.timeline, 1):
        categories[2].append(target(f"timeline:{index}", item))
    for chart_index, chart in enumerate(report.charts, 1):
        extra = chart.model_dump(exclude={"points"})
        for point_index, point in enumerate(chart.points, 1):
            categories[3].append(target(f"chart:{chart_index}:point:{point_index}", point, extra))
    for index, item in enumerate(report.comparisons, 1):
        categories[4].append(target(f"comparison:{index}", item))
    for item in report.reasoning:
        categories[5].append(target(f"reasoning:{item.id}", item))
    categories = [[item for item in category if item is not None] for category in categories]
    summary = target("summary", report.summary) if report.summary is not None else None
    result = [summary] if summary is not None else []
    result.extend(item for row in zip_longest(*categories) for item in row if item is not None)
    return result


def build_review_payload(targets: list[ReviewTarget], depth: str, language: str) -> dict:
    sources = {entry["evidence_id"]: entry for target in targets for entry in target.context}
    return canonical_numbers({"language": language, "depth": depth, "method": "ai_advisory",
                              "targets": [{"target_id": target.target_id, "statement": target.statement,
                                           "quotations": [{"evidence_id": citation.evidence_id, "quote": citation.quote}
                                                          for citation in target.citations]} for target in targets],
                              "source_context": list(sources.values())})


def review_input_characters(payload: dict) -> int:
    # Match complete()'s user-message serialization, including separator spaces.
    # The fixed system instruction/schema overhead is outside this payload cap.
    return len(json.dumps(payload, ensure_ascii=False, allow_nan=False))


def selected_review_targets(report: Report, language: str | None = None) -> list[ReviewTarget]:
    language = language or (report.citation_review.language if report.citation_review else report.language)
    selected = []
    for target in all_review_targets(report):
        if len(selected) >= REVIEW_CAPACITIES[report.depth]:
            break
        if review_input_characters(build_review_payload([*selected, target], report.depth, language)) <= REVIEW_INPUT_CHARACTER_LIMIT:
            selected.append(target)
    return selected


def reject_review(language="zh-CN"):
    raise ServiceError("invalid_citation_review", tr(
        "引文复核与当前报告的目标、原句、定位、上下文或计数不一致，未接受该复核。",
        "The citation review does not match the report's targets, quotations, locators, context, or counts and was rejected.",
        "引用レビューが現在のレポートの対象、原文、位置、文脈、件数と一致しないため、受け付けませんでした。", language), 422)


def validate_review_urls(explanation: str, report: Report, language="zh-CN") -> None:
    known_urls = {source.url for source in report.evidence}
    for url in re.findall(r"https?://[^\s\"<>]+", explanation, flags=re.IGNORECASE):
        if url.rstrip(".,，。;；)）]") not in known_urls:
            reject_review(language)


def validate_citation_review(report: Report) -> None:
    """Check imported advice against the present report; does not prove its origin."""
    review = report.citation_review
    if review is None:
        return
    language = review.language
    if report.mode != "ai-summary" or report.schema_version != "1.2":
        reject_review(language)
    targets = all_review_targets(report)
    capacity = REVIEW_CAPACITIES[report.depth]
    selected_targets = selected_review_targets(report, language)
    selected = {target.target_id: target for target in selected_targets}
    payload_size = review_input_characters(build_review_payload(selected_targets, report.depth, language))
    if (review.available_targets != len(targets) or review.capacity != capacity
            or review.selected_targets != len(selected_targets) or review.input_characters != payload_size
            or review.reviewed_targets != len(review.items)
            or review.not_reviewed_targets != len(targets) - len(review.items)
            or len(review.items) > len(selected_targets)):
        reject_review(language)
    sources = {item.id: item for item in report.evidence}
    seen = set()
    for item in review.items:
        target = selected.get(item.target_id)
        if (target is None or item.target_id in seen or item.target_sha256 != target_sha256(target)
                or len(item.issues) != len(set(item.issues))):
            reject_review(language)
        seen.add(item.target_id)
        if any(citation not in target.citations for citation in item.citations):
            reject_review(language)
        try:
            validate_citations(item.citations, sources, allowed_ids=[citation.evidence_id for citation in target.citations],
                               required=True, stored=True)
        except ServiceError:
            reject_review(language)
        validate_review_urls(item.explanation, report, language)
