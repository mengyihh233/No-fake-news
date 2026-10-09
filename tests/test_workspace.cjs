'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const I18n = require('../frontend/i18n.js');
const W = require('../frontend/workspace.js');
const demo = JSON.parse(fs.readFileSync(path.join(root, 'examples/demo-report.json'), 'utf8'));

test('all static and literal dynamic translation keys exist in every language', () => {
  const app = fs.readFileSync(path.join(root, 'frontend/app.js'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
  const keys = [...app.matchAll(/\bt\('([^']+)'/g), ...html.matchAll(/data-i18n(?:-placeholder|-aria-label|-title)?="([^"]+)"/g)].map(match => match[1]);
  for (const language of I18n.languages) {
    I18n.setLanguage(language);
    for (const key of keys) assert(I18n.has(key), `${language}: missing ${key}`);
    for (const [key, value] of Object.entries(I18n.dictionaries[language])) {
      assert.equal(typeof value, 'string', `${language}: invalid ${key}`);
      assert(value.length > 0);
      const placeholders = value.match(/\{[a-zA-Z0-9_]+\}/g) || [];
      assert.deepEqual(placeholders.sort(), (I18n.dictionaries['zh-CN'][key].match(/\{[a-zA-Z0-9_]+\}/g) || []).sort(), `${language}: placeholders ${key}`);
    }
  }
  I18n.setLanguage('zh-CN');
});

test('resident source serialization allowlists nonsecret preferences', () => {
  const safe = W.safeSourcePreferences({ sources: [{ url:'https://example.org/report', label:'Source', password:'PRIVATE_PASSWORD', token:'PRIVATE_TOKEN' }], source_policy:'preferred-only', source_credentials:[{ token:'PRIVATE_TOKEN' }] });
  assert.deepEqual(safe, { sources:[{ url:'https://example.org/report', label:'Source' }], source_policy:'preferred-only' });
  assert(!JSON.stringify(safe).includes('PRIVATE'));
  assert.throws(() => W.sourceURL('https://name:password@example.org/'));
  assert.throws(() => W.sourceURL('http://example.org', true));
  assert.throws(() => W.sourceURL('https://example.org/path', true));
  assert.equal(W.sourceURL('https://example.org:443/', true), 'https://example.org');
});

test('evidence map uses recorded source IDs and removes judgment relationships in evidence mode', () => {
  const input = structuredClone(demo);
  input.mode = 'evidence-only';
  const data = W.graphData(input, 'C1');
  assert.equal(data.claim.id, 'C1');
  assert.equal(data.reasoning.length, 0);
  assert(data.observations.length > 0);
  assert(data.edges.filter(edge => edge.to === 'C1').every(edge => ['relevant_to','context'].includes(edge.relation)));
  for (const edge of data.edges.filter(edge => edge.to.startsWith('observation-'))) {
    const observation = input.observations[Number(edge.to.split('-')[1])];
    assert(observation.evidence_ids.includes(edge.from));
  }
  assert(data.edges.some(edge => edge.from === 'E1' && edge.to === 'C1'));
  input.mode = 'ai-summary';
  const judgment = W.graphData(input, 'C1');
  assert(judgment.reasoning.length > 0);
  assert(judgment.edges.some(edge => edge.from === 'E1' && edge.to === 'R1'));
});

test('report language and source scope survive evidence export without summary language', () => {
  const source = fs.readFileSync(path.join(root, 'frontend/app.js'), 'utf8');
  const first = source.indexOf('function pick('), last = source.indexOf('function getAISettings(', first);
  const context = { structuredClone, asArray: value => Array.isArray(value) ? value : [] };
  vm.createContext(context); vm.runInContext(source.slice(first,last),context);
  for (const language of ['zh-CN','en','ja']) {
    context.input = { ...structuredClone(demo), language, summary_language:language, source_policy:'preferred-only', preferred_sources:[{ url:'https://example.org',label:'Public', token:'PRIVATE' }] };
    const projected = vm.runInContext('evidenceProjection(input)',context);
    assert.equal(projected.language,language); assert.equal(projected.source_policy,'preferred-only');
    assert.equal(projected.summary_language,undefined); assert(!JSON.stringify(projected).includes('PRIVATE'));
  }
});
