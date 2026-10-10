"""Resolve server-issued passage IDs without relaxing exact excerpt validation."""
from __future__ import annotations

from collections.abc import Iterator, Mapping

from pydantic import ValidationError

from .models import Analysis, AnalysisQuoteReference, QuoteCitation
from .security import ServiceError


def iter_analysis_quote_references(analysis: Analysis) -> Iterator[AnalysisQuoteReference]:
    items = [*analysis.claim_assessments, *analysis.timeline, *analysis.comparisons,
             *analysis.observations, *analysis.reasoning,
             *([analysis.summary] if analysis.summary is not None else []),
             *(point for chart in analysis.charts for point in chart.points)]
    for item in items:
        yield from item.citations


def reject() -> None:
    raise ServiceError("invalid_evidence_reference", "引文目录 ID 不存在、关联了其他证据，或提供的原句与服务器目录不一致。")


def resolve_analysis_quotes(analysis: Analysis, catalog: Mapping[str, Mapping[str, str]]) -> Analysis:
    """Return a resolved copy. Reports still verify every quote against its excerpt.

    This does not choose relevant passages, infer missing citations, or generate
    source text. A model must explicitly select a valid passage or provide an
    exact quotation. Caller-owned analysis and catalog remain unchanged on errors.
    """
    if not isinstance(catalog, Mapping):
        reject()
    result = analysis.model_copy(deep=True)
    chart_selections = [(point, [reference for reference in point.citations if reference.quote_id is not None])
                        for chart in result.charts for point in chart.points
                        if point.value is not None and point.calculation is None and not point.source_quote]
    for reference in iter_analysis_quote_references(result):
        if reference.quote_id is None:
            if not reference.quote.strip():
                reject()
            continue
        entry = catalog.get(reference.quote_id)
        if not isinstance(entry, Mapping):
            reject()
        try:
            original = QuoteCitation.model_validate({key: entry[key] for key in ("evidence_id", "quote") if key in entry})
        except (ValidationError, TypeError, ValueError):
            reject()
        if (reference.quote_id.split("Q", 1)[0] != reference.evidence_id
                or entry.get("quote_id", reference.quote_id) != reference.quote_id
                or original.evidence_id != reference.evidence_id
                or not original.quote.strip()
                or "[REDACTED CREDENTIAL]" in original.quote
                or (reference.quote and reference.quote != original.quote)):
            reject()
        reference.quote = original.quote
        reference.quote_id = None
    for point, selected in chart_selections:
        if not selected:
            continue
        # Import only at call time: reports uses this module to reject unresolved IDs.
        from decimal import Decimal
        from .reports import numeric_values
        quote = next((reference.quote for reference in selected
                      if reference.evidence_id in point.evidence_ids and len(reference.quote) <= 1000
                      and Decimal(str(point.value)) in numeric_values(reference.quote)), None)
        if quote is None:
            raise ServiceError("invalid_evidence_reference", "图表所选择的服务器引句未包含该数值，不能自动补写 source_quote。")
        point.source_quote = quote
    return result
