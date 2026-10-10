'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const I18n = globalThis.NoFakeNewsI18n;
  const t = (key, values) => I18n.t(key, values);
  const locale = () => I18n.getLocale();
  const Workspace = globalThis.NoFakeNewsWorkspace;
  const state = { report: null, isDemo: false, isImported: false, filter: null, pending: false, controller: null, elapsedTimer: null, operationId: 0, capabilities: { configured: {} } };
  const settingsKey = 'tell-me-truth.settings.v1';
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const asArray = (value) => Array.isArray(value) ? value : [];
  const textValue = (value) => value == null ? '' : Array.isArray(value) ? value.map(textValue).join('；') : typeof value === 'object' ? '' : String(value);

  function el(tag, className, content, attributes = {}) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined && content !== null) node.textContent = textValue(content);
    for (const [name, value] of Object.entries(attributes)) {
      if (value !== undefined && value !== null) node.setAttribute(name, String(value));
    }
    return node;
  }

  function svg(tag, attributes = {}, content) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    if (content !== undefined) node.textContent = textValue(content);
    return node;
  }

  function safeUrl(value, capture = false) {
    if (typeof value !== 'string' || !value.trim()) return null;
    try {
      const raw = value.trim();
      if (raw.startsWith('/') && !raw.startsWith('//')) {
        if (!capture || !raw.startsWith('/captures/')) return null;
        const parsed = new URL(raw, window.location.origin);
        if (!parsed.pathname.startsWith('/captures/')) return null;
        return parsed.href;
      }
      const parsed = new URL(raw);
      return ['https:', 'http:'].includes(parsed.protocol) && !parsed.username && !parsed.password ? parsed.href : null;
    } catch { return null; }
  }

  function externalLink(label, url, className = '') {
    const href = safeUrl(url);
    if (!href) return el('span', className, label);
    return el('a', className, label, { href, target: '_blank', rel: 'noopener noreferrer' });
  }

  function dateLabel(value, includeTime = false) {
    if (!value) return t('common.not_provided');
    const raw = textValue(value);
    // A date is not a timestamp. Never manufacture a capture hour or infer a timezone.
    if (/^\d{4}(-\d{2}){0,2}$/.test(raw)) return raw;
    const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/i);
    if (!iso) return raw;
    const year = Number(iso[1]), month = Number(iso[2]), day = Number(iso[3]);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const monthDays = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > monthDays[month - 1] || Number(iso[4]) > 23 || Number(iso[5]) > 59 || Number(iso[6] || 0) > 59) return raw;
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return raw;
    return new Intl.DateTimeFormat(locale(), { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', ...(includeTime ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}) }).format(parsed);
  }

  function hostLabel(value) {
    try { return new URL(value).hostname.replace(/^www\./, ''); } catch { return textValue(value); }
  }

  function pick(object, fields) {
    const result = {};
    if (!object || typeof object !== 'object') return result;
    for (const key of fields) if (Object.prototype.hasOwnProperty.call(object, key)) result[key] = structuredClone(object[key]);
    return result;
  }

  function projectCitations(citations) {
    return asArray(citations).map(citation => {
      const item = pick(citation, ['evidence_id', 'quote', 'verification', 'semantic_support']);
      if (citation.locator) item.locator = pick(citation.locator, ['start', 'end', 'prefix', 'suffix', 'excerpt_sha256', 'match_count', 'coordinate_system']);
      return item;
    });
  }

  function citedPick(item, fields) {
    return { ...pick(item, fields), citations: projectCitations(item.citations) };
  }

  // Work in Unicode code points, matching the server rather than UTF-16 offsets.
  function citationPosition(citation, source) {
    if (!source || typeof citation?.quote !== 'string' || !citation.quote.trim()) return null;
    const excerpt = source.excerpt || '';
    const chars = Array.from(excerpt);
    const quote = Array.from(citation.quote);
    const starts = [];
    let cursor = excerpt.indexOf(citation.quote);
    while (cursor >= 0) { starts.push(Array.from(excerpt.slice(0, cursor)).length); cursor = excerpt.indexOf(citation.quote, cursor + 1); }
    if (!starts.length) return null;
    const start = starts[0], end = start + quote.length;
    const position = { start, end, prefix: chars.slice(Math.max(0, start - 80), start).join(''), suffix: chars.slice(end, end + 80).join(''), match_count: starts.length };
    const locator = citation.locator;
    if (locator && (locator.start !== start || locator.end !== end || locator.prefix !== position.prefix || locator.suffix !== position.suffix || locator.match_count !== starts.length || locator.coordinate_system !== 'unicode_codepoints' || (source.excerpt_metadata && locator.excerpt_sha256 !== source.excerpt_metadata.sha256))) return null;
    return position;
  }

  // An allowlist is deliberate: changing the view also removes AI conclusions from the data.
  function evidenceProjection(report) {
    const projected = pick(report, ['schema_version', 'topic', 'depth', 'language', 'source_policy', 'generated_at', 'scope', 'limitations', 'questions']);
    projected.preferred_sources = asArray(report.preferred_sources).map(source => pick(source, ['url', 'label']));
    projected.mode = 'evidence-only';
    projected.claims = asArray(report.claims).map((claim) => pick(claim, ['id', 'text', 'kind']));
    projected.evidence = asArray(report.evidence).map((source) => {
      const item = pick(source, ['id', 'title', 'url', 'publisher', 'published_at', 'retrieved_at', 'source_type', 'content_kind', 'document_format', 'content_sha256', 'excerpt', 'context', 'source_family', 'source_family_method', 'source_family_evidence_ids', 'status', 'claim_ids']);
      if (source.excerpt_metadata) item.excerpt_metadata = pick(source.excerpt_metadata, ['sha256', 'coordinate_system']);
      item.screenshots = asArray(source.screenshots).map((capture) => pick(capture, ['url', 'captured_at', 'sha256', 'source_url']));
      return item;
    });
    projected.links = asArray(report.links).map((link) => ({ ...pick(link, ['from', 'to']), relation: link.relation === 'context' ? 'context' : 'relevant_to' }));
    projected.timeline = asArray(report.timeline).map((item) => citedPick(item, ['date', 'title', 'detail', 'evidence_ids']));
    projected.charts = asArray(report.charts).map((chart) => ({ ...pick(chart, ['title', 'unit', 'kind', 'note']), points: asArray(chart.points).map((point) => {
      const item = citedPick(point, ['label', 'value', 'evidence_ids']);
      if (point.calculation && typeof point.calculation === 'object') item.calculation = pick(point.calculation, ['operation', 'source_quotes', 'description']);
      return item;
    }) }));
    projected.comparisons = asArray(report.comparisons).map((item) => citedPick(item, ['case', 'date', 'similarities', 'differences', 'limits', 'evidence_ids']));
    projected.observations = asArray(report.observations).map((item) => citedPick(item, ['kind', 'text', 'claim_ids', 'evidence_ids']));
    projected.search_log = asArray(report.search_log).map((item) => pick(item, ['query', 'intent', 'provider', 'result_count', 'ran_at', 'round', 'gap_claim_ids']));
    projected.retrieval_gaps = asArray(report.retrieval_gaps).map(item => pick(item, ['claim_id', 'reason', 'query', 'attempted']));
    return projected;
  }

  function getAISettings() {
    return { base_url: $('ai-base-url').value.trim().replace(/\/+$/, ''), model: $('ai-model').value.trim(), api_key: $('ai-key').value.trim() };
  }

  function getSearchSettings() {
    return { provider: $('search-provider').value, api_key: $('search-key').value.trim() };
  }

  function isLoopbackAI(baseURL) {
    try { return ['localhost', '127.0.0.1', '[::1]', '::1'].includes(new URL(baseURL).hostname.toLowerCase()); }
    catch { return false; }
  }

  function canUseAIWithoutKey(ai) {
    return isLoopbackAI(ai.base_url) || (!ai.base_url && Boolean(state.capabilities.configured?.ai_base_url));
  }

  function canReuseDeepSeekKey(ai) {
    if (!ai.api_key) return false;
    try {
      const endpoint = new URL(ai.base_url);
      return endpoint.protocol === 'https:' && endpoint.hostname === 'api.deepseek.com' && (!endpoint.port || endpoint.port === '443') && !endpoint.username && !endpoint.password;
    } catch { return false; }
  }

  function searchCredentialReady(ai = getAISettings()) {
    const search = getSearchSettings();
    return Boolean(search.api_key || state.capabilities.configured?.[search.provider] || (search.provider === 'deepseek' && canReuseDeepSeekKey(ai)));
  }

  function saveSettings() {
    const ai = getAISettings();
    const safeSettings = { base_url: ai.base_url, model: ai.model, search_provider: $('search-provider').value, depth: $('research-depth').value, include_screenshots: $('include-screenshots').checked, adaptive_search: $('adaptive-search').checked };
    try { localStorage.setItem(settingsKey, JSON.stringify(safeSettings)); } catch { /* The app also works when browser storage is disabled. */ }
    updateConnectionStatus();
  }

  function restoreSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem(settingsKey) || '{}');
      if (typeof saved.base_url === 'string') $('ai-base-url').value = saved.base_url;
      if (typeof saved.model === 'string') $('ai-model').value = saved.model;
      if (['deepseek', 'tavily', 'brave'].includes(saved.search_provider)) $('search-provider').value = saved.search_provider;
      if (typeof saved.include_screenshots === 'boolean') $('include-screenshots').checked = saved.include_screenshots;
      if (typeof saved.adaptive_search === 'boolean') $('adaptive-search').checked = saved.adaptive_search;
      if (['brief', 'standard', 'deep'].includes(saved.depth)) $('research-depth').value = saved.depth;
    } catch { /* Invalid old preferences are ignored; no keys are ever restored. */ }
    updateConnectionStatus();
  }

  function updateConnectionStatus() {
    const configured = state.capabilities.configured || {};
    const ai = getAISettings();
    const ready = Boolean((ai.api_key || configured.ai_key || canUseAIWithoutKey(ai)) && (ai.model || configured.ai_model) && searchCredentialReady(ai));
    $('connection-status').textContent = ready ? t('common.connection_ready') : t('common.connection_missing');
    $('connection-status').classList.toggle('ready', ready);
  }

  function validateAI() {
    const ai = getAISettings();
    if (ai.base_url && !safeUrl(ai.base_url)) throw new Error(t('errors.ai_url'));
    if (!ai.model && !state.capabilities.configured?.ai_model) throw new Error(t('errors.ai_model'));
    if (!ai.api_key && !state.capabilities.configured?.ai_key && !canUseAIWithoutKey(ai)) throw new Error(t('errors.ai_key'));
    return ai;
  }

  function clearError() { $('error-message').hidden = true; $('error-message').replaceChildren(); }

  function showError(message, withSettings = false) {
    const box = $('error-message');
    box.replaceChildren(el('div', '', message));
    if (withSettings) {
      const button = el('button', '', t('common.open_settings'), { type: 'button' });
      button.addEventListener('click', openSettings);
      box.append(button);
    }
    box.hidden = false;
  }

  function toast(message) {
    document.querySelector('.toast')?.remove();
    const node = el('div', 'toast', message, { role: 'status' });
    document.body.append(node);
    window.setTimeout(() => node.remove(), 4200);
  }

  function openSettings() { $('settings-dialog').showModal(); }

  function setPending(pending, action = 'research') {
    state.pending = pending;
    $('research-button').disabled = pending;
    $('demo-button').disabled = pending;
    $('report').querySelectorAll('[data-request-action]').forEach((button) => { button.disabled = pending; });
    const status = $('request-status');
    if (state.elapsedTimer) window.clearInterval(state.elapsedTimer);
    if (!pending) { status.hidden = true; status.replaceChildren(); return; }
    const start = Date.now();
    const heading = el('div', '', action === 'demo' ? t('status.demo_loading') : action === 'summary' ? t('status.summary_loading') : t('status.research_loading'));
    const note = el('p', '', action === 'demo' ? t('status.demo_note') : t('status.pending_note'));
    const text = el('div', '');
    text.append(heading, note);
    const cancel = el('button', 'button button-secondary', t('status.cancel'), { type: 'button' });
    cancel.addEventListener('click', () => {
      state.controller?.abort();
      toast(t('status.cancelled'));
    });
    status.replaceChildren(el('span', 'spinner', '', { 'aria-hidden': 'true' }), text, cancel);
    status.hidden = false;
    state.elapsedTimer = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - start) / 1000);
      const elapsed = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
      note.textContent = t(action === 'demo' ? 'status.demo_elapsed' : 'status.elapsed', { elapsed });
    }, 1000);
  }

  async function requestJSON(path, options, action) {
    clearError();
    const operation = ++state.operationId;
    const controller = new AbortController();
    state.controller = controller;
    setPending(true, action);
    try {
      const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', 'Accept-Language': I18n.getLanguage(), ...(options?.headers || {}) }, signal: controller.signal, cache: 'no-store' });
      const raw = await response.text();
      let payload;
      try { payload = JSON.parse(raw); } catch { throw new Error(t('errors.response', { status: response.status })); }
      if (!response.ok) {
        const detail = typeof payload.detail === 'string' ? payload.detail : typeof payload.error?.message === 'string' ? payload.error.message : typeof payload.message === 'string' ? payload.message : typeof payload.error === 'string' ? payload.error : t('errors.http', { status: response.status });
        throw new Error(detail.slice(0, 1400));
      }
      if (!payload || typeof payload !== 'object' || !Array.isArray(payload.evidence) || !Array.isArray(payload.claims)) throw new Error(t('errors.report_format'));
      return payload;
    } catch (error) {
      if (error.name !== 'AbortError') showError(error instanceof TypeError ? t('errors.network') : error.message || t('errors.request'));
      return null;
    } finally {
      if (state.operationId === operation) { state.controller = null; setPending(false); }
    }
  }

  function installReport(report, mode, isDemo, isImported = false) {
    state.report = mode === 'evidence-only' ? evidenceProjection(report) : { ...report, mode: 'ai-summary' };
    state.isDemo = isDemo;
    state.isImported = isImported;
    state.filter = null;
    state.mapClaim = null;
    document.querySelector(`input[name="mode"][value="${mode}"]`).checked = true;
    if (['brief', 'standard', 'deep'].includes(report.depth)) $('research-depth').value = report.depth;
    renderReport();
    $('report').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function submitResearch(event) {
    event.preventDefault();
    if (state.pending) return;
    const topic = $('topic').value.trim();
    if (topic.length < 3) { showError(t('errors.topic')); $('topic').focus(); return; }
    let ai;
    try { ai = validateAI(); } catch (error) { showError(error.message, true); return; }
    const search = getSearchSettings();
    if (!searchCredentialReady(ai)) { showError(t('errors.search_key'), true); return; }
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const depth = $('research-depth').value;
    saveSettings();
    let sourceSettings;
    try { sourceSettings = Workspace.getSourceRequest(); } catch (error) { showError(error.message); return; }
    const report = await requestJSON('/api/research', { method: 'POST', body: JSON.stringify({ topic, mode, depth, language: I18n.getLanguage(), ai, search, ...sourceSettings, include_screenshots: $('include-screenshots').checked, adaptive_search: $('adaptive-search').checked }) }, 'research');
    if (report) installReport(report, mode, false);
  }

  async function loadDemo() {
    if (state.pending) return;
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const report = await requestJSON(`/api/demo?mode=${encodeURIComponent(mode)}&language=${encodeURIComponent(I18n.getLanguage())}`, { method: 'GET' }, 'demo');
    if (report) installReport(report, mode, true);
  }

  function askSummary() {
    if (state.pending || !state.report) return;
    let ai;
    try { ai = validateAI(); } catch (error) { showError(error.message, true); $('error-message').scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
    const destination = $('summary-destination');
    destination.replaceChildren(el('span', '', t('summary.destination')), el('strong', '', ai.base_url || (state.capabilities.configured?.ai_base_url ? t('summary.env_endpoint') : t('summary.default_endpoint'))), el('span', '', t('summary.model', { model: ai.model || t('summary.env_model') })));
    $('summary-dialog').showModal();
  }

  async function generateSummary() {
    $('summary-dialog').close();
    if (state.pending || !state.report) return;
    let ai;
    try { ai = validateAI(); } catch (error) { showError(error.message, true); return; }
    const isDemo = state.isDemo;
    const isImported = state.isImported;
    const report = await requestJSON('/api/summarize', { method: 'POST', body: JSON.stringify({ report: evidenceProjection(state.report), ai, language: I18n.getLanguage() }) }, 'summary');
    if (report) { installReport(report, 'ai-summary', isDemo, isImported); toast(t('report.summary_added')); }
  }

  function normalizeImport(input) {
    if (!input || typeof input !== 'object' || Array.isArray(input) || !['1.0', '1.1'].includes(input.schema_version)) throw new Error(t('errors.schema'));
    const string = (value, fallback = '', max = 12000) => {
      if (value == null) return fallback;
      if (typeof value !== 'string' || Array.from(value).length > max) throw new Error(t('errors.import_text'));
      return value;
    };
    const list = (value, map, max = 80) => {
      if (value == null) return [];
      if (!Array.isArray(value) || value.length > max) throw new Error(t('errors.import_list'));
      return value.map(map);
    };
    const strings = (value, max = 40) => list(value, (item) => string(item), max);
    const refs = (value, max = 24) => list(value, (id) => {
      if (typeof id !== 'string' || !/^[ECR][1-9]\d*$/.test(id)) throw new Error(t('errors.import_ref'));
      return id;
    }, max);
    const object = (value) => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(t('errors.import_object'));
      return value;
    };
    const id = (value, prefix) => {
      if (typeof value !== 'string' || !new RegExp(`^${prefix}[1-9]\\d*$`).test(value)) throw new Error(t('errors.import_id', { prefix }));
      return value;
    };
    const url = (value, capture = false) => {
      const raw = string(value);
      if (raw && !safeUrl(raw, capture)) throw new Error(t('errors.import_url'));
      return raw;
    };
    const enumValue = (value, values, fallback) => {
      if (value == null && fallback !== undefined) return fallback;
      if (!values.includes(value)) throw new Error(t('errors.import_metadata'));
      return value;
    };
    const hash = (value) => {
      if (typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value)) throw new Error(t('errors.import_fingerprint'));
      return value;
    };
    const citations = (value, max = 24) => list(value, raw => {
      const citation = object(raw);
      const item = { evidence_id: id(citation.evidence_id, 'E'), quote: string(citation.quote, '', 2000), semantic_support: enumValue(citation.semantic_support, ['unverified'], 'unverified') };
      if (!item.quote.trim()) throw new Error(t('errors.import_citation'));
      if (citation.verification != null) item.verification = enumValue(citation.verification, ['exact_match']);
      if (citation.locator != null) {
        const locator = object(citation.locator);
        for (const key of ['start', 'end', 'match_count']) if (!Number.isInteger(locator[key]) || locator[key] < (key === 'start' ? 0 : 1) || locator[key] > 5000) throw new Error(t('errors.import_citation'));
        item.locator = { start: locator.start, end: locator.end, prefix: string(locator.prefix, '', 80), suffix: string(locator.suffix, '', 80), excerpt_sha256: hash(locator.excerpt_sha256), match_count: locator.match_count, coordinate_system: enumValue(locator.coordinate_system, ['unicode_codepoints'], 'unicode_codepoints') };
      }
      if ((input.schema_version === '1.1' && (!item.locator || item.verification !== 'exact_match')) || (item.verification === 'exact_match' && !item.locator)) throw new Error(t('errors.import_citation'));
      return item;
    }, max);
    const report = {
      schema_version: input.schema_version, topic: string(input.topic, '', 6000), mode: input.mode === 'ai-summary' ? 'ai-summary' : 'evidence-only',
      generated_at: string(input.generated_at), scope: string(input.scope, '', 4000), limitations: strings(input.limitations, 80), questions: strings(input.questions, 20)
    };
    if (!report.topic.trim()) throw new Error(t('errors.import_topic'));
    for (const key of ['language', 'summary_language']) {
      if (input[key] != null && !I18n.languages.includes(input[key])) throw new Error(t('errors.language'));
    }
    report.language = input.language || 'zh-CN';
    if (report.mode === 'ai-summary' && input.summary_language) report.summary_language = input.summary_language;
    if (input.source_policy != null && !['balanced', 'preferred-only'].includes(input.source_policy)) throw new Error(t('sources.invalid'));
    report.source_policy = input.source_policy || 'balanced';
    report.preferred_sources = list(input.preferred_sources, raw => { const item = object(raw); return { url: url(item.url), label: string(item.label, '', 300) }; }, 6);
    if (input.depth != null) {
      if (!['brief', 'standard', 'deep'].includes(input.depth)) throw new Error(t('errors.import_depth'));
      report.depth = input.depth;
    }
    report.claims = list(input.claims, (raw) => {
      const claim = object(raw);
      const item = { id: id(claim.id, 'C'), text: string(claim.text, '', 1600), kind: string(claim.kind, 'fact', 100), citations: citations(claim.citations) };
      if (!item.text || !['fact', 'causal', 'prediction', 'value', 'mixed'].includes(item.kind)) throw new Error(t('errors.import_claim'));
      if (report.mode === 'ai-summary') { if (claim.verdict != null) item.verdict = string(claim.verdict); if (claim.analysis != null) item.analysis = string(claim.analysis); }
      return item;
    }, 12);
    if (!report.claims.length) throw new Error(t('errors.import_no_claim'));
    report.evidence = list(input.evidence, (raw) => {
      const source = object(raw);
      return {
        id: id(source.id, 'E'), title: string(source.title, '', 1000), url: url(source.url), publisher: string(source.publisher, '', 300), published_at: source.published_at == null ? null : string(source.published_at),
        retrieved_at: string(source.retrieved_at), source_type: string(source.source_type, 'unknown', 100), content_kind: string(source.content_kind, 'snippet', 100), excerpt: string(source.excerpt, '', 5000),
        context: string(source.context, '', 6000), source_family: string(source.source_family, '', 400), status: string(source.status, 'unavailable', 100), claim_ids: refs(source.claim_ids, 12),
        document_format: enumValue(source.document_format, ['unknown', 'html', 'text', 'pdf', 'csv', 'tsv'], 'unknown'),
        source_family_method: enumValue(source.source_family_method, ['domain', 'exact_content', 'exact_excerpt', 'near_duplicate'], 'domain'),
        source_family_evidence_ids: refs(source.source_family_evidence_ids), content_sha256: source.content_sha256 == null ? null : hash(source.content_sha256),
        excerpt_metadata: source.excerpt_metadata == null ? null : { sha256: hash(object(source.excerpt_metadata).sha256), coordinate_system: enumValue(source.excerpt_metadata.coordinate_system, ['unicode_codepoints'], 'unicode_codepoints') },
        screenshots: list(source.screenshots, (rawCapture) => {
          const capture = object(rawCapture);
          return { url: url(capture.url, true), captured_at: string(capture.captured_at), sha256: string(capture.sha256, '', 64), source_url: url(capture.source_url) };
        }, 3)
      };
    }, 24);
    report.links = list(input.links, (raw) => {
      const link = object(raw);
      const item = { from: id(link.from, 'E'), to: id(link.to, 'C'), relation: string(link.relation, 'relevant_to', 100) };
      if (report.mode === 'ai-summary' && link.note != null) item.note = string(link.note);
      return item;
    }, 120);
    report.timeline = list(input.timeline, (raw) => {
      const item = object(raw);
      return { date: string(item.date), title: string(item.title), detail: string(item.detail), evidence_ids: refs(item.evidence_ids), citations: citations(item.citations) };
    }, 30);
    report.charts = list(input.charts, (raw) => {
      const chart = object(raw);
      if (!['bar', 'line'].includes(chart.kind)) throw new Error(t('errors.import_chart'));
      return { title: string(chart.title), unit: string(chart.unit), kind: chart.kind, note: string(chart.note), points: list(chart.points, (rawPoint) => {
        const point = object(rawPoint);
        if (point.value != null && (typeof point.value !== 'number' || !Number.isFinite(point.value))) throw new Error(t('errors.import_number'));
        const item = { label: string(point.label), value: point.value ?? null, evidence_ids: refs(point.evidence_ids), citations: citations(point.citations, 100) };
        if (point.calculation != null) {
          const calculation = object(point.calculation);
          item.calculation = { operation: string(calculation.operation), source_quotes: strings(calculation.source_quotes, 100), description: string(calculation.description) };
        }
        return item;
      }, 40) };
    }, 5);
    report.comparisons = list(input.comparisons, (raw) => {
      const item = object(raw);
      return { case: string(item.case), date: string(item.date), similarities: string(item.similarities), differences: string(item.differences), limits: string(item.limits), evidence_ids: refs(item.evidence_ids), citations: citations(item.citations) };
    }, 10);
    report.observations = list(input.observations, (raw) => {
      const item = object(raw);
      if (!['data', 'logic', 'history'].includes(item.kind)) throw new Error(t('errors.import_observation'));
      const observation = { kind: item.kind, text: string(item.text, '', 5000), claim_ids: refs(item.claim_ids, 12), evidence_ids: refs(item.evidence_ids), citations: citations(item.citations) };
      if (!observation.text.trim() || !observation.claim_ids.length || !observation.evidence_ids.length) throw new Error(t('errors.import_premises'));
      return observation;
    }, 40);
    report.search_log = list(input.search_log, (raw) => {
      const query = object(raw);
      if (query.result_count != null && (!Number.isInteger(query.result_count) || query.result_count < 0 || query.result_count > 20)) throw new Error(t('errors.import_count'));
      return { query: string(query.query, '', 600), intent: string(query.intent), provider: string(query.provider), result_count: query.result_count ?? 0, ran_at: string(query.ran_at), round: enumValue(query.round, ['initial', 'supplemental'], 'initial'), gap_claim_ids: refs(query.gap_claim_ids, 12) };
    }, 10);
    report.retrieval_gaps = list(input.retrieval_gaps, raw => {
      const gap = object(raw);
      if (typeof gap.attempted !== 'boolean') throw new Error(t('errors.import_metadata'));
      return { claim_id: id(gap.claim_id, 'C'), reason: enumValue(gap.reason, ['no_keyword_match', 'limited_families']), query: string(gap.query, '', 600), attempted: gap.attempted };
    }, 12);
    report.reasoning = report.mode === 'ai-summary' ? list(input.reasoning, (raw) => {
      const item = object(raw);
      return { id: id(item.id, 'R'), premise_ids: refs(item.premise_ids, 48), claim_id: id(item.claim_id, 'C'), text: string(item.text), kind: string(item.kind), citations: citations(item.citations) };
    }, 30) : [];
    if (report.mode === 'ai-summary' && input.summary != null) {
      const summary = object(input.summary);
      report.summary = { text: string(summary.text), verdict: string(summary.verdict), caveats: strings(summary.caveats, 20), evidence_ids: refs(summary.evidence_ids), citations: citations(summary.citations) };
    }
    const claimIDs = new Set(report.claims.map((claim) => claim.id));
    const sourceIDs = new Set(report.evidence.map((source) => source.id));
    const reasoningIDs = new Set(report.reasoning.map((step) => step.id));
    if (claimIDs.size !== report.claims.length || sourceIDs.size !== report.evidence.length || reasoningIDs.size !== report.reasoning.length) throw new Error(t('errors.import_duplicates'));
    const check = (ids, allowed) => { if (asArray(ids).some((value) => !allowed.has(value))) throw new Error(t('errors.import_dangling')); };
    report.evidence.forEach((source) => { check(source.claim_ids, claimIDs); check(source.source_family_evidence_ids, sourceIDs); });
    report.links.forEach((link) => { check([link.from], sourceIDs); check([link.to], claimIDs); });
    [...report.timeline, ...report.comparisons, ...report.observations, ...report.charts.flatMap((chart) => chart.points), ...(report.summary ? [report.summary] : [])].forEach((item) => check(item.evidence_ids, sourceIDs));
    report.observations.forEach((item) => check(item.claim_ids, claimIDs));
    report.reasoning.forEach((step) => { check(step.premise_ids, new Set([...sourceIDs, ...reasoningIDs])); check([step.claim_id], claimIDs); });
    report.search_log.forEach(query => check(query.gap_claim_ids, claimIDs));
    report.retrieval_gaps.forEach(gap => check([gap.claim_id], claimIDs));
    const citedItems = [...report.claims, ...report.timeline, ...report.comparisons, ...report.observations, ...report.charts.flatMap(chart => chart.points), ...report.reasoning, ...(report.summary ? [report.summary] : [])];
    citedItems.forEach(item => {
      const seen = new Set();
      item.citations.forEach(citation => {
        const source = report.evidence.find(source => source.id === citation.evidence_id);
        const key = JSON.stringify([citation.evidence_id, citation.quote]);
        if (seen.has(key) || !citationPosition(citation, source) || (item.evidence_ids && !item.evidence_ids.includes(citation.evidence_id))) throw new Error(t('errors.import_citation'));
        seen.add(key);
      });
    });
    return report.mode === 'evidence-only' ? evidenceProjection(report) : report;
  }

  async function importReport(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    clearError();
    try {
      if (state.pending) throw new Error(t('errors.import_pending'));
      if (file.size > 2 * 1024 * 1024) throw new Error(t('errors.import_size'));
      let input;
      try { input = JSON.parse(await file.text()); } catch { throw new Error(t('errors.import_json')); }
      const report = normalizeImport(input);
      installReport(report, report.mode, false, true);
      toast(t('report.imported'));
    } catch (error) { showError(error.message || t('errors.import')); }
    finally { event.target.value = ''; }
  }

  async function loadCapabilities() {
    try {
      const response = await fetch('/api/health', { cache: 'no-store' });
      if (!response.ok) return;
      const health = await response.json();
      if (health && typeof health.configured === 'object') state.capabilities = health;
      const configured = state.capabilities.configured || {};
      const defaultSearch = health.default_search_provider;
      if (['deepseek', 'tavily', 'brave'].includes(defaultSearch) && !configured[$('search-provider').value] && configured[defaultSearch] && !getSearchSettings().api_key) $('search-provider').value = defaultSearch;
      if (configured.ai_model) $('ai-model').placeholder = t('settings.env_model');
      if (configured.ai_key) $('ai-key').placeholder = t('settings.env_key');
      if (configured[$('search-provider').value]) $('search-key').placeholder = t('settings.env_key');
      updateConnectionStatus();
    } catch { /* The next real request reports connection errors without inventing a fallback. */ }
  }

  function sourceReferences(ids, className = '') {
    const container = el('span', className);
    asArray(ids).forEach((id, index) => {
      if (index) container.append(document.createTextNode(' '));
      const button = el('button', 'source-ref', id, { type: 'button', 'aria-label': t('source.focus', { id: textValue(id) }) });
      button.addEventListener('click', () => focusSource(id));
      container.append(button);
    });
    return container;
  }

  function sourceDomId(id) { return `source-${textValue(id).replace(/[^a-zA-Z0-9_-]/g, '_')}`; }

  function renderCitations(citations) {
    const items = asArray(citations);
    if (!items.length) return el('p', 'citation-missing', t('citation.missing'));
    const details = el('details', 'citation-details');
    details.append(el('summary', '', t('citation.show', { count: items.length })), el('p', 'citation-disclosure', t('citation.disclosure')));
    items.forEach(citation => {
      const source = asArray(state.report?.evidence).find(source => source.id === citation.evidence_id);
      const position = citationPosition(citation, source);
      const item = el('div', 'citation-item');
      const meta = el('div', 'citation-meta');
      meta.append(sourceReferences([citation.evidence_id]), el('span', '', t(position ? 'citation.matched' : 'citation.unmatched')));
      item.append(meta, el('blockquote', 'citation-quote', citation.quote));
      if (position) {
        const context = el('p', 'citation-context');
        context.append(document.createTextNode(position.prefix), el('mark', '', citation.quote), document.createTextNode(position.suffix));
        const contextDetails = el('details', 'citation-context-details');
        contextDetails.append(el('summary', '', t('citation.context')), context);
        item.append(contextDetails);
        if (position.match_count > 1) item.append(el('p', 'citation-disclosure', t('citation.repeated', { count: position.match_count })));
        const locate = actionButton(t('citation.locate'), () => focusCitation(citation), 'citation-locate');
        locate.setAttribute('data-citation-source', citation.evidence_id);
        item.append(locate);
      }
      if (source) item.append(externalLink(t('citation.original'), source.url, 'citation-original'));
      details.append(item);
    });
    return details;
  }

  function focusCitation(citation) {
    const source = asArray(state.report?.evidence).find(source => source.id === citation.evidence_id);
    const position = citationPosition(citation, source);
    if (!position) { toast(t('citation.unmatched')); return; }
    focusSource(citation.evidence_id);
    const excerpt = $(`${sourceDomId(citation.evidence_id)}-excerpt`);
    if (!excerpt) return;
    const chars = Array.from(source.excerpt);
    excerpt.replaceChildren(document.createTextNode(chars.slice(0, position.start).join('')), el('mark', 'citation-highlight', citation.quote), document.createTextNode(chars.slice(position.end).join('')));
    excerpt.scrollIntoView({ behavior: 'smooth', block: 'center' });
    excerpt.focus({ preventScroll: true });
    toast(t('citation.located'));
  }

  function focusSource(id) {
    const exists = asArray(state.report?.evidence).some((source) => source.id === id);
    if (!exists) { toast(t('source.missing', { id: textValue(id) })); return; }
    let target = $(sourceDomId(id));
    if (!target && state.filter) { state.filter = null; renderEvidenceArea(); target = $(sourceDomId(id)); }
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.focus({ preventScroll: true });
    target.classList.add('flash');
    window.setTimeout(() => target.classList.remove('flash'), 1800);
  }

  function focusClaim(id) {
    state.filter = state.filter === id ? null : id;
    renderEvidenceArea();
    $('claims').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function sectionHeading(index, title, subtitle = '') {
    const heading = el('div', 'section-heading');
    const group = el('div', 'section-title-group');
    group.append(el('span', 'section-index', index), el('h2', '', title));
    heading.append(group, el('span', 'section-subtitle', subtitle));
    return heading;
  }

  function reportSection(id, index, title, subtitle) {
    const section = el('section', 'report-section', '', { id, 'aria-label': title });
    section.append(sectionHeading(index, title, subtitle));
    return section;
  }

  function actionButton(text, handler, className = 'button button-secondary', requestAction = false) {
    const button = el('button', className, text, { type: 'button' });
    if (requestAction) { button.setAttribute('data-request-action', ''); button.disabled = state.pending; }
    button.addEventListener('click', handler);
    return button;
  }

  function renderReport() {
    const report = state.report;
    if (!report) return;
    const aiMode = report.mode === 'ai-summary';
    const shell = el('article', 'report-shell');
    const topline = el('div', 'report-topline');
    const badges = el('div', '');
    if (state.isDemo) badges.append(el('span', 'demo-badge', t('report.demo_badge')));
    if (state.isImported) badges.append(el('span', 'demo-badge', t('report.import_badge')));
    badges.append(el('span', 'mode-badge', aiMode ? t('report.ai_mode') : t('report.evidence_mode')));
    topline.append(el('span', 'section-kicker', t('report.kicker')), badges);
    shell.append(topline, el('h2', 'report-title', report.topic || t('report.topic_fallback')));
    const meta = el('div', 'report-meta');
    meta.append(el('span', '', t('report.created', { date: dateLabel(report.generated_at, true) })), el('span', '', t('report.claim_count', { count: asArray(report.claims).length })), el('span', '', t('report.source_count', { count: asArray(report.evidence).length })));
    const families = new Set(asArray(report.evidence).map((source) => source.source_family).filter(Boolean));
    meta.append(el('span', '', t('report.family_count', { count: families.size })));
    if (report.depth) meta.append(el('span', '', t('report.depth', { depth: depthLabel(report.depth) })));
    shell.append(meta);
    shell.append(el('p', 'report-language', t('language.report', { language: I18n.languages.includes(report.language) ? t(`language.${report.language}`) : t('language.unknown') })));
    if (aiMode && report.summary_language) shell.append(el('p', 'report-language', t('language.summary', { language: t(`language.${report.summary_language}`) })));
    if (report.preferred_sources?.length) shell.append(el('p', 'report-language', `${t(report.source_policy === 'preferred-only' ? 'sources.restricted' : 'sources.wide')}: ${report.preferred_sources.map(source => source.label || hostLabel(source.url)).join(' · ')}`));
    if (report.scope) shell.append(el('p', 'report-scope', t('report.scope', { scope: textValue(report.scope) })));
    const actions = el('div', 'report-actions');
    if (aiMode) actions.append(actionButton(t('report.only_evidence'), () => {
      state.report = evidenceProjection(state.report);
      state.filter = null;
      document.querySelector('input[name="mode"][value="evidence-only"]').checked = true;
      renderReport();
      toast(t('report.remove_verdict'));
    }));
    else actions.append(actionButton(t('report.generate_summary'), askSummary, 'button button-secondary', true));
    const exports = el('div', 'export-group');
    const htmlExportButton = actionButton(t('report.export_html'), () => exportHTML());
    htmlExportButton.setAttribute('data-action', 'export-html');
    exports.append(actionButton(t('report.export_json'), () => exportJSON()), htmlExportButton);
    actions.append(exports);
    shell.append(actions);
    if (state.isDemo) {
      const demoNotice = el('div', 'report-notice');
      demoNotice.append(el('p', '', t('report.demo_notice')), el('p', '', t('report.demo_date', { date: dateLabel(report.generated_at, true) })));
      shell.append(demoNotice);
    }
    if (state.isImported) shell.append(el('div', 'report-notice', t('report.import_notice')));
    if (aiMode && report.summary) shell.append(renderSummary(report.summary));
    shell.append(Workspace.renderMap(report, { selected: state.mapClaim, select: id => { state.mapClaim = id; renderReport(); $('evidence-map').scrollIntoView({ block: 'start' }); }, focusSource, relationLabel }));
    const claims = reportSection('claims', '02', t('section.claims'), t('section.claims_help'));
    claims.append(el('div', '', '', { id: 'evidence-area' }));
    shell.append(claims);
    shell.append(renderObservations(report));
    if (aiMode && asArray(report.reasoning).length) shell.append(renderReasoning(report.reasoning));
    shell.append(renderData(report), renderHistory(report), renderQuestions(report), renderSearchLog(report));
    shell.append(el('div', 'report-end', t('report.end')));
    $('report').replaceChildren(shell);
    $('report').hidden = false;
    $('empty-state').hidden = true;
    document.body.classList.add('has-report');
    $('report-indicator').textContent = state.isDemo ? t('report.demo_indicator') : state.isImported ? t('report.import_indicator') : t('report.current_indicator');
    $('nav-evidence-count').textContent = String(asArray(report.evidence).length).padStart(2, '0');
    renderEvidenceArea();
  }

  function kindLabel(kind) {
    return ({ fact: t('claim.fact'), factual: t('claim.fact'), prediction: t('claim.prediction'), value: t('claim.value'), causal: t('claim.causal'), mixed: t('claim.mixed'), comparison: t('claim.comparison'), opinion: t('claim.opinion'), hypothesis: t('claim.hypothesis') })[kind] || textValue(kind) || t('claim.default');
  }

  function depthLabel(depth) {
    return ({ brief: t('depth.brief'), standard: t('depth.standard'), deep: t('depth.deep') })[depth] || t('language.unknown');
  }

  function relationLabel(relation) {
    return ({ supports: t('relation.supports'), support: t('relation.supports'), refutes: t('relation.refutes'), refute: t('relation.refutes'), contradicts: t('relation.contradicts'), contradict: t('relation.contradicts'), context: t('relation.context'), contextualizes: t('relation.contextualizes'), relevant_to: t('relation.related'), related: t('relation.related'), qualifies: t('relation.qualifies'), mixed: t('relation.mixed') })[relation] || textValue(relation) || t('relation.default');
  }

  function renderEvidenceArea() {
    const report = state.report;
    const area = $('evidence-area');
    if (!report || !area) return;
    const fragment = document.createDocumentFragment();
    const claims = asArray(report.claims);
    const grid = el('div', 'claim-grid');
    claims.forEach((claim) => {
      const card = el('button', `claim-card${state.filter === claim.id ? ' active' : ''}`, '', { type: 'button', 'aria-pressed': state.filter === claim.id, 'aria-label': t('claim.aria', { id: textValue(claim.id), text: textValue(claim.text) }) });
      const content = el('div', 'claim-content');
      content.append(el('p', 'claim-text', claim.text), el('div', 'claim-kind', kindLabel(claim.kind)));
      if (report.mode === 'ai-summary') {
        if (claim.verdict) content.append(el('span', 'claim-verdict', t('claim.verdict', { verdict: textValue(claim.verdict) })));
        if (claim.analysis) content.append(el('div', 'claim-analysis', claim.analysis));
      }
      card.append(el('span', 'claim-id', claim.id), content);
      card.addEventListener('click', () => { state.filter = state.filter === claim.id ? null : claim.id; renderEvidenceArea(); });
      const group = el('div', 'claim-group');
      group.append(card, renderCitations(claim.citations));
      grid.append(group);
    });
    if (claims.length) fragment.append(grid);
    else fragment.append(el('p', 'no-data', t('claim.no_claims')));
    const relevant = (source) => !state.filter || asArray(source.claim_ids).includes(state.filter) || asArray(report.links).some((link) => link.from === source.id && link.to === state.filter);
    const sources = asArray(report.evidence).filter(relevant);
    const filterRow = el('div', 'filter-row');
    const selectedClaim = claims.find((claim) => claim.id === state.filter);
    filterRow.append(el('span', '', state.filter ? t('claim.filtered', { id: state.filter, count: sources.length }) : t('claim.all_sources', { count: sources.length })));
    if (state.filter) filterRow.append(actionButton(t('claim.show_all'), () => { state.filter = null; renderEvidenceArea(); }, ''));
    else filterRow.append(el('span', '', t('claim.family_note')));
    fragment.append(filterRow);
    const chainList = el('div', 'chain-list', '', { 'aria-label': t('claim.chain_aria') });
    asArray(report.links).filter((link) => !state.filter || link.to === state.filter).forEach((link) => {
      const item = el('div', 'chain-item');
      const sourceButton = el('button', 'source-ref', link.from, { type: 'button', 'aria-label': t('source.focus_evidence', { id: textValue(link.from) }) });
      sourceButton.addEventListener('click', () => focusSource(link.from));
      const claimButton = el('button', '', link.to, { type: 'button', 'aria-label': t('claim.focus', { id: textValue(link.to) }) });
      claimButton.addEventListener('click', () => focusClaim(link.to));
      item.append(sourceButton, el('span', 'chain-relation', `— ${relationLabel(link.relation)} →`), claimButton);
      if (report.mode === 'ai-summary' && link.note) item.append(el('span', 'chain-note', link.note));
      chainList.append(item);
    });
    if (chainList.children.length) fragment.append(chainList);
    const list = el('div', 'evidence-list');
    sources.forEach((source) => list.append(renderSource(source)));
    if (!sources.length) list.append(el('p', 'no-data', selectedClaim ? t('claim.no_linked_sources') : t('claim.no_sources')));
    fragment.append(list);
    area.replaceChildren(fragment);
  }

  function sourceTypeLabel(type) {
    return ({ primary: t('source.primary'), secondary: t('source.secondary'), unknown: t('source.unknown'), official: t('source.official'), academic: t('source.academic'), research: t('source.research'), news: t('source.news'), government: t('source.government'), organization: t('source.organization'), dataset: t('source.dataset'), archive: t('source.archive') })[type] || textValue(type) || t('source.type_missing');
  }

  function contentKindLabel(kind) {
    return ({ full_text: t('source.body'), fulltext: t('source.body'), body: t('source.body'), page: t('source.body'), webpage: t('source.body'), html: t('source.body'), pdf: t('source.pdf'), search_extract: t('source.extract'), search_snippet: t('source.snippet'), 'search-snippet': t('source.snippet'), snippet: t('source.snippet'), snippet_only: t('source.snippet'), extracted_text: t('source.extracted') })[kind] || textValue(kind) || t('source.content_missing');
  }

  function statusLabel(status) {
    return ({ fetched: t('source.read'), retrieved: t('source.read'), accessible: t('source.accessible'), available: t('source.accessible'), success: t('source.read'), ok: t('source.read'), blocked: t('source.blocked'), failed: t('source.failed'), inaccessible: t('source.unavailable'), unavailable: t('source.unavailable'), snippet_only: t('source.snippet_only'), not_fetched: t('source.not_read'), partial: t('source.partial') })[status] || textValue(status) || t('source.status_missing');
  }

  function documentFormatLabel(format) {
    return ['unknown', 'html', 'text', 'pdf', 'csv', 'tsv'].includes(format) ? t(`source.format_${format}`) : textValue(format);
  }

  function familyMethodLabel(method) {
    return ['domain', 'exact_content', 'exact_excerpt', 'near_duplicate'].includes(method) ? t(`source.method_${method}`) : textValue(method);
  }

  function renderSource(source) {
    const card = el('article', 'source-card', '', { id: sourceDomId(source.id), tabindex: '-1', 'aria-label': t('source.aria', { id: textValue(source.id), title: textValue(source.title) }) });
    const top = el('div', 'source-topline');
    const labels = el('div', 'source-labels');
    const snippet = /snippet|search_extract|摘要/i.test(textValue(source.content_kind));
    labels.append(el('span', 'evidence-id', source.id), el('span', 'source-type', sourceTypeLabel(source.source_type)), el('span', `content-badge${snippet ? ' snippet' : ''}`, contentKindLabel(source.content_kind)));
    if (source.document_format && source.document_format !== 'unknown') labels.append(el('span', 'document-format', documentFormatLabel(source.document_format)));
    top.append(labels, el('span', 'source-status', statusLabel(source.status)));
    const title = el('h3', '');
    const link = externalLink(source.title || source.url || t('source.unnamed'), source.url);
    if (link.tagName === 'A') link.append(el('span', 'external-mark', '↗', { 'aria-hidden': 'true' }));
    title.append(link);
    const meta = el('div', 'source-meta');
    meta.append(el('span', '', source.publisher || t('source.publisher_missing')), externalLink(hostLabel(source.url), source.url), el('span', '', t('source.published', { date: dateLabel(source.published_at) })), el('span', '', t('source.retrieved', { date: dateLabel(source.retrieved_at, true) })));
    card.append(top, title, meta);
    if (source.excerpt) card.append(el('blockquote', 'source-excerpt', source.excerpt, { id: `${sourceDomId(source.id)}-excerpt`, tabindex: '-1', 'aria-label': t('citation.excerpt', { id: source.id }) }));
    else card.append(el('p', 'source-context', t('source.no_excerpt')));
    if (source.context) card.append(el('p', 'source-context', source.context));
    const bottom = el('div', 'source-bottom');
    bottom.append(el('span', 'source-family', t('source.family', { family: textValue(source.source_family) || t('common.unknown') })));
    const references = el('span', 'source-claim-refs', t('source.claims'));
    asArray(source.claim_ids).forEach((id) => {
      const button = el('button', '', id, { type: 'button' });
      button.addEventListener('click', () => focusClaim(id));
      references.append(button);
    });
    if (asArray(source.claim_ids).length) bottom.append(references);
    card.append(bottom);
    const provenance = el('details', 'provenance-details');
    provenance.append(el('summary', '', t('source.provenance')));
    provenance.append(el('p', '', t('source.family_method', { method: familyMethodLabel(source.source_family_method || 'domain') })), el('p', 'citation-disclosure', t('source.family_heuristic')));
    if (asArray(source.source_family_evidence_ids).length) { const related = el('p', '', t('source.family_related')); related.append(sourceReferences(source.source_family_evidence_ids)); provenance.append(related); }
    provenance.append(el('p', '', t('source.format', { format: documentFormatLabel(source.document_format || 'unknown') })));
    if (source.content_sha256) provenance.append(el('p', 'source-fingerprint', t('source.content_hash', { hash: source.content_sha256 })));
    if (source.excerpt_metadata?.sha256) provenance.append(el('p', 'source-fingerprint', t('source.excerpt_hash', { hash: source.excerpt_metadata.sha256 })));
    provenance.append(el('p', 'citation-disclosure', t(state.isImported ? 'source.import_fingerprint' : 'source.fingerprint_help')));
    card.append(provenance);
    const captures = asArray(source.screenshots).filter((capture) => safeUrl(capture.url, true));
    if (captures.length) {
      const details = el('details', '');
      details.append(el('summary', '', t('capture.show', { count: captures.length })));
      const captureGrid = el('div', 'capture-grid');
      captures.forEach((capture) => {
        const figure = el('figure', '');
        const url = safeUrl(capture.url, true);
        const anchor = el('a', '', '', { href: url, target: '_blank', rel: 'noopener noreferrer', 'aria-label': t('capture.open', { id: textValue(source.id) }) });
        const image = el('img', '', '', { src: url, alt: t('capture.alt', { id: textValue(source.id), title: textValue(source.title) }), loading: 'lazy' });
        image.addEventListener('error', () => { image.hidden = true; anchor.append(el('span', 'plain-message', t('capture.failed'))); }, { once: true });
        anchor.append(image);
        const caption = el('figcaption', '');
        caption.append(el('span', '', t('capture.date', { date: dateLabel(capture.captured_at, true) })), el('span', '', `SHA-256 ${textValue(capture.sha256) || t('common.not_provided')}`));
        const sourceURL = externalLink(t('capture.origin', { url: textValue(capture.source_url || source.url) }), capture.source_url || source.url);
        caption.append(sourceURL);
        figure.append(anchor, caption);
        captureGrid.append(figure);
      });
      details.append(captureGrid);
      card.append(details);
    }
    return card;
  }

  function renderSummary(summary) {
    const section = el('section', 'summary-panel', '', { 'aria-label': t('summary.aria') });
    section.append(el('span', 'section-kicker', t('summary.report_kicker')), el('h2', '', summary.verdict || t('summary.fallback')));
    if (summary.text) section.append(el('p', '', summary.text));
    const refs = el('div', 'summary-evidence', t('summary.evidence'));
    refs.append(sourceReferences(summary.evidence_ids));
    if (asArray(summary.evidence_ids).length) section.append(refs);
    section.append(renderCitations(summary.citations));
    if (asArray(summary.caveats).length) {
      const caveats = el('div', 'summary-caveats');
      const list = el('ul', '');
      summary.caveats.forEach((item) => list.append(el('li', '', item)));
      caveats.append(el('h3', '', t('summary.caveats')), list);
      section.append(caveats);
    }
    return section;
  }

  function observationLabel(kind) {
    return ({ data: t('observations.data'), logic: t('observations.logic'), history: t('section.history') })[kind] || textValue(kind);
  }

  function renderReasoning(reasoning) {
    const section = reportSection('reasoning', '↳', t('section.reasoning'), t('section.reasoning_help'));
    const list = el('ol', 'reasoning-list');
    reasoning.forEach((step) => {
      const item = el('li', 'reasoning-item', '', { id: `reason-${textValue(step.id).replace(/[^a-zA-Z0-9_-]/g, '_')}` });
      const content = el('div', '');
      content.append(el('p', '', step.text));
      const premises = el('div', 'reasoning-premises', t('reasoning.premises', { kind: step.kind ? ` · ${observationLabel(step.kind)}` : '' }));
      asArray(step.premise_ids).forEach((id) => {
        if (asArray(state.report.evidence).some((source) => source.id === id)) premises.append(sourceReferences([id]));
        else {
          const anchor = el('a', 'source-ref', id, { href: `#reason-${textValue(id).replace(/[^a-zA-Z0-9_-]/g, '_')}` });
          premises.append(anchor, document.createTextNode(' '));
        }
      });
      if (step.claim_id) premises.append(document.createTextNode(t('reasoning.claim', { id: textValue(step.claim_id) })));
      content.append(premises, renderCitations(step.citations));
      item.append(el('span', 'reasoning-id', step.id), content);
      list.append(item);
    });
    section.append(list);
    return section;
  }

  function renderObservations(report) {
    const section = reportSection('observations', '↳', t('section.observations'), t('section.observations_help'));
    section.append(el('p', 'report-section-description', t('observations.intro')));
    const observations = asArray(report.observations);
    if (!observations.length) {
      section.append(el('p', 'no-data', t('observations.empty')));
      return section;
    }
    const grid = el('div', 'observation-grid');
    observations.forEach((observation) => {
      const labels = { data: ['01', t('observations.data')], logic: ['02', t('observations.logic')], history: ['03', t('section.history')] };
      const [number, label] = labels[observation.kind] || ['—', t('observations.default')];
      const card = el('article', 'observation-card');
      const heading = el('div', 'observation-heading');
      heading.append(el('span', 'observation-number', number), el('h3', '', label));
      card.append(heading, el('p', 'observation-text', observation.text));
      const footer = el('div', 'observation-footer');
      const evidence = el('div', '', t('observations.evidence'));
      if (asArray(observation.evidence_ids).length) evidence.append(sourceReferences(observation.evidence_ids));
      else evidence.append(el('span', '', t('observations.no_source')));
      footer.append(evidence);
      if (asArray(observation.claim_ids).length) {
        const claims = el('div', 'observation-claims', t('observations.claim'));
        observation.claim_ids.forEach((id) => {
          const button = el('button', '', id, { type: 'button', 'aria-label': t('observations.focus_claim', { id: textValue(id) }) });
          button.addEventListener('click', () => focusClaim(id));
          claims.append(button);
        });
        footer.append(claims);
      }
      card.append(footer, renderCitations(observation.citations));
      grid.append(card);
    });
    section.append(grid);
    return section;
  }

  function renderData(report) {
    const section = reportSection('data', '03', t('section.data'), t('section.data_help'));
    const charts = asArray(report.charts);
    if (charts.length) {
      const grid = el('div', 'data-grid');
      charts.forEach((chart, index) => grid.append(renderChart(chart, index)));
      section.append(grid);
    } else section.append(el('p', 'no-data', t('data.empty')));
    const timeline = asArray(report.timeline);
    if (timeline.length) {
      const timelineHeading = el('div', 'section-heading');
      timelineHeading.style.marginTop = '25px';
      timelineHeading.append(el('h2', '', t('timeline.title')), el('span', 'section-subtitle', t('timeline.help')));
      const list = el('div', 'timeline');
      timeline.forEach((event) => {
        const row = el('article', 'timeline-item');
        const content = el('div', '');
        content.append(el('h3', '', event.title), el('p', '', event.detail), sourceReferences(event.evidence_ids, 'timeline-refs'), renderCitations(event.citations));
        row.append(el('div', 'timeline-date', dateLabel(event.date)), content);
        list.append(row);
      });
      section.append(timelineHeading, list);
    }
    return section;
  }

  function renderChart(chart, index) {
    const card = el('section', 'chart-card', '', { 'aria-label': chart.title || t('chart.title') });
    const heading = el('div', 'chart-heading');
    heading.append(el('h3', '', chart.title || t('chart.title')), el('span', 'chart-unit', t('chart.unit', { unit: textValue(chart.unit) || t('common.not_provided') })));
    card.append(heading);
    const points = asArray(chart.points);
    const valid = points.map((point, i) => ({ ...point, index: i })).filter((point) => typeof point.value === 'number' && Number.isFinite(point.value));
    if (valid.length) card.append(chartSVG(chart, points, valid, index));
    else card.append(el('p', 'no-data', t('chart.empty')));
    if (chart.note) card.append(el('p', 'chart-note', chart.note));
    const calculated = points.filter((point) => point.calculation && typeof point.calculation === 'object');
    if (calculated.length) {
      const calculations = el('details', 'calculation-details');
      calculations.append(el('summary', '', t('chart.calculation')));
      calculated.forEach((point) => {
        const item = el('div', 'calculation-item');
        item.append(el('strong', '', `${textValue(point.label)} · ${point.calculation.operation === 'count' ? t('chart.count') : textValue(point.calculation.operation)}`), el('p', '', point.calculation.description));
        const quotes = el('ul', '');
        asArray(point.calculation.source_quotes).forEach((quote) => quotes.append(el('li', '', quote)));
        item.append(quotes, sourceReferences(point.evidence_ids));
        calculations.append(item);
      });
      card.append(calculations);
    }
    const details = el('details', '');
    // The table remains accessible and contains every label and every missing value.
    details.open = true;
    details.append(el('summary', '', t('chart.table')));
    const wrap = el('div', 'table-wrap');
    const table = el('table', '');
    const header = el('thead', '');
    const headerRow = el('tr', '');
    [t('chart.item'), t('chart.value', { unit: chart.unit ? ` (${textValue(chart.unit)})` : '' }), t('chart.sources')].forEach((label) => headerRow.append(el('th', '', label, { scope: 'col' })));
    header.append(headerRow);
    const body = el('tbody', '');
    points.forEach((point) => {
      const row = el('tr', '');
      const refs = el('td', '');
      refs.append(asArray(point.evidence_ids).length ? sourceReferences(point.evidence_ids) : el('span', '', t('chart.no_source')), renderCitations(point.citations));
      row.append(el('td', '', point.label), el('td', '', typeof point.value === 'number' && Number.isFinite(point.value) ? point.value.toLocaleString(locale(), { maximumFractionDigits: 8 }) : t('common.missing')), refs);
      body.append(row);
    });
    table.append(header, body);
    wrap.append(table);
    details.append(wrap);
    card.append(details);
    return card;
  }

  function chartSVG(chart, points, valid, index) {
    const W = 760, H = 260, left = 60, right = 25, top = 26, bottom = 53;
    const plotW = W - left - right, plotH = H - top - bottom;
    let low = Math.min(0, ...valid.map((point) => point.value));
    let high = Math.max(0, ...valid.map((point) => point.value));
    if (low === high) high = low + 1;
    const range = high - low;
    const y = (value) => top + (high - value) / range * plotH;
    const step = plotW / Math.max(points.length, 1);
    const x = (i) => left + step * (i + .5);
    const chartNode = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart-visual', role: 'img', 'aria-labelledby': `chart-title-${index} chart-desc-${index}` });
    chartNode.append(svg('title', { id: `chart-title-${index}` }, chart.title || t('chart.title')), svg('desc', { id: `chart-desc-${index}` }, t('chart.description', { unit: textValue(chart.unit) || t('common.not_provided'), total: points.length, valid: valid.length })));
    for (let i = 0; i <= 4; i++) {
      const value = low + range * i / 4;
      const yy = y(value);
      chartNode.append(svg('line', { x1: left, x2: W - right, y1: yy, y2: yy, stroke: '#e2e8d8', 'stroke-width': 1 }));
      chartNode.append(svg('text', { x: left - 10, y: yy + 3, 'text-anchor': 'end' }, new Intl.NumberFormat(locale(), { notation: Math.abs(value) > 999999 ? 'compact' : 'standard', maximumFractionDigits: 2 }).format(value)));
    }
    chartNode.append(svg('line', { x1: left, x2: W - right, y1: y(0), y2: y(0), stroke: '#c1cfb2', 'stroke-width': 1 }));
    if (chart.kind === 'line') {
      let segment = [];
      const flush = () => {
        if (segment.length > 1) chartNode.append(svg('polyline', { points: segment.join(' '), fill: 'none', stroke: '#4b8264', 'stroke-width': 2.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
        segment = [];
      };
      points.forEach((point, i) => {
        if (typeof point.value === 'number' && Number.isFinite(point.value)) segment.push(`${x(i)},${y(point.value)}`);
        else flush();
      });
      flush();
    }
    const showLabels = points.length <= 14;
    valid.forEach((point) => {
      const group = svg('g');
      const refs = asArray(point.evidence_ids);
      const label = t('chart.point', { label: textValue(point.label), value: point.value.toLocaleString(locale()), unit: textValue(chart.unit), sources: refs.join(', ') || t('common.not_provided') });
      group.append(svg('title', {}, label));
      if (refs.length) {
        group.setAttribute('role', 'button');
        group.setAttribute('tabindex', '0');
        group.setAttribute('aria-label', t('chart.point_focus', { label, id: textValue(refs[0]) }));
        group.addEventListener('click', () => focusSource(refs[0]));
        group.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); focusSource(refs[0]); } });
      }
      if (chart.kind === 'line') group.append(svg('circle', { cx: x(point.index), cy: y(point.value), r: 4.5, fill: '#3d795b', stroke: '#fdfef7', 'stroke-width': 2 }));
      else {
        const barWidth = Math.min(58, step * .52);
        const barHeight = Math.abs(y(point.value) - y(0));
        group.append(svg('rect', { x: x(point.index) - barWidth / 2, y: Math.min(y(point.value), y(0)), width: barWidth, height: Math.max(barHeight, 1.3), rx: 2, fill: point.value >= 0 ? '#5f8e70' : '#b19a72' }));
      }
      if (showLabels) group.append(svg('text', { x: x(point.index), y: point.value >= 0 ? Math.max(top - 8, y(point.value) - 9) : Math.min(H - bottom + 14, y(point.value) + 14), 'text-anchor': 'middle', class: 'chart-value' }, String(point.value)));
      chartNode.append(group);
    });
    points.forEach((point, i) => {
      if (!showLabels && i % Math.ceil(points.length / 10) !== 0) return;
      const label = textValue(point.label);
      const trimmed = label.length > 12 ? `${label.slice(0, 11)}…` : label;
      chartNode.append(svg('text', { x: x(i), y: H - bottom + 28, 'text-anchor': 'middle' }, trimmed));
      if (typeof point.value !== 'number' || !Number.isFinite(point.value)) chartNode.append(svg('text', { x: x(i), y: top + plotH / 2, 'text-anchor': 'middle' }, t('common.missing')));
    });
    return chartNode;
  }

  function renderHistory(report) {
    const section = reportSection('history', '04', t('section.history'), t('section.history_help'));
    if (!asArray(report.comparisons).length) { section.append(el('p', 'no-data', t('history.empty'))); return section; }
    const wrap = el('div', 'table-wrap comparison-table');
    const table = el('table', '');
    const head = el('thead', '');
    const headings = el('tr', '');
    [t('history.case'), t('history.similarities'), t('history.differences'), t('history.limits')].forEach((title) => headings.append(el('th', '', title, { scope: 'col' })));
    head.append(headings);
    const body = el('tbody', '');
    report.comparisons.forEach((item) => {
      const row = el('tr', '');
      const caseCell = el('td', '');
      caseCell.append(el('strong', '', item.case), el('span', 'comparison-date', dateLabel(item.date)), sourceReferences(item.evidence_ids, 'comparison-refs'), renderCitations(item.citations));
      row.append(caseCell, el('td', '', item.similarities || t('common.not_provided')), el('td', '', item.differences || t('common.not_provided')), el('td', '', item.limits || t('common.not_provided')));
      body.append(row);
    });
    table.append(head, body);
    wrap.append(table);
    section.append(wrap);
    return section;
  }

  function renderQuestions(report) {
    const section = reportSection('questions', '05', t('section.questions'), t('section.questions_help'));
    const questions = asArray(report.questions);
    if (questions.length) {
      const list = el('ol', 'question-list');
      questions.forEach((question, i) => {
        const row = el('li', '');
        row.append(el('span', '', String(i + 1).padStart(2, '0')), el('span', '', question));
        list.append(row);
      });
      section.append(list);
    } else section.append(el('p', 'no-data', t('questions.empty')));
    if (asArray(report.limitations).length) {
      const limitations = el('div', 'limitations');
      const list = el('ul', '');
      report.limitations.forEach((limitation) => list.append(el('li', '', limitation)));
      limitations.append(el('h3', '', t('questions.limits')), list);
      section.append(limitations);
    }
    return section;
  }

  function renderSearchLog(report) {
    const details = el('details', 'search-log');
    details.append(el('summary', '', t('search.title', { count: asArray(report.search_log).length })));
    details.append(el('p', 'retrieval-disclosure', t('retrieval.disclosure')));
    const gaps = el('div', 'retrieval-gaps');
    gaps.append(el('h3', '', t('retrieval.title')));
    if (!asArray(report.retrieval_gaps).length) gaps.append(el('p', '', t('retrieval.no_records')));
    asArray(report.retrieval_gaps).forEach(gap => {
      const item = el('article', 'retrieval-gap');
      const claim = actionButton(gap.claim_id, () => focusClaim(gap.claim_id), 'source-ref claim-gap-ref');
      claim.setAttribute('aria-label', t('claim.focus', { id: gap.claim_id }));
      item.append(claim, el('span', '', ['no_keyword_match', 'limited_families'].includes(gap.reason) ? t(`retrieval.${gap.reason}`) : textValue(gap.reason)), el('span', 'retrieval-attempt', t(gap.attempted ? 'retrieval.attempted' : 'retrieval.not_attempted')));
      if (gap.query) item.append(el('p', 'retrieval-query', gap.query));
      gaps.append(item);
    });
    details.append(gaps);
    if (!asArray(report.search_log).length) { details.append(el('p', 'no-data', t('search.empty'))); return details; }
    const wrap = el('div', 'table-wrap');
    const table = el('table', '');
    const head = el('thead', '');
    const headings = el('tr', '');
    [t('search.query'), t('search.round'), t('search.gap_claims'), t('search.intent'), t('search.provider'), t('search.count'), t('search.date')].forEach((title) => headings.append(el('th', '', title, { scope: 'col' })));
    head.append(headings);
    const body = el('tbody', '');
    report.search_log.forEach((query) => {
      const row = el('tr', '');
      row.append(el('td', '', query.query), el('td', '', t(query.round === 'supplemental' ? 'search.supplemental' : 'search.initial')), el('td', '', asArray(query.gap_claim_ids).join(', ') || '—'), el('td', '', intentLabel(query.intent)), el('td', '', query.provider), el('td', '', query.result_count ?? t('common.not_provided')), el('td', '', dateLabel(query.ran_at, true)));
      body.append(row);
    });
    table.append(head, body);
    wrap.append(table);
    details.append(wrap);
    return details;
  }

  function intentLabel(intent) {
    return ['neutral', 'support', 'counter', 'actor_history'].includes(intent) ? t(`search.${intent}`) : textValue(intent);
  }

  function filename(extension) {
    const date = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    return `no-fake-news-${state.report.mode}-${date}.${extension}`;
  }

  function download(content, type, name) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const anchor = el('a', '', '', { href: url, download: name });
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  function exportJSON() {
    if (!state.report) return;
    const report = state.report.mode === 'evidence-only' ? evidenceProjection(state.report) : state.report;
    download(JSON.stringify(report, null, 2), 'application/json;charset=utf-8', filename('json'));
    toast(t('export.json_done'));
  }

  async function embedLocalCaptures(snapshot) {
    const limit = 12 * 1024 * 1024;
    let used = 0, embedded = 0, external = 0;
    const cache = new Map();
    for (const image of snapshot.querySelectorAll('.capture-grid img')) {
      let captureURL;
      try { captureURL = new URL(image.getAttribute('src'), window.location.origin); } catch { external++; continue; }
      const name = captureURL.pathname.match(/^\/captures\/([a-f0-9]{32}\.(png|jpg|webp))$/);
      if (captureURL.origin !== window.location.origin || !name || captureURL.search || captureURL.hash) { external++; continue; }
      try {
        let item = cache.get(captureURL.href);
        if (!item) {
          const response = await fetch(captureURL.href, { cache: 'force-cache' });
          if (!response.ok) throw new Error('capture_unavailable');
          const contentLength = Number(response.headers.get('content-length'));
          if (Number.isFinite(contentLength) && contentLength > 0 && 4 * Math.ceil(contentLength / 3) > limit - used) {
            await response.body?.cancel();
            throw new Error('capture_limit');
          }
          const blob = await response.blob();
          if (4 * Math.ceil(blob.size / 3) > limit - used) throw new Error('capture_limit');
          const bytes = new Uint8Array(await blob.slice(0, 12).arrayBuffer());
          const validPNG = name[2] === 'png' && [137, 80, 78, 71, 13, 10, 26, 10].every((byte, i) => bytes[i] === byte);
          const validJPEG = name[2] === 'jpg' && bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
          const validWebP = name[2] === 'webp' && [82, 73, 70, 70].every((byte, i) => bytes[i] === byte) && [87, 69, 66, 80].every((byte, i) => bytes[i + 8] === byte);
          if (!validPNG && !validJPEG && !validWebP) throw new Error('capture_type');
          const type = validPNG ? 'image/png' : validJPEG ? 'image/jpeg' : 'image/webp';
          const data = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error('capture_read'));
            reader.readAsDataURL(new Blob([blob], { type }));
          });
          item = { data, size: data.length };
          cache.set(captureURL.href, item);
        }
        if (item.size > limit - used) throw new Error('capture_limit');
        used += item.size;
        image.setAttribute('src', item.data);
        const anchor = image.closest('a');
        if (anchor) {
          anchor.setAttribute('href', item.data);
          anchor.setAttribute('download', name[1]);
          anchor.setAttribute('aria-label', t('capture.download'));
        }
        const caption = image.closest('figure')?.querySelector('figcaption');
        caption?.append(el('span', '', t('capture.embedded_note')));
        embedded++;
      } catch { external++; }
    }
    return { embedded, external };
  }

  async function exportHTML() {
    if (!state.report) return;
    const reportForExport = state.report;
    const filterForExport = state.filter;
    const exportFilename = filename('html');
    const snapshot = $('report').firstElementChild.cloneNode(true);
    const button = $('report').querySelector('[data-action="export-html"]');
    const originalLabel = button?.textContent;
    if (button) { button.disabled = true; button.textContent = t('export.packing'); }
    try {
      // The exported document is built from the visible report only, never from application state or settings.
      const cssResponses = await Promise.all(['/assets/styles.css', '/assets/workbench.css'].map(path => fetch(path, { cache: 'no-store' })));
      if (cssResponses.some(response => !response.ok)) throw new Error(t('errors.export_css'));
      const css = (await Promise.all(cssResponses.map(response => response.text()))).join('\n');
      snapshot.querySelectorAll('[data-map-control]').forEach(node => node.remove());
      snapshot.querySelector('.report-actions')?.remove();
      // Export all sources in the current mode, even if a claim filter is selected.
      if (filterForExport) {
        const area = snapshot.querySelector('#evidence-area');
        const header = el('p', 'report-section-description', t('export.all_sources'));
        const sources = el('div', 'evidence-list');
        asArray(reportForExport.evidence).forEach((source) => sources.append(renderSource(source)));
        const originalClaims = area.querySelector('.claim-grid')?.cloneNode(true);
        area.replaceChildren();
        if (originalClaims) { originalClaims.querySelectorAll('.active').forEach((node) => node.classList.remove('active')); area.append(originalClaims); }
        area.append(header, sources);
      }
      snapshot.querySelectorAll('details').forEach((details) => { details.open = true; });
      snapshot.querySelectorAll('.filter-row').forEach((node) => node.remove());
      snapshot.querySelectorAll('button').forEach((node) => {
        if (node.hasAttribute('data-citation-source')) {
          node.replaceWith(el('a', node.className, node.textContent, { href: `#${sourceDomId(node.getAttribute('data-citation-source'))}-excerpt` }));
        } else if (node.classList.contains('claim-gap-ref')) {
          node.replaceWith(el('a', 'source-ref', node.textContent, { href: '#claims' }));
        } else if (node.classList.contains('source-ref')) {
          const id = node.textContent;
          node.replaceWith(el('a', 'source-ref', id, { href: `#${sourceDomId(id)}` }));
        } else if (node.classList.contains('claim-card')) {
          const card = el('div', 'claim-card');
          while (node.firstChild) card.append(node.firstChild);
          node.replaceWith(card);
        } else {
          node.replaceWith(el('span', node.className, node.textContent));
        }
      });
      snapshot.querySelectorAll('svg [role="button"]').forEach((node) => { node.removeAttribute('role'); node.removeAttribute('tabindex'); });
      snapshot.querySelectorAll('img').forEach((image) => { image.removeAttribute('loading'); image.hidden = false; });
      const captures = await embedLocalCaptures(snapshot);
      const captureNote = captures.embedded ? t('export.embedded', { count: captures.embedded }) : t('export.no_captures');
      const externalNote = captures.external ? t('export.external', { count: captures.external }) : '';
      const note = el('p', 'export-note', t('export.note', { captures: captureNote, external: externalNote }));
      snapshot.append(note);
      const doc = document.implementation.createHTMLDocument(`No fake news · ${textValue(reportForExport.topic)}`);
      doc.documentElement.lang = I18n.getLanguage();
      doc.head.append(el('meta', '', '', { charset: 'utf-8' }), el('meta', '', '', { name: 'viewport', content: 'width=device-width, initial-scale=1' }));
      const style = el('style', '', css + '\nbody{padding:32px 24px}.report-shell{max-width:1050px;margin:0 auto}.report-actions{display:none}.claim-card{cursor:default}.source-ref{font-size:inherit}.source-card:focus{outline:none}@media print{body{padding:0}.search-log{display:block!important}}');
      doc.head.append(style);
      doc.body.append(snapshot);
      if (state.report !== reportForExport) throw new Error(t('errors.export_changed'));
      download('<!doctype html>\n' + doc.documentElement.outerHTML, 'text/html;charset=utf-8', exportFilename);
      toast(t('export.done', { count: captures.embedded, extra: captures.external ? t('export.remaining', { count: captures.external }) : t('export.offline') }));
    } catch (error) { showError(error.message || t('errors.export')); }
    finally { if (button?.isConnected) { button.disabled = false; button.textContent = originalLabel; } }
  }

  $('research-form').addEventListener('submit', submitResearch);
  $('demo-button').addEventListener('click', loadDemo);
  $('import-button').addEventListener('click', () => $('import-file').click());
  $('import-file').addEventListener('change', importReport);
  $('open-settings').addEventListener('click', openSettings);
  $('close-settings').addEventListener('click', () => $('settings-dialog').close());
  $('settings-form').addEventListener('submit', (event) => { event.preventDefault(); saveSettings(); $('settings-dialog').close(); toast(t('common.settings_saved')); });
  $('include-screenshots').addEventListener('change', saveSettings);
  $('adaptive-search').addEventListener('change', saveSettings);
  $('research-depth').addEventListener('change', saveSettings);
  $('ai-key').addEventListener('input', updateConnectionStatus);
  $('search-key').addEventListener('input', updateConnectionStatus);
  $('search-provider').addEventListener('change', () => { $('search-key').placeholder = state.capabilities.configured?.[$('search-provider').value] ? t('settings.env_key') : t('settings.search_key_placeholder'); updateConnectionStatus(); });
  $('ai-model').addEventListener('input', updateConnectionStatus);
  $('topic').addEventListener('input', () => { $('topic-count').textContent = `${$('topic').value.length} / 6000`; });
  $('close-summary').addEventListener('click', () => $('summary-dialog').close());
  $('cancel-summary').addEventListener('click', () => $('summary-dialog').close());
  $('confirm-summary').addEventListener('click', generateSummary);
  $('new-investigation').addEventListener('click', () => {
    if (state.pending) { toast(t('status.pending_new')); return; }
    state.report = null;
    state.filter = null;
    state.isDemo = false;
    state.isImported = false;
    document.body.classList.remove('has-report');
    document.querySelector('input[name="mode"][value="evidence-only"]').checked = true;
    $('report').replaceChildren();
    $('report').hidden = true;
    $('empty-state').hidden = false;
    $('topic').value = '';
    $('topic-count').textContent = '0 / 6000';
    $('report-indicator').textContent = t('static.not_started');
    $('nav-evidence-count').textContent = '—';
    clearError();
    $('inquiry').scrollIntoView({ behavior: 'smooth' });
    $('topic').focus({ preventScroll: true });
  });
  document.querySelectorAll('.section-nav a').forEach((anchor) => {
    anchor.addEventListener('click', (event) => {
      const target = document.querySelector(anchor.getAttribute('href'));
      if (!target) { event.preventDefault(); toast(t('status.nav_empty')); return; }
      document.querySelectorAll('.section-nav a').forEach((item) => item.classList.remove('nav-current'));
      anchor.classList.add('nav-current');
    });
  });
  function changeLanguage(language, persist = true) {
    if (state.pending) { $('ui-language').value = I18n.getLanguage(); return; }
    I18n.setLanguage(language);
    document.documentElement.lang = I18n.getLanguage();
    document.title = t('app.title');
    $('ui-language').value = I18n.getLanguage();
    I18n.apply();
    if (persist) { try { localStorage.setItem('no-fake-news.language.v1', I18n.getLanguage()); } catch { /* optional preference */ } }
    updateConnectionStatus();
    Workspace.renderSources();
    if (state.report) renderReport();
    else $('report-indicator').textContent = t('static.not_started');
  }
  Workspace.setupSources();
  let savedLanguage = 'zh-CN';
  try { savedLanguage = localStorage.getItem('no-fake-news.language.v1') || 'zh-CN'; } catch { /* default language */ }
  changeLanguage(savedLanguage, false);
  $('ui-language').addEventListener('change', () => changeLanguage($('ui-language').value));
  restoreSettings();
  loadCapabilities();
})();
