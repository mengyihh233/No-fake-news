'use strict';

// Snapshot consistency only: this never verifies a publisher, a webpage or truth.
(() => {
  const capacityByDepth = { brief: 12, standard: 24, deep: 40 };
  const characterLimit = 120000;
  class ReviewError extends Error {
    constructor(code = 'invalid') { super(code); this.name = 'ReviewError'; this.code = code; }
  }
  const text = value => typeof value === 'string' ? value.trim() : '';
  const list = value => Array.isArray(value) ? value : [];
  const fields = (item, keys) => Object.fromEntries(keys.map(key => [key, typeof item[key] === 'string' ? text(item[key]) : item[key]]));

  function decimalString(value) {
    if (!Number.isFinite(value)) throw new ReviewError();
    if (value === 0) return '0';
    const raw = String(value);
    if (!/[eE]/.test(raw)) return raw;
    const [coefficient, exponentText] = raw.toLowerCase().split('e');
    const negative = coefficient.startsWith('-');
    const unsigned = negative ? coefficient.slice(1) : coefficient;
    const [whole, fraction = ''] = unsigned.split('.');
    const digits = whole + fraction;
    const position = whole.length + Number(exponentText);
    const expanded = position <= 0 ? `0.${'0'.repeat(-position)}${digits}` : position >= digits.length ? digits + '0'.repeat(position - digits.length) : `${digits.slice(0, position)}.${digits.slice(position)}`;
    return `${negative ? '-' : ''}${expanded}`;
  }

  function canonicalNumbers(value) {
    if (typeof value === 'number') return decimalString(value);
    if (Array.isArray(value)) return value.map(canonicalNumbers);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, canonicalNumbers(item)]));
    return value;
  }

  // Python json.dumps(ensure_ascii=False): default separators contain spaces.
  function serialize(value, { sorted = false, compact = false } = {}) {
    const comma = compact ? ',' : ', ', colon = compact ? ':' : ': ';
    if (Array.isArray(value)) return `[${value.map(item => serialize(item, { sorted, compact })).join(comma)}]`;
    if (value && typeof value === 'object') {
      const keys = Object.keys(value); if (sorted) keys.sort();
      return `{${keys.map(key => `${JSON.stringify(key)}${colon}${serialize(value[key], { sorted, compact })}`).join(comma)}}`;
    }
    const encoded = JSON.stringify(value);
    if (encoded === undefined) throw new ReviewError();
    return encoded;
  }

  function storedCitation(citation) {
    const locator = citation.locator ? {
      ...fields(citation.locator, ['start', 'end']), prefix: citation.locator.prefix, suffix: citation.locator.suffix,
      excerpt_sha256: citation.locator.excerpt_sha256, match_count: citation.locator.match_count,
      coordinate_system: citation.locator.coordinate_system ?? 'unicode_codepoints'
    } : null;
    return { evidence_id: citation.evidence_id, quote: citation.quote, locator, verification: citation.verification ?? null, semantic_support: citation.semantic_support ?? 'unverified' };
  }

  function snapshot(report, target) {
    const item = target.item;
    let content;
    if (target.id === 'summary') content = { ...fields(item, ['text', 'verdict']), caveats: list(item.caveats).map(text), evidence_ids: list(item.evidence_ids) };
    else if (target.id.startsWith('claim:')) content = { ...fields(item, ['id', 'text', 'kind']), verdict: item.verdict == null ? null : text(item.verdict), analysis: item.analysis == null ? null : text(item.analysis) };
    else if (target.id.startsWith('observation:')) content = { ...fields(item, ['kind', 'text']), claim_ids: list(item.claim_ids), evidence_ids: list(item.evidence_ids) };
    else if (target.id.startsWith('timeline:')) content = { ...fields(item, ['date', 'title', 'detail']), evidence_ids: list(item.evidence_ids) };
    else if (target.id.startsWith('comparison:')) content = { ...fields(item, ['case', 'date', 'similarities', 'differences', 'limits']), evidence_ids: list(item.evidence_ids) };
    else if (target.id.startsWith('reasoning:')) content = { ...fields(item, ['id']), premise_ids: list(item.premise_ids), ...fields(item, ['claim_id', 'text', 'kind']) };
    else if (target.id.startsWith('chart:')) {
      const index = Number(target.id.split(':')[1]) - 1;
      const chart = report.charts[index];
      const calculation = item.calculation ? { operation: text(item.calculation.operation), source_quotes: list(item.calculation.source_quotes), description: text(item.calculation.description) } : null;
      content = { ...fields(chart, ['title', 'unit', 'kind']), note: text(chart.note), point: { label: text(item.label), value: item.value ?? null, evidence_ids: list(item.evidence_ids), calculation } };
    } else throw new ReviewError();
    const citations = list(item.citations).map(storedCitation);
    const sourceIds = [...new Set(citations.map(citation => citation.evidence_id))];
    const context = sourceIds.map(evidence_id => {
      const source = report.evidence.find(source => source.id === evidence_id);
      if (!source) throw new ReviewError();
      return { evidence_id, title: text(source.title), context: text(source.context), excerpt: source.excerpt };
    });
    return { target_id: target.id, statement: { report_topic: text(report.topic), report_scope: text(report.scope), content }, citations, context };
  }

  function payload(targets, depth, language) {
    const sources = new Map();
    for (const target of targets) for (const source of target.context) sources.set(source.evidence_id, source);
    return canonicalNumbers({ language, depth, method: 'ai_advisory', targets: targets.map(target => ({ target_id: target.target_id, statement: target.statement, quotations: target.citations.map(citation => ({ evidence_id: citation.evidence_id, quote: citation.quote })) })), source_context: [...sources.values()] });
  }

  const inputCharacters = value => Array.from(serialize(value)).length;
  function selectTargets(targets, depth, language) {
    const selected = [];
    for (const target of targets) {
      if (selected.length >= capacityByDepth[depth]) break;
      if (inputCharacters(payload([...selected, target], depth, language)) <= characterLimit) selected.push(target);
    }
    return selected;
  }

  async function sha256(value) {
    if (!globalThis.crypto?.subtle || typeof TextEncoder === 'undefined') throw new ReviewError('unavailable');
    const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  }

  async function verify(report, targetRefs) {
    const review = report.citation_review;
    if (review == null) return report;
    if (report.mode !== 'ai-summary' || report.schema_version !== '1.2') throw new ReviewError();
    const depth = report.depth || 'standard';
    const targets = targetRefs.map(target => snapshot(report, target));
    const selected = selectTargets(targets, depth, review.language);
    if (review.available_targets !== targets.length || review.selected_targets !== selected.length || review.capacity !== capacityByDepth[depth] || review.input_character_limit !== characterLimit || review.input_characters !== inputCharacters(payload(selected, depth, review.language)) || review.reviewed_targets !== review.items.length || review.not_reviewed_targets !== targets.length - review.items.length) throw new ReviewError();
    // Recompute source fingerprints rather than trusting imported hash declarations.
    const sourceHashes = new Map();
    for (const target of targets) for (const citation of target.citations) {
      const source = report.evidence.find(source => source.id === citation.evidence_id);
      if (!sourceHashes.has(source.id)) sourceHashes.set(source.id, await sha256(source.excerpt));
      const actual = sourceHashes.get(source.id);
      if (citation.locator?.excerpt_sha256 !== actual || (source.excerpt_metadata && source.excerpt_metadata.sha256 !== actual)) throw new ReviewError();
    }
    const selectedMap = new Map(selected.map(target => [target.target_id, target]));
    const seen = new Set();
    for (const item of review.items) {
      const target = selectedMap.get(item.target_id);
      if (!target || seen.has(item.target_id)) throw new ReviewError();
      seen.add(item.target_id);
      if (item.target_sha256 !== await sha256(serialize(canonicalNumbers(target), { sorted: true, compact: true }))) throw new ReviewError();
      const originals = new Set(target.citations.map(citation => serialize(citation, { sorted: true, compact: true })));
      if (!item.citations.length || item.citations.some(citation => !originals.has(serialize(storedCitation(citation), { sorted: true, compact: true })))) throw new ReviewError();
    }
    return report;
  }

  const api = { verify, snapshot, payload, inputCharacters, selectTargets, canonicalNumbers, serialize, sha256, ReviewError };
  globalThis.NoFakeNewsReview = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
