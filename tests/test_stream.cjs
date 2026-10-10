'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {readResearchStream} = require('../frontend/stream.js');
const encoder = new TextEncoder();
const report = {schema_version:'1.1',topic:'原句 🛰️',claims:[],evidence:[]};
const event = (name,payload,newline='\n') => `event: ${name}${newline}data: ${JSON.stringify(payload)}${newline}${newline}`;
function chunks(text, width = 7) {
  const data = encoder.encode(text);let cursor=0,canceled=0,released=0;
  return {
    body:{getReader:()=>({read:async()=>cursor>=data.length?{done:true}:{done:false,value:data.slice(cursor,(cursor+=width))},cancel:async()=>{canceled++;},releaseLock:()=>{released++;}})},
    canceled:()=>canceled,released:()=>released
  };
}

test('SSE incrementally decodes split UTF-8, LF/CRLF frames and multiline data without inventing totals', async () => {
  const progress=[];
  const text = ': keepalive\r\n\r\n' + event('progress',{stage:'reading',completed:2,total:null},'\r\n') + event('progress',{stage:'reading',completed:3,total:6}) + 'event: result\ndata: {"schema_version":"1.1",\ndata: "topic":"原句 🛰️","claims":[],"evidence":[]}\n\n';
  const stream=chunks(text,1);
  const output=await readResearchStream(stream.body,{onProgress:value=>progress.push(value)});
  assert.equal(output.topic,report.topic);
  assert.deepEqual(progress,[{stage:'reading',completed:2,total:null},{stage:'reading',completed:3,total:6}]);
  assert.equal(stream.released(),1);
  assert.equal(stream.canceled(),0);
});

test('exactly one terminal event is required; duplicate result/error or post-result progress rejects the report', async () => {
  for (const trailer of [event('result',report),event('error',{error:{code:'failed',message:'failed'}}),event('progress',{stage:'complete',completed:1,total:1})]) {
    const stream=chunks(event('result',report)+trailer);
    await assert.rejects(readResearchStream(stream.body),failure=>failure.code==='duplicate_terminal');
    assert.equal(stream.canceled(),1);
  }
  await assert.rejects(readResearchStream(chunks(': ping\n\n').body),failure=>failure.code==='incomplete');
  await assert.rejects(readResearchStream(chunks(event('result',report).trimEnd()).body),failure=>failure.code==='incomplete');
});

test('server errors preserve the message, malformed frames and invalid counters do not succeed', async () => {
  await assert.rejects(readResearchStream(chunks(event('error',{error:{code:'provider_failed',message:'服务失败'}})).body),failure=>failure.code==='server'&&failure.message==='服务失败');
  for(const text of [
    'event: result\ndata: not-json\n\n',event('result',{claims:[]}),
    event('progress',{stage:'invented',completed:0,total:1}),event('progress',{stage:'reading',completed:2,total:1}),
    event('progress',{stage:'reading',completed:-1,total:null}),event('progress',{stage:'reading',completed:0}),
    event('error',{error:{message:'missing code'}})
  ]) await assert.rejects(readResearchStream(chunks(text).body),failure=>failure.code==='invalid');
});

test('UTF-8 byte frame and total limits stop reading and cancel the reader', async () => {
  const oversized=chunks('event: result\ndata: '+JSON.stringify({...report,topic:'中'.repeat(40)})+'\n\n',1024);
  await assert.rejects(readResearchStream(oversized.body,{frameLimit:100}),failure=>failure.code==='limit');
  assert.equal(oversized.canceled(),1);
  const many=chunks(event('progress',{stage:'reading',completed:1,total:2})+event('result',report),20);
  await assert.rejects(readResearchStream(many.body,{totalLimit:80}),failure=>failure.code==='limit');
  assert.equal(many.canceled(),1);
  const noDelimiter=chunks('data: '+ '中'.repeat(100),5);
  await assert.rejects(readResearchStream(noDelimiter.body,{frameLimit:50}),failure=>failure.code==='limit');
});

test('abort cancels a pending read and never yields the terminal report', async () => {
  const controller=new AbortController();let resolveRead,canceled=0,released=0;
  const body={getReader:()=>({read:()=>new Promise(resolve=>{resolveRead=resolve;}),cancel:async()=>{canceled++;resolveRead?.({done:true});},releaseLock:()=>{released++;}})};
  const waiting=readResearchStream(body,{signal:controller.signal});
  controller.abort();
  await assert.rejects(waiting,failure=>failure.name==='AbortError');
  assert(canceled>=1);
  assert.equal(released,1);
});
