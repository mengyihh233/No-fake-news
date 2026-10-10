from truth_backend.models import Evidence
from truth_backend.quote_candidates import quote_candidates


def source(eid, text):
    return Evidence(id=eid, title="Record", url="https://example.org/record", publisher="records",
                    retrieved_at="2026-10-10T00:00:00Z", content_kind="full_text", excerpt=text,
                    source_family="example.org", status="retrieved")


def test_fragments_are_original_bounded_deterministic_and_preserve_whitespace():
    text = "  😀 Original record.\n" + "A sentence about events and limitations. " * 100 + "\t"
    catalog = quote_candidates([source("E1", text)])
    assert catalog == quote_candidates([source("E1", text)])
    assert "".join(item["quote"] for item in catalog) == text
    assert all(0 < len(item["quote"]) <= 700 and item["quote"] in text for item in catalog)
    assert len({item["quote_id"] for item in catalog}) == len(catalog)
    assert all(item["evidence_id"] == "E1" for item in catalog)


def test_omission_and_privacy_markers_are_never_quotable_or_joined():
    text = "Before omission. […] After omission. [REDACTED CREDENTIAL] Unredacted record."
    catalog = quote_candidates([source("E1", text)])
    assert [item["quote"] for item in catalog] == ["Before omission. ", " After omission. ", " Unredacted record."]
    assert all("[…]" not in item["quote"] and "[REDACTED CREDENTIAL]" not in item["quote"] for item in catalog)


def test_missing_material_produces_no_catalog_and_source_ids_stay_distinct():
    catalog = quote_candidates([source("E1", ""), source("E2", "原文。"), source("E3", "原文。")])
    assert [item["quote_id"] for item in catalog] == ["E2Q1", "E3Q1"]


def test_long_unbroken_cjk_text_is_split_without_changes():
    text = "原始資料" * 1000
    catalog = quote_candidates([source("E1", text)])
    assert "".join(item["quote"] for item in catalog) == text
    assert max(len(item["quote"]) for item in catalog) <= 700
