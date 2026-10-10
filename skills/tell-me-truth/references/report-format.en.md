# Report JSON format v1.2 (v1.0 / v1.1 compatible)

Use UTF-8 JSON. The web app and standalone renderer share these fields. Store facts and provenance; model interpretations must not alter server-retrieved URLs, dates, or excerpts.

| Field | Meaning |
| --- | --- |
| `schema_version` | `1.1` for new research; `1.2` with a checked citation review; existing `1.0` / `1.1` remains readable |
| `topic`, `scope` | Original question and time/place/definition boundaries |
| `language` | Narrative language: `zh-CN` (fallback), `en`, or `ja` |
| `summary_language` | Language of a later summary, or null; existing evidence and observations are not silently translated |
| `mode` | `evidence-only` or `ai-summary` |
| `depth` | `brief`, `standard` (default), or `deep`; independent of mode |
| `source_policy` | `balanced` (default) or `preferred-only`; disclose restricted coverage |
| `preferred_sources` | Up to 6 nonsecret `{url, label}` entries; actual included material is in evidence |
| `generated_at` | Actual generation timestamp with timezone |
| `limitations` | Array of limitations and evidence gaps |
| `claims` | `{id, text, kind}`; kind: fact/causal/prediction/value/mixed |
| `evidence` | Source objects described below |
| `links` | `{from, to, relation, note}`; evidence ID → claim ID |
| `timeline` | `{date, title, detail, evidence_ids}` |
| `charts` | `{title, unit, kind, points, note}`; kind: bar/line |
| `comparisons` | `{case, date, similarities, differences, limits, evidence_ids}` |
| `observations` | Shared in both modes: `{kind, text, claim_ids, evidence_ids}`, kind: data/logic/history; cited neutral analysis, not verdicts |
| `questions` | Array of open questions |
| `search_log` | `{query, intent, provider, result_count, ran_at}` |
| `reasoning` | Summary only: `{id, premise_ids, claim_id, text, kind}` |
| `summary` | Summary only: `{text, verdict, caveats, evidence_ids}` |

Use unique C1… claim IDs, E1… evidence IDs, and R1… reasoning IDs. References must exist. Reasoning cites evidence or earlier reasoning, never cycles. Chart count does not measure evidence sufficiency.

Each evidence record contains:

```json
{
  "id": "E1",
  "title": "Original source title",
  "url": "https://example.org/original",
  "publisher": "Publisher",
  "published_at": null,
  "retrieved_at": "2026-10-09T10:00:00+08:00",
  "source_type": "unknown",
  "content_kind": "full_text",
  "excerpt": "Short original extract, preserving source wording and whitespace.",
  "context": "Location, access limits, and translation/paraphrase notes.",
  "source_family": "Shared identifier for reprints of one original",
  "status": "retrieved",
  "claim_ids": ["C1"],
  "screenshots": []
}
```

`source_type`: primary/secondary/unknown. `content_kind`: full_text/search_extract/snippet. `status`: retrieved/snippet_only/unavailable. A snippet is not a read original. Respect quotation limits; do not export long full-text copies. Preserve original titles/excerpts/exact quotes/queries/URLs/values/dates/images across localized reports, adding labeled translation separately.

Screenshot objects use `{url, captured_at, sha256, source_url}` in the web app, with a `/captures/<file>` URL. The standalone renderer accepts `{path, captured_at, sha256, source_url}` where path is relative to the JSON, or app URLs with `--capture-dir`. Hash actual files; never fabricate missing hashes. The screenshot source URL should match its source, with legitimate redirects explained.

Chart points use `{label, value, evidence_ids}`; values are finite numbers or null. Null is missing, never zero. Retain units and calculation rules. If data are absent, use an empty charts array. Timeline dates are event dates, not publication/retrieval dates.

The web app also supports deterministic counts: add `calculation: {operation: "count", source_quotes: ["exact, distinct entries in cited excerpts"], description: "inclusion/exclusion rules"}`. Value must equal the number of entries. Zero may use an empty entry list with an explicit complete-list scope, but the program cannot establish that the list covers the entire population. Review other transformations in a separate calculation workflow; do not let the model invent numbers.

`links.relation`: relevant_to/supports/contradicts/qualifies/context. Support, contradiction, and qualification are interpretations. Evidence-only output retains relevant_to/context and removes evaluative notes. Present by time or original-source order, never by preferred verdict.

## Mode and language boundaries

Evidence-only exports use an allowlist and delete summary, reasoning, claim verdict/analysis, and evaluative edge notes. This applies to visible HTML, downloadable JSON, inline scripts, titles, and accessibility text, not just CSS.

Keep observations in both modes: data definitions, necessary premises, historical similarities/differences/confounders, with existing claim and evidence references. No global verdicts or judgments about political positions. Deep web research allows up to 24 sources and 8 initial queries, plus at most 2 optional supplemental queries; all depths use the same structure.

Free-text scope/limitations/excerpts/questions/chart notes must also respect the mode. Structural filters cannot detect every slanted statement; review wording and selection. Retain reproducible numbers and comparisons without a total verdict. Summary conclusions cite evidence and reasoning; summary is not evidence itself. State what could change the assessment.

The renderer's `--language zh-CN|en|ja` localizes labels and errors only; omitted language follows report.language or zh-CN. It does not translate existing report prose or quotes. If summary language differs, record summary_language and retain the original base analysis.

## Nonsecret source metadata and accounts

`preferred_sources` records explicit public URLs/labels, not proof of successful retrieval. Never place passwords, cookies, Authorization headers, bearer tokens, MFA codes, or other credentials in any report field, source URL, search log, screenshot, or export. Scope metadata must not include secrets. The web app keeps account credentials only in memory, binds them to the exact origin, and disables captures for authenticated sources. Tell users before source text is sent to external AI. A designated-only source list must be disclosed as restricted coverage.

## v1.1 quotations and retrieval metadata

Every observation, timeline item, comparison, reasoning step, claim assessment, and summary in new research includes nonempty `citations: [{evidence_id: "E1", quote: "verbatim text from E1's displayed extract"}]`. Quotes must match character-for-character, including whitespace and original language, and cite the item's evidence IDs or evidence reachable through its reasoning premises. Omit unsupported factual items; put missing information in questions/limitations. A new judgment on a `1.0` base still supplies exact quotes but retains the legacy base unchanged. Do not invent locators for old material.

The web server derives each stored citation's `verification: "exact_match"`, `semantic_support: "unverified"`, and `locator: {start, end, prefix, suffix, excerpt_sha256, match_count, coordinate_system: "unicode_codepoints"}`. `[start,end)` indexes Unicode codepoints in the **stored extract**, not a source webpage/PDF page. Prefix and suffix retain at most 80 characters each. Use the first occurrence and record the total occurrence count. `excerpt_sha256` is lowercase SHA-256 of the UTF-8 extract; evidence may also include `excerpt_metadata: {sha256, coordinate_system: "unicode_codepoints"}`. Match all metadata to the actual text; the model must not generate server verification fields. Host Skills without a deterministic verifier use schema `1.0` with plain `{evidence_id, quote}` and must not claim server verification. Import/rendering consistency is not source authentication or semantic entailment.

Chart points retain `citations` after validation of the input `source_quote` or `calculation.source_quotes`; values must occur in the corresponding quotes, and each counted entry has a matching citation. Missing values remain null. An empty-list zero has no entries to quote and requires the existing completeness caveat.

Optional evidence metadata: `document_format` is `unknown|html|text|pdf|csv|tsv`; `content_sha256` is null or lowercase SHA-256 of retrieved **response bytes**, distinct from the extract hash. `source_family_method` is `domain|exact_content|exact_excerpt|near_duplicate`; `source_family_evidence_ids` lists related existing evidence IDs. These are provisional dependence hints, potentially transitive, not proof of ownership, independent reporting, truth, or a publisher signature. Do not infer a byte hash from extracted text or a search snippet.

`search_log` additionally accepts `round: "initial"|"supplemental"` and `gap_claim_ids: ["C1"]`, up to 10 total entries. `retrieval_gaps` contains up to 12 `{claim_id, reason: "no_keyword_match"|"limited_families", query, attempted}` records describing the **initial** heuristic snapshot. An attempted query may fail; failure is disclosed separately, never logged as a successful zero result. Neither an absent gap nor `attempted=true` certifies coverage or resolves a claim. The web request flag `adaptive_search` defaults to false. When enabled, brief/standard/deep allow 1/2/2 extra queries, additional fees, and unchanged source/deadline limits. Host tools and user budgets determine a standalone Skill's actual execution limits.

## v1.2 optional citation-review snapshot

Only an AI-summary report may carry `citation_review`; evidence-only responses and exports remove it in full. `1.2` retains all `1.1` exact-quote requirements. The absence of a review is valid, including an evidence-only projection. Legacy `1.0` / `1.1` remain readable; a `1.1` report does not store review metadata until the server attaches a review and upgrades it.

`citation_review` contains `generated_at` (1–100 characters), `language` (`zh-CN|en|ja`), `model` (1–200), `method: "ai_advisory"`, `available_targets` (0–323), `selected_targets` (0–40), `reviewed_targets` (0–40), `not_reviewed_targets` (0–323), `capacity` (12/24/40 by brief/standard/deep), `input_character_limit: 120000`, `input_characters` (0–120000), and `items` (0–40). Counts are integers, never truth/confidence scores. Reviewed equals the number of unique items; unreviewed equals available minus reviewed. Selected/input counts must reproduce the server's capacity- and input-bounded selection.

Each item has `target_id`, lowercase 64-hex `target_sha256`, `relation` (`aligned|partial|unsupported|conflicting|unclear`), up to seven distinct `issues` (`scope|time|definition|causality|numeric|translation|context`), `explanation` (1–3000), and 1–100 existing complete `Citation` objects. Citations must be a subset of the target's original citations, preserving original quotes and exact locators. No new evidence or changed `semantic_support` is allowed. Treat explanations as escaped plain text.

Target IDs are `summary`, `claim:C1`, `reasoning:R1`, `observation:1`, `timeline:1`, `comparison:1`, and `chart:1:point:1` (numeric indexes start at one). Only targets with complete exact citations are eligible. Select summary first, then rotate the six other categories in that order: observations, assessed claims, timeline, chart points, comparisons, reasoning. Trial-add targets until capacity; skip input-oversized targets and try later ones. Serialize the user-message payload with Unicode preserved and default JSON separators, measuring Unicode codepoints against 120,000; fixed system instructions and schema add separate overhead; do not truncate quotes/statements/extracts. [Evidence boundaries](../../../docs/EVIDENCE.md) explain coverage and cost.

The server snapshot binds `target_id`, `statement: {report_topic, report_scope, content}`, the target's complete stored `citations`, and ordered unique `context: [{evidence_id, title, context, excerpt}]`. `content` is the visible target object without citations; chart content also includes chart title/unit/kind/note and its point. Complete model defaults are included. Hashing recursively converts nonboolean numbers to fixed decimal strings, removes trailing fractional zeros and a terminal decimal point, normalizes negative zero to `"0"`, then SHA-256 hashes UTF-8 JSON with sorted keys, Unicode preserved, and compact separators. The server derives this metadata; the model never invents it. It verifies report-snapshot consistency, not AI authorship, correctness, or source authenticity. Updated analysis clears stale reviews.

A standalone host without deterministic server capabilities may give requested semantic advice using schema `1.0` optional judgment fields, but must not fabricate `1.2` snapshots or claim server verification. The offline renderer only validates and displays existing reviews; it makes no AI/search calls.
