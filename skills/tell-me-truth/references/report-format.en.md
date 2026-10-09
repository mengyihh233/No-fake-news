# Report JSON format v1.0

Use UTF-8 JSON. The web app and standalone renderer share these fields. Store facts and provenance; model interpretations must not alter server-retrieved URLs, dates, or excerpts.

| Field | Meaning |
| --- | --- |
| `schema_version` | Fixed string `1.0` |
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
  "excerpt": "Short original excerpt or explicitly labeled faithful paraphrase.",
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

Keep observations in both modes: data definitions, necessary premises, historical similarities/differences/confounders, with existing claim and evidence references. No global verdicts or judgments about political positions. Deep web research allows up to 24 sources and 8 logged queries; all depths use the same structure.

Free-text scope/limitations/excerpts/questions/chart notes must also respect the mode. Structural filters cannot detect every slanted statement; review wording and selection. Retain reproducible numbers and comparisons without a total verdict. Summary conclusions cite evidence and reasoning; summary is not evidence itself. State what could change the assessment.

The renderer's `--language zh-CN|en|ja` localizes labels and errors only; omitted language follows report.language or zh-CN. It does not translate existing report prose or quotes. If summary language differs, record summary_language and retain the original base analysis.

## Nonsecret source metadata and accounts

`preferred_sources` records explicit public URLs/labels, not proof of successful retrieval. Never place passwords, cookies, Authorization headers, bearer tokens, MFA codes, or other credentials in any report field, source URL, search log, screenshot, or export. Scope metadata must not include secrets. The web app keeps account credentials only in memory, binds them to the exact origin, and disables captures for authenticated sources. Tell users before source text is sent to external AI. A designated-only source list must be disclosed as restricted coverage.
