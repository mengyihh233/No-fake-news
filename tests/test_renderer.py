"""Behavioral invariants for portable, user-selectable evidence reports."""
import importlib.util
from pathlib import Path
import unittest


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
