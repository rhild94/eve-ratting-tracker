(()=>{
'use strict';
const BOOT=window.__BOOTSTRAP__||{};
const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const money=v=>Number(v||0);
function localDateTime(v){if(!v)return '—';const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);const p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`}
function localShortDate(v){if(!v)return '—';const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);return d.toLocaleDateString(undefined,{month:'short',day:'2-digit'})}
function localZone(){try{return Intl.DateTimeFormat().resolvedOptions().timeZone||'Local time'}catch{return 'Local time'}}
function applyBetaBrand(){
 const v=BOOT.version?`v${BOOT.version} Beta`:'Beta';const small=q('.brand small');if(small)small.textContent=v;
 if(!document.title.includes('Beta'))document.title+=' Beta';
 if(location.pathname==='/'){const labels=qa('.tracker-stats .card > span');for(const el of labels)if(el.textContent.trim()==='Bounty ISK/hr')el.textContent='Tracked Bounty ISK/h'}
 if(location.pathname==='/dashboard'){
  qa('.metric-card').forEach(card=>{const s=q('span',card),sm=q('small',card);if(s?.textContent.trim()==='Avg ISK/h'){s.textContent='Ratting ISK/h';if(sm)sm.textContent='Bounty + ESS only'}if(s?.textContent.trim()==='Best ISK/h')s.textContent='Best Ratting ISK/h'});
  const h=q('.performance-panel h2'),p=q('.performance-panel .muted');if(h)h.textContent='Ratting ISK per Hour';if(p)p.textContent='Bounty + ESS only · Total ISK/h includes loot, salvage, rare drops and sold escalations.';
 }
 if(location.pathname==='/progression'){const first=q('.progression-metrics .metric-card span');if(first&&first.textContent.includes('ISK/h'))first.textContent='Recent Bounty ISK/h'}
 if(new URLSearchParams(location.search).get('view')==='settings'){qa('.setting-row').forEach(row=>{if(q('span',row)?.textContent.trim()==='Version'){const b=q('b',row);if(b&&!b.textContent.includes('Beta'))b.textContent=`${b.textContent} Beta`}})}
}
function applyLocalTimes(){
 const zone=localZone();
 if(location.pathname==='/history'&&BOOT.history){
  for(const r of BOOT.history.runs||[]){const cell=q(`#runRow${r.id} td:first-child`);if(cell){cell.textContent=localDateTime(r.ended_at);cell.title=zone}}
  const essRows=qa('.history-lower section:first-child tbody tr');(BOOT.history.ess||[]).slice(0,8).forEach((e,i)=>{const c=q('td:first-child',essRows[i]);if(c){c.textContent=localDateTime(e.date);c.title=zone}});
  const escRows=qa('.escalation-list > div');(BOOT.history.runs||[]).filter(r=>r.escalation_name).slice(0,8).forEach((r,i)=>{const st=q('span',escRows[i]);if(st){st.textContent=localDateTime(r.ended_at);st.title=zone}});
 }
 if(location.pathname==='/dashboard'&&BOOT.perf?.rows){const displayed=[...(BOOT.perf.rows||[])].slice(-5).reverse();qa('.mock-recent-row').forEach((row,i)=>{const st=q('span',row),src=displayed[i];if(st&&src){st.textContent=localShortDate(src.ended_at);st.title=`${localDateTime(src.ended_at)} · ${zone}`}})}
 if(location.pathname==='/progression'&&new URLSearchParams(location.search).get('view')==='characters'){(BOOT.characters||[]).forEach((c,i)=>{const card=qa('.character-card-xl')[i];if(!card||!c.captured_at)return;qa('.character-facts > div',card).forEach(box=>{if(q('small',box)?.textContent.trim()==='Last Snapshot'){const b=q('b',box);if(b){b.textContent=localDateTime(c.captured_at);b.title=zone}}})})}
}
function installDashboardSync(){
 if(location.pathname!=='/dashboard'||q('#betaDashboardSync'))return;const clock=q('.eve-time');if(!clock)return;
 const b=document.createElement('button');b.id='betaDashboardSync';b.className='beta-sync-icon';b.type='button';b.textContent='↻';b.title='Sync ESI';clock.parentElement.insertBefore(b,clock);
 b.addEventListener('click',async()=>{if(b.disabled)return;b.disabled=true;b.classList.add('syncing');try{const r=await fetch('/api/sync',{method:'POST'}),j=await r.json();if(!r.ok||j.ok===false)throw new Error((j.errors||[]).join('; ')||'ESI sync failed');b.classList.remove('syncing');b.classList.add('success');b.textContent='✓';const t=j.dashboard?.esi?.last_success||j.dashboard?.esi?.last_sync;b.title=t?`Last synced ${localDateTime(t)} (${localZone()})`:'ESI synced';setTimeout(()=>location.reload(),650)}catch(e){b.classList.remove('syncing');b.classList.add('error');b.textContent='!';b.title=String(e?.message||e);setTimeout(()=>{b.disabled=false;b.classList.remove('error');b.textContent='↻'},2200)}})
}
function recommendationBox(){
 if(location.pathname!=='/progression'||new URLSearchParams(location.search).get('view')||q('#betaRecommendation'))return;
 fetch('/api/dashboard').then(r=>r.ok?r.json():null).then(d=>{const recent=d?.recent||[];if(!recent.length)return;const groups={};for(const r of recent){const rate=money(r.isk_hr),dur=money(r.duration_seconds);if(!rate||!dur)continue;const k=r.anomaly||'Other';(groups[k] ||= []).push({rate,dur})}const scored=Object.entries(groups).map(([name,a])=>{const n=a.length,avg=a.reduce((sum,x)=>sum+x.rate,0)/n,avgDur=a.reduce((sum,x)=>sum+x.dur,0)/n,variance=a.reduce((sum,x)=>sum+(x.rate-avg)**2,0)/n,cv=avg?Math.sqrt(variance)/avg:1,confidence=n>=4?'High':n>=2?'Medium':'Low',score=avg*Math.min(1,n/3)*(1-Math.min(.35,cv*.12));return{name,n,avg,avgDur,confidence,score}}).sort((a,b)=>b.score-a.score);if(!scored.length)return;const x=scored[0],panel=document.createElement('section');panel.id='betaRecommendation';panel.className='panel sci-panel beta-recommendation';panel.innerHTML=`<div class="panel-head"><div><span class="eyebrow">RECOMMENDED SITE</span><h2>${esc(x.name)}</h2><span class="muted">Best current balance of recent pace, consistency and sample size.</span></div><span class="confidence-chip ${x.confidence.toLowerCase()}">${x.confidence} confidence</span></div><div class="recommend-grid"><div><small>Avg site bounty rate</small><b>${(x.avg/1e6).toFixed(1)}M/h</b></div><div><small>Avg completion</small><b>${Math.floor(x.avgDur/60)}m ${Math.round(x.avgDur%60)}s</b></div><div><small>Runs tracked</small><b>${x.n}</b></div></div><p class="recommend-why"><b>Why:</b> strongest weighted recent site performance. Lucky loot and escalation values are excluded.</p>`;q('.progression-metrics')?.insertAdjacentElement('afterend',panel)}).catch(()=>{})
}
function installFetchRules(){if(window.__betaFetchInstalled)return;window.__betaFetchInstalled=true;const native=window.fetch.bind(window);window.fetch=async function(input,init){let url=typeof input==='string'?input:input?.url||'',opts=init?{...init}:init;if(opts?.body&&/\/api\/run\/\d+\/bonus(?:\?|$)/.test(url)){try{const body=JSON.parse(opts.body);if(!['Sold','Ran Myself'].includes(body.escalation_status))body.escalation_sale_value=0;opts.body=JSON.stringify(body)}catch{}}return native(input,opts)}}
async function repairStaleEscalations(){if(location.pathname!=='/history'||!BOOT.history?.runs||sessionStorage.getItem('betaEscRepair')==='done')return;const stale=BOOT.history.runs.filter(r=>!['Sold','Ran Myself'].includes(r.escalation_status)&&money(r.escalation_sale_value)>0);if(!stale.length){sessionStorage.setItem('betaEscRepair','done');return}let fixed=0;for(const r of stale){try{const resp=await fetch(`/api/run/${r.id}/bonus`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({escalation_name:r.escalation_name||'',escalation_status:r.escalation_status||'',escalation_sale_value:0,rare_spawn_type:r.rare_spawn_type||'',rare_spawn_name:r.rare_spawn_name||'',rare_spawn_value:money(r.rare_spawn_value),notes:r.notes||''})});if(resp.ok)fixed++}catch{}}sessionStorage.setItem('betaEscRepair','done');if(fixed)location.reload()}
function observe(){let scheduled=false;const run=()=>{scheduled=false;applyBetaBrand();applyLocalTimes();installDashboardSync()};const mo=new MutationObserver(()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(run)});mo.observe(document.documentElement,{childList:true,subtree:true});run()}
installFetchRules();
function init(){applyBetaBrand();applyLocalTimes();installDashboardSync();recommendationBox();repairStaleEscalations();observe()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
