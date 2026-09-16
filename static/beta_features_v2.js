(()=>{
'use strict';
const q=(s,r=document)=>r.querySelector(s);
const zone=()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone||'Local time'}catch{return'Local time'}};
const localDT=v=>{if(!v)return'Never';const d=new Date(v);return Number.isNaN(d.getTime())?String(v):d.toLocaleString(undefined,{month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'})};
function installSyncCard(){if(location.pathname!=='/dashboard'||q('#esiSyncCardV2'))return;const clock=q('.eve-time');if(!clock)return;const old=q('#betaDashboardSync');if(old){old.style.display='none';old.setAttribute('aria-hidden','true')}const card=document.createElement('div');card.id='esiSyncCardV2';card.className='esi-sync-card-v2';card.innerHTML=`<div><span>ESI SYNC</span><small id="esiSyncLast">Checking…</small></div><button id="esiSyncV2">↻ Sync</button>`;clock.parentElement.insertBefore(card,clock);fetch('/api/dashboard').then(r=>r.json()).then(d=>{const t=d.esi?.last_success||d.esi?.last_sync;q('#esiSyncLast',card).textContent=t?`Last: ${localDT(t)}`:'Not synced yet';q('#esiSyncLast',card).title=zone()}).catch(()=>{q('#esiSyncLast',card).textContent='Status unavailable'});q('#esiSyncV2',card).onclick=async()=>{const b=q('#esiSyncV2',card);b.disabled=true;b.textContent='Syncing…';try{const r=await fetch('/api/sync',{method:'POST'}),j=await r.json();if(!r.ok||j.ok===false)throw new Error('ESI sync failed');const t=j.dashboard?.esi?.last_success||j.dashboard?.esi?.last_sync;q('#esiSyncLast',card).textContent=t?`Last: ${localDT(t)}`:'Synced';b.textContent='✓ Synced';setTimeout(()=>{b.disabled=false;b.textContent='↻ Sync'},1500)}catch{b.textContent='! Retry';b.disabled=false}}}
function dashboardCopy(){if(location.pathname!=='/dashboard')return;const p=q('.performance-panel .muted');if(p)p.textContent='Ratting ISK/h = Bounty + ESS performance · Total ISK = actual session income including loot, salvage, rare drops and sold escalations.'}
function uiPolish(){document.body.classList.add('beta-ui-polish-v2')}
function init(){uiPolish();installSyncCard();dashboardCopy()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
window.renderEsiStatus=window.renderEsiStatus||function(){
 const e=(window.DATA&&window.DATA.esi)||{},pending=Number(e.pending_runs||0),status=document.querySelector('#systemStatus'),alertBox=document.querySelector('#esiAlert');
 const parts=[e.last_success||e.last_sync?'Synced recently':'Not synced yet',e.next_check?'Next check scheduled':'Auto sync enabled',pending+' run'+(pending===1?'':'s')+' pending bounty data'];
 if(status)status.textContent='ESI: '+parts.join(' · ');
 if(alertBox){if(e.last_error){alertBox.textContent='⚠ ESI sync issue — ESI-based values may be stale. Local tracker data is safe.';alertBox.title=e.last_error;alertBox.classList.remove('hidden')}else{alertBox.textContent='';alertBox.title='';alertBox.classList.add('hidden')}}
};
