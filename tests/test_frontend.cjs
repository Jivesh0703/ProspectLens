'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');

const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
function harness({saved = {}, research, storageFailure = false} = {}) {
 const elements = new Map();
 const values = new Map(Object.entries(saved));
 const writes = [];
 class Element {
  constructor() { this.value = ''; this.disabled = false; this.listeners = {}; this.files = []; this.innerHTML = ''; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  replaceChildren() {}
  add() {}
  append() {}
  click() {}
 }
 const element = selector => {
  if(!elements.has(selector)) elements.set(selector, new Element());
  return elements.get(selector);
 };
 const context = vm.createContext({
  document: {querySelector: element, createElement: () => new Element()},
  localStorage: {getItem: key => values.get(key) || null, setItem: (key, value) => {
   if(storageFailure) throw new Error('Storage full');
   values.set(key, value); writes.push(key);
  }},
  Option: function(text, value) { this.text = text; this.value = value; },
  URL, URLSearchParams, Blob, crypto, console, setTimeout: () => {},
  fetch: async (url, options) => {
   if(url === '/api/salesforce/status') return {json: async () => ({configured: false, connected: false})};
   return research(url, options);
  }
 });
 vm.runInContext(source, context);
 return {element, values, writes, evaluate: code => vm.runInContext(code, context),
  event: async (selector, name, event = {}) => element(selector).listeners[name](event)};
}
function result(account) {
 return {account, status:'Review draft', coverage:{supported:1,total:2,meaning:'Evidence coverage'},
  fit:[{criterion:'Subscription pricing',evidence_ids:['E1']},{criterion:'International customers',evidence_ids:[]}],
  evidence:[{id:'E1',quote:'Monthly subscriptions.',source_url:'https://example.com',retrieved_at:'2026-11-09T00:00:00Z'}],
  hypothesis:'Is this relevant?',buyer_role:'Finance leader',unknowns:[],outreach_draft:'Draft for review.',review_note:'Review',pages_read:1,tool_calls:1,trace:[],warnings:[],markdown:'Brief',elapsed_seconds:1};
}
function setupBatch(h, csv) {
 h.element('#product').value = 'We help finance teams reconcile subscription payments.';
 h.element('#criteria').value = 'Subscription pricing\nInternational customers';
 h.element('#batch-file').files = [{size:csv.length,text:async()=>csv}];
}

test('CSV accepts BOM, CRLF, quoted commas, blanks and duplicate URLs', () => {
 const h=harness();
 const csv='\uFEFFname,url\r\n"Example, Inc",https://example.com/\r\nSecond,https://second.com/\r\nAgain,https://example.com/\r\n';
 assert.equal(JSON.stringify(h.evaluate(`companyUrls(${JSON.stringify(csv)})`)),JSON.stringify(['https://example.com/','https://second.com/']));
});

test('CSV rejects oversized lists, malformed quoting, missing headers and unsafe schemes', () => {
 const h=harness();
 for(const csv of ['company\nhttps://example.com/','url\n"https://example.com/', 'url\nftp://example.com/', 'url\nhttps://user:secret@example.com/', 'url\n'+Array(21).fill('https://example.com/').join('\n')]) {
  assert.throws(()=>h.evaluate(`companyUrls(${JSON.stringify(csv)})`));
 }
});

test('spreadsheet formula prefixes are escaped in CSV exports', () => {
 const h=harness();
 for(const text of ['=SUM(1,2)','+cmd','@test','-1','   =1+1','\t=1']) {
  const escaped=h.evaluate(`csvCell(${JSON.stringify(text)})`);
  assert.ok(escaped.startsWith('"\''));
 }
 assert.equal(h.evaluate('csvCell(3)'), '"3"');
});

test('profiles persist and earlier AccountBrief data migrates on save', async () => {
 const h=harness({saved:{'accountbrief.workspace.v1':JSON.stringify({profiles:[{name:'Old',product:'A sufficiently long offering.',criteria:['Software']}],briefs:[]})}});
 assert.equal(h.evaluate('workspace.profiles[0].name'),'Old');
 h.element('#profile-name').value='Finance';
 h.element('#product').value='We help finance teams match incoming invoice payments.';
 h.element('#criteria').value='Subscription pricing';
 await h.event('#save-profile','click');
 assert.ok(h.values.has('prospectlens.workspace.v1'));
 assert.equal(JSON.parse(h.values.get('prospectlens.workspace.v1')).profiles.length,2);
});

test('storage failures leave research usable and display a download reminder', () => {
 const h=harness({storageFailure:true});
 h.evaluate(`saveBrief({url:'https://example.com/',product:'A sufficiently long offering.',criteria:['Software']},${JSON.stringify(result('example.com'))})`);
 assert.match(h.element('#storage-status').textContent,/Download/);
 assert.equal(h.evaluate('workspace.briefs.length'),1);
});

test('batch processes sequentially, preserves shared profile and stores completed briefs', async () => {
 const requests=[];
 let active=0,maxActive=0;
 const h=harness({research: async (url,options)=>{
  active++; maxActive=Math.max(maxActive,active);
  const input=JSON.parse(options.body); requests.push(input);
  await Promise.resolve(); active--;
  return {ok:true,status:200,json:async()=>result(new URL(input.url).hostname)};
 }});
 setupBatch(h,'url\nhttps://example.com/\nhttps://second.com/');
 await h.event('#batch-start','click');
 assert.equal(maxActive,1);
 assert.equal(requests.length,2);
 assert.deepEqual(requests[0].criteria,requests[1].criteria);
 assert.equal(h.evaluate('workspace.briefs.length'),2);
 assert.equal(h.evaluate('batchRows[0].status'),'Manual review needed');
 assert.equal(h.element('#run').disabled,false);
});

test('429 keeps current row queued and resume continues without repeating completed rows', async () => {
 let count=0;
 const h=harness({research:async()=>{
  count++;
  if(count===2) return {ok:false,status:429,json:async()=>({error:'Quota reached'})};
  return {ok:true,status:200,json:async()=>result('example.com')};
 }});
 setupBatch(h,'url\nhttps://example.com/\nhttps://second.com/');
 await h.event('#batch-start','click');
 assert.equal(h.evaluate('batchRows[0].status'),'Manual review needed');
 assert.equal(h.evaluate('batchRows[1].status'),'Queued');
 await h.event('#batch-start','click');
 assert.equal(count,3);
 assert.equal(h.evaluate('workspace.briefs.length'),2);
});

test('provider failure pauses remaining accounts and is excluded from history', async () => {
 let count=0;
 const h=harness({research:async()=>{
  count++;
  return {ok:true,status:200,json:async()=>({service_error:'Provider unavailable'})};
 }});
 setupBatch(h,'url\nhttps://example.com/\nhttps://second.com/');
 await h.event('#batch-start','click');
 assert.equal(count,1);
 assert.equal(h.evaluate('workspace.briefs.length'),0);
 assert.equal(h.evaluate('batchRows[1].status'),'Queued');
});

test('invalid batch makes no research request', async () => {
 let count=0;
 const h=harness({research:async()=>{count++;}});
 setupBatch(h,'website\nhttps://example.com/');
 await h.event('#batch-start','click');
 assert.equal(count,0);
 assert.match(h.element('#batch-status').textContent,/url column/);
});

test('Salesforce requires account selection and review, then saves the selected ID', async () => {
 const requests=[];
 const h=harness({research:async(url,options)=>{
  requests.push({url,options});
  if(url.startsWith('/api/salesforce/accounts?')) return {ok:true,status:200,json:async()=>({accounts:[{id:'001000000000001',name:'Example Demo',website:'https://example.com'}]})};
  return {ok:true,status:201,json:async()=>({id:'00T000000000001'})};
 }});
 await h.evaluate(`attachSalesforceReview(${JSON.stringify(result('www.example.com'))})`);
 assert.match(requests[0].url,/q=example.com/);
 assert.equal(h.element('#salesforce-save').disabled,true);
 h.element('#review-confirm').checked=true;
 await h.event('#review-confirm','change');
 assert.equal(h.element('#salesforce-save').disabled,true);
 await h.event('#salesforce-matches','click',{target:{closest:()=>({dataset:{accountId:'001000000000001'}})}});
 assert.equal(h.element('#salesforce-save').disabled,false);
 await h.event('#salesforce-save','click');
 assert.equal(JSON.parse(requests[1].options.body).account_id,'001000000000001');
 assert.equal(h.element('#salesforce-save').disabled,true);
});

test('Salesforce unmatched account offers a create link and keeps save disabled', async () => {
 const h=harness({research:async()=>({ok:true,status:200,json:async()=>({accounts:[],create_url:'https://org.my.salesforce.com/lightning/o/Account/new'})})});
 await h.evaluate(`attachSalesforceReview(${JSON.stringify(result('example.com'))})`);
 assert.match(h.element('#salesforce-matches').innerHTML,/Create an account in Salesforce/);
 assert.equal(h.element('#salesforce-save').disabled,true);
});

test('editing account search clears the previous selection', async () => {
 const h=harness({research:async()=>({ok:true,status:200,json:async()=>({accounts:[{id:'001000000000001',name:'Example',website:null}]})})});
 await h.evaluate(`attachSalesforceReview(${JSON.stringify(result('example.com'))})`);
 h.element('#review-confirm').checked=true;
 await h.event('#salesforce-matches','click',{target:{closest:()=>({dataset:{accountId:'001000000000001'}})}});
 assert.equal(h.element('#salesforce-save').disabled,false);
 h.element('#salesforce-search').value='Another';
 await h.event('#salesforce-search','input');
 assert.equal(h.element('#salesforce-save').disabled,true);
});

test('quality review displays flagged claims with escaped model text', () => {
 const h=harness();
 const review={status:'completed',summary:{review_required:true},evaluation:{fit:[{criterion:'Subscription pricing',verdict:'partial',explanation:'Limited support.'}],outreach:{explanation:'Unverified pain.'},discovery:{explanation:'Conditional question.'},unsupported_claims:[{section:'outreach',claim:'<script>bad</script>',explanation:'Not established.'}]}};
 const html=h.evaluate(`evaluationMarkup(${JSON.stringify({judge_evaluation:review})})`);
 assert.match(html,/Review flagged items/);
 assert.match(html,/&lt;script&gt;/);
 assert.doesNotMatch(html,/<script>/);
});

test('quality review outage stays distinct from research failure', () => {
 const h=harness();
 const html=h.evaluate(`evaluationMarkup({judge_evaluation:{status:'unavailable',error:'Judge busy'}})`);
 assert.match(html,/Unavailable/);
 assert.match(html,/Judge busy/);
 assert.match(html,/Review this brief manually/);
});

test('completed automatic evaluation is displayed at the end of the rendered brief', () => {
 const h=harness({research:async()=>({ok:false,json:async()=>({error:'Not connected'})})});
 const brief=result('example.com');
 brief.judge_evaluation={status:'completed',summary:{review_required:false},evaluation:{fit:[{criterion:'Subscription pricing',verdict:'supported',explanation:'Monthly terms support recurring billing.'}],outreach:{explanation:'Grounded in cited evidence.'},discovery:{explanation:'Conditional and relevant.'},unsupported_claims:[]}};
 h.evaluate(`render(${JSON.stringify(brief)})`);
 const html=h.element('#output').innerHTML;
 assert.match(html,/No issues flagged/);
 assert.match(html,/Monthly terms support recurring billing/);
 assert.ok(html.indexOf('AI quality review')>html.indexOf('Research activity'));
});
