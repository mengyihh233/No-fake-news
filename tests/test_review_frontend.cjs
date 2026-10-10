'use strict';

// Backend fixtures are constructed locally; no app import, .env, HTTP or model calls.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const { webcrypto } = require('node:crypto');
const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'frontend/app.js'), 'utf8');
function part(start, end) {const first=app.indexOf(start),last=app.indexOf(end,first);assert(first>=0&&last>first);return app.slice(first,last);}
function browser() {
  const context={URL,structuredClone,Intl,Date,TextEncoder,Uint8Array,crypto:webcrypto,window:{location:{origin:'http://localhost:8000'}},state:{capabilities:{configured:{}}}};
  vm.createContext(context);
  for (const file of ['i18n.js','review.js']) vm.runInContext(fs.readFileSync(path.join(root,'frontend',file),'utf8'),context);
  vm.runInContext(`const I18n=NoFakeNewsI18n, Review=NoFakeNewsReview;const t=(key,values)=>I18n.t(key,values);const asArray=value=>Array.isArray(value)?value:[];const textValue=value=>value==null?'':typeof value==='object'?'':String(value);${part('function safeUrl(', 'function externalLink(')}${part('function pick(', 'function getAISettings(')}${part('function normalizeImport(', 'async function importReport(')}`,context);
  return {context,run(code,input){context.input=input;return vm.runInContext(code,context);}};
}
const pythonFixture = String.raw`
import sys,json
sys.path.insert(0,'tests')
from test_review import reviewed_source_report,QUOTE
from truth_backend.models import CitationReview,ReviewItem,Calculation
from truth_backend.reports import public_report,validate_references
from truth_backend.review_targets import all_review_targets,target_sha256,selected_review_targets,build_review_payload,review_input_characters
from truth_backend.citations import locate_quote,excerpt_metadata
result=[]
for case,depth in [('all-targets','standard'),('capacity','brief'),('input-budget','deep')]:
 r=reviewed_source_report(depth)
 # Astral characters exercise Python codepoint counts and UTF-8 hashing.
 r.evidence[0].excerpt='🧭🚀'+r.evidence[0].excerpt
 r.evidence[0].excerpt_metadata=excerpt_metadata(r.evidence[0].excerpt)
 sources={s.id:s for s in r.evidence}
 items=[*r.claims,*r.observations,*r.timeline,*r.comparisons,*r.reasoning,r.summary,*r.charts[0].points]
 for item in items:
  item.citations=[locate_quote(c,sources) for c in item.citations]
 # Real backend defaults include calculation:null, verdict/analysis:null.
 r.charts[0].points.append(r.charts[0].points[0].model_copy(deep=True,update={'label':'missing','value':None}))
 r.charts[0].points.append(r.charts[0].points[0].model_copy(deep=True,update={'label':'count','value':1.0,'calculation':Calculation(operation='count',source_quotes=[QUOTE],description='Count only the single listed record.')}))
 if case!='all-targets':
  r.observations=[r.observations[0].model_copy(deep=True,update={'text':str(i)+('x'*4900 if case=='input-budget' else ' observed record')}) for i in range(40)]
 all_targets=all_review_targets(r)
 selected=selected_review_targets(r,'ja')
 r.schema_version='1.2'
 r.citation_review=CitationReview(generated_at='2026-10-10T00:00:00Z',language='ja',model='offline-fixture',available_targets=len(all_targets),selected_targets=len(selected),reviewed_targets=len(selected),not_reviewed_targets=len(all_targets)-len(selected),capacity={'brief':12,'standard':24,'deep':40}[depth],input_characters=review_input_characters(build_review_payload(selected,depth,'ja')),items=[ReviewItem(target_id=t.target_id,target_sha256=target_sha256(t),relation='partial',issues=['scope'],explanation='Fixture model advice, not verification.',citations=t.citations) for t in selected])
 validate_references(r)
 result.append({'case':case,'report':public_report(r),'hashes':{t.target_id:target_sha256(t) for t in all_targets},'selected':[t.target_id for t in selected]})
print(json.dumps(result,ensure_ascii=True))
`;
let cached;
function fixtures() {
  if (!cached) cached=JSON.parse(execFileSync('python',['-X','utf8','-c',pythonFixture],{cwd:root,encoding:'utf8',maxBuffer:5*1024*1024}));
  return structuredClone(cached);
}

test('Python-created 1.2 targets, defaults, float/null/count points, budgets and Unicode hashes agree in the browser', async () => {
  const b=browser();
  for(const fixture of fixtures()) {
    const report=b.run('normalizeImport(input)',fixture.report);
    const targets=b.run('reviewTargets(input)',report);
    const snapshots=targets.map(target=>b.context.NoFakeNewsReview.snapshot(report,target));
    for(const target of snapshots) {
      const actual=await b.context.NoFakeNewsReview.sha256(b.context.NoFakeNewsReview.serialize(b.context.NoFakeNewsReview.canonicalNumbers(target),{sorted:true,compact:true}));
      assert.equal(actual,fixture.hashes[target.target_id],`${fixture.case}: ${target.target_id}`);
    }
    const selected=b.context.NoFakeNewsReview.selectTargets(snapshots,report.depth,'ja');
    assert.deepEqual(Array.from(selected,item=>item.target_id),fixture.selected,fixture.case);
    await b.context.NoFakeNewsReview.verify(report,targets);
    const exported=JSON.stringify(report);
    // The real backend must accept the actual JS JSON round trip, including 20.0 -> 20.
    const validated=execFileSync('python',['-X','utf8','-c','import sys,json; from truth_backend.models import Report; from truth_backend.reports import validate_references; r=Report.model_validate(json.load(sys.stdin)); validate_references(r); print("valid")'],{cwd:root,input:exported,encoding:'utf8',maxBuffer:1024*1024});
    assert.equal(validated.trim(),'valid');
  }
});

test('stale review fingerprints, input counts and selection counts are rejected before installation', async () => {
  const b=browser();
  for(const mutate of [
    report=>{report.summary.text+=' changed';},
    report=>{report.evidence[0].context+=' changed';},
    report=>{report.evidence[0].title+=' changed';},
    report=>{report.evidence[0].excerpt+=' more context';},
    report=>{report.citation_review.items[0].target_sha256='d'.repeat(64);},
    report=>{report.citation_review.input_characters++;},
    report=>{report.citation_review.selected_targets--;}
  ]) {
    const report=b.run('normalizeImport(input)',fixtures()[0].report);
    mutate(report);
    await assert.rejects(()=>b.context.NoFakeNewsReview.verify(report,b.run('reviewTargets(input)',report)),error=>error.name==='ReviewError');
  }
  const report=b.run('normalizeImport(input)',fixtures()[0].report);
  b.context.crypto=null;
  await assert.rejects(()=>b.context.NoFakeNewsReview.verify(report,b.run('reviewTargets(input)',report)),error=>error.code==='unavailable');
});

test('installation waits for fingerprint validation, rejects stale data without overwriting and retains mode flags', async () => {
  const b=browser();
  const original={topic:'Previous valid report'};
  b.context.state={report:original,installationId:0,operationId:0};
  const errors=[];let rendered=0;
  b.context.showError=message=>errors.push(message);
  b.context.renderReport=()=>{rendered++;};
  b.context.document={querySelector:()=>({checked:false})};
  b.context.$=()=>({scrollIntoView(){},value:''});
  vm.runInContext(part('async function installReport(', 'async function submitResearch('),b.context);
  const report=fixtures()[0].report;
  const installing=b.run("installReport(input,'ai-summary',true,true)",report);
  assert.equal(b.context.state.report,original);assert.equal(rendered,0);
  assert.equal(await installing,true);assert.equal(rendered,1);assert.equal(b.context.state.isDemo,true);assert.equal(b.context.state.isImported,true);
  const installed=b.context.state.report;
  report.summary.text+=' stale';
  assert.equal(await b.run("installReport(input,'ai-summary',false,false)",report),false);
  assert.equal(b.context.state.report,installed);assert.equal(rendered,1);assert.equal(errors.length,1);
  assert.equal(await b.run("installReport(input,'evidence-only',false,true)",report),true);
  assert.equal('citation_review' in b.context.state.report,false);
  assert.equal('summary' in b.context.state.report,false);
});

test('canonical decimal strings and Python-spaced Unicode JSON counts avoid float formatting drift', () => {
  const b=browser();
  const values=[20,20.0,-0,0.000001,1e-7,1e21,-2.5e25,1.23e-10];
  const expected=JSON.parse(execFileSync('python',['-X','utf8','-c','import sys,json; from truth_backend.review_targets import canonical_numbers; print(json.dumps(canonical_numbers(json.load(sys.stdin))))'],{cwd:root,input:JSON.stringify(values),encoding:'utf8'}));
  assert.deepEqual(Array.from(b.context.NoFakeNewsReview.canonicalNumbers(values)),expected);
  assert.equal(b.context.NoFakeNewsReview.inputCharacters({text:'🛰️ 日本語',numbers:['20',null]}),Array.from('{"text": "🛰️ 日本語", "numbers": ["20", null]}').length);
});

test('new investigation invalidates an installation still awaiting fingerprint verification', async () => {
  const b=browser();
  b.context.state={report:{topic:'Previous report'},installationId:0,operationId:0,pending:false};
  let release,rendered=0;
  b.context.NoFakeNewsReview.verify=()=>new Promise(resolve=>{release=resolve;});
  b.context.renderReport=()=>{rendered++;};
  b.context.showError=message=>{throw new Error(message);};
  b.context.toast=()=>{};b.context.clearError=()=>{};
  const handlers=new Map(),controls=new Map();
  b.context.$=id=>{if(!controls.has(id))controls.set(id,{addEventListener(event,handler){handlers.set(`${id}:${event}`,handler);},replaceChildren(){},scrollIntoView(){},focus(){},value:''});return controls.get(id);};
  b.context.document={querySelector:()=>({checked:false}),body:{classList:{remove(){}}}};
  vm.runInContext(part('async function installReport(', 'async function submitResearch('),b.context);
  vm.runInContext(part("$('new-investigation').addEventListener", "document.querySelectorAll('.section-nav a')"),b.context);
  const installing=b.run("installReport(input,'ai-summary',false,true)",fixtures()[0].report);
  assert.equal(b.context.state.installationId,1);
  handlers.get('new-investigation:click')();
  assert.equal(b.context.state.report,null);assert.equal(b.context.state.installationId,2);
  release();
  assert.equal(await installing,false);assert.equal(rendered,0);assert.equal(b.context.state.report,null);
});
