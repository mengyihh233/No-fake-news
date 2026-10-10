
from truth_backend.models import Claim, Evidence
from truth_backend.provenance import canonical_url_key, group_source_families
from truth_backend.retrieval import identify_retrieval_gaps


def test_canonical_url_keeps_distinct_nontracking_raw_query_bytes():
    assert canonical_url_key("https://example.com/?key=%FF") != canonical_url_key("https://example.com/?key=%FE")
    assert canonical_url_key("https://example.com/?key=a+b") != canonical_url_key("https://example.com/?key=a%20b")
    assert canonical_url_key("https://example.com/?signature=%2f&key=%FF&%75tm_source=x") == "https://example.com/?signature=%2f&key=%FF"


def source(index, host, text, **extra):
    return Evidence(id=f"E{index}", title="Original", url=f"https://{host}/article",
                    publisher=host, retrieved_at="2026-10-09T00:00:00Z", content_kind="full_text",
                    excerpt=text, source_family=host, status="retrieved", **extra)


def long_record():
    return " ".join(f"Historical mission {number} carried instrument unit{number} on flight day{number}." for number in range(40))


def test_url_dedup_ignores_fragments_and_known_tracking_but_preserves_identifiers():
    first = "https://EXAMPLE.com:443/report?id=7&utm_source=copy#section"
    assert canonical_url_key(first) == canonical_url_key("https://example.com/report?id=7")
    assert canonical_url_key(first) != canonical_url_key("https://example.com/report?id=8")
    assert canonical_url_key("http://example.com/report?id=7") != canonical_url_key(first)
    assert canonical_url_key("https://example.com/report?a=1&a=2") != canonical_url_key("https://example.com/report?a=2&a=1")
    assert first.endswith("#section")  # keys never overwrite recorded URLs


def test_similar_reprints_are_one_provisional_family_with_recorded_reason():
    first = long_record()
    rows = [source(1, "original.example", first), source(2, "reprint.example", first.replace("unit39", "sensor39")),
            source(3, "unrelated.example", "Unrelated economic report with a completely different dataset. " * 25)]
    group_source_families(rows)
    assert rows[0].source_family == rows[1].source_family != rows[2].source_family
    assert rows[1].source_family_method == "near_duplicate"
    assert rows[0].source_family_evidence_ids == ["E2"]
    assert rows[1].excerpt != rows[0].excerpt  # grouping never rewrites a source


def test_exact_response_hash_is_distinct_from_exact_excerpt_and_domain_only():
    rows = [source(1, "first.example", "Selected extract A", content_sha256="a" * 64),
            source(2, "second.example", "Selected extract B", content_sha256="a" * 64),
            source(3, "third.example", long_record()), source(4, "fourth.example", long_record()),
            source(5, "first.example", "Another independent page on the same domain")]
    group_source_families(rows)
    assert rows[1].source_family_method == "exact_content"
    assert rows[3].source_family_method == "exact_excerpt"
    assert rows[4].source_family_method == "domain"
    assert rows[4].source_family == rows[0].source_family


def test_short_boilerplate_or_empty_extracts_do_not_merge_different_domains():
    for excerpt in ("", "Please enable JavaScript and sign in."):
        rows = [source(1, "a.example", excerpt), source(2, "b.example", excerpt)]
        group_source_families(rows)
        assert rows[0].source_family != rows[1].source_family


def test_gap_heuristics_prioritize_missing_material_and_ignore_unavailable_sources():
    claims = [Claim(id="C1", text="Apollo lunar landings completed missions", kind="fact"),
              Claim(id="C2", text="Ozone atmospheric recovery measurements", kind="fact")]
    rows = [source(1, "nasa.example", "Apollo lunar landings completed several missions."),
            source(2, "blocked.example", "Ozone atmospheric recovery measurements.")]
    rows[1].status = "unavailable"
    gaps = identify_retrieval_gaps(claims, rows, "en")
    assert [(gap.claim_id, gap.reason) for gap in gaps] == [("C2", "no_keyword_match"), ("C1", "limited_families")]
    assert all(not gap.attempted for gap in gaps)
    assert "original sources" in gaps[0].query


def test_two_keyword_matched_families_only_clear_heuristic_gap_not_truth_status():
    claim = Claim(id="C1", text="Apollo lunar landings completed missions", kind="fact")
    rows = [source(1, "a.example", "Apollo lunar landings completed missions with incomplete records."),
            source(2, "b.example", "Apollo lunar landings were disputed; completed missions need verification.")]
    assert identify_retrieval_gaps([claim], rows) == []
    assert claim.verdict is None and claim.analysis is None
