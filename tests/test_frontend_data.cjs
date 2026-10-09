'use strict';

// Run with: node --test tests/test_frontend_data.cjs
// These checks exercise the actual browser-side data functions without a DOM or external packages.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

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

test('deep reports can import 24 sources, 8 searches and 24-source observations', () => {
  const browser = browserData();
  const report = structuredClone(demo);
  report.depth = 'deep';
  report.evidence = Array.from({ length: 24 }, (_, i) => ({ ...structuredClone(demo.evidence[0]), id: `E${i + 1}`, claim_ids: ['C1'] }));
  report.search_log = Array.from({ length: 8 }, (_, i) => ({ query: `query ${i}`, intent: 'neutral', provider: 'tavily', result_count: 1, ran_at: '2026-10-09' }));
  report.observations = [{ kind: 'data', text: '对照全部来源的数据口径。', claim_ids: ['C1'], evidence_ids: report.evidence.map(source => source.id) }];
  const imported = browser.run('normalizeImport(input)', report);
  assert.equal(imported.evidence.length, 24);
  assert.equal(imported.search_log.length, 8);
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
