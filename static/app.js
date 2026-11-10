'use strict';
const $ = s => document.querySelector(s);
const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let lastResult;
function download(kind) {
 if(!lastResult) return;
 const body=kind==='json'?JSON.stringify(lastResult,null,2):lastResult.markdown;
 const url=URL.createObjectURL(new Blob([body],{type:kind==='json'?'application/json':'text/markdown'}));
 const a=document.createElement('a');a.href=url;a.download=`prospectlens-${lastResult.account}.${kind==='json'?'json':'md'}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function evaluationMarkup(result) {
 const review=result.judge_evaluation;
 if(!review) return '<div class="panel result-section"><h3>AI quality review</h3><p class="small">Run research again to evaluate this saved brief.</p></div>';
 if(review.status!=='completed') return `<div class="panel result-section"><div class="section-title"><h3>AI quality review</h3><span class="badge amber">Unavailable</span></div><p class="small">${escapeHtml(review.error || review.reason || 'Quality review could not be completed.')} Review this brief manually.</p>${review.models_attempted?.length?`<p class="small">Evaluation attempts: ${review.models_attempted.length} · ${review.models_attempted.map(escapeHtml).join(' → ')}</p>`:''}</div>`;
 const evaluation=review.evaluation;
 return `<div class="panel result-section quality-review"><div class="section-title"><h3>AI quality review</h3><span class="badge ${review.summary.review_required?'amber':''}">${review.summary.review_required?'Review flagged items':'No issues flagged'}</span></div>${evaluation.fit.map(f=>`<div class="fit-row"><span>${escapeHtml(f.criterion)}<small class="fit-reason">${escapeHtml(f.explanation)}</small></span><span>${escapeHtml(f.verdict)}</span></div>`).join('')}<p class="small"><strong>Outreach</strong> · ${escapeHtml(evaluation.outreach.explanation)}</p><p class="small"><strong>Discovery question</strong> · ${escapeHtml(evaluation.discovery.explanation)}</p>${evaluation.unsupported_claims.map(c=>`<div class="quality-flag"><strong>Review this ${escapeHtml(c.section)} claim</strong><p>“${escapeHtml(c.claim)}”</p><p>${escapeHtml(c.explanation)}</p></div>`).join('')}<p class="small">AI feedback can be wrong. Check the original sources before using the brief.</p></div>`;
}
function render(r) {
 const e=escapeHtml;
 if(r.service_error){
  $('#output').innerHTML=`<div class="panel empty"><p class="eyebrow">RESEARCH UNAVAILABLE</p><h2>We couldn’t complete the research.</h2><p>${e(r.service_error)}</p><p>No account assessment was made. Resolve the connection issue, then try again.</p></div>`;
  return;
 }
 $('#output').innerHTML=`<div class="panel result-header"><p class="eyebrow">ACCOUNT RESEARCH / READY FOR YOUR REVIEW</p><div class="result-headline"><h2>${e(r.account)}</h2><span class="badge ${r.outreach_draft?'':'amber'}">${e(r.status)}</span></div><div class="stats"><div><strong>${r.coverage.supported}<small> / ${r.coverage.total}</small></strong><span>Criteria with evidence</span></div><div><strong>${r.pages_read}</strong><span>Pages inspected</span></div><div><strong>${r.tool_calls}</strong><span>Research steps</span></div></div><p class="small">${e(r.coverage.meaning)}</p></div>
 <div class="panel result-section"><div class="section-title"><h3>Is this account a fit?</h3><span class="section-label">INFERENCE · REVIEW RELEVANCE</span></div>${r.fit.map(f=>`<div class="fit-row ${f.evidence_ids.length?'':'unknown'}"><span>${e(f.criterion)}${f.reason?`<small class="fit-reason">${e(f.reason)}</small>`:''}</span><span>${f.evidence_ids.length?'Evidence found · '+f.evidence_ids.map(e).join(', '):'Unknown'}</span></div>`).join('')}<p class="small">A relevant quote supports an inference. It does not establish buying intent.</p></div>
 <div class="panel result-section" id="evidence-section"><div class="section-title"><h3>What the website actually says</h3><span class="section-label">SOURCE EVIDENCE</span></div>${r.evidence.length?r.evidence.map(item=>`<div class="evidence"><div class="evidence-line"><span class="eid">${e(item.id)}</span><div><p>“${e(item.quote)}”</p><a class="source" href="${e(item.source_url)}" target="_blank" rel="noopener noreferrer">${e(item.source_url)} ↗</a><p class="small">Retrieved · ${e(item.retrieved_at.slice(0,19))} UTC</p></div></div></div>`).join(''):'<p class="small">No relevant evidence was found. Try another page or refine your criteria.</p>'}<p class="small">Quotes are checked against retrieved text. Company claims are not independently verified.</p></div>
 <div class="panel result-section" id="hypothesis-section"><div class="section-title"><h3>A question to validate</h3><span class="section-label">HYPOTHESIS</span></div><div class="hypothesis">${e(r.hypothesis)}</div><p class="small">Suggested buyer role: <strong>${e(r.buyer_role)}</strong> · confirm during discovery</p><ul class="unknowns">${r.unknowns.map(x=>`<li>${e(x)}</li>`).join('')}</ul></div>
 <div class="panel result-section" id="draft-section"><div class="section-title"><h3>Start a better conversation</h3><span class="section-label">DRAFT · HUMAN REVIEW</span></div><pre class="draft">${e(r.outreach_draft||'Outreach withheld: insufficient relevant evidence. Research manually before personalizing a message.')}</pre><p class="small">${e(r.review_note)}</p><div class="export-row"><button class="export" id="export-md">Download brief .md ↓</button><button class="export" id="export-json">Download evidence .json ↓</button></div></div>
 <div class="panel result-section trace" id="trace-section"><details><summary>Research activity · ${r.trace.length} steps</summary><div class="trace-list">${r.trace.map(t=>`<div class="trace-row"><strong>${t.step.toString().padStart(2,'0')} / ${e(t.tool)} · ${e(t.status)}</strong><p>${e(t.detail)}</p><code>${e(JSON.stringify(t.arguments))}</code></div>`).join('')}</div></details>${r.warnings.map(w=>`<p class="warning">${e(w)}</p>`).join('')}</div>${evaluationMarkup(r)}`;
 attachSalesforceReview(r);
 $('#export-md').addEventListener('click',()=>download('md'));$('#export-json').addEventListener('click',()=>download('json'));
}
$('#research-form').addEventListener('submit',async event=>{
 event.preventDefault();if(batchRunning) return;$('#error').hidden=true;$('#run').disabled=true;$('#run').textContent='Researching…';$('#batch-start').disabled=true;
 $('#progress').textContent='Researching the company, checking sources, and evaluating the brief. This may take a few minutes.';
 // Clear the previous account so an error cannot leave stale results looking current.
 lastResult=null;$('#output').innerHTML='<div class="panel empty"><p class="eyebrow">RESEARCH IN PROGRESS</p><h2>Following the evidence.</h2><p>Inspecting sources and reviewing evidence relevance and outreach claims. Your brief and AI quality review will appear together.</p></div>';
 try{
  const researchInput={url:$('#url').value,product:$('#product').value,criteria:$('#criteria').value.split('\n').map(x=>x.trim()).filter(Boolean)};
  const response=await fetch('/api/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'gemini',workflow:'agent',...researchInput})});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'Research request failed.');lastResult=result;render(result);if(!result.service_error)saveBrief(researchInput,result);$('#progress').textContent=`Completed in ${result.elapsed_seconds}s. Review the evidence before using the draft.`;
 }catch(error){$('#error').textContent=error.message;$('#error').hidden=false;$('#progress').textContent='';$('#output').innerHTML='<div class="panel empty"><p class="eyebrow">INPUT NEEDS ATTENTION</p><h2>No brief was generated.</h2><p>Resolve the input error shown beside the form, then run again.</p></div>';}
 finally{$('#batch-start').disabled=false;$('#run').disabled=false;$('#run').innerHTML='Build account brief <span>↗</span>';}
});


const storageKey = 'prospectlens.workspace.v1';
let workspace = {profiles: [], briefs: []};
try {
 const saved = JSON.parse(localStorage.getItem(storageKey) || localStorage.getItem('accountbrief.workspace.v1'));
 if(saved && Array.isArray(saved.profiles) && Array.isArray(saved.briefs)) {
  workspace.profiles = saved.profiles.filter(p => p && typeof p.name === 'string' && typeof p.product === 'string' && Array.isArray(p.criteria) && p.criteria.every(c => typeof c === 'string')).slice(0, 20);
  workspace.briefs = saved.briefs.filter(b => b && typeof b.id === 'string' && b.input && typeof b.input.url === 'string' && typeof b.input.product === 'string' && Array.isArray(b.input.criteria) && b.result && b.result.coverage && Array.isArray(b.result.fit) && Array.isArray(b.result.trace)).slice(0, 30);
 }
} catch(error) {
 $('#storage-status').textContent = 'Saved data could not be loaded. New research and downloads are still available.';
}
function persistWorkspace() {
 try {
  localStorage.setItem(storageKey, JSON.stringify(workspace));
  $('#storage-status').textContent = 'Saved in this browser.';
 } catch(error) {
  $('#storage-status').textContent = 'Browser storage is unavailable or full. Download your current brief to keep it.';
 }
}
function renderProfiles() {
 $('#profiles').replaceChildren(new Option('Choose a saved profile', ''));
 workspace.profiles.forEach((profile, index) => $('#profiles').add(new Option(profile.name, String(index))));
}
function renderHistory() {
 const query = $('#history-search').value.toLowerCase().trim();
 const entries = workspace.briefs.filter(b => (b.result.account+' '+b.input.criteria.join(' ')).toLowerCase().includes(query));
 $('#history-list').innerHTML = entries.length ? entries.map(b => `<div class="history-entry"><strong>${escapeHtml(b.result.account)}</strong><p class="help">${escapeHtml(new Date(b.savedAt).toLocaleString())} · ${escapeHtml(b.result.coverage.supported)}/${escapeHtml(b.result.coverage.total)} criteria supported</p><button class="export" data-open="${escapeHtml(b.id)}">Open brief</button> <button class="export" data-delete="${escapeHtml(b.id)}">Delete</button></div>`).join('') : '<p class="help">No saved briefs match.</p>';
}
function saveBrief(input, result) {
 workspace.briefs.unshift({id:crypto.randomUUID(), savedAt:new Date().toISOString(), input, result});
 workspace.briefs = workspace.briefs.slice(0, 30);
 persistWorkspace();
 renderHistory();
}
$('#save-profile').addEventListener('click', () => {
 const name = $('#profile-name').value.trim();
 const product = $('#product').value.trim();
 const criteria = $('#criteria').value.split('\n').map(c => c.trim()).filter(Boolean);
 if(!name || product.length < 20 || product.length > 1200 || criteria.some(c=>c.length<3 || c.length>120) || criteria.length < 1 || criteria.length > 5 || new Set(criteria.map(c=>c.toLowerCase())).size !== criteria.length) {
  $('#storage-status').textContent = 'Enter a profile name, an offering of 20–1200 characters, and 1–5 unique criteria.';
  return;
 }
 workspace.profiles = [{name,product,criteria}, ...workspace.profiles.filter(p=>p.name.toLowerCase()!==name.toLowerCase())].slice(0,20);
 persistWorkspace();
 renderProfiles();
});
$('#profiles').addEventListener('change', () => {
 if($('#profiles').value === '') return;
 const profile = workspace.profiles[Number($('#profiles').value)];
 $('#profile-name').value = profile.name;
 $('#product').value = profile.product;
 $('#criteria').value = profile.criteria.join('\n');
});
$('#delete-profile').addEventListener('click', () => {
 if($('#profiles').value === '') return;
 workspace.profiles.splice(Number($('#profiles').value),1);
 persistWorkspace();
 renderProfiles();
});
$('#history-search').addEventListener('input', renderHistory);
$('#history-list').addEventListener('click', event => {
 const button = event.target.closest('button');
 if(!button || $('#run').disabled) return;
 const entry = workspace.briefs.find(b=>b.id === (button.dataset.open || button.dataset.delete));
 if(!entry) return;
 if(button.dataset.delete) {
  workspace.briefs = workspace.briefs.filter(b=>b.id !== entry.id);
  persistWorkspace();
  renderHistory();
  return;
 }
 $('#url').value = entry.input.url;
 $('#product').value = entry.input.product;
 $('#criteria').value = entry.input.criteria.join('\n');
 lastResult = entry.result;
 render(lastResult);
 $('#error').hidden = true;
 $('#progress').textContent = 'Opened saved research from '+new Date(entry.savedAt).toLocaleString()+'. Run again to refresh sources.';
});
renderProfiles();
renderHistory();


let batchRows = [];
let batchInput = null;
let batchRunning = false;
let batchPaused = false;
function parseCsv(text) {
 const rows = [];
 let row = [], cell = '', quoted = false;
 for(let i=0; i<text.length; i++) {
  const c = text[i];
  if(c === '"') {
   if(quoted && text[i+1] === '"') { cell += '"'; i++; }
   else if(!quoted && cell !== '') throw new Error('Unexpected quote in CSV.');
   else quoted = !quoted;
  } else if(!quoted && (c === ',' || c === '\n' || c === '\r')) {
   row.push(cell); cell = '';
   if(c !== ',') {
    if(row.some(value=>value.trim())) rows.push(row);
    row = [];
    if(c === '\r' && text[i+1] === '\n') i++;
   }
  } else cell += c;
 }
 if(quoted) throw new Error('CSV has an unclosed quoted field.');
 row.push(cell);
 if(row.some(value=>value.trim())) rows.push(row);
 return rows;
}
function companyUrls(text) {
 const rows = parseCsv(text.replace(/^\uFEFF/, ''));
 if(rows.length < 2) throw new Error('Include a url header and at least one company.');
 const column = rows[0].findIndex(c=>c.trim().toLowerCase()==='url');
 if(column < 0) throw new Error('CSV needs a url column.');
 if(rows.length > 21) throw new Error('Upload at most 20 account rows.');
 return [...new Set(rows.slice(1).map((row,index)=>{
  const value = (row[column] || '').trim();
  let url;
  try { url = new URL(value); } catch(error) { throw new Error('Invalid URL on CSV row '+(index+2)+'.'); }
  if(!['http:','https:'].includes(url.protocol) || url.username || url.password || url.port) throw new Error('Use a public HTTP(S) URL without credentials or custom ports on row '+(index+2)+'.');
  url.hash='';
  return url.href;
 }))];
}
function csvCell(value) {
 let text = String(value ?? '');
 if(/^[=+@\-\t\r\n]/.test(text.trimStart())) text = "'"+text;
 return '"'+text.replace(/"/g,'""')+'"';
}
function downloadCsv(rows,name) {
 const url = URL.createObjectURL(new Blob(['\uFEFF'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
 const link = document.createElement('a'); link.href=url; link.download=name; link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function renderBatch() {
 $('#batch-results').innerHTML = batchRows.map((row,index)=>`<div class="history-entry"><strong>${escapeHtml(row.url)}</strong><p class="help">${escapeHtml(row.status)}</p>${row.result ? `<p class="help">${row.result.fit.map(f=>escapeHtml(f.criterion)+': '+(f.evidence_ids.length?'Evidence found':'Unknown')).join('<br>')}</p><button class="export" data-batch-open="${index}">Open full brief</button>` : ''}</div>`).join('');
}
$('#batch-file').addEventListener('change',()=>{
 if(batchRunning) return;
 batchRows=[]; batchInput=null;
 $('#batch-start').textContent='Run batch'; renderBatch();
});
$('#batch-start').addEventListener('click', async()=>{
 if(batchRunning || $('#run').disabled) return;
 try {
  if(batchRows.length && !batchRows.some(row=>row.status==='Queued')) batchRows=[];
  if(!batchRows.length) {
   const file = $('#batch-file').files[0];
   if(!file || file.size>100000) throw new Error('Choose a CSV file smaller than 100 KB.');
   const product = $('#product').value.trim();
   const criteria = $('#criteria').value.split('\n').map(c=>c.trim()).filter(Boolean);
   if(product.length<20 || product.length>1200 || criteria.length<1 || criteria.length>5 || criteria.some(c=>c.length<3 || c.length>120) || new Set(criteria).size!==criteria.length) throw new Error('Enter an offering of 20–1200 characters and 1–5 unique criteria of 3–120 characters.');
   const urls=companyUrls(await file.text());
   batchInput={product,criteria};
   batchRows=urls.map(url=>({url,status:'Queued'}));
  }
  batchRunning=true; batchPaused=false;
  $('#run').disabled=true; $('#batch-start').disabled=true; $('#batch-stop').disabled=false; $('#batch-file').disabled=true;
  for(const row of batchRows) {
   if(batchPaused) break;
   if(row.status!=='Queued') continue;
   row.status='Researching'; renderBatch();
   $('#batch-status').textContent='Researching '+row.url+'. Requests run sequentially.';
   try {
    const input={...batchInput,url:row.url};
    const response=await fetch('/api/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...input,mode:'gemini',workflow:'agent'})});
    const result=await response.json();
    if(response.status===429) {
     row.status='Queued'; batchPaused=true;
     $('#batch-status').textContent=(result.error || 'Rate limit reached.')+' Resume when quota is available.';
     break;
    }
    if(!response.ok) throw new Error(result.error || 'Research failed.');
    if(result.service_error) {
     row.status='Research unavailable: '+result.service_error;
     batchPaused=true;
     $('#batch-status').textContent='Batch paused after a provider or retrieval failure. Completed briefs are saved. Resume to continue remaining accounts.';
    } else {
     row.result=result;
     row.status=result.judge_evaluation?.status==='unavailable'?'AI quality review unavailable':result.judge_evaluation?.summary?.review_required?'Quality review flagged issues':result.coverage.supported<result.coverage.total?'Manual review needed':'Ready for review';
     saveBrief(input,result);
    }
   } catch(error) { row.status='Error: '+error.message; }
   renderBatch();
  }
  if(!batchPaused) $('#batch-status').textContent='Batch finished. Open each brief to review its evidence.';
 } catch(error) { $('#batch-status').textContent=error.message; }
 finally {
  batchRunning=false;
  $('#run').disabled=false; $('#batch-start').disabled=false; $('#batch-stop').disabled=true; $('#batch-file').disabled=false;
  $('#batch-start').textContent=batchRows.some(row=>row.status==='Queued')?'Resume batch':'Run batch';
  renderBatch();
 }
});
$('#batch-stop').addEventListener('click',()=>{
 batchPaused=true;
 $('#batch-status').textContent='Pausing after the current account. Resume to continue queued accounts.';
});
$('#batch-results').addEventListener('click',event=>{
 const button=event.target.closest('[data-batch-open]');
 if(!button || $('#run').disabled) return;
 const row=batchRows[Number(button.dataset.batchOpen)];
 lastResult=row.result; render(lastResult);
 $('#url').value=row.url; $('#product').value=batchInput.product; $('#criteria').value=batchInput.criteria.join('\n');
 $('#progress').textContent='Opened batch research. Review the cited evidence.';
});
$('#batch-export').addEventListener('click',()=>{
 if(!batchRows.length) return;
 downloadCsv([['website','status','supported','total','supported_criteria','unknown_criteria','ai_quality_review'],...batchRows.map(row=>[row.url,row.status,row.result?.coverage.supported ?? '',row.result?.coverage.total ?? '',row.result?.fit.filter(f=>f.evidence_ids.length).map(f=>f.criterion).join('; ') ?? '',row.result?.fit.filter(f=>!f.evidence_ids.length).map(f=>f.criterion).join('; ') ?? '',row.result?.judge_evaluation?.status==='completed'?(row.result.judge_evaluation.summary.review_required?'Flagged for review':'No issues flagged'):row.result?.judge_evaluation?.status ?? ''])],'prospectlens-batch.csv');
});
function attachSalesforceReview(result) {
 if(!result.outreach_draft) return;
 const section=document.createElement('div');
 section.className='saved-tools';
 section.innerHTML='<h3>Save to Salesforce</h3><label><input id="review-confirm" type="checkbox" class="review-checkbox"> I reviewed the evidence, AI quality feedback, fit, and outreach draft.</label><label for="salesforce-search">Find the Salesforce account</label><div class="account-search-row"><input id="salesforce-search" type="search" maxlength="120" placeholder="Company name or website"><button id="salesforce-search-button" type="button" class="export">Search</button></div><p id="salesforce-search-status" class="help" role="status"></p><div id="salesforce-matches" class="account-matches" aria-label="Matching Salesforce accounts"></div><p id="salesforce-selection" class="help" role="status">Choose an account before saving.</p><button id="salesforce-save" class="export" disabled>Save reviewed brief to Salesforce</button><p id="salesforce-save-status" class="help" role="status"></p>';
 $('#draft-section').append(section);
 const search=$('#salesforce-search');
 const searchButton=$('#salesforce-search-button');
 const matchesElement=$('#salesforce-matches');
 const searchStatus=$('#salesforce-search-status');
 const selection=$('#salesforce-selection');
 const review=$('#review-confirm');
 const button=$('#salesforce-save');
 const saveStatus=$('#salesforce-save-status');
 let matches=[];
 let selected=null;
 let searchVersion=0;
 let saving=false;
 let uncertain=false;
 const updateSave=()=>{button.disabled=!review.checked || !selected || saving || uncertain || Boolean(result.salesforce_task);};
 if(result.salesforce_task) saveStatus.textContent='Already saved as task '+result.salesforce_task+'.';
 function showMatches() {
  matchesElement.innerHTML=matches.map(account=>`<button type="button" class="account-match ${selected?.id===account.id?'selected':''}" data-account-id="${escapeHtml(account.id)}" aria-pressed="${selected?.id===account.id}" ${saving?'disabled':''}><span><strong>${escapeHtml(account.name)}</strong><small>${escapeHtml(account.website || 'Website not provided')}</small></span><span aria-hidden="true">${selected?.id===account.id?'✓':'＋'}</span></button>`).join('');
 }
 async function searchAccounts() {
  if(saving) return;
  const version=++searchVersion;
  selected=null; matches=[]; showMatches(); updateSave();
  selection.textContent='Choose an account before saving.';
  const query=search.value.trim();
  if(query.length<2 || query.length>120) {searchStatus.textContent='Enter a company name or website of 2–120 characters.';return;}
  searchButton.disabled=true;
  searchStatus.textContent='Searching your Salesforce accounts…';
  try {
   const response=await fetch('/api/salesforce/accounts?'+new URLSearchParams({q:query}));
   const data=await response.json();
   if(version!==searchVersion) return;
   if(!response.ok) throw new Error(data.error || 'Account search failed.');
   matches=data.accounts;
   if(!Array.isArray(matches)) throw new Error('Account search returned an invalid response.');
   showMatches();
   if(matches.length) {
    searchStatus.textContent=matches.length+' matching account'+(matches.length===1?'':'s')+'. Confirm the company name and website.';
   } else {
    searchStatus.textContent='No matching accounts. Try another company name or website.';
    const url=new URL(data.create_url);
    if(url.protocol==='https:' && url.hostname.endsWith('.salesforce.com')) {
     matchesElement.innerHTML=`<a class="source" href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">Create an account in Salesforce ↗</a><p class="help">Return here and search again after creating the account.</p>`;
    }
   }
  } catch(error) {
   if(version===searchVersion) searchStatus.textContent=error.message;
  } finally {if(version===searchVersion) searchButton.disabled=false;}
 }
 review.addEventListener('change',updateSave);
 search.addEventListener('input',()=>{
  searchVersion++; selected=null; matches=[]; showMatches(); updateSave();
  searchButton.disabled=false;
  searchStatus.textContent='Search to find matching accounts.';
  selection.textContent='Choose an account before saving.';
 });
 search.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();searchAccounts();}});
 searchButton.addEventListener('click',searchAccounts);
 matchesElement.addEventListener('click',event=>{
  const match=event.target.closest('[data-account-id]');
  if(!match || saving) return;
  selected=matches.find(account=>account.id===match.dataset.accountId) || null;
  selection.textContent=selected?'Selected account: '+selected.name+' · '+(selected.website || 'Website not provided'):'Choose an account before saving.';
  showMatches(); updateSave();
 });
 button.addEventListener('click',async()=>{
  if(!selected || !review.checked || saving || uncertain || result.salesforce_task) return;
  saving=true; uncertain=true; updateSave(); search.disabled=true; searchButton.disabled=true; showMatches();
  saveStatus.textContent='Saving reviewed research to '+selected.name+'…';
  try {
   const brief={account:result.account,hypothesis:result.hypothesis,outreach_draft:result.outreach_draft,evidence:result.evidence};
   const response=await fetch('/api/salesforce/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:selected.id,reviewed:review.checked,brief})});
   const data=await response.json();
   if(!response.ok) {uncertain=response.status>=500;throw new Error(data.error || 'Salesforce save failed.');}
   result.salesforce_task=data.id;
   uncertain=false;
   persistWorkspace();
   saveStatus.textContent='Saved to '+selected.name+' as task '+data.id+'.';
  } catch(error) {
   if(error instanceof TypeError) uncertain=true;
   saveStatus.textContent=error.message;
  } finally {
   saving=false; search.disabled=false; searchButton.disabled=false;
   showMatches(); updateSave();
  }
 });
 search.value=String(result.account).replace(/\\/g,'').replace(/^www\./i,'');
 return searchAccounts();
}
async function salesforceStatus() {
 try {
  const response=await fetch('/api/salesforce/status');
  const data=await response.json();
  $('#salesforce-status').textContent=data.connected?'Salesforce connected. Open a brief to review and save it.':data.configured?'Connect your Salesforce account to save reviewed research.':'Salesforce setup is required. See the README for OAuth configuration.';
 } catch(error) { $('#salesforce-status').textContent='Could not check Salesforce connection.'; }
}
$('#salesforce-disconnect').addEventListener('click',async()=>{
 try {
  const response=await fetch('/api/salesforce/disconnect',{method:'POST'});
  if(!response.ok) throw new Error('Could not disconnect. Try again.');
  await salesforceStatus();
 } catch(error) { $('#salesforce-status').textContent=error.message; }
});
salesforceStatus();
