import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from truth_backend import providers, review
from truth_backend.models import Analysis, CitationReview, Report, ReviewRequest
from truth_backend.reports import apply_analysis, public_report, validate_references
from truth_backend.review import ReviewResponse, ReviewSelection
from truth_backend.review_targets import (REVIEW_CAPACITIES, REVIEW_INPUT_CHARACTER_LIMIT, all_review_targets,
                                         build_review_payload, canonical_numbers, review_input_characters,
                                         selected_review_targets, target_sha256)
from truth_backend.security import ServiceError


QUOTE = "年度记录中，2021 年的总量为 20，口径只包含已登记项目。"


def reviewed_source_report(depth="standard"):
    report = Report(schema_version="1.1", topic="年度总量是否为 20", mode="ai-summary", depth=depth,
                    language="zh-CN", generated_at="2026-10-10T00:00:00Z", scope="已登记项目的年度记录",
                    claims=[{"id": "C1", "text": "年度总量为 20。", "kind": "fact"}],
                    evidence=[{"id": "E1", "title": "年度记录", "url": "https://example.com/records",
                               "publisher": "example.com", "retrieved_at": "2026-10-10T00:00:00Z",
                               "content_kind": "full_text", "excerpt": "定义与边界。\n" + QUOTE + "\n后续限定条件。",
                               "context": "仅登记项目，不包括未登记对象。", "source_family": "example.com", "status": "retrieved"}])
    citations = [{"evidence_id": "E1", "quote": QUOTE}]
    analysis = Analysis.model_validate({
        "claim_assessments": [{"claim_id": "C1", "verdict": "有条件成立", "analysis": "需核对登记口径。", "citations": citations}],
        "observations": [{"kind": "data", "text": "摘录包含年度记录的总量。", "claim_ids": ["C1"], "evidence_ids": ["E1"], "citations": citations}],
        "timeline": [{"date": "2021", "title": "年度记录", "detail": "该年记录列出 20。", "evidence_ids": ["E1"], "citations": citations}],
        "comparisons": [{"case": "年度口径比较", "date": "2021", "similarities": "登记项目", "differences": "未登记对象范围不同",
                         "limits": "仅当前摘录", "evidence_ids": ["E1"], "citations": citations}],
        "charts": [{"title": "年度总量", "unit": "项", "kind": "bar", "note": "仅登记对象", "points": [
            {"label": "2021", "value": 20, "evidence_ids": ["E1"], "source_quote": QUOTE}]}],
        "reasoning": [{"id": "R1", "premise_ids": ["E1"], "claim_id": "C1", "text": "口径内记录有该数值。", "kind": "data", "citations": citations}],
        "summary": {"text": "只在登记口径内讨论总量。", "verdict": "有条件成立", "caveats": ["不能外推全部对象"],
                    "evidence_ids": ["E1"], "citations": citations},
    })
    return apply_analysis(report, analysis)


def choice(target="summary", **kwargs):
    return ReviewSelection(target_id=target, relation="partial", issues=["scope"],
                           explanation="引用限定了登记对象，不能推及所有对象。", quotation_indices=[0], **kwargs)


def install_model(monkeypatch, items=None):
    model = AsyncMock(return_value=ReviewResponse(items=items if items is not None else [choice()]))
    monkeypatch.setattr(review, "complete", model)
    monkeypatch.setattr(review, "resolve_ai", lambda config: config)
    searching, fetching = AsyncMock(), AsyncMock()
    monkeypatch.setattr(providers, "search_web", searching)
    monkeypatch.setattr(providers, "fetch_evidence", fetching)
    return model, searching, fetching


def run_review(report, language="en"):
    return asyncio.run(review.review_report(ReviewRequest(report=report, ai={"model": "mock-review-model", "api_key": "dummy-ai-secret"}, language=language)))


@pytest.mark.parametrize("language,marker", [("zh-CN", "简体中文"), ("en", "OUTPUT LANGUAGE"), ("ja", "出力言語")])
def test_one_advisory_call_preserves_original_material_and_copies_only_selected_quotes(monkeypatch, language, marker):
    report = reviewed_source_report()
    original = deepcopy(report.model_dump())
    before = public_report(report)
    model, searching, fetching = install_model(monkeypatch)
    output = run_review(report, language)
    assert report.model_dump() == original
    assert output["schema_version"] == "1.2" and output["language"] == "zh-CN"
    metadata = output["citation_review"]
    assert metadata["language"] == language and metadata["model"] == "mock-review-model"
    assert metadata["method"] == "ai_advisory" and metadata["available_targets"] == 7
    assert metadata["selected_targets"] == 7 and metadata["reviewed_targets"] == 1 and metadata["not_reviewed_targets"] == 6
    assert metadata["items"][0]["citations"] == output["summary"]["citations"]
    assert metadata["items"][0]["citations"][0]["semantic_support"] == "unverified"
    assert {key: value for key, value in output.items() if key not in {"schema_version", "citation_review"}} == {
        key: value for key, value in before.items() if key not in {"schema_version", "citation_review"}}
    assert model.await_count == 1 and marker in model.await_args.args[1]
    payload = model.await_args.args[2]
    assert payload["source_context"][0]["excerpt"] == report.evidence[0].excerpt
    assert payload["targets"][0]["target_id"] == "summary"
    assert payload["targets"][0]["quotations"] == [{"evidence_id": "E1", "quote": QUOTE}]
    assert metadata["input_characters"] == review_input_characters(payload) <= REVIEW_INPUT_CHARACTER_LIMIT
    assert "dummy-ai-secret" not in json.dumps(payload) and "dummy-ai-secret" not in json.dumps(output)
    searching.assert_not_awaited()
    fetching.assert_not_awaited()
    validate_references(Report.model_validate(output))


def test_empty_model_selection_is_explicitly_all_unreviewed_not_fake_success(monkeypatch):
    install_model(monkeypatch, [])
    output = run_review(reviewed_source_report())
    metadata = output["citation_review"]
    assert metadata["items"] == [] and metadata["reviewed_targets"] == 0
    assert metadata["not_reviewed_targets"] == metadata["available_targets"] == 7


@pytest.mark.parametrize("version,mode", [("1.0", "ai-summary"), ("1.1", "evidence-only"), ("1.2", "evidence-only")])
@pytest.mark.parametrize("language,fragment", [("zh-CN", "仅适用"), ("en", "requires"), ("ja", "のみ対応")])
def test_unavailable_reports_never_call_model(monkeypatch, version, mode, language, fragment):
    report = reviewed_source_report().model_copy(update={"schema_version": version, "mode": mode})
    model, _, _ = install_model(monkeypatch)
    with pytest.raises(ServiceError) as error:
        run_review(report, language)
    assert error.value.code == "review_not_available" and fragment in error.value.message
    model.assert_not_awaited()


def test_no_exact_target_rejects_without_creating_missing_citations(monkeypatch):
    report = reviewed_source_report()
    report = report.model_copy(update={"summary": None, "observations": [], "timeline": [], "charts": [], "comparisons": [], "reasoning": []})
    report.claims[0].verdict, report.claims[0].analysis, report.claims[0].citations = None, None, []
    model, _, _ = install_model(monkeypatch)
    with pytest.raises(ServiceError) as error:
        run_review(report)
    assert error.value.code == "no_review_targets"
    model.assert_not_awaited()


def expanded_report(depth):
    report = reviewed_source_report(depth)
    report.observations = [report.observations[0].model_copy(deep=True) for _ in range(40)]
    report.timeline = [report.timeline[0].model_copy(deep=True) for _ in range(30)]
    report.comparisons = [report.comparisons[0].model_copy(deep=True) for _ in range(10)]
    report.charts[0].points = [report.charts[0].points[0].model_copy(deep=True) for _ in range(40)]
    report.reasoning = [report.reasoning[0].model_copy(update={"id": f"R{number}"}, deep=True) for number in range(1, 31)]
    return report


@pytest.mark.parametrize("depth,capacity", [("brief", 12), ("standard", 24), ("deep", 40)])
def test_depth_capacity_is_real_and_categories_are_not_starved(monkeypatch, depth, capacity):
    report = expanded_report(depth)
    model, _, _ = install_model(monkeypatch)
    output = run_review(report)
    targets = model.await_args.args[2]["targets"]
    assert len(targets) == capacity == REVIEW_CAPACITIES[depth]
    assert [target["target_id"] for target in targets[:7]] == ["summary", "observation:1", "claim:C1", "timeline:1", "chart:1:point:1", "comparison:1", "reasoning:R1"]
    assert output["citation_review"]["available_targets"] == 152
    assert output["citation_review"]["not_reviewed_targets"] == 151


def test_input_budget_skips_oversized_target_without_truncating_any_source_or_statement(monkeypatch):
    report = reviewed_source_report()
    # Many unique exact quotes can fit one target's storage schema but exceed the
    # model payload cap. Other small targets must remain reviewable.
    excerpt = "x" * 5000
    report.evidence[0].excerpt = excerpt
    report.evidence[0].excerpt_metadata = None
    from truth_backend.citations import locate_quote
    from truth_backend.models import QuoteCitation
    small = locate_quote(QuoteCitation(evidence_id="E1", quote="x"), {"E1": report.evidence[0]})
    big = [locate_quote(QuoteCitation(evidence_id="E1", quote="x" * size), {"E1": report.evidence[0]}) for size in range(1901, 2001)]
    report.summary = None
    report.observations = []
    report.timeline = []
    report.comparisons = []
    report.reasoning = []
    point = report.charts[0].points[0]
    point.value, point.citations = None, big
    report.claims[0].citations = [small]
    model, _, _ = install_model(monkeypatch, [choice("claim:C1")])
    output = run_review(report)
    payload = model.await_args.args[2]
    assert [target["target_id"] for target in payload["targets"]] == ["claim:C1"]
    assert payload["source_context"][0]["excerpt"] == excerpt
    assert output["charts"][0]["points"][0]["citations"] == [citation.model_dump() for citation in big]
    assert output["citation_review"]["available_targets"] == 2
    assert output["citation_review"]["selected_targets"] == 1 and output["citation_review"]["not_reviewed_targets"] == 1
    assert review_input_characters(payload) <= 120000


@pytest.mark.parametrize("mutation", [
    lambda items: items.append(deepcopy(items[0])),
    lambda items: setattr(items[0], "target_id", "observation:999"),
    lambda items: setattr(items[0], "quotation_indices", [99]),
    lambda items: setattr(items[0], "quotation_indices", [0, 0]),
    lambda items: setattr(items[0], "issues", ["scope", "scope"]),
    lambda items: setattr(items[0], "explanation", "Read https://invented.example/fake"),
    lambda items: setattr(items[0], "explanation", "Read HTTPS://invented.example/fake"),
])
def test_invalid_model_selection_is_rejected_once_without_changing_report(monkeypatch, mutation):
    report = reviewed_source_report()
    before = deepcopy(report.model_dump())
    items = [choice()]
    mutation(items)
    model, _, _ = install_model(monkeypatch, items)
    with pytest.raises(ServiceError) as error:
        run_review(report)
    assert error.value.code == "invalid_citation_review"
    assert model.await_count == 1 and report.model_dump() == before


@pytest.mark.parametrize("indices", [[], [-1], [True], [1.5], [100]])
def test_response_schema_rejects_missing_or_non_integer_quotation_indices(indices):
    data = choice().model_dump()
    data["quotation_indices"] = indices
    with pytest.raises(ValidationError):
        ReviewResponse.model_validate({"items": [data]})


@pytest.mark.parametrize("extra", ["quote", "citations", "locator", "target_sha256"])
def test_model_cannot_inject_source_text_or_server_generated_verification(extra):
    data = choice().model_dump()
    data[extra] = "invented"
    with pytest.raises(ValidationError):
        ReviewResponse.model_validate({"items": [data]})


def test_upstream_error_is_not_retried_and_original_report_survives(monkeypatch):
    report = reviewed_source_report()
    original = deepcopy(report.model_dump())
    model, _, _ = install_model(monkeypatch)
    model.side_effect = ServiceError("invalid_model_output", "Safe format failure")
    with pytest.raises(ServiceError):
        run_review(report)
    assert model.await_count == 1 and report.model_dump() == original


@pytest.mark.parametrize("mutation", [
    lambda report: setattr(report.citation_review, "available_targets", 999),
    lambda report: setattr(report.citation_review, "selected_targets", 1),
    lambda report: setattr(report.citation_review, "reviewed_targets", 0),
    lambda report: setattr(report.citation_review, "not_reviewed_targets", 0),
    lambda report: setattr(report.citation_review, "capacity", 12),
    lambda report: setattr(report.citation_review, "input_characters", 1),
    lambda report: setattr(report.citation_review.items[0], "target_sha256", "0" * 64),
    lambda report: setattr(report.citation_review.items[0], "target_id", "claim:C1"),
    lambda report: setattr(report.citation_review.items[0].citations[0].locator, "start", 0),
    lambda report: setattr(report.citation_review.items[0], "explanation", "https://invented.example/report"),
    lambda report: report.citation_review.items[0].citations.append(report.citation_review.items[0].citations[0].model_copy(deep=True)),
    lambda report: setattr(report.summary, "text", "Changed conclusion using unchanged quotes"),
    lambda report: setattr(report, "topic", "Changed topic"),
    lambda report: setattr(report, "scope", "Changed scope"),
    lambda report: setattr(report.evidence[0], "context", "Changed source context"),
    lambda report: setattr(report.evidence[0], "title", "Changed source title"),
])
def test_import_rejects_stale_or_forged_review_before_export_or_new_ai_call(monkeypatch, mutation):
    model, _, _ = install_model(monkeypatch)
    report = Report.model_validate(run_review(reviewed_source_report()))
    mutation(report)
    with pytest.raises(ServiceError):
        public_report(report)
    with pytest.raises(ServiceError):
        validate_references(report)
    with pytest.raises(ServiceError):
        run_review(report)
    assert model.await_count == 1


def test_public_export_rejects_structurally_bad_raw_review_instead_of_forwarding_it(monkeypatch):
    install_model(monkeypatch)
    raw = run_review(reviewed_source_report())
    raw["citation_review"]["items"][0]["citations"] = []
    with pytest.raises(ServiceError) as error:
        public_report(raw)
    assert error.value.code == "invalid_citation_review"


def test_evidence_projection_removes_entire_review_and_new_analysis_clears_it(monkeypatch):
    install_model(monkeypatch)
    report = Report.model_validate(run_review(reviewed_source_report()))
    projected = public_report(report, "evidence-only")
    assert "citation_review" not in projected and "summary" not in projected and "reasoning" not in projected
    updated = apply_analysis(report, Analysis(summary={"text": "New summary", "verdict": "Needs review", "evidence_ids": ["E1"],
        "citations": [{"evidence_id": "E1", "quote": QUOTE}]}), judgment_only=True)
    assert updated.schema_version == "1.2" and updated.citation_review is None


def test_schema_1_2_retains_exact_citation_rules_even_without_optional_review():
    report = reviewed_source_report().model_copy(update={"schema_version": "1.2"})
    report.observations[0].citations = []
    with pytest.raises(ServiceError):
        validate_references(report)


def test_hash_numeric_normalization_survives_javascript_integer_roundtrip():
    assert canonical_numbers({"a": 20.0, "b": -0.0, "c": 1e-7, "d": True}) == {"a": "20", "b": "0", "c": "0.0000001", "d": True}
    report = reviewed_source_report()
    first = next(target for target in all_review_targets(report) if target.target_id.startswith("chart:"))
    raw = report.model_dump()
    raw["charts"][0]["points"][0]["value"] = 20
    second = next(target for target in all_review_targets(Report.model_validate(raw)) if target.target_id.startswith("chart:"))
    assert target_sha256(first) == target_sha256(second)


def test_review_payload_context_is_deduplicated_and_input_cap_accounts_for_unicode():
    report = reviewed_source_report()
    selected = selected_review_targets(report, "en")
    payload = build_review_payload(selected, report.depth, "en")
    assert len(payload["source_context"]) == 1
    assert review_input_characters(payload) == len(json.dumps(payload, ensure_ascii=False))
    assert review_input_characters(build_review_payload(selected, report.depth, "zh-CN")) == review_input_characters(payload) + 3


def test_all_targets_over_input_limit_fail_before_model_without_truncating_original(monkeypatch):
    report = reviewed_source_report()
    report = report.model_copy(update={"summary": None, "observations": [], "timeline": [], "comparisons": [], "reasoning": []})
    report.claims[0].verdict, report.claims[0].analysis, report.claims[0].citations = None, None, []
    from truth_backend.citations import locate_quote
    from truth_backend.models import QuoteCitation
    report.evidence[0].excerpt, report.evidence[0].excerpt_metadata = "x" * 5000, None
    point = report.charts[0].points[0]
    point.value = None
    point.citations = [locate_quote(QuoteCitation(evidence_id="E1", quote="x" * length), {"E1": report.evidence[0]})
                       for length in range(1901, 2001)]
    original = deepcopy(report.model_dump())
    model, _, _ = install_model(monkeypatch)
    with pytest.raises(ServiceError) as error:
        run_review(report)
    assert error.value.code == "review_input_limit" and report.model_dump() == original
    model.assert_not_awaited()


def test_api_review_returns_schema_1_2_and_localized_unavailability(monkeypatch):
    from fastapi.testclient import TestClient
    import app
    model, _, _ = install_model(monkeypatch)
    client = TestClient(app.app, base_url="http://127.0.0.1")
    report = reviewed_source_report()
    response = client.post("/api/review", json={"report": report.model_dump(by_alias=True), "ai": {"model": "mock-review-model"}, "language": "en"})
    assert response.status_code == 200, response.text
    assert response.json()["schema_version"] == "1.2" and response.json()["citation_review"]["reviewed_targets"] == 1
    report.mode = "evidence-only"
    response = client.post("/api/review", json={"report": report.model_dump(by_alias=True), "language": "ja"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "review_not_available"
    assert "のみ対応" in response.json()["error"]["message"]
    assert model.await_count == 1


def test_api_summarize_validates_old_review_then_clears_advice_and_preserves_base_analysis(monkeypatch):
    from fastapi.testclient import TestClient
    import app
    from truth_backend import research
    install_model(monkeypatch)
    reviewed = run_review(reviewed_source_report())
    completion = AsyncMock(return_value=Analysis(summary={"text": "Replacement judgment", "verdict": "Conditional",
        "evidence_ids": ["E1"], "citations": [{"evidence_id": "E1", "quote": QUOTE}]}))
    monkeypatch.setattr(research, "complete", completion)
    client = TestClient(app.app, base_url="http://127.0.0.1")
    response = client.post("/api/summarize", json={"report": reviewed, "language": "en", "ai": {"model": "mock-review-model"}})
    assert response.status_code == 200, response.text
    output = response.json()
    assert output["citation_review"] is None and output["summary"]["text"] == "Replacement judgment"
    for section in ("evidence", "observations", "timeline", "charts", "comparisons"):
        assert output[section] == reviewed[section]
    assert completion.await_count == 1
    reviewed["citation_review"]["items"][0]["target_sha256"] = "0" * 64
    response = client.post("/api/summarize", json={"report": reviewed, "language": "en", "ai": {"model": "mock-review-model"}})
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_citation_review"
    assert completion.await_count == 1
