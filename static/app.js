'use strict';
const $ = s => document.querySelector(s);
const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let lastResult;
function download(kind) {
 if(!lastResult) return;
 const body=kind==='json'?JSON.stringify(lastResult,null,2):lastResult.markdown;
 const url=URL.createObjectURL(new Blob([body],{type:kind==='json'?'application/json':'text/markdown'}));
 const a=document.createElement('a');a.href=url;a.download=`accountbrief-${lastResult.account}.${kind==='json'?'json':'md'}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
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
 <div class="panel result-section trace" id="trace-section"><details><summary>Research activity · ${r.trace.length} steps</summary><div class="trace-list">${r.trace.map(t=>`<div class="trace-row"><strong>${t.step.toString().padStart(2,'0')} / ${e(t.tool)} · ${e(t.status)}</strong><p>${e(t.detail)}</p><code>${e(JSON.stringify(t.arguments))}</code></div>`).join('')}</div></details>${r.warnings.map(w=>`<p class="warning">${e(w)}</p>`).join('')}</div>`;
 $('#export-md').addEventListener('click',()=>download('md'));$('#export-json').addEventListener('click',()=>download('json'));
}
$('#research-form').addEventListener('submit',async event=>{
 event.preventDefault();$('#error').hidden=true;$('#run').disabled=true;$('#run').textContent='Researching…';
 $('#progress').textContent='Researching the company and checking sources. This may take a few minutes.';
 // Clear the previous account so an error cannot leave stale results looking current.
 lastResult=null;$('#output').innerHTML='<div class="panel empty"><p class="eyebrow">RESEARCH IN PROGRESS</p><h2>Following the evidence.</h2><p>Inspecting pages and checking source quotations. Your brief will appear when the research is complete.</p></div>';
 try{
  const response=await fetch('/api/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'gemini',workflow:'agent',url:$('#url').value,product:$('#product').value,criteria:$('#criteria').value.split('\n').map(x=>x.trim()).filter(Boolean)})});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'Research request failed.');lastResult=result;render(result);$('#progress').textContent=`Completed in ${result.elapsed_seconds}s. Review the evidence before using the draft.`;
 }catch(error){$('#error').textContent=error.message;$('#error').hidden=false;$('#progress').textContent='';$('#output').innerHTML='<div class="panel empty"><p class="eyebrow">INPUT NEEDS ATTENTION</p><h2>No brief was generated.</h2><p>Resolve the input error shown beside the form, then run again.</p></div>';}
 finally{$('#run').disabled=false;$('#run').innerHTML='Build account brief <span>↗</span>';}
});
