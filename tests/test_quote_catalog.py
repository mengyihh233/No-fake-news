from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from truth_backend.models import Analysis, AnalysisQuoteReference, Citation, QuoteCitation, Report
from truth_backend.quote_catalog import iter_analysis_quote_references, resolve_analysis_quotes
from truth_backend.reports import apply_analysis, public_report, validate_references
from truth_backend.security import ServiceError


QUOTE = "\n  Annual total was 20.\t"
CATALOG = {"E1Q1": {"quote_id": "E1Q1", "evidence_id": "E1", "quote": QUOTE}}


def source_report():
    return Report.model_validate({"schema_version": "1.1", "topic": "核查年度记录", "mode": "ai-summary",
                                  "generated_at": "2026-10-10T00:00:00Z", "scope": "Provided extract",
                                  "claims": [{"id": "C1", "text": "Annual total was 20", "kind": "fact"}],
                                  "evidence": [{"id": "E1", "title": "Report", "url": "https://example.com/record", "publisher": "example.com",
                                                "retrieved_at": "2026-10-10T00:00:00Z", "content_kind": "full_text", "excerpt": "Header😀" + QUOTE + "End",
                                                "source_family": "example.com", "status": "retrieved"}]})


def analysis_data(reference=None):
    citation = [reference or {"evidence_id": "E1", "quote_id": "E1Q1"}]
    return deepcopy({
        "claim_assessments": [{"claim_id": "C1", "verdict": "Conditional", "analysis": "Check the definition", "citations": citation}],
        "observations": [{"kind": "data", "text": "A total is listed", "claim_ids": ["C1"], "evidence_ids": ["E1"], "citations": citation}],
        "timeline": [{"date": "2021", "title": "Annual record", "detail": "Recorded value", "evidence_ids": ["E1"], "citations": citation}],
        "comparisons": [{"case": "Yearly record", "date": "2021", "similarities": "Definitions", "differences": "Scope", "limits": "Check original", "evidence_ids": ["E1"], "citations": citation}],
        "reasoning": [{"id": "R1", "claim_id": "C1", "premise_ids": ["E1"], "kind": "data", "text": "Read the value", "citations": citation}],
        "summary": {"text": "Definitions remain unverified", "verdict": "Conditional", "evidence_ids": ["E1"], "citations": citation},
        "charts": [{"title": "Total", "kind": "bar", "unit": "Records", "points": [{"label": "Year", "value": 20, "evidence_ids": ["E1"], "source_quote": QUOTE, "citations": citation}]}],
    })


def test_catalog_resolves_all_analysis_fields_without_modifying_inputs_or_excerpt():
    analysis = Analysis.model_validate(analysis_data())
    original = analysis.model_dump()
    catalog = deepcopy(CATALOG)
    resolved = resolve_analysis_quotes(analysis, catalog)
    assert analysis.model_dump() == original
    assert catalog == CATALOG
    assert len(list(iter_analysis_quote_references(resolved))) == 7
    for reference in iter_analysis_quote_references(resolved):
        assert reference.quote == QUOTE and reference.quote_id is None
    report = source_report()
    excerpt = report.evidence[0].excerpt
    output = public_report(apply_analysis(report, resolved))
    assert output["evidence"][0]["excerpt"] == excerpt
    assert "quote_id" not in str(output)
    assert output["observations"][0]["citations"][0]["quote"] == QUOTE
    assert output["observations"][0]["citations"][0]["verification"] == "exact_match"
    assert output["observations"][0]["citations"][0]["semantic_support"] == "unverified"
    validate_references(Report.model_validate(output))


@pytest.mark.parametrize("reference", [
    {"evidence_id": "E1", "quote_id": "E1Q999"},
    {"evidence_id": "E2", "quote_id": "E1Q1"},
    {"evidence_id": "E1", "quote_id": "E1Q1", "quote": "Annual total was 200."},
    {"evidence_id": "E1", "quote_id": "E1Q1", "quote": QUOTE.strip()},
    {"evidence_id": "E1"},
    {"evidence_id": "E1", "quote": " "},
])
def test_unknown_mismatched_conflicting_or_empty_quote_references_are_rejected(reference):
    with pytest.raises(ServiceError) as error:
        resolve_analysis_quotes(Analysis.model_validate(analysis_data(reference)), CATALOG)
    assert error.value.code == "invalid_evidence_reference"


@pytest.mark.parametrize("catalog", [
    {},
    {"E1Q1": {"evidence_id": "E2", "quote": QUOTE}},
    {"E1Q1": {"evidence_id": "E1", "quote": " "}},
    {"E1Q1": {"evidence_id": "E1", "quote": "[REDACTED CREDENTIAL]"}},
    {"E1Q1": {"evidence_id": "E1", "quote": "a" * 2001}},
    {"E1Q1": {"quote_id": "E1Q2", "evidence_id": "E1", "quote": QUOTE}},
    {"E1Q1": "not a passage"},
    None,
])
def test_bad_catalog_entries_cannot_supply_verified_source_content(catalog):
    with pytest.raises(ServiceError) as error:
        resolve_analysis_quotes(Analysis.model_validate(analysis_data()), catalog)
    assert error.value.code == "invalid_evidence_reference"


def test_matching_explicit_quote_is_accepted_but_legacy_exact_quote_needs_no_catalog():
    reference = {"evidence_id": "E1", "quote_id": "E1Q1", "quote": QUOTE}
    resolved = resolve_analysis_quotes(Analysis.model_validate(analysis_data(reference)), CATALOG)
    assert all(item.quote == QUOTE for item in iter_analysis_quote_references(resolved))
    legacy = Analysis.model_validate(analysis_data({"evidence_id": "E1", "quote": QUOTE}))
    output = public_report(apply_analysis(source_report(), resolve_analysis_quotes(legacy, {})))
    assert "quote_id" not in str(output)
    validate_references(Report.model_validate(output))


def test_id_resolution_does_not_replace_strict_excerpt_or_chart_numeric_checks():
    resolved = resolve_analysis_quotes(Analysis.model_validate(analysis_data()), {"E1Q1": {"evidence_id": "E1", "quote": "Not in the excerpt"}})
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), resolved)
    data = analysis_data()
    data["charts"][0]["points"][0]["value"] = 200
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), CATALOG)
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), resolved)


def test_unresolved_id_cannot_bypass_catalog_validation_by_also_supplying_a_real_quote():
    analysis = Analysis.model_validate(analysis_data({"evidence_id": "E1", "quote_id": "E1Q999", "quote": QUOTE}))
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), analysis)


def test_failed_resolution_never_partially_modifies_the_callers_analysis():
    data = analysis_data()
    data["summary"]["citations"][0]["quote_id"] = "E1Q999"
    analysis = Analysis.model_validate(data)
    before = analysis.model_dump()
    with pytest.raises(ServiceError):
        resolve_analysis_quotes(analysis, CATALOG)
    assert analysis.model_dump() == before


def test_catalog_ids_are_not_allowed_in_stored_citation_models():
    reference = {"evidence_id": "E1", "quote": QUOTE, "quote_id": "E1Q1"}
    with pytest.raises(ValidationError):
        QuoteCitation.model_validate(reference)
    with pytest.raises(ValidationError):
        Citation.model_validate(reference)


@pytest.mark.parametrize("quote_id", ["E0Q1", "E1Q0", " E1Q1", "E1Q1 ", "E1-Q1", "E1Q1<script>"])
def test_analysis_quote_reference_rejects_malformed_ids_without_trimming(quote_id):
    with pytest.raises(ValidationError):
        AnalysisQuoteReference(evidence_id="E1", quote_id=quote_id)


def test_resolved_id_does_not_allow_source_outside_the_items_declared_evidence():
    data = analysis_data()
    data["observations"][0]["evidence_ids"] = ["E2"]
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), CATALOG)
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), resolved)


def test_catalog_metadata_is_allowlisted_and_never_enters_stored_citations():
    catalog = {"E1Q1": {"quote_id": "E1Q1", "evidence_id": "E1", "quote": QUOTE,
                         "server_metadata": "not citation content"}}
    output = public_report(apply_analysis(source_report(), resolve_analysis_quotes(Analysis.model_validate(analysis_data()), catalog)))
    assert "server_metadata" not in str(output)
    assert "quote_id" not in str(output)


def test_chart_can_resolve_selected_numeric_passage_without_recopying_source_quote():
    data = analysis_data()
    data["charts"][0]["points"][0]["source_quote"] = ""
    analysis = Analysis.model_validate(data)
    resolved = resolve_analysis_quotes(analysis, CATALOG)
    assert resolved.charts[0].points[0].source_quote == QUOTE
    assert analysis.charts[0].points[0].source_quote == ""
    output = public_report(apply_analysis(source_report(), resolved))
    assert output["charts"][0]["points"][0]["value"] == 20
    assert "quote_id" not in str(output)
    validate_references(Report.model_validate(output))


def test_chart_catalog_does_not_fill_wrong_values_or_use_unselected_quotes():
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    point.update(source_quote="", value=200)
    with pytest.raises(ServiceError):
        resolve_analysis_quotes(Analysis.model_validate(data), CATALOG)
    point["value"] = 20
    point["citations"] = [{"evidence_id": "E1", "quote_id": "E1Q2"}, {"evidence_id": "E1", "quote": QUOTE}]
    catalog = {**CATALOG, "E1Q2": {"evidence_id": "E1", "quote": "Header😀"}}
    with pytest.raises(ServiceError):
        resolve_analysis_quotes(Analysis.model_validate(data), catalog)


def test_chart_without_quote_id_never_receives_automatic_source_quote():
    data = analysis_data({"evidence_id": "E1", "quote": QUOTE})
    data["charts"][0]["points"][0]["source_quote"] = ""
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), CATALOG)
    assert resolved.charts[0].points[0].source_quote == ""
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), resolved)


def test_nonempty_chart_source_quote_is_never_corrected_or_replaced():
    data = analysis_data()
    data["charts"][0]["points"][0]["source_quote"] = "Annual total was 200."
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), CATALOG)
    assert resolved.charts[0].points[0].source_quote == "Annual total was 200."
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), resolved)


def test_count_records_never_receive_automatic_quote_list_from_catalog():
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    point.update(value=1, source_quote="", calculation={"operation": "count", "source_quotes": [],
                                                        "description": "Count only explicitly quoted records; verify completeness separately."})
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), CATALOG)
    assert resolved.charts[0].points[0].calculation.source_quotes == []
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), resolved)


def url_quote_report():
    current = source_report()
    quote = QUOTE + ' Original reference: https://elsewhere.example/info?x=1&y=2 <img src=x onerror="alert(1)">'
    current.evidence[0].excerpt = "Header😀" + quote + " End"
    catalog = {"E1Q1": {"quote_id": "E1Q1", "evidence_id": "E1", "quote": quote}}
    return current, catalog, quote


def test_original_external_urls_are_allowed_in_exact_catalog_quotes_and_escaped_in_html():
    current, catalog, quote = url_quote_report()
    data = analysis_data()
    data["charts"][0]["points"][0]["source_quote"] = ""
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), catalog)
    before = resolved.model_dump()
    output = public_report(apply_analysis(current, resolved), "evidence-only")
    assert resolved.model_dump() == before
    assert output["observations"][0]["citations"][0]["quote"] == quote
    validate_references(Report.model_validate(output))
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("quote_url_renderer", root / "skills/tell-me-truth/scripts/render_report.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    package = renderer.project_report(output, "evidence-only")
    renderer.validate(package)
    page = renderer.render(package, root, language="en")
    assert 'https://elsewhere.example/info?x=1&amp;y=2' in page
    assert '&lt;img src=x' in page
    assert '<img src=x' not in page
    assert 'href="https://elsewhere.example/' not in page  # Quoted links stay text.


@pytest.mark.parametrize("mutation", [
    lambda data, url: data["observations"][0].update(text="See " + url),
    lambda data, url: data["claim_assessments"][0].update(analysis="See " + url),
    lambda data, url: data["timeline"][0].update(detail="See " + url),
    lambda data, url: data["comparisons"][0].update(limits="See " + url),
    lambda data, url: data["reasoning"][0].update(text="See " + url),
    lambda data, url: data["summary"].update(text="See " + url),
    lambda data, url: data["summary"].update(caveats=["See " + url]),
    lambda data, url: data.update(questions=["Check " + url]),
    lambda data, url: data.update(limitations=["Check " + url]),
    lambda data, url: data["charts"][0].update(note="See " + url),
    lambda data, url: data.update(links=[{"from": "E1", "to": "C1", "relation": "relevant_to", "note": "See " + url}]),
    lambda data, url: data.update(evidence_annotations=[{"evidence_id": "E1", "claim_ids": ["C1"], "context": "See " + url}]),
])
def test_external_url_in_analysis_narrative_is_rejected_even_if_the_url_also_occurs_in_a_real_quote(mutation):
    current, catalog, _ = url_quote_report()
    data = analysis_data()
    mutation(data, "https://elsewhere.example/info?x=1&y=2")
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), catalog)
    with pytest.raises(ServiceError):
        apply_analysis(current, resolved)


def test_original_count_quote_may_contain_external_url_but_count_description_cannot_add_source():
    current, catalog, quote = url_quote_report()
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    point.update(value=1, source_quote="", calculation={"operation": "count", "source_quotes": [quote],
                                                        "description": "Count only this exact original record; list completeness remains unverified."})
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), catalog)
    output = public_report(apply_analysis(current, resolved))
    assert output["charts"][0]["points"][0]["calculation"]["source_quotes"] == [quote]
    point["calculation"]["description"] += " See https://new-source.example/record"
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), catalog)
    with pytest.raises(ServiceError):
        apply_analysis(current, resolved)


@pytest.mark.parametrize("kind", ["direct", "count"])
def test_url_exemptions_never_allow_fabricated_chart_quotation(kind):
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    fabricated = "Annual total was 20. See https://fabricated.example/source"
    if kind == "count":
        point.update(value=1, source_quote="", calculation={"operation": "count", "source_quotes": [fabricated],
                                                            "description": "Count exactly the listed quoted records, subject to manual completeness review."})
    else:
        point["source_quote"] = fabricated
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), CATALOG)
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), resolved)


@pytest.mark.parametrize("kind", ["null", "count"])
def test_unused_source_quote_is_not_exempt_from_narrative_url_check(kind):
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    point["source_quote"] = "https://unvalidated.example/unused"
    if kind == "null":
        point["value"] = None
    else:
        point.update(value=1, calculation={"operation": "count", "source_quotes": [QUOTE],
                                          "description": "Count only the explicit original record, with incomplete coverage acknowledged."})
    resolved = resolve_analysis_quotes(Analysis.model_validate(data), CATALOG)
    with pytest.raises(ServiceError):
        apply_analysis(source_report(), resolved)
