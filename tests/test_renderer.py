"""Behavioral invariants for portable, user-selectable evidence reports."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("renderer", ROOT / "skills/tell-me-truth/scripts/render_report.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def fixture():
    return {
        "schema_version": "1.0", "topic": "Example <script>alert(1)</script>",
        "claims": [{"id": "C1", "text": "Claim", "kind": "fact", "verdict": "VERDICT_SECRET", "analysis": "ANALYSIS_SECRET"}],
        "evidence": [{"id": "E1", "url": "https://example.org/source", "title": "Source", "claim_ids": ["C1"], "excerpt": '<img src=x onerror="alert(2)">'}],
        "links": [{"from": "E1", "to": "C1", "relation": "contradicts", "note": "NOTE_SECRET"}],
        "summary": {"text": "SUMMARY_SECRET", "evidence_ids": ["E1"]},
        "reasoning": [{"id": "R1", "premise_ids": ["E1"], "claim_id": "C1", "text": "REASONING_SECRET"}],
        "unknown_private": "PRIVATE_SECRET",
        "depth": "deep",
        "observations": [{"kind": "logic", "text": "NEUTRAL_ANALYSIS", "claim_ids": ["C1"], "evidence_ids": ["E1"], "private": "PRIVATE_SECRET"}],
        "charts": [{"kind": "bar", "title": "Chart", "points": [{"label": "positive", "value": 2, "evidence_ids": ["E1"]}, {"label": "negative", "value": -1, "evidence_ids": ["E1"]}, {"label": "missing", "value": None, "evidence_ids": ["E1"]}]}],
    }


def fixture_v11():
    excerpt = '前言😀\n  2021 total = 20. <img src=x onerror="alert(2)">\nAgain: 2021 total = 20.\t'
    quote = "2021 total = 20."
    start = excerpt.index(quote)
    end = start + len(quote)
    digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    citation = {"evidence_id": "E1", "quote": quote, "verification": "exact_match", "semantic_support": "unverified",
                "locator": {"start": start, "end": end, "prefix": excerpt[:start], "suffix": excerpt[end:end + 80],
                            "excerpt_sha256": digest, "match_count": 2, "coordinate_system": "unicode_codepoints"}}
    result = fixture()
    result["schema_version"] = "1.1"
    result["claims"][0]["citations"] = [citation]
    result["evidence"][0].update(excerpt=excerpt, document_format="csv", content_sha256="1" * 64,
                                 source_family_method="near_duplicate", source_family_evidence_ids=["E1"],
                                 excerpt_metadata={"sha256": digest, "coordinate_system": "unicode_codepoints"})
    result["observations"][0]["citations"] = [citation]
    result["summary"]["citations"] = [citation]
    result["reasoning"][0]["citations"] = [citation]
    result["timeline"] = [{"date": "2021", "title": "年度记录", "detail": "年度数据", "evidence_ids": ["E1"], "citations": [citation]}]
    result["comparisons"] = [{"case": "年度比较", "date": "2021", "similarities": "年度口径", "differences": "范围不同", "limits": "待复核", "evidence_ids": ["E1"], "citations": [citation]}]
    result["charts"][0]["points"] = [{"label": "2021", "value": 20, "evidence_ids": ["E1"], "citations": [citation]}]
    result["retrieval_gaps"] = [{"claim_id": "C1", "reason": "limited_families", "query": "追加資料 <img onerror=alert(1)>", "attempted": True}]
    result["search_log"] = [{"query": "年度資料", "intent": "counter", "provider": "mock", "result_count": 1, "ran_at": "2026-10-10T00:00:00Z", "round": "supplemental", "gap_claim_ids": ["C1"]}]
    # JSON round trip separates shared quotation dictionaries for mutation tests.
    return json.loads(json.dumps(result, ensure_ascii=False))


def fixture_v12():
    result = fixture_v11()
    result.update(schema_version="1.2", mode="ai-summary", language="en", scope="Annual records",
                  generated_at="2026-10-10T00:00:00Z")
    result["evidence"][0].update(publisher="Source publisher", retrieved_at="2026-10-10T00:00:00Z",
                                 source_family="example.org", content_kind="full_text", status="retrieved", context="Original source context")
    result["charts"][0].update(unit="records", note="Original chart definition")
    result["reasoning"][0]["kind"] = "logic"
    result["summary"].update(verdict="Conditional assessment", caveats=[])
    result["timeline"][0]["title"] = "Annual record"
    result["topic"] = "Check the annual total"
    return attach_review(renderer.project_report(result, "ai-summary"))


def attach_review(result, identifiers=None, language="en"):
    projected = renderer.project_report(result, "ai-summary")
    targets = renderer.review_targets(projected)
    selected = renderer.selected_review_targets(projected, language)
    identifiers = ["summary"] if identifiers is None else identifiers
    result["citation_review"] = {
        "generated_at": "2026-10-10T00:01:00Z", "language": language,
        "model": 'configured-model <img src=x onerror="alert(4)">', "method": "ai_advisory",
        "available_targets": len(targets), "selected_targets": len(selected), "reviewed_targets": len(identifiers),
        "not_reviewed_targets": len(targets) - len(identifiers), "capacity": {"brief": 12, "standard": 24, "deep": 40}[result["depth"]],
        "input_character_limit": 120000,
        "input_characters": renderer.review_input_characters(renderer.build_review_payload(selected, result["depth"], language)),
        "items": [{"target_id": target["target_id"], "target_sha256": renderer.review_target_sha256(target),
                   "relation": "partial", "issues": ["scope", "context"],
                   "explanation": 'REVIEW_ADVICE <script>alert(3)</script> The scope needs inspection.',
                   "citations": target["citations"]} for target in targets if target["target_id"] in identifiers],
    }
    return result


def test_v12_renderer_matches_backend_target_hashes_and_selection():
    from truth_backend.models import Report
    from truth_backend.review_targets import all_review_targets, selected_review_targets, target_sha256, build_review_payload, review_input_characters, validate_citation_review
    original = fixture_v12()
    model = Report.model_validate(original)
    validate_citation_review(model)
    projected = renderer.project_report(model.model_dump(by_alias=True), "ai-summary")
    renderer.validate(projected)
    actual = renderer.review_targets(projected)
    expected = all_review_targets(model)
    assert len(actual) == 7
    assert [target["target_id"] for target in actual] == [target.target_id for target in expected]
    assert [renderer.review_target_sha256(target) for target in actual] == [target_sha256(target) for target in expected]
    selected = selected_review_targets(model, "en")
    assert renderer.build_review_payload(renderer.selected_review_targets(projected, "en"), model.depth, "en") == build_review_payload(selected, model.depth, "en")
    assert projected["citation_review"]["input_characters"] == review_input_characters(build_review_payload(selected, model.depth, "en"))
    for point in projected["charts"][0]["points"]:
        point["value"] = float(point["value"])
    renderer.validate(projected)


@pytest.mark.parametrize("language,label,unreviewed", [
    ("zh-CN", "AI 引文关系复核", "未复核目标"),
    ("en", "AI citation relationship review", "Unreviewed targets"),
    ("ja", "引用関係の AI 確認", "未確認の対象"),
])
def test_v12_review_advice_is_escaped_and_coverage_is_explicit(language, label, unreviewed):
    projected = renderer.project_report(fixture_v12(), "ai-summary")
    renderer.validate(projected, language)
    output = renderer.render(projected, ROOT, language=language)
    assert label in output and unreviewed in output
    assert "REVIEW_ADVICE &lt;script&gt;" in output and "configured-model &lt;img" in output
    assert "<script>" not in output and "<img src=x" not in output
    assert renderer.esc(renderer.tr(language, "review_note")) in output
    assert 'href="#review-summary"' in output and 'id="review-summary"' in output
    assert "120000" in output and "semantic_support" not in output
    assert projected["summary"]["citations"][0]["semantic_support"] == "unverified"


def test_v12_evidence_only_projection_drops_whole_review_even_if_malformed():
    original = fixture_v12()
    original["citation_review"] = {"private": "REVIEW_SECRET", "items": "malformed"}
    projected = renderer.project_report(original, "evidence-only")
    renderer.validate(projected)
    assert "citation_review" not in projected
    assert "REVIEW_SECRET" not in str(projected) and "REVIEW_SECRET" not in renderer.render(projected, ROOT)
    assert "citations" not in projected["claims"][0]
    assert projected["observations"][0]["citations"] and projected["evidence"][0]["excerpt"]


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version="1.1"),
    lambda d: d.update(mode="evidence-only"),
    lambda d: d["citation_review"].update(method="independent_verified"),
    lambda d: d["citation_review"].update(language="fr"),
    lambda d: d["citation_review"].update(model=" "),
    lambda d: d["citation_review"].update(generated_at=""),
    lambda d: d["citation_review"].update(available_targets=8),
    lambda d: d["citation_review"].update(available_targets=True),
    lambda d: d["citation_review"].update(reviewed_targets=0),
    lambda d: d["citation_review"].update(not_reviewed_targets=0),
    lambda d: d["citation_review"].update(selected_targets=0),
    lambda d: d["citation_review"].update(input_characters=0),
    lambda d: d["citation_review"].update(input_character_limit=120001),
    lambda d: d["citation_review"].update(capacity=24),
    lambda d: d["citation_review"]["items"][0].update(target_id="claim:C999"),
    lambda d: d["citation_review"]["items"][0].update(target_sha256="0" * 64),
    lambda d: d["citation_review"]["items"][0].update(relation="true"),
    lambda d: d["citation_review"]["items"][0].update(issues=["scope", "scope"]),
    lambda d: d["citation_review"]["items"][0].update(issues=["truth"]),
    lambda d: d["citation_review"]["items"][0].update(explanation=""),
    lambda d: d["citation_review"]["items"][0].update(explanation="https://unknown.example/fabricated"),
    lambda d: d["citation_review"]["items"][0].update(citations=[]),
    lambda d: d["citation_review"]["items"][0]["citations"][0].update(verification=None),
    lambda d: d["citation_review"]["items"][0]["citations"][0]["locator"].update(start=0),
    lambda d: d["summary"].update(text="Changed after review"),
    lambda d: d["evidence"][0].update(context="Changed source context"),
    lambda d: d.update(scope="Changed scope"),
    lambda d: d.update(topic="Changed topic"),
])
def test_v12_review_rejects_inconsistent_targets_metadata_and_advice(mutation):
    projected = renderer.project_report(fixture_v12(), "ai-summary")
    mutation(projected)
    with pytest.raises(ValueError):
        renderer.validate(projected)


def test_v12_review_rejects_duplicate_target_and_genuine_but_unselected_quote():
    original = fixture_v12()
    review = original["citation_review"]
    review["items"] *= 2
    review.update(reviewed_targets=2, not_reviewed_targets=5)
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "ai-summary"))
    original = fixture_v12()
    excerpt = original["evidence"][0]["excerpt"]
    quote = "2021"
    start = excerpt.index(quote)
    end = start + len(quote)
    citation = original["citation_review"]["items"][0]["citations"][0]
    citation.update(quote=quote, locator={"start": start, "end": end, "prefix": excerpt[max(0, start - 80):start],
                    "suffix": excerpt[end:end + 80], "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                    "match_count": 2, "coordinate_system": "unicode_codepoints"})
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "ai-summary"))


def test_v12_review_selection_capacity_and_input_budget_match_server():
    from truth_backend.models import Report
    from truth_backend.review_targets import selected_review_targets, target_sha256
    original = fixture_v12()
    original["depth"] = "brief"
    original["observations"] *= 40
    original = attach_review(original, [])
    targets = renderer.review_targets(renderer.project_report(original, "ai-summary"))
    skipped = targets[12]
    original["citation_review"]["items"] = [{"target_id": skipped["target_id"], "target_sha256": renderer.review_target_sha256(skipped),
        "relation": "unclear", "issues": [], "explanation": "Outside selected capacity", "citations": skipped["citations"]}]
    original["citation_review"].update(reviewed_targets=1, not_reviewed_targets=len(targets)-1)
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "ai-summary"))
    original["depth"] = "deep"
    for observation in original["observations"]:
        observation["text"] = "L" * 4900
    original = attach_review(original, [])
    projected = renderer.project_report(original, "ai-summary")
    renderer.validate(projected)
    model = Report.model_validate(original)
    selected = renderer.selected_review_targets(projected, "en")
    expected = selected_review_targets(model, "en")
    assert 0 < len(selected) < len(targets)
    assert [(t["target_id"], renderer.review_target_sha256(t)) for t in selected] == [(t.target_id, target_sha256(t)) for t in expected]
    assert original["citation_review"]["input_characters"] <= 120000


def test_standalone_renderer_cli_v12_has_no_backend_dependency(tmp_path):
    package = tmp_path / "report.json"
    output = tmp_path / "report.html"
    package.write_text(json.dumps(fixture_v12(), ensure_ascii=False), encoding="utf-8")
    subprocess.run([sys.executable, "-I", str(ROOT / "skills/tell-me-truth/scripts/render_report.py"), str(package),
                    "--output", str(output), "--mode", "ai-summary", "--language", "en"],
                   capture_output=True, text=True, encoding="utf-8", check=True)
    assert "AI citation relationship review" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("language,exact,gap,format_label", [
    ("zh-CN", "精确原句引用", "检索缺口与补搜", "CSV 表格"),
    ("en", "Exact quotations", "Retrieval gaps and follow-up searches", "CSV table"),
    ("ja", "精確な原文引用", "検索の不足と追加検索", "CSV 表"),
])
def test_v11_three_language_exact_quotes_metadata_and_gaps(language, exact, gap, format_label):
    projected = renderer.project_report(fixture_v11(), "evidence-only")
    renderer.validate(projected, language)
    output = renderer.render(projected, ROOT, language=language)
    assert exact in output and gap in output and format_label in output
    assert '<mark>2021 total = 20.</mark>' in output
    assert projected["evidence"][0]["excerpt"].endswith("\t")
    assert "1" * 64 in output and projected["evidence"][0]["excerpt_metadata"]["sha256"] in output
    assert '<script>' not in output and '<img src=x' not in output
    assert '&lt;img' in output
    assert '<script' not in output and 'fetch(' not in output
    assert renderer.esc(renderer.tr(language, "citation_note")) in output
    for secret in ("VERDICT_SECRET", "ANALYSIS_SECRET", "SUMMARY_SECRET", "NOTE_SECRET", "REASONING_SECRET", "PRIVATE_SECRET"):
        assert secret not in output and secret not in str(projected)


@pytest.mark.parametrize("field", ["claims", "timeline", "comparisons", "observations", "reasoning", "summary"])
def test_renderer_v11_factual_items_require_exact_citation(field):
    original = fixture_v11()
    item = original[field] if field == "summary" else original[field][0]
    item.pop("citations")
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "ai-summary"))


@pytest.mark.parametrize("mutation", [
    lambda citation: citation.update(quote="2021 total=20."),
    lambda citation: citation.update(evidence_id="E999"),
    lambda citation: citation.update(semantic_support="verified"),
    lambda citation: citation.update(verification="supported"),
    lambda citation: citation.update(locator=None),
    lambda citation: citation["locator"].update(start=0),
    lambda citation: citation["locator"].update(end=999),
    lambda citation: citation["locator"].update(prefix="invented"),
    lambda citation: citation["locator"].update(suffix="invented"),
    lambda citation: citation["locator"].update(match_count=1),
    lambda citation: citation["locator"].update(excerpt_sha256="0" * 64),
    lambda citation: citation["locator"].update(coordinate_system="utf16"),
    lambda citation: citation["locator"].update(start=True),
])
def test_renderer_rejects_forged_or_semantically_overstated_citations(mutation):
    original = fixture_v11()
    mutation(original["observations"][0]["citations"][0])
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "evidence-only"))


def test_renderer_old_reports_do_not_claim_exact_locator_verification():
    projected = renderer.project_report(fixture(), "evidence-only")
    renderer.validate(projected)
    output = renderer.render(projected, ROOT, language="en")
    assert renderer.tr("en", "citation_legacy") in output
    assert '<mark>' not in output
    assert 'Extract character positions' not in output


def test_renderer_legacy_quote_without_locator_is_checked_but_labeled_without_metadata():
    original = fixture()
    original["observations"][0]["citations"] = [{"evidence_id": "E1", "quote": "onerror"}]
    projected = renderer.project_report(original, "evidence-only")
    renderer.validate(projected)
    output = renderer.render(projected, ROOT, language="en")
    assert renderer.tr("en", "citation_no_locator") in output
    assert '<mark>onerror</mark>' in output
    original["observations"][0]["citations"][0]["quote"] = "fabricated"
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "evidence-only"))


def test_renderer_keeps_numeric_value_bound_to_retained_quote():
    original = fixture_v11()
    original["charts"][0]["points"][0]["value"] = 2021
    renderer.validate(renderer.project_report(original, "evidence-only"))
    original["charts"][0]["points"][0]["value"] = 200
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "evidence-only"))


def test_renderer_preserves_count_quote_positions_and_allows_scoped_empty_count():
    original = fixture_v11()
    point = original["charts"][0]["points"][0]
    quote = point["citations"][0]["quote"]
    point.update(value=1, calculation={"operation": "count", "source_quotes": [quote], "description": "Count only the exact quoted record; coverage remains unverified."})
    renderer.validate(renderer.project_report(original, "evidence-only"))
    point["citations"] = []
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "evidence-only"))
    point["calculation"]["source_quotes"] = []
    point["value"] = 0
    renderer.validate(renderer.project_report(original, "evidence-only"))


@pytest.mark.parametrize("mutation", [
    lambda data: data["evidence"][0].update(document_format="xlsx"),
    lambda data: data["evidence"][0].update(content_sha256="not-a-hash"),
    lambda data: data["evidence"][0]["excerpt_metadata"].update(sha256="0" * 64),
    lambda data: data["evidence"][0].update(source_family_method="verified_independent"),
    lambda data: data["evidence"][0].update(source_family_evidence_ids=["E999"]),
    lambda data: data["retrieval_gaps"][0].update(claim_id="C999"),
    lambda data: data["retrieval_gaps"][0].update(reason="false_claim"),
    lambda data: data["retrieval_gaps"][0].update(attempted="yes"),
    lambda data: data["search_log"][0].update(round="verified"),
    lambda data: data["search_log"][0].update(gap_claim_ids=["C999"]),
])
def test_renderer_metadata_rejects_invalid_hashes_or_invented_verification(mutation):
    original = fixture_v11()
    mutation(original)
    with pytest.raises(ValueError):
        renderer.validate(renderer.project_report(original, "evidence-only"))


def test_renderer_nested_projection_drops_judgment_side_channels():
    original = fixture_v11()
    original["observations"][0]["citations"][0]["private_judgment"] = "NESTED_SECRET"
    original["observations"][0]["citations"][0]["locator"]["private_judgment"] = "NESTED_SECRET"
    original["evidence"][0]["excerpt_metadata"]["private_judgment"] = "NESTED_SECRET"
    original["retrieval_gaps"][0]["private_judgment"] = "NESTED_SECRET"
    original["search_log"][0]["private_judgment"] = "NESTED_SECRET"
    projected = renderer.project_report(original, "evidence-only")
    renderer.validate(projected)
    assert "NESTED_SECRET" not in str(projected)
    assert "NESTED_SECRET" not in renderer.render(projected, ROOT)


def test_evidence_projection_drops_assessment_citations_and_keeps_neutral_quotations():
    original = fixture_v11()
    original["claims"][0]["citations"][0]["assessment_only"] = "ASSESSMENT_CITATION_PRIVATE"
    projected = renderer.project_report(original, "evidence-only")
    renderer.validate(projected)
    assert set(projected["claims"][0]) == {"id", "text", "kind"}
    assert "citations" not in projected["claims"][0]
    assert projected["observations"][0]["citations"] == original["observations"][0]["citations"]
    assert projected["evidence"][0]["excerpt"] == original["evidence"][0]["excerpt"]
    assert "summary" not in projected and "reasoning" not in projected
    assert "ASSESSMENT_CITATION_PRIVATE" not in str(projected)
    output = renderer.render(projected, ROOT, language="en")
    assert "ASSESSMENT_CITATION_PRIVATE" not in output
    assert "NEUTRAL_ANALYSIS" in output and "Exact quotations" in output
    assert original["claims"][0]["citations"][0]["assessment_only"] == "ASSESSMENT_CITATION_PRIVATE"


def test_renderer_unknown_label_fallback_is_escaped_without_format_evaluation():
    original = fixture()
    original["claims"][0]["kind"] = '<script>{unknown}</script>'
    original["evidence"][0]["source_type"] = '<img src=x onerror=alert(1)>'
    output = renderer.render(renderer.project_report(original, "evidence-only"), ROOT)
    assert '<script>' not in output and '<img src=x' not in output
    assert '&lt;script&gt;{unknown}&lt;/script&gt;' in output


def test_standalone_renderer_cli_v11_uses_only_local_material(tmp_path):
    package = tmp_path / "report.json"
    output = tmp_path / "report.html"
    package.write_text(json.dumps(fixture_v11(), ensure_ascii=False), encoding="utf-8")
    result = subprocess.run([sys.executable, "-I", str(ROOT / "skills/tell-me-truth/scripts/render_report.py"), str(package),
                             "--output", str(output), "--language", "en"], capture_output=True, text=True,
                            encoding="utf-8", check=True)
    assert "Saved" in result.stdout
    content = output.read_text(encoding="utf-8")
    assert "Exact quotations" in content and "Retrieval gaps" in content
    assert "SUMMARY_SECRET" not in content


class ReportTests(unittest.TestCase):
    def test_evidence_mode_never_serializes_analysis(self):
        original = fixture()
        projected = renderer.project_report(original, "evidence-only")
        renderer.validate(projected)
        output = renderer.render(projected, ROOT)
        for marker in ("VERDICT_SECRET", "ANALYSIS_SECRET", "SUMMARY_SECRET", "NOTE_SECRET", "REASONING_SECRET", "PRIVATE_SECRET"):
            self.assertNotIn(marker, str(projected))
            self.assertNotIn(marker, output)
        self.assertEqual(original["links"][0]["relation"], "contradicts")
        self.assertEqual(projected["depth"], "deep")
        self.assertIn("NEUTRAL_ANALYSIS", output)

    def test_html_and_attributes_escape_external_content(self):
        projected = renderer.project_report(fixture(), "ai-summary")
        output = renderer.render(projected, ROOT)
        self.assertNotIn("<script>", output)
        self.assertNotIn("<img src=x", output)
        self.assertIn("&lt;script&gt;", output)

    def test_missing_is_not_zero_and_negative_bars_keep_valid_geometry(self):
        report = renderer.project_report(fixture(), "evidence-only")
        svg = renderer.chart_svg(report["charts"][0])
        self.assertIn("缺失", svg)
        import re
        heights = re.findall(r'<rect[^>]+height="([^"]+)"', svg)
        self.assertEqual(len(heights), 2)
        self.assertTrue(all(float(height) > 0 for height in heights))

    def test_fabricated_citation_and_unsafe_url_rejected(self):
        report = renderer.project_report(fixture(), "evidence-only")
        report["charts"][0]["points"][0]["evidence_ids"] = ["E999"]
        with self.assertRaises(ValueError):
            renderer.validate(report)
        report = renderer.project_report(fixture(), "evidence-only")
        report["evidence"][0]["url"] = "javascript:alert(1)"
        with self.assertRaises(ValueError):
            renderer.validate(report)

    def test_nonfinite_chart_value_and_circular_reasoning_rejected(self):
        report = renderer.project_report(fixture(), "ai-summary")
        report["reasoning"][0]["premise_ids"] = ["R1"]
        with self.assertRaises(ValueError):
            renderer.validate(report)
        report = renderer.project_report(fixture(), "ai-summary")
        report["charts"][0]["points"][0]["value"] = float("nan")
        with self.assertRaises(ValueError):
            renderer.validate(report)

    def test_derived_counts_are_bound_to_existing_unique_entries(self):
        report = renderer.project_report(fixture(), "evidence-only")
        report["charts"][0]["points"] = [{"label": "count", "value": 1, "evidence_ids": ["E1"], "calculation": {"operation": "count", "source_quotes": ["onerror"], "description": "只统计所引摘录中的这一条记录"}}]
        renderer.validate(report)
        report["charts"][0]["points"][0]["calculation"]["source_quotes"] = ["fabricated"]
        with self.assertRaises(ValueError):
            renderer.validate(report)

    def test_shared_analysis_requires_actual_claims_and_evidence(self):
        report = renderer.project_report(fixture(), "evidence-only")
        report["observations"][0]["claim_ids"] = ["C999"]
        with self.assertRaises(ValueError):
            renderer.validate(report)

    def test_three_languages_have_accessible_maps_without_judgment_leaks(self):
        for language, label in [("zh-CN", "证据关系图"), ("en", "Evidence map"), ("ja", "証拠の関連図")]:
            report = renderer.project_report(fixture(), "evidence-only")
            report["language"] = language
            output = renderer.render(report, ROOT, language=language)
            self.assertIn(f'<html lang="{language}">', output)
            self.assertIn(label, output)
            self.assertIn('aria-labelledby="evidence-map-title evidence-map-desc"', output)
            self.assertIn('id="analysis-observation-0"', output)
            for secret in ("VERDICT_SECRET", "SUMMARY_SECRET", "REASONING_SECRET"):
                self.assertNotIn(secret, output)


if __name__ == "__main__":
    unittest.main()
