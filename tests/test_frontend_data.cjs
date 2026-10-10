'use strict';

// Run with: node --test tests/test_frontend_data.cjs
// These checks exercise the actual browser-side data functions without a DOM or external packages.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash } = require('node:crypto');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'frontend', 'app.js'), 'utf8');
const demo = JSON.parse(fs.readFileSync(path.join(root, 'examples', 'demo-report.json'), 'utf8'));

function portion(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert(first >= 0 && last > first, `Browser function markers were not found: ${start}`);
  return source.slice(first, last);
}

function browserData() {
  const context = {
    URL, structuredClone, Intl, Date, Set,
    window: { location: { origin: 'http://127.0.0.1:8000' } },
    state: { capabilities: { configured: {} } }
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root, 'frontend', 'i18n.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(root, 'frontend', 'workspace.js'), 'utf8'), context);
  vm.runInContext(`
    const I18n = globalThis.NoFakeNewsI18n;
    const t = (key, values) => I18n.t(key, values);
    const locale = () => I18n.getLocale();
    const asArray = value => Array.isArray(value) ? value : [];
    const textValue = value => value == null ? '' : Array.isArray(value) ? value.map(textValue).join('；') : typeof value === 'object' ? '' : String(value);
    ${portion('function safeUrl(', 'function externalLink(')}
    ${portion('function dateLabel(', 'function hostLabel(')}
    ${portion('function pick(', 'function getAISettings(')}
    ${portion('function isLoopbackAI(', 'function saveSettings(')}
    ${portion('function normalizeImport(', 'async function importReport(')}
    ${portion('function sourceDomId(', 'function focusSource(')}
    ${portion('function observationLabel(', 'function renderObservations(')}
    ${portion('function intentLabel(', 'function filename(')}
  `, context);
  return {
    context,
    run(expression, input) { context.input = input; return vm.runInContext(expression, context); }
  };
}

test('AI reasoning renders every premise type in three languages', () => {
  const browser = browserData();
  browser.context.el = (tag, cls, text, attrs) => ({ tag, cls, text, attrs, children: [], append(...children) { this.children.push(...children); } });
  browser.context.reportSection = (...args) => browser.context.el('section', '', args);
  browser.context.sourceReferences = ids => ids.join(',');
  browser.context.document = { createTextNode: value => value };
  browser.context.state.report = { evidence: [{ id: 'E1' }] };
  for (const language of ['zh-CN', 'en', 'ja']) {
    browser.run('I18n.setLanguage(input)', language);
    for (const kind of ['data', 'logic', 'history']) {
      const output = browser.run('renderReasoning(input)', [{id:'R1',text:'A cited premise',premise_ids:['E1'],claim_id:'C1',kind}]);
      assert(JSON.stringify(output).includes('A cited premise'));
      assert(JSON.stringify(output).includes(browser.run('observationLabel(input)', kind)));
    }
    assert.notEqual(browser.run('intentLabel(input)', 'counter'), 'search.counter');
  }
});

test('DeepSeek search reuses an entered key only for the official HTTPS origin', () => {
  const browser = browserData();
  for (const base_url of ['https://api.deepseek.com', 'https://api.deepseek.com:443/v1']) {
    assert.equal(browser.run('canReuseDeepSeekKey(input)', {base_url,api_key:'TEST_ONLY'}), true);
  }
  for (const base_url of ['http://api.deepseek.com', 'https://api.deepseek.com:8443', 'https://api.deepseek.com.evil.example', 'https://user:pass@api.deepseek.com', 'https://example.com']) {
    assert.equal(browser.run('canReuseDeepSeekKey(input)', {base_url,api_key:'TEST_ONLY'}), false);
  }
  assert.equal(browser.run('canReuseDeepSeekKey(input)', {base_url:'https://api.deepseek.com',api_key:''}), false);
});

test('evidence view removes all AI verdicts and normalizes evaluative link relations', () => {
  const browser = browserData();
  const report = structuredClone(demo);
  report.mode = 'ai-summary';
  report.summary = { text: 'PRIVATE_AI_SUMMARY', verdict: 'PRIVATE_AI_VERDICT', caveats: [], evidence_ids: ['E1'] };
  report.reasoning = [{ id: 'R1', text: 'PRIVATE_AI_REASONING', premise_ids: ['E1'], claim_id: 'C1', kind: 'logic' }];
  report.claims[0].verdict = 'PRIVATE_CLAIM_VERDICT';
  report.claims[0].analysis = 'PRIVATE_CLAIM_ANALYSIS';
  report.links = ['supports', 'contradicts', 'qualifies', 'context'].map(relation => ({ from: 'E1', to: 'C1', relation, note: 'PRIVATE_AI_LINK_NOTE' }));
  const projected = browser.run('evidenceProjection(input)', report);
  assert.equal(projected.mode, 'evidence-only');
  assert.equal('summary' in projected, false);
  assert.equal('reasoning' in projected, false);
  assert(projected.claims.every(claim => !('verdict' in claim) && !('analysis' in claim)));
  assert(projected.links.every(link => !('note' in link)));
  assert.deepEqual(Array.from(projected.links, link => link.relation), ['relevant_to', 'relevant_to', 'relevant_to', 'context']);
  assert.equal(JSON.stringify(projected).includes('PRIVATE_'), false);
});

test('JSON import ignores secret settings and unknown nested fields', () => {
  const browser = browserData();
  const report = structuredClone(demo);
  report.api_key = 'SECRET_TOP_LEVEL';
  report.ai = { api_key: 'SECRET_AI' };
  report.search = { api_key: 'SECRET_SEARCH' };
  report.claims[0].api_key = 'SECRET_CLAIM';
  report.evidence[0].api_key = 'SECRET_EVIDENCE';
  report.charts[0].points[0].api_key = 'SECRET_POINT';
  const imported = browser.run('normalizeImport(input)', report);
  assert.equal(JSON.stringify(imported).includes('SECRET_'), false);
  assert.equal(imported.topic, report.topic);
  assert.equal(imported.evidence.length, report.evidence.length);
});

test('objective count formulas survive evidence projection while extra calculation fields do not', () => {
  const browser = browserData();
  const report = structuredClone(demo);
  report.charts[0].points[0].calculation = {
    operation: 'count', description: '对原始清单中的指定条目逐条计数。', source_quotes: ['A', 'B'], api_key: 'SECRET_CALCULATION'
  };
  const projected = browser.run('evidenceProjection(input)', report);
  const calculation = projected.charts[0].points[0].calculation;
  assert.equal(calculation.operation, 'count');
  assert.equal(calculation.description, report.charts[0].points[0].calculation.description);
  assert.deepEqual(Array.from(calculation.source_quotes), ['A', 'B']);
  assert.equal('api_key' in calculation, false);
});

test('date-only values never acquire a fabricated capture time', () => {
  const browser = browserData();
  for (const value of ['2026', '2026-10', '2026-10-09', '2026-10-09T10:00:00', 'not a date', '2026-02-30T10:00:00Z']) {
    assert.equal(browser.run('dateLabel(input, true)', value), value);
  }
  assert.match(browser.run('dateLabel(input, true)', '2026-10-09T00:00:00Z'), /08:00/);
});

test('only explicit loopback AI addresses qualify for keyless local operation', () => {
  const browser = browserData();
  for (const base_url of ['http://localhost:11434/v1', 'http://127.0.0.1:1234/v1', 'http://[::1]:11434/v1']) {
    assert.equal(browser.run('canUseAIWithoutKey(input)', { base_url }), true);
  }
  for (const base_url of ['https://api.openai.com/v1', 'http://localhost.example.org/v1', 'http://127.0.0.1.evil.example/v1', 'https://localhost@evil.example/v1']) {
    assert.equal(browser.run('canUseAIWithoutKey(input)', { base_url }), false);
  }
  assert.equal(browser.run('canUseAIWithoutKey(input)', { base_url: '' }), false);
  browser.context.state.capabilities.configured.ai_base_url = true;
  assert.equal(browser.run('canUseAIWithoutKey(input)', { base_url: '' }), true);
});

test('missing and negative chart values remain distinct after import and projection', () => {
  const browser = browserData();
  const report = structuredClone(demo);
  report.charts[0].points = [
    { label: 'negative', value: -12.5, evidence_ids: ['E1'] },
    { label: 'missing', value: null, evidence_ids: ['E1'] },
    { label: 'zero', value: 0, evidence_ids: ['E1'] }
  ];
  const imported = browser.run('normalizeImport(input)', report);
  const projected = browser.run('evidenceProjection(input)', imported);
  assert.deepEqual(Array.from(projected.charts[0].points, point => point.value), [-12.5, null, 0]);
});

test('import rejects unsupported schemas, dangling citations and executable URLs', () => {
  const browser = browserData();
  const badVersion = { ...structuredClone(demo), schema_version: '9.0' };
  assert.throws(() => browser.run('normalizeImport(input)', badVersion), /schema_version/);
  const dangling = structuredClone(demo);
  dangling.evidence[0].claim_ids = ['C999'];
  assert.throws(() => browser.run('normalizeImport(input)', dangling), /引用编号/);
  const executable = structuredClone(demo);
  executable.evidence[0].url = 'javascript:alert(document.cookie)';
  assert.throws(() => browser.run('normalizeImport(input)', executable), /链接地址/);
});

test('depth and neutral observations survive both modes while AI conclusions remain optional', () => {
  const browser = browserData();
  const report = structuredClone(demo);
  report.depth = 'deep';
  report.observations = ['data', 'logic', 'history'].map(kind => ({
    kind, text: `${kind}：记录口径、前提和适用边界。`, claim_ids: ['C1'], evidence_ids: ['E1'],
    verdict: 'PRIVATE_OBSERVATION_VERDICT', api_key: 'SECRET_OBSERVATION_KEY'
  }));
  report.summary = { text: 'PRIVATE_AI_SUMMARY', verdict: 'PRIVATE_AI_VERDICT', caveats: [], evidence_ids: ['E1'] };
  for (const mode of ['evidence-only', 'ai-summary']) {
    report.mode = mode;
    const imported = browser.run('normalizeImport(input)', report);
    assert.equal(imported.depth, 'deep');
    assert.equal(imported.observations.length, 3);
    assert.deepEqual(Array.from(imported.observations, observation => observation.kind), ['data', 'logic', 'history']);
    assert.equal(JSON.stringify(imported.observations).includes('PRIVATE_'), false);
    assert.equal(JSON.stringify(imported.observations).includes('SECRET_'), false);
    const evidence = browser.run('evidenceProjection(input)', imported);
    assert.equal(evidence.depth, 'deep');
    assert.equal(evidence.observations.length, 3);
    assert.equal(evidence.observations[0].text, report.observations[0].text);
    assert.deepEqual(Array.from(evidence.observations[0].claim_ids), ['C1']);
    assert.deepEqual(Array.from(evidence.observations[0].evidence_ids), ['E1']);
    assert.equal('summary' in evidence, false);
    assert.equal('reasoning' in evidence, false);
    if (mode === 'ai-summary') assert.equal(imported.summary.verdict, 'PRIVATE_AI_VERDICT');
    else assert.equal('summary' in imported, false);
  }
});

test('deep reports can import 24 sources, 10 searches and 24-source observations', () => {
  const browser = browserData();
  const report = structuredClone(demo);
  report.depth = 'deep';
  report.evidence = Array.from({ length: 24 }, (_, i) => ({ ...structuredClone(demo.evidence[0]), id: `E${i + 1}`, claim_ids: ['C1'] }));
  report.search_log = Array.from({ length: 10 }, (_, i) => ({ query: `query ${i}`, intent: 'neutral', provider: 'tavily', result_count: 1, ran_at: '2026-10-09' }));
  report.observations = [{ kind: 'data', text: '对照全部来源的数据口径。', claim_ids: ['C1'], evidence_ids: report.evidence.map(source => source.id) }];
  const imported = browser.run('normalizeImport(input)', report);
  assert.equal(imported.evidence.length, 24);
  assert.equal(imported.search_log.length, 10);
  assert.equal(imported.observations[0].evidence_ids.length, 24);
  const tooManySources = structuredClone(report);
  tooManySources.evidence.push({ ...structuredClone(report.evidence[0]), id: 'E25' });
  assert.throws(() => browser.run('normalizeImport(input)', tooManySources), /数量超出/);
  const tooManyQueries = structuredClone(report);
  tooManyQueries.search_log.push({ ...report.search_log[0] });
  assert.throws(() => browser.run('normalizeImport(input)', tooManyQueries), /数量超出/);
});

test('import validates observation citations, non-empty premises and depth values', () => {
  const browser = browserData();
  const report = structuredClone(demo);
  report.observations = [{ kind: 'logic', text: '检查论断的前提。', claim_ids: ['C1'], evidence_ids: ['E999'] }];
  assert.throws(() => browser.run('normalizeImport(input)', report), /引用编号/);
  report.observations[0].evidence_ids = ['E1'];
  report.observations[0].claim_ids = [];
  assert.throws(() => browser.run('normalizeImport(input)', report), /关联命题/);
  report.observations[0].claim_ids = ['C1'];
  report.depth = 'unlimited';
  assert.throws(() => browser.run('normalizeImport(input)', report), /分析深度/);
});

function exactCitation(excerpt, quote, evidence_id = 'E1') {
  const startUTF16 = excerpt.indexOf(quote);
  assert(startUTF16 >= 0);
  const chars = Array.from(excerpt);
  const start = Array.from(excerpt.slice(0, startUTF16)).length;
  const end = start + Array.from(quote).length;
  let match_count = 0, cursor = startUTF16;
  while (cursor >= 0) { match_count++; cursor = excerpt.indexOf(quote, cursor + 1); }
  return {
    evidence_id, quote, verification: 'exact_match', semantic_support: 'unverified',
    locator: { start, end, prefix: chars.slice(Math.max(0, start - 80), start).join(''), suffix: chars.slice(end, end + 80).join(''), excerpt_sha256: createHash('sha256').update(excerpt).digest('hex'), match_count, coordinate_system: 'unicode_codepoints' }
  };
}

function citedReport() {
  const report = structuredClone(demo);
  report.schema_version = '1.1';
  report.mode = 'ai-summary';
  report.evidence[0].excerpt = '前文 🧭 第一行\n  原句 🛰️ 保留空白。\n后文。原句 🛰️ 保留空白。';
  const citation = exactCitation(report.evidence[0].excerpt, '原句 🛰️ 保留空白。');
  report.evidence[0].excerpt_metadata = { sha256: citation.locator.excerpt_sha256, coordinate_system: 'unicode_codepoints', api_key: 'SECRET_METADATA' };
  report.evidence[0].content_sha256 = 'b'.repeat(64);
  report.evidence[0].document_format = 'pdf';
  report.evidence[0].source_family_method = 'near_duplicate';
  report.evidence[0].source_family_evidence_ids = ['E2'];
  report.claims[0].citations = [structuredClone(citation)];
  report.claims[0].verdict = 'PRIVATE_VERDICT';
  report.observations = [{ kind: 'data', text: '资料比对', claim_ids: ['C1'], evidence_ids: ['E1'], citations: [structuredClone(citation)] }];
  report.timeline = [{ date: '2026-10-09', title: '记录', detail: '原始记录', evidence_ids: ['E1'], citations: [structuredClone(citation)] }];
  report.comparisons = [{ case: '参照', date: '2026', similarities: '数据口径', differences: '边界', limits: '有限', evidence_ids: ['E1'], citations: [structuredClone(citation)] }];
  report.charts = [{ title: '图表', unit: '次', kind: 'bar', points: [{ label: '记录', value: 1, evidence_ids: ['E1'], citations: [structuredClone(citation)] }] }];
  report.reasoning = [{ id: 'R1', claim_id: 'C1', premise_ids: ['E1'], kind: 'logic', text: 'PRIVATE_REASONING', citations: [structuredClone(citation)] }];
  report.summary = { text: 'PRIVATE_SUMMARY', verdict: 'PRIVATE_SUMMARY_VERDICT', evidence_ids: ['E1'], caveats: [], citations: [structuredClone(citation)] };
  report.search_log = [{ query: 'query', provider: 'tavily', intent: 'counter', result_count: 1, ran_at: '2026-10-09', round: 'supplemental', gap_claim_ids: ['C1'] }];
  report.retrieval_gaps = [{ claim_id: 'C1', reason: 'limited_families', query: '补搜', attempted: true }];
  return report;
}

test('1.1 import and evidence export preserve exact quotations and neutral metadata using nested allowlists', () => {
  const browser = browserData();
  const report = citedReport();
  report.claims[0].citations[0].password = 'SECRET_CITATION';
  report.claims[0].citations[0].locator.token = 'SECRET_LOCATOR';
  report.retrieval_gaps[0].verdict = 'PRIVATE_GAP_VERDICT';
  const imported = browser.run('normalizeImport(input)', report);
  assert.equal(imported.schema_version, '1.1');
  assert.equal(imported.summary.citations[0].quote, report.summary.citations[0].quote);
  const projected = browser.run('evidenceProjection(input)', imported);
  assert.deepEqual(Object.keys(projected.claims[0]).sort(), ['id', 'kind', 'text']);
  for (const item of [projected.observations[0], projected.timeline[0], projected.comparisons[0], projected.charts[0].points[0]]) {
    assert.equal(item.citations[0].quote, report.claims[0].citations[0].quote);
    assert.equal(item.citations[0].locator.match_count, 2);
    assert.equal(item.citations[0].semantic_support, 'unverified');
  }
  assert.equal(projected.evidence[0].document_format, 'pdf');
  assert.equal(projected.evidence[0].source_family_method, 'near_duplicate');
  assert.deepEqual(Array.from(projected.evidence[0].source_family_evidence_ids), ['E2']);
  assert.equal(projected.evidence[0].content_sha256, 'b'.repeat(64));
  assert.equal(projected.search_log[0].round, 'supplemental');
  assert.equal(projected.search_log[0].gap_claim_ids[0], 'C1');
  assert.equal(projected.retrieval_gaps[0].attempted, true);
  assert(!JSON.stringify(projected).includes('PRIVATE_'));
  assert(!JSON.stringify(imported).includes('SECRET_'));
});

test('summary-to-evidence JSON and static HTML drop assessment citations and retain source text and neutral citations', async () => {
  const browser = browserData();
  const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  class Node {
    constructor(tag, text = '') { this.tagName = tag.toUpperCase(); this.attributes = {}; this.className = ''; this.children = []; this.value = text; this.parent = null; }
    append(...nodes) { nodes.forEach(node => { if (typeof node === 'string') node = new Node('#text',node); node.remove(); node.parent = this; this.children.push(node); }); }
    replaceChildren(...nodes) { this.children.forEach(node => {node.parent=null;}); this.children=[];this.value='';this.append(...nodes); }
    remove() { if(this.parent){const siblings=this.parent.children;siblings.splice(siblings.indexOf(this),1);this.parent=null;} }
    replaceWith(node) {const parent=this.parent;if(!parent)return;const index=parent.children.indexOf(this);node.remove();parent.children[index]=node;node.parent=parent;this.parent=null;}
    setAttribute(key,value) {this.attributes[key]=String(value);}
    getAttribute(key) {return this.attributes[key] ?? null;}
    hasAttribute(key) {return key in this.attributes;}
    removeAttribute(key) {delete this.attributes[key];}
    addEventListener() {}
    get classList() {return {contains:value=>this.className.split(/\s+/).includes(value)};}
    get firstChild() {return this.children[0] || null;}
    get firstElementChild() {return this.children.find(node=>!node.tagName.startsWith('#')) || null;}
    get textContent() {return this.value + this.children.map(node=>node.textContent).join('');}
    set textContent(value) {this.replaceChildren();this.value=String(value);}
    querySelectorAll(selector) {
      const matches = node => selector.startsWith('.') ? node.classList.contains(selector.slice(1)) : selector.startsWith('#') ? node.attributes.id===selector.slice(1) : selector.startsWith('[') ? node.hasAttribute(selector.slice(1,-1).split('=')[0]) : node.tagName===selector.toUpperCase();
      return this.children.flatMap(node=>[...(matches(node)?[node]:[]),...node.querySelectorAll(selector)]);
    }
    querySelector(selector) {return this.querySelectorAll(selector)[0] || null;}
    cloneNode(deep) {const clone=new Node(this.tagName,this.value);clone.attributes={...this.attributes};clone.className=this.className;if(deep)clone.append(...this.children.map(node=>node.cloneNode(true)));return clone;}
    get outerHTML() {
      if(this.tagName==='#TEXT')return escape(this.value);
      if(this.tagName==='#FRAGMENT')return this.children.map(node=>node.outerHTML).join('');
      const attrs={...this.attributes,...(this.className?{class:this.className}:{}),...(this.lang?{lang:this.lang}:{}),...(this.open?{open:''}:{})};
      return `<${this.tagName.toLowerCase()}${Object.entries(attrs).map(([key,value])=>` ${key}="${escape(value)}"`).join('')}>${escape(this.value)}${this.children.map(node=>node.outerHTML).join('')}</${this.tagName.toLowerCase()}>`;
    }
  }
  const rootNode = new Node('div');
  const article = new Node('article');
  const area = new Node('div');area.setAttribute('id','evidence-area');
  article.append(area);rootNode.append(article);
  browser.context.document = {
    createElement:tag=>new Node(tag), createTextNode:value=>new Node('#text',String(value)), createDocumentFragment:()=>new Node('#fragment'),
    implementation:{createHTMLDocument:()=>{const documentElement=new Node('html'),head=new Node('head'),body=new Node('body');documentElement.append(head,body);return {documentElement,head,body};}}
  };
  browser.context.$ = id => id==='report'?rootNode:id==='evidence-area'?area:null;
  browser.context.fetch = async () => ({ok:true,text:async()=>''});
  browser.context.embedLocalCaptures = async () => ({embedded:0,external:0});
  browser.context.toast = () => {};
  browser.context.showError = message => {throw new Error(message);};
  browser.context.filename = extension => `report.${extension}`;
  const downloads = {};
  browser.context.download = (content,_type,name) => {downloads[name]=content;};
  vm.runInContext(`
    ${portion('function el(', 'function svg(')}
    ${portion('function externalLink(', 'function dateLabel(')}
    ${portion('function hostLabel(', 'function pick(')}
    ${portion('function sourceReferences(', 'function sourceDomId(')}
    ${portion('function actionButton(', 'function renderReport(')}
    ${portion('function kindLabel(', 'function renderEvidenceArea(')}
    ${portion('function renderEvidenceArea(', 'function sourceTypeLabel(')}
    ${portion('function sourceTypeLabel(', 'function renderSummary(')}
    ${portion('function exportJSON(', 'async function embedLocalCaptures(')}
    ${portion('async function exportHTML(', "  $('research-form')")}
  `, browser.context);
  const report = citedReport();
  report.evidence[0].excerpt = 'ASSESSMENT_ONLY_ORIGINAL passage. NEUTRAL_ORIGINAL passage.';
  report.evidence[0].excerpt_metadata.sha256 = createHash('sha256').update(report.evidence[0].excerpt).digest('hex');
  report.evidence.forEach(source=>{source.screenshots=[];});
  report.claims[0].citations = [exactCitation(report.evidence[0].excerpt,'ASSESSMENT_ONLY_ORIGINAL')];
  for (const item of [report.observations[0],report.timeline[0],report.comparisons[0],report.charts[0].points[0]]) item.citations = [exactCitation(report.evidence[0].excerpt,'NEUTRAL_ORIGINAL')];
  for (const item of [report.reasoning[0],report.summary]) item.citations = [exactCitation(report.evidence[0].excerpt,'ASSESSMENT_ONLY_ORIGINAL')];
  browser.context.state.report = browser.run('evidenceProjection(normalizeImport(input))',report);
  browser.context.state.filter = null;
  browser.run('renderEvidenceArea()');
  article.append(browser.run('renderCitations(state.report.observations[0].citations)'));
  const claimMarkup = area.querySelector('.claim-grid').outerHTML;
  assert(!claimMarkup.includes('ASSESSMENT_ONLY_ORIGINAL'));
  assert.equal(area.querySelector('.claim-grid').querySelectorAll('.citation-details').length,0);
  browser.run('exportJSON()');
  await browser.run('exportHTML()');
  const json = JSON.parse(downloads['report.json']);
  assert.deepEqual(Object.keys(json.claims[0]).sort(),['id','kind','text']);
  assert.equal(json.evidence[0].excerpt,report.evidence[0].excerpt);
  assert.equal(json.observations[0].citations[0].quote,'NEUTRAL_ORIGINAL');
  const html = downloads['report.html'];
  assert(html.includes('ASSESSMENT_ONLY_ORIGINAL passage. NEUTRAL_ORIGINAL passage.'));
  assert(html.includes('class="citation-quote">NEUTRAL_ORIGINAL</blockquote>'));
  assert(!html.includes('class="citation-quote">ASSESSMENT_ONLY_ORIGINAL</blockquote>'));
  assert(!html.includes('PRIVATE_'));
});

test('quotation locators use code points, preserve whitespace and select the first repeated occurrence', () => {
  const browser = browserData();
  const report = citedReport();
  const citation = report.claims[0].citations[0];
  const checked = browser.run('citationPosition(input.citation,input.source)', {citation,source:report.evidence[0]});
  assert.equal(checked.start, Array.from(report.evidence[0].excerpt.split(citation.quote)[0]).length);
  assert.notEqual(checked.start, report.evidence[0].excerpt.indexOf(citation.quote));
  assert.equal(checked.match_count, 2);
  const broken = structuredClone(report);
  broken.claims[0].citations[0].locator.start++;
  assert.throws(() => browser.run('normalizeImport(input)', broken), /精确引文/);
  for (const mutate of [
    quote => { quote.quote = '原句 🛰️  保留空白。'; },
    quote => { quote.locator.prefix = '虚构上下文'; },
    quote => { quote.locator.match_count = 1; },
    quote => { quote.locator.excerpt_sha256 = 'c'.repeat(64); },
    quote => { quote.locator.coordinate_system = 'utf16'; },
    quote => { quote.semantic_support = 'verified'; },
    quote => { quote.evidence_id = 'E999'; }
  ]) {
    const invalid = structuredClone(report);
    mutate(invalid.claims[0].citations[0]);
    assert.throws(() => browser.run('normalizeImport(input)', invalid));
  }
});

test('legacy quotations need no locator, but 1.1 matching markers require position metadata', () => {
  const browser = browserData();
  const report = citedReport();
  for (const version of ['1.0', '1.1']) {
    const input = structuredClone(report);
    input.schema_version = version;
    delete input.claims[0].citations[0].locator;
    delete input.claims[0].citations[0].verification;
    if (version === '1.0') assert.equal(browser.run('normalizeImport(input)', input).claims[0].citations[0].quote, report.claims[0].citations[0].quote);
    else assert.throws(() => browser.run('normalizeImport(input)', input), /精确引文/);
  }
  const legacy = browser.run('normalizeImport(input)', demo);
  assert.equal(legacy.schema_version, '1.0');
  assert.equal('citations' in legacy.claims[0], false);
});

test('new metadata rejects invalid types, fingerprints, enums and dangling references', () => {
  const browser = browserData();
  const mutations = [
    input => { input.evidence[0].content_sha256 = 'short'; },
    input => { input.evidence[0].excerpt_metadata.sha256 = 123; },
    input => { input.evidence[0].document_format = 'javascript'; },
    input => { input.evidence[0].source_family_method = 'proven_independent'; },
    input => { input.evidence[0].source_family_evidence_ids = ['E999']; },
    input => { input.retrieval_gaps[0].attempted = 'true'; },
    input => { input.retrieval_gaps[0].reason = 'proven_false'; },
    input => { delete input.retrieval_gaps[0].reason; },
    input => { input.retrieval_gaps[0].claim_id = 'C999'; },
    input => { input.search_log[0].round = 'confirmed'; },
    input => { input.search_log[0].gap_claim_ids = ['C999']; },
    input => { input.retrieval_gaps = Array.from({length:13}, () => input.retrieval_gaps[0]); }
  ];
  for (const mutate of mutations) { const input = citedReport(); mutate(input); assert.throws(() => browser.run('normalizeImport(input)', input)); }
});

test('chart points allow 100 distinct quotations while other entries remain limited to 24', () => {
  const browser = browserData();
  const report = citedReport();
  const quoteStrings = Array.from({length:100}, (_, index) => `[item${index}]`);
  report.evidence[1].excerpt = quoteStrings.join(' ');
  const quotes = quoteStrings.map(quote => exactCitation(report.evidence[1].excerpt, quote, 'E2'));
  report.charts[0].points[0].evidence_ids = ['E2'];
  report.charts[0].points[0].citations = quotes;
  assert.equal(browser.run('normalizeImport(input)', report).charts[0].points[0].citations.length, 100);
  const over = structuredClone(report);
  over.charts[0].points[0].citations.push(quotes[0]);
  assert.throws(() => browser.run('normalizeImport(input)', over), /数量超出/);
  report.claims[0].citations = quotes.slice(0,25);
  assert.throws(() => browser.run('normalizeImport(input)', report), /数量超出/);
});

test('citation UI keeps original quotation text and discloses excerpt-only matching in all three languages', () => {
  const browser = browserData();
  browser.context.el = (tag, cls, text, attrs = {}) => ({ tag, cls, text, attrs, children: [], append(...nodes) { this.children.push(...nodes); }, setAttribute(key,value) { this.attrs[key] = value; } });
  browser.context.sourceReferences = ids => ids.join(',');
  browser.context.externalLink = (label, url) => browser.context.el('a', '', label, {href:url});
  browser.context.actionButton = label => browser.context.el('button', '', label);
  browser.context.document = { createTextNode: value => value };
  const report = citedReport();
  browser.context.state.report = report;
  for (const language of ['zh-CN','en','ja']) {
    browser.run('I18n.setLanguage(input)', language);
    const view = browser.run('renderCitations(input)', report.claims[0].citations);
    assert(JSON.stringify(view).includes(report.claims[0].citations[0].quote));
    assert(JSON.stringify(view).includes(browser.run("t('citation.disclosure')")));
    assert(JSON.stringify(view).includes(browser.run("t('citation.repeated',{count:2})")));
    assert(JSON.stringify(view).includes('data-citation-source'));
    assert.equal(browser.run('renderCitations(input)', []).text, browser.run("t('citation.missing')"));
  }
});

test('adaptive search is opt-in and only its nonsecret preference is persisted and restored', () => {
  const browser = browserData();
  const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
  assert.match(html, /<input id="adaptive-search" type="checkbox" aria-describedby="adaptive-help">/);
  const controls = { 'adaptive-search': {checked:true}, 'include-screenshots':{checked:true}, 'research-depth':{value:'deep'}, 'search-provider':{value:'brave'}, 'ai-base-url':{value:''}, 'ai-model':{value:''} };
  browser.context.$ = id => controls[id];
  browser.context.getAISettings = () => ({base_url:'http://localhost:11434/v1',model:'local',api_key:'PRIVATE_API_KEY'});
  browser.context.updateConnectionStatus = () => {};
  let saved;
  browser.context.localStorage = { setItem:(_key,value) => { saved=value; }, getItem:() => saved };
  vm.runInContext(`const settingsKey = 'test'; ${portion('function saveSettings(', 'function updateConnectionStatus(')}`, browser.context);
  browser.run('saveSettings()');
  assert.equal(JSON.parse(saved).adaptive_search,true);
  assert(!saved.includes('PRIVATE'));
  controls['adaptive-search'].checked = false;
  browser.run('restoreSettings()');
  assert.equal(controls['adaptive-search'].checked,true);
});

test('research submits the actual adaptive selection alongside language, depth and source scope', async () => {
  const browser = browserData();
  const controls = { topic:{value:'A concrete question'}, 'research-depth':{value:'standard'}, 'adaptive-search':{checked:false}, 'include-screenshots':{checked:false} };
  browser.context.$ = id => controls[id];
  browser.context.state.pending = false;
  browser.context.document = {querySelector:() => ({value:'evidence-only'})};
  browser.context.validateAI = () => ({base_url:'http://localhost:11434/v1',model:'local',api_key:''});
  browser.context.getSearchSettings = () => ({provider:'tavily',api_key:'TEST_ONLY'});
  browser.context.searchCredentialReady = () => true;
  browser.context.saveSettings = () => {};
  browser.context.Workspace = {getSourceRequest:() => ({sources:[{url:'https://example.org/source',label:'source'}],source_policy:'preferred-only',source_credentials:[]})};
  let request;
  browser.context.requestJSON = async (endpoint,options) => {request={endpoint,...JSON.parse(options.body)};return null;};
  vm.runInContext(portion('async function submitResearch(', 'async function loadDemo('), browser.context);
  for (const enabled of [false,true]) {
    controls['adaptive-search'].checked = enabled;
    await browser.run('submitResearch({preventDefault(){}})');
    assert.equal(request.endpoint,'/api/research');
    assert.equal(request.adaptive_search,enabled);
    assert.equal(request.language,'zh-CN');
    assert.equal(request.depth,'standard');
    assert.equal(request.source_policy,'preferred-only');
    assert.equal(request.sources[0].url,'https://example.org/source');
  }
});
