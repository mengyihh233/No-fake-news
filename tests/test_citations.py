from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from truth_backend.citations import excerpt_metadata, locate_quote, validate_citations
from truth_backend.models import Analysis, Evidence, QuoteCitation, Report
from truth_backend.reports import apply_analysis, numeric_values, public_report, validate_references
from truth_backend.security import ServiceError


QUOTE = "2021 年总量为 20。"
EXCERPT = "前言😀\n  2020 年总量为 10；" + QUOTE + "\n范围只包括年度记录。\n再次引用：" + QUOTE


def source(eid="E1", excerpt=EXCERPT):
    return Evidence(id=eid, title="年度记录", url=f"https://example.com/{eid}", publisher="example.com",
                    retrieved_at="2026-10-09T08:00:00Z", content_kind="full_text", excerpt=excerpt,
                    source_family="example.com", status="retrieved", document_format="html")


def report(version="1.1", mode="ai-summary"):
    return Report(schema_version=version, topic="核查年度总量", mode=mode, generated_at="2026-10-09T08:00:00Z",
                  scope="年度记录范围", claims=[{"id": "C1", "text": "2021 年总量是 20。", "kind": "fact"}],
                  evidence=[source()])


def quoted(eid="E1", quote=QUOTE):
    return {"evidence_id": eid, "quote": quote}


def analysis_data():
    citation = [quoted()]
    return {
        "claim_assessments": [{"claim_id": "C1", "verdict": "需核查口径", "analysis": "记录列出年度值。", "citations": citation}],
        "observations": [{"kind": "data", "text": "摘录列出 2021 年总量。", "claim_ids": ["C1"], "evidence_ids": ["E1"], "citations": citation}],
        "timeline": [{"date": "2021", "title": "年度记录", "detail": "摘录有该年度的数值。", "evidence_ids": ["E1"], "citations": citation}],
        "comparisons": [{"case": "年度比较", "date": "2020–2021", "similarities": "年度总量记录", "differences": "两个年度不同", "limits": "口径待复核", "evidence_ids": ["E1"], "citations": citation}],
        "reasoning": [{"id": "R1", "premise_ids": ["E1"], "claim_id": "C1", "text": "摘录是分析依据。", "kind": "data", "citations": citation},
                      {"id": "R2", "premise_ids": ["R1"], "claim_id": "C1", "text": "口径仍待复核。", "kind": "logic", "citations": citation}],
        "summary": {"text": "只在记录的范围内讨论数值。", "verdict": "仍需复核", "evidence_ids": ["E1"], "citations": citation},
        "charts": [{"title": "年度总量", "unit": "个", "kind": "bar", "points": [{"label": "2021", "value": 20, "evidence_ids": ["E1"], "source_quote": QUOTE}]}],
    }


def test_server_generates_codepoint_offsets_context_hash_and_ambiguity():
    output = public_report(apply_analysis(report(), Analysis.model_validate(analysis_data())))
    assert output["schema_version"] == "1.1"
    citation = output["observations"][0]["citations"][0]
    locator = citation["locator"]
    assert locator["start"] == EXCERPT.index(QUOTE)
    assert EXCERPT[locator["start"]:locator["end"]] == QUOTE
    assert locator["prefix"] == EXCERPT[:locator["start"]]
    assert locator["suffix"] == EXCERPT[locator["end"]:]
    assert locator["match_count"] == 2
    assert locator["coordinate_system"] == "unicode_codepoints"
    assert locator["excerpt_sha256"] == output["evidence"][0]["excerpt_metadata"]["sha256"]
    assert citation["verification"] == "exact_match"
    assert citation["semantic_support"] == "unverified"
    # A source quote remains available as a citation in exported chart data.
    assert output["charts"][0]["points"][0]["citations"][0]["quote"] == QUOTE
    assert "source_quote" not in output["charts"][0]["points"][0]
    validate_references(Report.model_validate(output))


@pytest.mark.parametrize("field", ["claim_assessments", "observations", "timeline", "comparisons", "reasoning", "summary"])
def test_new_analysis_requires_exact_citation_for_every_factual_item(field):
    data = analysis_data()
    item = data[field] if field == "summary" else data[field][0]
    item.pop("citations")
    with pytest.raises(ServiceError, match="精确原文"):
        apply_analysis(report(), Analysis.model_validate(data))


def test_old_report_remains_importable_without_invented_citation_verification():
    old = report("1.0", "evidence-only")
    old = Report.model_validate({**old.model_dump(), "observations": [{"kind": "data", "text": "原来的观察", "claim_ids": ["C1"], "evidence_ids": ["E1"]}]})
    validate_references(old)
    output = public_report(old)
    assert "citations" not in output["observations"][0]
    assert output["evidence"][0]["excerpt_metadata"] is None


def test_legacy_summary_can_require_citations_without_upgrading_or_rewriting_old_material():
    old = report("1.0", "evidence-only")
    old = Report.model_validate({**old.model_dump(), "observations": [{"kind": "logic", "text": "旧观察", "claim_ids": ["C1"], "evidence_ids": ["E1"]}]})
    original = deepcopy(old.evidence)
    old.mode = "ai-summary"
    result = apply_analysis(old, Analysis.model_validate(analysis_data()), judgment_only=True, require_citations=True)
    assert result.schema_version == "1.0"
    assert result.evidence == original
    assert result.observations == old.observations
    assert result.summary.citations[0].verification == "exact_match"
    data = analysis_data()
    data["summary"].pop("citations")
    with pytest.raises(ServiceError):
        apply_analysis(old, Analysis.model_validate(data), judgment_only=True, require_citations=True)


@pytest.mark.parametrize("quote", ["2021年总量为20。", "The 2021 total was 20.", "2021 年总量为 200。", " ", "[REDACTED CREDENTIAL]"])
def test_quotes_reject_translation_rewrites_whitespace_and_redaction(quote):
    with pytest.raises(ServiceError):
        locate_quote(QuoteCitation(evidence_id="E1", quote=quote), {"E1": source()})


def test_quote_whitespace_and_unicode_are_never_normalized():
    quote = "\n  2020 年总量为 10；"
    citation = QuoteCitation(evidence_id="E1", quote=quote)
    assert citation.quote == quote
    result = locate_quote(citation, {"E1": source()})
    assert result.quote == quote and result.locator.prefix == "前言😀"
    # NFC and decomposed code points are different source text.
    with pytest.raises(ServiceError):
        locate_quote(QuoteCitation(evidence_id="E1", quote="é"), {"E1": source(excerpt="e\u0301")})


def test_repeated_overlapping_matches_are_reported_explicitly():
    item = source(excerpt="aaaaa")
    result = locate_quote(QuoteCitation(evidence_id="E1", quote="aa"), {"E1": item})
    assert result.locator.match_count == 4
    assert result.locator.start == 0 and result.locator.end == 2


@pytest.mark.parametrize("mutation", [
    lambda data: data["locator"].update(start=0),
    lambda data: data["locator"].update(end=5000),
    lambda data: data["locator"].update(prefix="伪造上下文"),
    lambda data: data["locator"].update(suffix="伪造上下文"),
    lambda data: data["locator"].update(excerpt_sha256="0" * 64),
    lambda data: data["locator"].update(match_count=1),
    lambda data: data.update(locator=None),
    lambda data: data.update(verification=None),
])
def test_imported_new_report_cannot_forge_positions_context_or_hash(mutation):
    output = public_report(apply_analysis(report(), Analysis.model_validate(analysis_data())))
    mutation(output["observations"][0]["citations"][0])
    with pytest.raises(ServiceError):
        validate_references(Report.model_validate(output))


def test_import_detects_changed_excerpt_even_when_quoted_words_still_exist():
    output = public_report(apply_analysis(report(), Analysis.model_validate(analysis_data())))
    output["evidence"][0]["excerpt"] += "已修改的上下文"
    with pytest.raises(ServiceError):
        validate_references(Report.model_validate(output))


@pytest.mark.parametrize("field", ["locator", "verification", "semantic_support"])
def test_ai_cannot_generate_server_location_or_verification_fields(field):
    data = analysis_data()
    data["observations"][0]["citations"][0][field] = "invented"
    with pytest.raises(ValidationError):
        Analysis.model_validate(data)


def test_citation_cannot_reference_unlisted_source_or_duplicate_quote():
    sources = {"E1": source(), "E2": source("E2")}
    with pytest.raises(ServiceError):
        validate_citations([QuoteCitation(**quoted("E2"))], sources, allowed_ids=["E1"])
    with pytest.raises(ServiceError):
        validate_citations([QuoteCitation(**quoted()), QuoteCitation(**quoted())], sources)
    with pytest.raises(ServiceError):
        validate_citations([QuoteCitation(**quoted("E3"))], sources)


def test_reasoning_quote_must_belong_to_transitive_premises():
    current = report()
    current.evidence.append(source("E2"))
    data = analysis_data()
    data["reasoning"][1]["citations"] = [quoted("E2")]
    with pytest.raises(ServiceError):
        apply_analysis(current, Analysis.model_validate(data))


def test_exact_match_does_not_claim_semantic_entailment():
    data = analysis_data()
    data["observations"][0]["text"] = "这是未经语义验证的模型分析。"
    output = public_report(apply_analysis(report(), Analysis.model_validate(data)))
    assert output["observations"][0]["citations"][0]["semantic_support"] == "unverified"
    assert any("足以支持论断" in item for item in output["limitations"])
    output["observations"][0]["citations"][0]["semantic_support"] = "verified"
    with pytest.raises(ValidationError):
        Report.model_validate(output)


def test_evidence_mode_drops_judgment_and_its_citations_but_keeps_neutral_quotes():
    output = public_report(apply_analysis(report(), Analysis.model_validate(analysis_data())), "evidence-only")
    assert "summary" not in output and "reasoning" not in output
    assert set(output["claims"][0]) == {"id", "text", "kind"}
    assert output["observations"][0]["citations"][0]["quote"] == QUOTE
    validate_references(Report.model_validate(output))


def test_empty_derived_count_is_allowed_without_invented_quote_but_positive_count_is_quoted():
    data = analysis_data()
    point = data["charts"][0]["points"][0]
    point.update(value=0, source_quote="", calculation={"operation": "count", "source_quotes": [], "description": "仅统计所列摘录中明确列出的 2019 年记录，并未核实资料完整性。"})
    output = public_report(apply_analysis(report(), Analysis.model_validate(data)))
    assert "citations" not in output["charts"][0]["points"][0]
    validate_references(Report.model_validate(output))
    point.update(value=1, calculation={"operation": "count", "source_quotes": [QUOTE], "description": "只统计所引摘录中明确列出的 2021 年记录，单位是记录数，完整性待复核。"})
    output = public_report(apply_analysis(report(), Analysis.model_validate(data)))
    assert output["charts"][0]["points"][0]["citations"][0]["quote"] == QUOTE
    point["value"] = 2
    with pytest.raises(ServiceError):
        apply_analysis(report(), Analysis.model_validate(data))


def test_imported_chart_keeps_numeric_binding_to_exact_retained_quote():
    output = public_report(apply_analysis(report(), Analysis.model_validate(analysis_data())))
    point = output["charts"][0]["points"][0]
    point["citations"] = [locate_quote(QuoteCitation(evidence_id="E1", quote="2020 年总量为 10"), {"E1": source()}).model_dump()]
    with pytest.raises(ServiceError):
        validate_references(Report.model_validate(output))


def test_retrieval_gap_metadata_does_not_bypass_known_claim_validation():
    current = report("1.0")
    data = current.model_dump()
    data["retrieval_gaps"] = [{"claim_id": "C999", "reason": "limited_families", "query": "query", "attempted": False}]
    with pytest.raises(ServiceError):
        validate_references(Report.model_validate(data))
    data["retrieval_gaps"][0]["claim_id"] = "C1"
    data["search_log"] = [{"query": "query", "intent": "support", "provider": "mock", "result_count": 0, "ran_at": "2026-10-09T08:00:00Z", "round": "supplemental", "gap_claim_ids": ["C999"]}]
    with pytest.raises(ServiceError):
        validate_references(Report.model_validate(data))


def test_excerpt_hash_is_utf8_digest_not_a_truth_or_full_response_signature():
    item = source()
    assert excerpt_metadata(item.excerpt).coordinate_system == "unicode_codepoints"
    assert item.content_sha256 is None
    assert item.excerpt_metadata is None


def test_numeric_matching_accepts_sentence_period_without_accepting_partial_decimal():
    assert numeric_values("The annual total was 20.") == {Decimal(20)}
    assert numeric_values("The result was 20.5.") == {Decimal("20.5")}
    assert numeric_values("20.5.6") == set()


def test_evidence_preserves_leading_whitespace_and_trailing_empty_table_cells():
    excerpt = "  Year\tA\tB\n2024\t10\t"
    item = source(excerpt=excerpt)
    assert item.excerpt == excerpt
    result = locate_quote(QuoteCitation(evidence_id="E1", quote="2024\t10\t"), {"E1": item})
    assert result.locator.end == len(excerpt)


def test_chart_source_quotes_and_count_record_quotes_preserve_exact_whitespace():
    current = report("1.1", "evidence-only")
    data = analysis_data()
    data["claim_assessments"], data["reasoning"], data["summary"] = [], [], None
    quote = "\n  2020 年总量为 10；"
    point = data["charts"][0]["points"][0]
    point.update(value=10, source_quote=quote)
    analysis = Analysis.model_validate(data)
    assert analysis.charts[0].points[0].source_quote == quote
    output = public_report(apply_analysis(current, analysis))
    assert output["charts"][0]["points"][0]["citations"][0]["quote"] == quote
    point.update(value=1, calculation={"operation": "count", "source_quotes": [quote], "description": "按所列原句统计唯一年度记录，范围仅限所列摘录，未验证完整性。"})
    analysis = Analysis.model_validate(data)
    assert analysis.charts[0].points[0].calculation.source_quotes == [quote]
    output = public_report(apply_analysis(current, analysis))
    assert output["charts"][0]["points"][0]["citations"][0]["quote"] == quote


def test_legacy_long_count_quotes_are_preserved_without_fabricating_new_locator():
    quote = "年度记录 " + "原文" * 1100
    current = report("1.0", "evidence-only")
    current.evidence = [source(excerpt=quote)]
    analysis = Analysis.model_validate({"charts": [{"title": "计数", "unit": "记录", "kind": "bar", "points": [{
        "label": "一条记录", "value": 1, "evidence_ids": ["E1"],
        "calculation": {"operation": "count", "source_quotes": [quote], "description": "只统计摘录中逐字引用的这一条原始记录，资料范围及完整性另行核验。"}}]}]})
    output = public_report(apply_analysis(current, analysis))
    point = output["charts"][0]["points"][0]
    assert point["calculation"]["source_quotes"] == [quote]
    assert "citations" not in point
    validate_references(Report.model_validate(output))
    current.schema_version = "1.1"
    with pytest.raises(ServiceError):
        apply_analysis(current, analysis)
