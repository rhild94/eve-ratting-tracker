(()=>{
'use strict';
const BOOT=window.__BOOTSTRAP__||{};
const FITS_KEY='eveRattingFits.v1', LAST_FITS_KEY='eveRattingLastFits.v1', SESSION_FITS_KEY='eveRattingSessionFits.v1', RUN_FITS_KEY='eveRattingRunFits.v1';
const q=(s,r=document)=>r.querySelector(s), qa=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const read=(k,fallback)=>{try{return JSON.parse(localStorage.getItem(k)||'')||fallback}catch{return fallback}};
const write=(k,v)=>localStorage.setItem(k,JSON.stringify(v));
const uid=()=>crypto.randomUUID?crypto.randomUUID():`fit-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const money=v=>Number(v||0);
function localDateTime(v){if(!v)return '—';const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);const p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`}
function localShortDate(v){if(!v)return '—';const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);return d.toLocaleDateString(undefined,{month:'short',day:'2-digit'})}
function localZone(){try{return Intl.DateTimeFormat().resolvedOptions().timeZone||'Local time'}catch{return 'Local time'}}
function connectedCharacters(){return BOOT.data?.characters||BOOT.characters||[]}
function fits(){return read(FITS_KEY,[])}
function setFits(v){write(FITS_KEY,v)}
function lastFits(){return read(LAST_FITS_KEY,{})}
function sessionFits(){return read(SESSION_FITS_KEY,{})}
function runFits(){return read(RUN_FITS_KEY,{})}
function slotGroups(raw){
 const lines=String(raw||'').replace(/\r/g,'').split('\n');
 const header=(lines.shift()||'').trim();
 const hm=header.match(/^\[([^,\]]+)(?:,\s*([^\]]+))?\]$/);
 const blocks=[];let cur=[];
 for(const original of lines){const line=original.trim();if(!line){if(cur.length){blocks.push(cur);cur=[]}continue}if(/^\[Empty .* slot\]$/i.test(line))continue;cur.push(line.replace(/\s+x\d+$/i,''))}
 if(cur.length)blocks.push(cur);
 const names=['low','mid','high','rigs','drones','charges'];const groups={low:[],mid:[],high:[],rigs:[],drones:[],charges:[]};
 blocks.forEach((b,i)=>{groups[names[Math.min(i,names.length-1)]].push(...b)});
 return {ship:hm?.[1]?.trim()||'',name:hm?.[2]?.trim()||'',groups};
}
function addFitsNav(){
 const nav=q('.side-nav');if(!nav||q('a[data-beta-fits]',nav))return;
 const a=document.createElement('a');a.href='/?view=fits';a.dataset.betaFits='1';a.innerHTML='<span>◈</span>Fits';
 const chars=q('a[href="/progression?view=characters"]',nav);nav.insertBefore(a,chars||null);
 if(new URLSearchParams(location.search).get('view')==='fits'){qa('a',nav).forEach(x=>x.classList.remove('active'));a.classList.add('active')}
}
function applyBetaBrand(){
 const v=BOOT.version?`v${BOOT.version} Beta`:'Beta';const small=q('.brand small');if(small)small.textContent=v;
 if(!document.title.includes('Beta'))document.title+=' Beta';
 if(location.pathname==='/'&&new URLSearchParams(location.search).get('view')==='fits'){const e=q('.system-head em');if(e)e.textContent='SAVED FITS'}
 if(location.pathname==='/'&&new URLSearchParams(location.search).get('view')!=='fits'){const labels=qa('.tracker-stats .card > span');for(const el of labels)if(el.textContent.trim()==='Bounty ISK/hr')el.textContent='Tracked Bounty ISK/h'}
 if(location.pathname==='/dashboard'){
  qa('.metric-card').forEach(card=>{const s=q('span',card),sm=q('small',card);if(s?.textContent.trim()==='Avg ISK/h'){s.textContent='Ratting ISK/h';if(sm)sm.textContent='Bounty + ESS only'}if(s?.textContent.trim()==='Best ISK/h')s.textContent='Best Ratting ISK/h'});
  const h=q('.performance-panel h2'),p=q('.performance-panel .muted');if(h)h.textContent='Ratting ISK per Hour';if(p)p.textContent='Bounty + ESS only · Total ISK/h includes loot, salvage, rare drops and sold escalations.';
 }
 if(location.pathname==='/progression'){
  const first=q('.progression-metrics .metric-card span');if(first&&first.textContent.includes('ISK/h'))first.textContent='Recent Bounty ISK/h';
 }
 if(new URLSearchParams(location.search).get('view')==='settings'){
  qa('.setting-row').forEach(row=>{if(q('span',row)?.textContent.trim()==='Version'){const b=q('b',row);if(b&&!b.textContent.includes('Beta'))b.textContent=`${b.textContent} Beta`}})
 }
}
function applyLocalTimes(){
 const zone=localZone();
 if(location.pathname==='/history'&&BOOT.history){
  for(const r of BOOT.history.runs||[]){const cell=q(`#runRow${r.id} td:first-child`);if(cell){cell.textContent=localDateTime(r.ended_at);cell.title=zone}}
  const essRows=qa('.history-lower section:first-child tbody tr');(BOOT.history.ess||[]).slice(0,8).forEach((e,i)=>{const c=q('td:first-child',essRows[i]);if(c){c.textContent=localDateTime(e.date);c.title=zone}});
  const escRows=qa('.escalation-list > div');(BOOT.history.runs||[]).filter(r=>r.escalation_name).slice(0,8).forEach((r,i)=>{const s=q('span',escRows[i]);if(s){s.textContent=localDateTime(r.ended_at);s.title=zone}});
 }
 if(location.pathname==='/dashboard'&&BOOT.perf?.rows){const displayed=[...(BOOT.perf.rows||[])].slice(-5).reverse();qa('.mock-recent-row').forEach((row,i)=>{const s=q('span',row);const src=displayed[i];if(s&&src){s.textContent=localShortDate(src.ended_at);s.title=`${localDateTime(src.ended_at)} · ${zone}`}})}
 if(location.pathname==='/progression'&&new URLSearchParams(location.search).get('view')==='characters'){
  (BOOT.characters||[]).forEach((c,i)=>{const card=qa('.character-card-xl')[i];if(!card||!c.captured_at)return;qa('.character-facts > div',card).forEach(box=>{if(q('small',box)?.textContent.trim()==='Last Snapshot'){const b=q('b',box);if(b){b.textContent=localDateTime(c.captured_at);b.title=zone}}})})
 }
}
function installDashboardSync(){
 if(location.pathname!=='/dashboard'||q('#betaDashboardSync'))return;const clock=q('.eve-time');if(!clock)return;
 const b=document.createElement('button');b.id='betaDashboardSync';b.className='beta-sync-icon';b.type='button';b.textContent='↻';b.title='Sync ESI';clock.parentElement.insertBefore(b,clock);
 b.addEventListener('click',async()=>{if(b.disabled)return;b.disabled=true;b.classList.add('syncing');b.textContent='↻';try{const r=await fetch('/api/sync',{method:'POST'}),j=await r.json();if(!r.ok||j.ok===false)throw new Error((j.errors||[]).join('; ')||'ESI sync failed');b.classList.remove('syncing');b.classList.add('success');b.textContent='✓';const t=j.dashboard?.esi?.last_success||j.dashboard?.esi?.last_sync;b.title=t?`Last synced ${localDateTime(t)} (${localZone()})`:'ESI synced';setTimeout(()=>location.reload(),650)}catch(e){b.classList.remove('syncing');b.classList.add('error');b.textContent='!';b.title=String(e?.message||e);setTimeout(()=>{b.disabled=false;b.classList.remove('error');b.textContent='↻'},2200)}})
}
function recommendationBox(){
 if(location.pathname!=='/progression'||new URLSearchParams(location.search).get('view')||q('#betaRecommendation'))return;
 fetch('/api/dashboard').then(r=>r.ok?r.json():null).then(d=>{const recent=d?.recent||[];if(!recent.length)return;const groups={};for(const r of recent){const rate=money(r.isk_hr),dur=money(r.duration_seconds);if(!rate||!dur)continue;const k=r.anomaly||'Other';(groups[k] ||= []).push({rate,dur})}
  const scored=Object.entries(groups).map(([name,a])=>{const n=a.length,avg=a.reduce((s,x)=>s+x.rate,0)/n,avgDur=a.reduce((s,x)=>s+x.dur,0)/n;const variance=a.reduce((s,x)=>s+(x.rate-avg)**2,0)/n,cv=avg?Math.sqrt(variance)/avg:1;const confidence=n>=4?'High':n>=2?'Medium':'Low';const score=avg*(Math.min(1,n/3))*(1-Math.min(.35,cv*.12));return {name,n,avg,avgDur,confidence,score}}).sort((a,b)=>b.score-a.score);if(!scored.length)return;const x=scored[0];const panel=document.createElement('section');panel.id='betaRecommendation';panel.className='panel sci-panel beta-recommendation';panel.innerHTML=`<div class="panel-head"><div><span class="eyebrow">RECOMMENDED SITE</span><h2>${esc(x.name)}</h2><span class="muted">Best current balance of recent pace, consistency and sample size.</span></div><span class="confidence-chip ${x.confidence.toLowerCase()}">${x.confidence} confidence</span></div><div class="recommend-grid"><div><small>Avg site bounty rate</small><b>${(x.avg/1e6).toFixed(1)}M/h</b></div><div><small>Avg completion</small><b>${Math.floor(x.avgDur/60)}m ${Math.round(x.avgDur%60)}s</b></div><div><small>Runs tracked</small><b>${x.n}</b></div></div><p class="recommend-why"><b>Why:</b> strongest weighted recent site performance. Lucky loot and escalation values are excluded.</p>`;
  const metrics=q('.progression-metrics');metrics?.insertAdjacentElement('afterend',panel)
 }).catch(()=>{})
}
function groupHtml(title,items,cls){return `<section class="fit-slot-group ${cls}"><h4>${title}<span>${items.length}</span></h4>${items.length?items.map(x=>`<div>${esc(x)}</div>`).join(''):'<small>None</small>'}</section>`}
function fitCard(f){const counts=Object.values(f.groups||{}).map(a=>a.length).reduce((a,b)=>a+b,0);return `<article class="saved-fit-card" data-fit-id="${esc(f.id)}"><div class="saved-fit-head"><div><span>${esc(f.characterName||'Unassigned')}</span><h3>${esc(f.name||'Unnamed fit')}</h3><b>${esc(f.ship||'Unknown ship')}</b></div><div class="fit-actions"><button data-act="view">View</button><button data-act="edit">Edit</button><button data-act="duplicate">Duplicate</button><button class="danger" data-act="delete">Delete</button></div></div><div class="mini-fit-wheel"><div class="fit-wheel-center"><small>SHIP</small><strong>${esc(f.ship||'Unknown')}</strong><span>${counts} saved items</span></div><i class="slot-dot d1"></i><i class="slot-dot d2"></i><i class="slot-dot d3"></i><i class="slot-dot d4"></i><i class="slot-dot d5"></i><i class="slot-dot d6"></i></div><div class="fit-counts"><span>High <b>${f.groups?.high?.length||0}</b></span><span>Mid <b>${f.groups?.mid?.length||0}</b></span><span>Low <b>${f.groups?.low?.length||0}</b></span><span>Rigs <b>${f.groups?.rigs?.length||0}</b></span><span>Drones <b>${f.groups?.drones?.length||0}</b></span></div></article>`}
function fitDetailHtml(f){return `<div class="fit-detail"><div class="fit-detail-wheel"><div class="fit-wheel-center big"><small>${esc(f.characterName||'Unassigned')}</small><strong>${esc(f.ship)}</strong><span>${esc(f.name)}</span></div></div><div class="fit-module-grid">${groupHtml('High slots',f.groups?.high||[],'high')}${groupHtml('Mid slots',f.groups?.mid||[],'mid')}${groupHtml('Low slots',f.groups?.low||[],'low')}${groupHtml('Rigs',f.groups?.rigs||[],'rig')}${groupHtml('Drones',f.groups?.drones||[],'drone')}${groupHtml('Charges / cargo',f.groups?.charges||[],'charge')}</div></div>`}
function showFitDialog(existing=null,duplicate=false){
 let f=existing?JSON.parse(JSON.stringify(existing)):null;if(duplicate&&f){f.id='';f.name=`${f.name} Copy`}
 const chars=connectedCharacters();const modal=document.createElement('div');modal.className='beta-modal-backdrop';modal.innerHTML=`<div class="beta-modal"><div class="modal-head"><div><span class="eyebrow">${existing?'SAVED FIT':'NEW FIT'}</span><h2>${existing&&!duplicate?'Edit Fit':'Import EVE / EFT Fit'}</h2></div><button class="icon-btn" data-close>×</button></div><div class="fit-editor-grid"><label>Character<select id="betaFitCharacter"><option value="">Unassigned</option>${chars.map(c=>`<option value="${c.id}" ${String(f?.characterId||'')===String(c.id)?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label>Fit name<input id="betaFitName" value="${esc(f?.name||'')}"></label><label class="full">EVE / EFT fit<textarea id="betaFitRaw" rows="15" placeholder="[Raven, Angel Haven Cruise]\nBallistic Control System II\n...">${esc(f?.raw||'')}</textarea></label><div class="full import-hint">Paste the normal EVE fitting text. Ship, modules, rigs, drones and charges will be organized visually.</div></div><div class="modal-actions"><button class="secondary" data-preview>Preview</button><button class="good big" data-save>Save Fit</button></div><div id="betaFitPreview"></div></div>`;document.body.appendChild(modal);
 const close=()=>modal.remove();q('[data-close]',modal).onclick=close;modal.onclick=e=>{if(e.target===modal)close()};
 const parse=()=>{const raw=q('#betaFitRaw',modal).value,p=slotGroups(raw),cid=q('#betaFitCharacter',modal).value,character=chars.find(c=>String(c.id)===cid);return {id:f?.id||uid(),ship:p.ship||f?.ship||'',name:q('#betaFitName',modal).value.trim()||p.name||f?.name||'Unnamed fit',characterId:cid?Number(cid):null,characterName:character?.name||'Unassigned',groups:p.groups,raw,createdAt:f?.createdAt||new Date().toISOString(),updatedAt:new Date().toISOString()}}
 q('[data-preview]',modal).onclick=()=>{const x=parse();q('#betaFitPreview',modal).innerHTML=x.ship?fitDetailHtml(x):'<div class="warning">Paste a valid EFT fit beginning with [Ship, Fit name].</div>'};
 q('[data-save]',modal).onclick=()=>{const x=parse();if(!x.ship){alert('Paste a valid EVE / EFT fit first.');return}const all=fits(),idx=all.findIndex(z=>z.id===x.id);if(idx>=0)all[idx]=x;else all.unshift(x);setFits(all);close();renderFitsPage()};
}
function showFitView(f){const modal=document.createElement('div');modal.className='beta-modal-backdrop';modal.innerHTML=`<div class="beta-modal wide"><div class="modal-head"><div><span class="eyebrow">${esc(f.characterName||'SAVED FIT')}</span><h2>${esc(f.name)}</h2></div><button class="icon-btn" data-close>×</button></div>${fitDetailHtml(f)}</div>`;document.body.appendChild(modal);q('[data-close]',modal).onclick=()=>modal.remove();modal.onclick=e=>{if(e.target===modal)modal.remove()}}
function renderFitsPage(){
 if(new URLSearchParams(location.search).get('view')!=='fits')return;addFitsNav();applyBetaBrand();const stage=q('.main-stage');if(!stage)return;const header=q('.eve-topbar',stage),footer=q('.eve-footer',stage);if(!header||!footer)return;qa(':scope > *',stage).forEach(el=>{if(el!==header&&el!==footer)el.remove()});
 const all=fits();const wrap=document.createElement('div');wrap.className='fits-page';wrap.innerHTML=`<section class="panel sci-panel fits-hero"><div><span class="eyebrow">FITTING LIBRARY</span><h2>Saved Fits</h2><p class="muted">Store the ships and modules you actually use while ratting. Performance calculations are intentionally excluded for now.</p></div><button id="betaAddFit" class="button">+ Add Fit</button></section><section class="fit-library">${all.length?all.map(fitCard).join(''):'<div class="panel empty fit-empty"><b>No saved fits yet.</b><span>Paste an EVE / EFT fit to build your fitting library.</span><button id="betaEmptyAdd" class="button">Add your first fit</button></div>'}</section>`;stage.insertBefore(wrap,footer);q('#betaAddFit',wrap)?.addEventListener('click',()=>showFitDialog());q('#betaEmptyAdd',wrap)?.addEventListener('click',()=>showFitDialog());qa('.saved-fit-card',wrap).forEach(card=>{const f=all.find(x=>x.id===card.dataset.fitId);qa('[data-act]',card).forEach(btn=>btn.onclick=()=>{if(btn.dataset.act==='view')showFitView(f);if(btn.dataset.act==='edit')showFitDialog(f);if(btn.dataset.act==='duplicate')showFitDialog(f,true);if(btn.dataset.act==='delete'&&confirm(`Delete ${f.name}?`)){setFits(fits().filter(x=>x.id!==f.id));renderFitsPage()}})})
}
function fitOptionsForCharacter(cid){const all=fits().filter(f=>!f.characterId||String(f.characterId)===String(cid)),last=lastFits()[cid];return `<option value="">No fit selected</option>${all.map(f=>`<option value="${esc(f.id)}" ${f.id===last?'selected':''}>${esc(f.ship)} — ${esc(f.name)}</option>`).join('')}`}
function enhanceTrackerFitSelectors(){
 if(location.pathname!=='/'||new URLSearchParams(location.search).get('view'))return;const participants=q('.participants');if(!participants||q('.fit-selection-panel'))return;const panel=document.createElement('div');panel.className='field full fit-selection-panel';panel.innerHTML='<label>Fits used <span class="muted">(optional)</span></label><div class="fit-select-grid"></div><a class="fit-manage-link" href="/?view=fits">Manage saved fits →</a>';const grid=q('.fit-select-grid',panel);qa('.participant-card input',participants).forEach(input=>{const cid=input.value,c=connectedCharacters().find(x=>String(x.id)===String(cid));const row=document.createElement('label');row.className='fit-select-row';row.innerHTML=`<span>${esc(c?.name||cid)}</span><select class="beta-fit-select" data-character-id="${cid}">${fitOptionsForCharacter(cid)}</select>`;grid.appendChild(row);const sel=q('select',row);sel.onchange=()=>{const m=lastFits();m[cid]=sel.value;write(LAST_FITS_KEY,m)}});const notes=q('#runNotes')?.closest('.field');if(notes)notes.before(panel);else participants.closest('.field')?.after(panel)
}
function currentFitSelection(){const all=fits(),out={};qa('.beta-fit-select').forEach(sel=>{if(!sel.value)return;const cid=sel.dataset.characterId,f=all.find(x=>x.id===sel.value);if(f)out[cid]={id:f.id,ship:f.ship,name:f.name,characterName:f.characterName}});return out}
function decorateHistoryFits(){
 if(location.pathname!=='/history')return;const sf=sessionFits(),rf=runFits();for(const [sid,entry] of Object.entries(sf)){const cell=q(`#sessionRow${sid} td:first-child`);if(!cell||q('.beta-session-fits',cell))continue;const vals=Object.values(entry.characters||{});if(vals.length){const sm=document.createElement('small');sm.className='beta-session-fits';sm.textContent=vals.map(x=>`${x.ship} — ${x.name}`).join(' · ');cell.appendChild(sm)}}for(const [rid,entry] of Object.entries(rf)){const cell=q(`#runRow${rid} td:nth-child(3)`);if(!cell||q('.beta-run-fits',cell))continue;const vals=Object.values(entry.characters||{});if(vals.length){const sm=document.createElement('small');sm.className='beta-run-fits';sm.textContent=vals.map(x=>x.ship).join(' + ');cell.appendChild(sm)}}
}
function installFetchRules(){
 if(window.__betaFetchInstalled)return;window.__betaFetchInstalled=true;const native=window.fetch.bind(window);window.fetch=async function(input,init){let url=typeof input==='string'?input:input?.url||'',opts=init?{...init}:init,pendingFits=null;
  if(opts?.body&&/\/api\/run\/\d+\/bonus(?:\?|$)/.test(url)){try{const body=JSON.parse(opts.body);if(!['Sold','Ran Myself'].includes(body.escalation_status))body.escalation_sale_value=0;opts.body=JSON.stringify(body)}catch{}}
  if(opts?.body&&/\/api\/run\/start(?:\?|$)/.test(url)){pendingFits=currentFitSelection();try{const body=JSON.parse(opts.body);body.fit_selection=pendingFits;opts.body=JSON.stringify(body)}catch{}}
  const res=await native(input,opts);
  if(pendingFits&&res.ok){res.clone().json().then(j=>{if(!j?.run?.id||!j?.session_id)return;const runMap=runFits();runMap[j.run.id]={characters:pendingFits,recordedAt:new Date().toISOString()};write(RUN_FITS_KEY,runMap);const sesMap=sessionFits();const prev=sesMap[j.session_id]||{characters:{},runs:{}};prev.characters={...prev.characters,...pendingFits};prev.runs={...(prev.runs||{}),[j.run.id]:pendingFits};prev.updatedAt=new Date().toISOString();sesMap[j.session_id]=prev;write(SESSION_FITS_KEY,sesMap)}).catch(()=>{})}
  return res
 }
}
async function repairStaleEscalations(){
 if(location.pathname!=='/history'||!BOOT.history?.runs||sessionStorage.getItem('betaEscRepair')==='done')return;const stale=BOOT.history.runs.filter(r=>!['Sold','Ran Myself'].includes(r.escalation_status)&&money(r.escalation_sale_value)>0);if(!stale.length){sessionStorage.setItem('betaEscRepair','done');return}let fixed=0;for(const r of stale){try{const resp=await fetch(`/api/run/${r.id}/bonus`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({escalation_name:r.escalation_name||'',escalation_status:r.escalation_status||'',escalation_sale_value:0,rare_spawn_type:r.rare_spawn_type||'',rare_spawn_name:r.rare_spawn_name||'',rare_spawn_value:money(r.rare_spawn_value),notes:r.notes||''})});if(resp.ok)fixed++}catch{}}sessionStorage.setItem('betaEscRepair','done');if(fixed)location.reload()}
function observe(){let scheduled=false;const run=()=>{scheduled=false;addFitsNav();applyBetaBrand();applyLocalTimes();installDashboardSync();enhanceTrackerFitSelectors();decorateHistoryFits()};const mo=new MutationObserver(()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(run)});mo.observe(document.documentElement,{childList:true,subtree:true});run()}
installFetchRules();
function init(){addFitsNav();applyBetaBrand();renderFitsPage();applyLocalTimes();installDashboardSync();recommendationBox();enhanceTrackerFitSelectors();decorateHistoryFits();repairStaleEscalations();observe()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
