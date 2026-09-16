from pathlib import Path
import re


def write(path, text):
    Path(path).write_text(text, encoding="utf-8")


# Backend: remove fit storage/API/run payload support, with a one-time schema cleanup.
p = Path("app.py")
s = p.read_text(encoding="utf-8")
s = s.replace(
    '            "CREATE TABLE IF NOT EXISTS fits(id TEXT PRIMARY KEY,character_id BIGINT,character_name TEXT,ship TEXT NOT NULL,name TEXT NOT NULL,raw_text TEXT NOT NULL,groups_json TEXT NOT NULL,type_ids_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",\n',
    "",
)
s = s.replace(',"fit_selection_json TEXT"]', "]")
s = s.replace(
    '    try:d["fit_selection"]=json.loads(d.get("fit_selection_json") or "{}")\n    except:d["fit_selection"]={}\n',
    "",
)
s = re.sub(
    r'\ndef fit_payload\(row\):.*?\n@app\.get\("/login"\)',
    '\n@app.get("/login")',
    s,
    flags=re.S,
)
s = s.replace(
    '        c.execute("UPDATE runs SET fit_selection_json=? WHERE id=?",(json.dumps(body.get("fit_selection") or {}),rid))\n',
    "",
)
anchor = '''        for d in ["cache_system_name TEXT","cache_ship_name TEXT","last_esi_sync TEXT","character_role TEXT DEFAULT 'alt'","connected INTEGER DEFAULT 1"]:\n            ensure_col(c,"characters",d)\n'''
cleanup = '''        for d in ["cache_system_name TEXT","cache_ship_name TEXT","last_esi_sync TEXT","character_role TEXT DEFAULT 'alt'","connected INTEGER DEFAULT 1"]:\n            ensure_col(c,"characters",d)\n        # One-time database cleanup for the retired feature. Remove this block after the production migration runs.\n        c.execute("DROP TABLE IF EXISTS fits")\n        if col_exists(c,"runs","fit_selection_json"):\n            c.execute("ALTER TABLE runs DROP COLUMN fit_selection_json")\n'''
if anchor not in s:
    raise SystemExit("app.py character column anchor not found")
s = s.replace(anchor, cleanup, 1)
p.write_text(s, encoding="utf-8")

# React navigation.
p = Path("static/react/main.tsx")
s = p.read_text(encoding="utf-8")
token = '["fits","◈","Fits","/?view=fits"],'
if token not in s:
    raise SystemExit("React Fits nav token not found")
s = s.replace(token, "", 1)
p.write_text(s, encoding="utf-8")

# Shell no longer has any feature-specific loading/navigation.
write(
    "static/eve_shell.js",
    """(()=>{\n'use strict';\nfunction updateEveClock(){document.querySelectorAll('[data-eve-clock]').forEach(el=>el.textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'UTC',hour12:false}))}\nfunction apply(){window.applyNextUpdateV2?.();window.applyProdUpdateV3?.();window.applyReleaseV4?.()}\nwindow.applyEveShell=apply;\ndocument.readyState==='loading'?document.addEventListener('DOMContentLoaded',apply):apply();\nsetInterval(updateEveClock,1000);updateEveClock();\n})();\n""",
)

# Preserve only the useful non-feature compatibility behavior.
write(
    "static/beta_features.js",
    r"""(()=>{
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
""",
)

write(
    "static/beta_features_v2.js",
    r"""(()=>{
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
""",
)

write(
    "static/beta_features.css",
    """/* Dashboard sync, recommendation and small UX additions. */
.beta-sync-icon{width:34px;height:34px;border:1px solid rgba(74,205,235,.45);border-radius:9px;background:rgba(4,21,32,.78);color:#7feaff;font-size:18px;display:grid;place-items:center;cursor:pointer;margin-right:10px;box-shadow:inset 0 0 18px rgba(32,199,229,.06)}
.beta-sync-icon:hover{border-color:rgba(91,224,248,.8);background:rgba(7,32,46,.95)}
.beta-sync-icon.syncing{animation:betaSpin 1s linear infinite}.beta-sync-icon.success{color:#62f1bd;border-color:rgba(98,241,189,.6)}.beta-sync-icon.error{color:#ff9d83;border-color:rgba(255,120,90,.65)}
@keyframes betaSpin{to{transform:rotate(360deg)}}
.beta-recommendation{margin:14px 0 18px}.confidence-chip{align-self:flex-start;padding:7px 10px;border-radius:999px;border:1px solid rgba(101,221,240,.35);font-size:11px;text-transform:uppercase;letter-spacing:.08em}.confidence-chip.high{color:#66efba}.confidence-chip.medium{color:#f2d96c}.confidence-chip.low{color:#b4c2cd}.recommend-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px}.recommend-grid>div{padding:14px;border:1px solid rgba(75,157,186,.22);background:rgba(3,18,29,.54);border-radius:9px}.recommend-grid small{display:block;color:#8197a8;text-transform:uppercase;font-size:10px;letter-spacing:.08em}.recommend-grid b{display:block;margin-top:5px;font-size:20px}.recommend-why{margin:12px 0 0;color:#95aaba;font-size:12px}
@media(max-width:800px){.recommend-grid{grid-template-columns:1fr}.beta-sync-icon{margin-right:5px}}
""",
)
write(
    "static/beta_features_v2.css",
    """/* ESI sync card and global alignment polish. */
.beta-sync-icon{display:none!important}
.esi-sync-card-v2{display:flex;align-items:center;gap:12px;min-width:178px;height:54px;padding:7px 9px 7px 12px;border:1px solid rgba(74,205,235,.24);border-radius:9px;background:rgba(4,18,29,.78);box-sizing:border-box;margin-right:10px}.esi-sync-card-v2>div{display:flex;flex-direction:column;gap:2px;min-width:88px}.esi-sync-card-v2 span{font-size:9px;letter-spacing:.13em;color:#7ed7eb;font-weight:700}.esi-sync-card-v2 small{font-size:9px;color:#8097a7;white-space:nowrap}.esi-sync-card-v2 button{height:34px;padding:0 11px;border-radius:7px;border:1px solid rgba(73,197,226,.42);background:rgba(7,39,55,.92);color:#c9f7ff;font-size:11px;white-space:nowrap}.esi-sync-card-v2 button:hover{border-color:#67dff4;background:rgba(10,52,70,.96)}.esi-sync-card-v2 button:disabled{opacity:.65}
.beta-ui-polish-v2 .panel,.beta-ui-polish-v2 .metric-card{box-sizing:border-box}.beta-ui-polish-v2 .metric-grid{align-items:stretch}.beta-ui-polish-v2 .metric-grid>.metric-card{height:100%;min-height:116px;display:flex;flex-direction:column;justify-content:center}.beta-ui-polish-v2 .panel-head{min-height:44px;align-items:center}.beta-ui-polish-v2 button,.beta-ui-polish-v2 .button{box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;line-height:1.1}.beta-ui-polish-v2 .history-main table th,.beta-ui-polish-v2 .history-main table td,.beta-ui-polish-v2 .session-history-panel table th,.beta-ui-polish-v2 .session-history-panel table td{vertical-align:middle}.beta-ui-polish-v2 .history-lower,.beta-ui-polish-v2 .progression-lower,.beta-ui-polish-v2 .dashboard-lower{align-items:stretch}.beta-ui-polish-v2 .history-lower>.panel,.beta-ui-polish-v2 .progression-lower>.panel,.beta-ui-polish-v2 .dashboard-lower>.panel{height:100%}.beta-ui-polish-v2 .settings-grid{align-items:stretch}.beta-ui-polish-v2 .setting-card{height:100%}.beta-ui-polish-v2 .tracker-stats>.card{height:100%}.beta-ui-polish-v2 .eve-topbar{align-items:center}.beta-ui-polish-v2 .eve-time{margin-left:0}
@media(max-width:820px){.esi-sync-card-v2{min-width:150px}}
@media(max-width:560px){.esi-sync-card-v2 small{display:none}.esi-sync-card-v2{min-width:auto}}
""",
)

# Remove production nav injection.
p = Path("static/prod_update_v3.js")
s = p.read_text(encoding="utf-8")
s, n = re.subn(r"\nfunction nav\(\)\{.*?\}\nconst ago=", "\nconst ago=", s, count=1, flags=re.S)
if n != 1:
    raise SystemExit("prod_update_v3 nav function not found")
s = s.replace(
    "function apply(){triggers();nav();sync();exportsOff();historyTime();chars();progression()}",
    "function apply(){triggers();sync();exportsOff();historyTime();chars();progression()}",
)
p.write_text(s, encoding="utf-8")

# Remove leftover selectors from generic polish.
p = Path("static/next_update.css")
s = p.read_text(encoding="utf-8")
s = s.replace(".side-nav a.nav-fits>span{font-size:16px}", "")
s = s.replace(",.fit-actions", "")
p.write_text(s, encoding="utf-8")

# Dedicated files.
for f in [
    "static/fits.css",
    "static/fits.js",
    "static/fits_empty_v3.js",
    "tests/test_fits_current.py",
]:
    Path(f).unlink(missing_ok=True)

# Tests dedicated to the removed feature.
p = Path("tests/test_tracker_api.py")
s = p.read_text(encoding="utf-8")
s, n = re.subn(
    r"\n\ndef test_beta_v2_fits_are_persisted\(test_app\):.*?(?=\n\ndef test_non_sold_escalation_value_is_cleared_by_backend)",
    "",
    s,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit("fit API tests block not found")
p.write_text(s, encoding="utf-8")

p = Path("tests/test_tracker_ui.py")
s = p.read_text(encoding="utf-8")
s = re.sub(r"\n\ndef test_beta_fits_tab_and_tracker_selector_are_visible\(page\):.*\Z", "\n", s, count=1, flags=re.S)
p.write_text(s, encoding="utf-8")

p = Path("tests/conftest.py")
s = p.read_text(encoding="utf-8")
s = re.sub(r"\n\ndef pytest_collection_modifyitems\(items\):.*\Z", "\n", s, count=1, flags=re.S)
p.write_text(s, encoding="utf-8")

p = Path("tests/test_prod_v3.py")
s = p.read_text(encoding="utf-8")
s = s.replace("def test_global_sync_and_single_fits_navigation(page):", "def test_global_sync_navigation(page):")
s = s.replace('        expect(page.locator(".side-nav a").filter(has_text="Fits")).to_have_count(1)\n', "")
s = s.replace('    expect(page.locator(".queue-modal")).not_to_contain_text("Fit Readiness")\n', "")
p.write_text(s, encoding="utf-8")

# Direct SQL seed data in release regressions.
p = Path("tests/test_release_v4.py")
s = p.read_text(encoding="utf-8")
s = s.replace(",fit_selection_json", "")
s = re.sub(r'(\b(?:end|now)\.isoformat\(\)),\s*"\{\}"', r"\1", s)
p.write_text(s, encoding="utf-8")

# Temporary audit workflow is no longer needed.
Path(".github/workflows/inventory-fits.yml").unlink(missing_ok=True)

# Audit the actual feature signatures. The one-time DB migration intentionally still contains
# only the old table/column names until production has completed one startup with this release.
needles = [
    "/?view=fits",
    "/api/fits",
    "fitWorkbench",
    "beta-fit",
    "eveRattingFits",
    "Saved Fits",
    "FITTING LIBRARY",
]
bad = []
for path in Path(".").rglob("*"):
    if str(path) == "static/react/app.js" or not path.is_file() or ".git" in path.parts or path.name in {"apply-remove-fits.yml", "remove_fits_once.py"}:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        continue
    for needle in needles:
        if needle in text:
            bad.append((str(path), needle))
if bad:
    raise SystemExit("Remaining feature references: " + repr(bad[:30]))
