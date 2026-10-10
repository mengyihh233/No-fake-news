# tell me truth — complete usage

Create a reproducible evidence report from the user's topic. Readers must be able to trace sources and inferences. Insufficient, conflicting, or uncheckable evidence is a valid outcome; do not promise a single final truth.

## Input, language, modes, and depth

Accept text, a news URL, a question, or a scenario. Preserve the requested time, place, subject, and output language. Support `zh-CN`, `en`, and `ja`: prefer an explicit choice, then the conversation language, then `zh-CN`. Set report `language` to the narrative language. Keep original titles, excerpts, exact source quotes, queries, URLs, values, dates, and screenshots unchanged. Clearly label any added translation; do not overwrite the original or change the evidence standard by language.

Default to **evidence for your own judgment** and **standard depth**. Distinguish actual events from hypothetical scenarios; assumptions are not established events.

- **evidence-only**: show claims, original material, timelines, and data, logic, and historical comparisons. Explain reproducible calculations, necessary premises, shared conditions, differences, and open questions. Omit truth verdicts, fallacy labels, slanted summaries, and probability scores, including hidden JSON or HTML payloads. Disclose selection bias, coverage, and gaps.
- **ai-summary**: add claim assessments and cited reasoning to the same evidence and shared analysis. On switching modes, reuse the evidence; refresh only when needed and identify changes.

Proceed when the input is sufficiently clear. Ask only when an unresolved subject, date, or quotation would change what is checked. State other assumptions and continue.

Depth is independent of judgment; never force deep research into summary mode:

- **brief**: focus on the core claim while attempting neutral background, supporting evidence, counterevidence, and the subject's history. Provide essential original material, comparisons, and gaps.
- **standard**: execute the complete workflow; cross-check central claims, data definitions, and historical comparability.
- **deep**: add independent sources and competing explanations; extend the subject's chronology and comparable cases with opposite outcomes. Where real numbers permit, inspect conversions and sensitivity. More material does not guarantee certainty.

Respect time, cost, network, and tool limits; describe actual coverage. The web app has separate query, source, and time caps. Pursue fairness through consistent standards and reproducible selection, not promises of absolute neutrality.

## Research workflow

1. **Decompose claims.** Preserve the original statement; separate facts, causation, predictions, and values. Assign C1… and specify qualifiers, units, dates, scope, and reasonable interpretations. Value judgments do not receive objective truth labels.
2. **Plan competing searches.** Attempt neutral background, the strongest support, the strongest counterevidence, and the subject's original historical statements/data/promises. Define what evidence would change the assessment. Do not assume the user or a particular side must be wrong.
3. **Retrieve originals.** Use tools actually available in this session and open sources for context. Search snippets, model memory, and generated answers are not read originals. If tools or authorization are unavailable, state the limit and deliver a research plan or unverified material; do not claim completed verification.
4. **Audit source lineage.** Prefer locatable original data, documents, full interviews, and research papers. Check publisher, methods, dates, revisions, and interests. Reprints of one original are one evidence family. Official sources also need checking. Assess reliability separately from whether a source supports the claim.
5. **Analyze data, logic, and history.** Follow [Methodology](methodology.en.md): check denominators, units, samples, periods, causal conditions, and comparability. Inconsistent historical statements do not by themselves make the present claim false. List similarities, differences, confounders, inference limits, and comparable cases with opposite outcomes.
6. **Build the chain.** Assign E1… to materials. Every plotted value, event, historical comparison, and published inference must cite read evidence IDs. Shared `observations` hold neutral data/logic/history analysis; verdicts and evaluative reasoning belong only to summary fields. Separate excerpts, calculations, assumptions, and unknowns. Publish inspectable premises and conclusions, not internal model reasoning.
7. **Package the report.** Follow [Report format](report-format.en.md) and use actual retrieval timestamps. Plot only locatable real values; use tables or timelines when numbers are absent. Never invent charts, materials, or source counts to fill a layout.

For complex topics, where supported, delegate independent support/counterevidence searches or reasoning reviews in parallel. Deduplicate by source lineage; do not vote on truth.

## v0.2: exact quotations, documents, and supplemental search

New research uses schema `1.1`; existing `1.0` reports remain readable. Attach `citations` to observations, timeline entries, historical comparisons, chart data, and optional judgments: the evidence ID and verbatim `quote`, preserving its original language, whitespace, and newlines. Do not substitute translations or paraphrases. After actual tool checks, locators contain a Unicode codepoint range `[start, end)`, up to 80 characters of context on each side, an excerpt SHA-256, and a match count. Repeated quotes select their first occurrence. Locations refer only to the **stored, displayed excerpt**, not a webpage DOM or PDF page. `verification=exact_match` establishes textual presence only; `semantic_support=unverified` leaves support for the analysis open to review. Quotes, captures, and hashes do not authenticate truth. If the host cannot check or calculate a locator, disclose the missing capability; do not invent positions, hashes, or verified markers. Adding an AI summary reuses existing material without claiming fresh retrieval or authentication of imported sources.

Reading PDFs, HTML tables, CSV, and TSV depends on tools actually available in the host; the web app's extraction capabilities do not automatically belong to the Skill. Without suitable tools, mark material unread or extraction failed; never fabricate tables, page/row/column positions, or captures. Check headers, units, footnotes, empty cells, and reading order, and disclose truncation, merged cells, and parsing limits. The web app extracts text-based PDFs without OCR or password unlocking; a PDF table is not verified cell reconstruction. See [Methodology](methodology.en.md) for resource limits.

Supplemental search is optional and disabled by default: `adaptive_search=false`. It is independent of judgment mode. Initial web research still attempts neutral, support, counterevidence, and actor-history queries. When enabled, brief / standard / deep add at most **1 / 2 / 2 queries**, potentially increasing service fees, including DeepSeek model/search calls. Source, claim, excerpt, and overall time limits do not increase. Preferred-source priority and designated-only domain restrictions apply to both rounds. Skip supplemental search without capacity or with fewer than 45 seconds left, and disclose actual limits.

`retrieval_gaps` records an **initial-round** heuristic snapshot: no matching excerpt keywords, or fewer than two matching source families. `attempted` means a query was dispatched, not that it succeeded or resolved the gap. Successful searches record `round` and `gap_claim_ids` in `search_log`; disclose supplemental failures separately and retain initial material. Keywords and family counts establish neither semantic coverage, completeness, nor truth. Group source families provisionally by domain, response-byte hashes, sufficiently long identical extracts, or highly similar long text, exposing `source_family_method` and related evidence IDs. These methods prove neither a shared origin nor independence; explain the methodology's limits.

## v0.3: progress and optional citation review

Report actual completed steps and tool counts only. The web app streams research stages via SSE: successful query returns and completed retrieval attempts (including unavailable pages). Totals can change after supplemental searches, and unknown totals stay unknown. A stage denominator counts that stage's actual steps, not overall investigation progress. Canceling stops subsequent local work but cannot recall calls already sent to a provider or guarantee a refund. Do not fabricate percentages, ETA, or streamed model tokens; a standalone host must describe only tools it actually ran.

Only when requested, review how an existing AI-summary report's statements relate to their quoted passages. Before the extra call, disclose that the same configured AI uses existing extracts without new search/retrieval, may incur fees, and provides advice rather than independent verification or source authentication. Web review requires `1.1` or `1.2` with exact citations; `1.0` cannot use that endpoint. Brief / standard / deep select at most **12 / 24 / 40 targets**, also limited by input size. Label omitted and model-skipped targets unreviewed, never silently approved. Inspect scope, time, definitions, causality, numbers, translation, and context; do not issue confidence or truth scores. Keep original evidence and `semantic_support=unverified` unchanged.

The web server attaches checked `citation_review` snapshot metadata and uses schema `1.2`. A standalone Skill may perform the requested semantic comparison with its available tools, while clearly labeling the advice. Without the deterministic server capabilities, keep schema `1.0` and ordinary optional judgment fields; never invent `1.1` locators, `1.2` review hashes/counts, or metadata claiming a server operation. Evidence-only delivery removes review judgments in full.

## Screenshots and delivery

Use real browser/PDF capture tools available in the current environment. Capture the relevant passage with sufficient context; preserve the original URL, title, capture time, and unmodified image. Disclose cropping, OCR, translation, or annotation. Never replace a source capture with generated imagery, recreated webpages, or composites.

If capture fails, retain the URL, read excerpt, location, and failure reason, clearly marking the missing screenshot. Screenshots and SHA-256 help inspect captured files; they do not verify factual claims.

Deliver clickable claim → source → data/event/comparison → analysis and limits links. Use available interactive visualization tools where useful. For portable HTML, use this Skill's standard-library renderer:

```text
python <skill-directory>/scripts/render_report.py report.json --output report.html --mode evidence-only --language en
python <skill-directory>/scripts/render_report.py report.json --output report-summary.html --mode ai-summary --language en
```

The second command requires an existing checked summary. The renderer neither researches nor generates verdicts. `--language` changes labels/messages only, never report prose. Local screenshots are resolved relative to the JSON and embedded; only genuine PNG/JPEG/WebP is accepted. Inspect the result before delivery.

The separate web app provides OpenAI-compatible AI, Tavily/Brave search, and optional captures. Its permissions, keys, and browser capabilities are independent of this Skill. Do not assume every host has them. Web reports can be inputs for further checking.

## Preferred sources and account websites

Accept user-specified source lists. Distinguish supplemental sources from a designated-only scope. If the host supports preference storage and the user authorizes it, save only nonsecret source lists and scope preferences; never promise persistent memory without actually saving. Disclose designated sources, access failures, and coverage gaps. A restricted list neither covers the whole web nor guarantees truth.

Access account websites only with user authorization and suitable tools available now. Do not request, repeat, or expose passwords, cookies, bearer tokens, or MFA codes in chat/reports, and never bypass login or MFA. Use the host's authorization flow or dedicated credential controls; otherwise accept authorized nonsecret source text and report access limits. Tell the user before retrieved content is sent to an external AI service.

The web app accepts up to six preferred sources. Basic/Cookie/Bearer credentials stay in the current in-memory session and are bound to the exact authorized origin (scheme, host, port). Never send them to another origin or save them in reports/search logs. Authenticated sources are excluded from screenshots. `source_policy` and `preferred_sources` contain nonsecret scope metadata only.

## Assessment and corrections

In summary mode, use evidence-matched descriptions such as supported, contradicted, partly established, missing context, conflicting evidence, insufficient evidence, or uncheckable. Cite evidence and the inference. Do not issue uncalibrated truth percentages. “Not found” is different from “proven nonexistent.”

Deliver an openable report and sources, with scope, cutoff, unresolved questions, and new evidence that could change the assessment. Keep old reports when correcting; use a new file stating the change and reason. Do not promise to bypass another AI's restrictions or eliminate all bias.

A standalone Skill without deterministic locator computation uses `1.0` with original quotes and disclosed limitations. `1.1` requires complete, reproducible locator metadata; never guess it with a model.
