"""Provider-only strict generation schema; legacy parsing remains compatible."""
import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from truth_backend import providers
from truth_backend.models import AIConfig, Analysis, Evidence, Plan, Report
from truth_backend.reports import apply_analysis
from truth_backend.security import Fetched, ServiceError


def capture_prompt(monkeypatch, schema=Analysis, *, flag=True, response=None, catalog=None):
    if response is None:
        response = ({} if schema is Analysis else
                    {"claims": [{"text": "A claim", "kind": "fact"}],
                     "queries": [{"query": "Original data", "intent": "neutral"}], "scope": "Test scope"})
    envelope = {"choices": [{"message": {"content": json.dumps(response)}}]}
    transport = AsyncMock(return_value=Fetched("https://compatible.example/v1/chat/completions",
                                               json.dumps(envelope).encode(), "application/json", 200))
    monkeypatch.setattr(providers, "pinned_request", transport)
    data = {"topic": "A claim"}
    if flag is not None:
        data["require_exact_citations"] = flag
    if catalog is not None:
        data["quote_catalog"] = catalog
    parsed = asyncio.run(providers.complete(
        AIConfig(base_url="https://compatible.example/v1", model="mock", api_key="synthetic-key"),
        "Use the supplied evidence.", data, schema))
    payload = transport.call_args.kwargs["json_body"]
    prompt_schema = json.loads(payload["messages"][0]["content"].split("JSON Schema：\n", 1)[1])
    return prompt_schema, parsed, payload


@pytest.mark.parametrize("definition", ["Assessment", "AnalysisObservation", "AnalysisTimelineItem",
                                        "AnalysisReasoning", "AnalysisSummary", "AnalysisComparison"])
def test_every_factual_analysis_object_requires_a_nonempty_citation_array(monkeypatch, definition):
    prompt, parsed, payload = capture_prompt(monkeypatch)
    obj = prompt["$defs"][definition]
    assert "citations" in obj["required"]
    assert obj["properties"]["citations"]["minItems"] == 1
    assert obj["properties"]["citations"]["maxItems"] == 24
    assert obj["properties"]["citations"]["items"] == {"$ref": "#/$defs/AnalysisQuoteReference"}
    assert isinstance(parsed, Analysis)
    assert "response_format" not in payload
    assert "synthetic-key" not in json.dumps(payload)


def test_chart_source_quote_and_derived_count_contract_are_not_overconstrained(monkeypatch):
    original = Analysis.model_json_schema()
    prompt, _, _ = capture_prompt(monkeypatch)
    point = prompt["$defs"]["VerifiedChartPoint"]
    assert point == original["$defs"]["VerifiedChartPoint"]
    assert "citations" not in point["required"] and "minItems" not in point["properties"]["citations"]
    assert prompt["$defs"]["Calculation"] == original["$defs"]["Calculation"]
    assert prompt["$defs"]["AnalysisQuoteReference"] == original["$defs"]["AnalysisQuoteReference"]


def test_generation_schema_is_a_copy_and_does_not_mutate_class_or_input(monkeypatch):
    original = deepcopy(Analysis.model_json_schema())
    strict, _, _ = capture_prompt(monkeypatch)
    assert Analysis.model_json_schema() == original
    legacy, _, _ = capture_prompt(monkeypatch, flag=False)
    assert legacy == original
    assert strict != original
    assert all("citations" not in original["$defs"][name]["required"] for name in
               ("Assessment", "AnalysisObservation", "AnalysisTimelineItem", "AnalysisReasoning", "AnalysisSummary", "AnalysisComparison"))


@pytest.mark.parametrize("flag", [None, False, "true", 1])
def test_direct_or_nonboolean_analysis_calls_keep_the_legacy_schema(monkeypatch, flag):
    prompt, parsed, _ = capture_prompt(monkeypatch, flag=flag)
    assert prompt == Analysis.model_json_schema() and isinstance(parsed, Analysis)


def test_planning_schema_does_not_change_even_with_the_strict_analysis_flag(monkeypatch):
    prompt, parsed, _ = capture_prompt(monkeypatch, Plan)
    assert prompt == Plan.model_json_schema() and isinstance(parsed, Plan)


def test_strict_prompt_does_not_replace_server_citation_validation_or_legacy_parser(monkeypatch):
    response = {"observations": [{"kind": "data", "text": "The excerpt records 17.",
                                  "claim_ids": ["C1"], "evidence_ids": ["E1"]}]}
    _, parsed, _ = capture_prompt(monkeypatch, response=response)
    assert parsed.observations[0].citations == []  # Parsing stays backward compatible.
    report = Report(schema_version="1.1", topic="Check a count", mode="evidence-only", generated_at="2026-10-10T00:00:00Z",
                    scope="Original record", claims=[{"id": "C1", "text": "There are 17 entries.", "kind": "fact"}],
                    evidence=[Evidence(id="E1", title="Record", url="https://example.com/record", publisher="example.com",
                                       retrieved_at="2026-10-10T00:00:00Z", content_kind="full_text", excerpt="The record contains 17 entries.",
                                       source_family="example.com", status="retrieved")])
    with pytest.raises(ServiceError) as caught:
        apply_analysis(report, parsed, require_citations=True)
    assert caught.value.code == "invalid_evidence_reference"


def quote_catalog():
    return [{"quote_id": "E1Q1", "evidence_id": "E1", "quote": "  Original sentence with whitespace.\n"},
            {"quote_id": "E2Q1", "evidence_id": "E2", "quote": "Another original sentence.😀"},
            {"quote_id": "E1Q2", "evidence_id": "E1", "quote": "A second passage in the first source."}]


def test_valid_catalog_changes_only_model_reference_properties_to_issued_quote_ids(monkeypatch):
    catalog = quote_catalog()
    prompt, parsed, payload = capture_prompt(monkeypatch, catalog=catalog)
    reference = prompt["$defs"]["AnalysisQuoteReference"]
    original = Analysis.model_json_schema()["$defs"]["AnalysisQuoteReference"]
    assert set(reference["properties"]) == {"evidence_id", "quote_id"}
    assert reference["properties"]["evidence_id"] == original["properties"]["evidence_id"]
    assert reference["properties"]["quote_id"]["type"] == "string"
    assert reference["properties"]["quote_id"]["enum"] == ["E1Q1", "E2Q1", "E1Q2"]
    assert reference["required"] == ["evidence_id", "quote_id"] and reference["additionalProperties"] is False
    assert isinstance(parsed, Analysis)
    assert json.loads(payload["messages"][1]["content"])["quote_catalog"] == catalog
    assert "Original sentence" not in json.dumps(reference)
    assert prompt["$defs"]["AnalysisObservation"]["properties"]["citations"]["minItems"] == 1


def test_quote_id_only_model_response_still_parses_as_analysis_for_server_resolution(monkeypatch):
    response = {"observations": [{"kind": "data", "text": "The original record needs comparison.",
                                  "claim_ids": ["C1"], "evidence_ids": ["E1"],
                                  "citations": [{"evidence_id": "E1", "quote_id": "E1Q1"}]}]}
    _, parsed, _ = capture_prompt(monkeypatch, catalog=quote_catalog(), response=response)
    citation = parsed.observations[0].citations[0]
    assert citation.quote_id == "E1Q1" and citation.quote == ""


@pytest.mark.parametrize("catalog", [
    [], {}, "not-a-catalog", [{"quote_id": "E1Q1", "evidence_id": "E1"}],
    [{"quote_id": 1, "evidence_id": "E1", "quote": "Original"}],
    [{"quote_id": " E1Q1", "evidence_id": "E1", "quote": "Original"}],
    [{"quote_id": "E1Q0", "evidence_id": "E1", "quote": "Original"}],
    [{"quote_id": "E1Q1", "evidence_id": "E2", "quote": "Original"}],
    [{"quote_id": "E1Q1", "evidence_id": "E1", "quote": " \n\t "}],
    [{"quote_id": "E1Q1", "evidence_id": "E1", "quote": 123}],
    [{"quote_id": "E1Q1", "evidence_id": "E1", "quote": "x" * 2001}],
    [{"quote_id": "E1Q1", "evidence_id": "E1", "quote": "Original", "unexpected": "field"}],
    [{"quote_id": "E1Q1", "evidence_id": "E1", "quote": "Original"}, {"quote_id": "E1Q1", "evidence_id": "E1", "quote": "Duplicate ID"}],
    [{"quote_id": "E1Q1", "evidence_id": "E1", "quote": "Original"}, None],
])
def test_invalid_catalog_never_generates_partial_or_malformed_enum(monkeypatch, catalog):
    prompt, _, _ = capture_prompt(monkeypatch, catalog=catalog)
    assert prompt == providers._prompt_schema(Analysis, True)
    assert prompt["$defs"]["AnalysisQuoteReference"] == Analysis.model_json_schema()["$defs"]["AnalysisQuoteReference"]


def test_catalog_size_and_identifier_length_have_explicit_bounds():
    assert providers._catalog_quote_ids([{"quote_id": "E1Q" + str(index), "evidence_id": "E1", "quote": "Original"} for index in range(1, 2402)]) is None
    assert providers._catalog_quote_ids([{"quote_id": "E1Q" + "1" * 100, "evidence_id": "E1", "quote": "Original"}]) is None


def test_catalog_schema_is_copied_and_never_changes_class_or_later_legacy_calls(monkeypatch):
    original, catalog = deepcopy(Analysis.model_json_schema()), quote_catalog()
    saved_catalog = deepcopy(catalog)
    prompt, _, _ = capture_prompt(monkeypatch, catalog=catalog)
    assert Analysis.model_json_schema() == original and catalog == saved_catalog
    legacy, _, _ = capture_prompt(monkeypatch, flag=False)
    assert legacy == original
    assert "quote" in legacy["$defs"]["AnalysisQuoteReference"]["properties"]
    assert "quote" not in prompt["$defs"]["AnalysisQuoteReference"]["properties"]


def test_catalog_selection_is_independent_of_nonempty_citation_array_flag(monkeypatch):
    prompt, _, _ = capture_prompt(monkeypatch, flag=False, catalog=quote_catalog())
    assert prompt["$defs"]["AnalysisQuoteReference"]["properties"]["quote_id"]["enum"] == ["E1Q1", "E2Q1", "E1Q2"]
    assert "minItems" not in prompt["$defs"]["AnalysisObservation"]["properties"]["citations"]


def test_catalog_is_not_applied_to_a_planning_request(monkeypatch):
    prompt, _, _ = capture_prompt(monkeypatch, Plan, catalog=quote_catalog())
    assert prompt == Plan.model_json_schema()


def test_legacy_quote_response_without_catalog_remains_parseable(monkeypatch):
    response = {"observations": [{"kind": "data", "text": "Compare the original record.", "claim_ids": ["C1"], "evidence_ids": ["E1"],
                                  "citations": [{"evidence_id": "E1", "quote": "Original quoted text."}]}]}
    prompt, parsed, _ = capture_prompt(monkeypatch, response=response)
    assert prompt["$defs"]["AnalysisQuoteReference"] == Analysis.model_json_schema()["$defs"]["AnalysisQuoteReference"]
    assert parsed.observations[0].citations[0].quote == "Original quoted text."
    assert parsed.observations[0].citations[0].quote_id is None
