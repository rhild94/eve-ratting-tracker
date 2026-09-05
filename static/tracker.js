
let DATA=window.INITIAL_DATA;
let timerHandle=null;
const fmtM=v=>(Number(v||0)/1e6).toFixed(2)+"m";
const $=s=>document.querySelector(s);
const escapeHtml=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const rawIsk=v=>Number(String(v??"").replace(/[^0-9]/g,"")||0);
const formatIsk=v=>rawIsk(v).toLocaleString("en-US");
function bindIskMask(el){
 if(!el)return;
 const apply=()=>{el.value=el.value?formatIsk(el.value):""};
 el.addEventListener("input",()=>{
   const digits=String(el.value).replace(/[^0-9]/g,"");
   el.value=digits?Number(digits).toLocaleString("en-US"):"";
 });
 el.addEventListener("blur",apply);
 apply();
}

function setStatus(t){$("#saveStatus").textContent=t||"";}
function relativePast(v){
 if(!v)return null;
 const sec=Math.max(0,Math.floor((Date.now()-new Date(v).getTime())/1000));
 if(sec<60)return "just now";
 if(sec<3600)return Math.floor(sec/60)+"m ago";
 if(sec<86400)return Math.floor(sec/3600)+"h ago";
 return Math.floor(sec/86400)+"d ago";
}
function relativeFuture(v){
 if(!v)return null;
 const sec=Math.max(0,Math.floor((new Date(v).getTime()-Date.now())/1000));
 if(sec<60)return "in <1m";
 if(sec<3600)return "in "+Math.ceil(sec/60)+"m";
 return "in "+Math.ceil(sec/3600)+"h";
}
function renderEsiStatus(){
 const e=DATA.esi||{}, pending=Number(e.pending_runs||0);
 const last=e.last_success||e.last_sync;
 let next=e.next_check;
 if(!next && last){
   const d=new Date(last);d.setMinutes(d.getMinutes()+Number(e.interval_minutes||30));next=d.toISOString();
 }
 const parts=[last?"Synced "+relativePast(last):"Not synced yet",next?"Next check "+relativeFuture(next):"Auto every "+Number(e.interval_minutes||30)+"m",pending+" run"+(pending===1?"":"s")+" pending bounty data"];
 $("#systemStatus").textContent="ESI: "+parts.join(" · ");
 const a=$("#esiAlert");
 if(e.last_error){
   a.textContent="⚠ ESI sync issue — ESI-based values may be stale. Local tracker data is safe.";
   a.title=e.last_error;
   a.classList.remove("hidden");
 }else{
   a.textContent="";a.title="";a.classList.add("hidden");
 }
}
function renderStats(){
 $("#statBounty").textContent=fmtM(DATA.stats.today_isk);
 $("#statEss").textContent=fmtM(DATA.stats.today_ess);
 $("#statSites").textContent=DATA.stats.today_sites;
 $("#statIskHr").textContent=fmtM(DATA.stats.avg_isk_hr);
}
function participantCard(c){
 return `<label class="participant-card">
   <input type="checkbox" value="${c.id}" checked>
   <img src="${c.portrait}" alt="${escapeHtml(c.name)}">
   <span>${escapeHtml(c.name)}</span>
   <b>✓</b>
 </label>`;
}
function startForm(){
 const opts=DATA.anomalies.map(x=>`<option>${escapeHtml(x)}</option>`).join("");
 return `<div class="start-layout">
 <div class="field"><label>Anomaly</label><select id="anomaly">${opts}</select></div>
 <div class="field"><label>Variant</label><select id="variant"></select><div id="variantHint" class="hint"></div></div>
 <div class="field full"><label>Participants</label><div class="participants">${DATA.characters.map(participantCard).join("")}</div></div>
 <div class="field full"><label>Quick note <span class="muted">(optional)</span></label><input id="runNotes" placeholder="Only if something unusual happened"></div>
 <div class="start-row"><button id="startBtn" class="start big">▶ Start Site</button><span class="muted">Timer starts immediately after the request succeeds.</span></div>
 </div>`;
}
function setupVariants(){
 const a=$("#anomaly"),v=$("#variant"),h=$("#variantHint");
 function update(){const list=window.VARIANTS[a.value]||["Default"];v.innerHTML=list.map(x=>`<option>${escapeHtml(x)}</option>`).join("");h.textContent=window.VARIANT_HINTS[a.value]||"";}
 a.addEventListener("change",update);update();
}
function waveRows(w){
 let rareStarted=false,out="";
 for(const r of w[1]){
   if(!rareStarted && (r[0]==="commander" || r[0]==="capital")){
     rareStarted=true;
     out+=`<div class="rare-separator"><span>Possible Rare Spawn</span></div>`;
   }
   out+=`<div class="rat-row ${rareStarted?"rare-row":""}">
     <img class="eve-icon" src="${window.ICON_URLS[r[0]]||window.ICON_URLS.frigate}" alt="">
     <b>${escapeHtml(r[1])}× ${escapeHtml(r[2])}</b>
     <span>${escapeHtml(r[3])}</span>
   </div>`;
 }
 return out;
}
function runningView(run){
 const waves=(window.SITE_DATA[run.anomaly]?.variants||{})[run.variant||"Default"]||[];
 let wave=Number(localStorage.getItem("wave_"+run.id)||0); wave=Math.max(0,Math.min(wave,Math.max(0,waves.length-1)));
 const renderWave=()=>{
   const box=$("#waveBox"); if(!box)return;
   if(!waves.length){box.innerHTML=`<div class="helper-card"><b>Site Helper</b><p class="hint">Detailed waves are intentionally omitted for this unverified variant.</p></div>`;return;}
   const w=waves[wave], note=w[2]||"";
   box.innerHTML=`<div class="helper-card">
    <div class="helper-head"><div><span class="small-title">Current wave</span><h3>${escapeHtml(w[0])}</h3></div><b>${wave+1}/${waves.length}</b></div>
    ${waveRows(w)}
    ${note?`<div class="${note.startsWith("TRIGGER")?"trigger":"wave-note"}">${note.startsWith("TRIGGER")?"⚠ ":""}${escapeHtml(note)}</div>`:""}
    <div class="helper-nav"><button id="prevWave" ${wave===0?"disabled":""}>← Previous</button><button id="nextWave" class="good" ${wave===waves.length-1?"disabled":""}>${wave===waves.length-1?"Final Wave":"✓ Next Wave →"}</button></div>
   </div>`;
   $("#prevWave")?.addEventListener("click",()=>{if(wave>0){wave--;localStorage.setItem("wave_"+run.id,wave);renderWave()}});
   $("#nextWave")?.addEventListener("click",()=>{if(wave<waves.length-1){wave++;localStorage.setItem("wave_"+run.id,wave);renderWave()}});
 };
 $("#trackerContent").innerHTML=`<div class="running-head"><div><div class="eyebrow">${escapeHtml(run.system_name||"Unknown system")}</div><h2>${escapeHtml(run.anomaly)} <span>· ${escapeHtml(run.variant||"Default")}</span></h2></div><div id="timer" class="timer">00:00:00</div></div>
 <div id="waveBox"></div>
 <div class="run-actions"><button id="pauseBtn" class="secondary">${run.is_paused?"▶ Resume Timer":"⏸ Pause Timer"}</button><button id="completeBtn" class="complete big">✓ Complete Site</button><button id="cancelBtn" class="danger">Delete Test / Cancel</button></div>`;
 renderWave();
 if(timerHandle)clearInterval(timerHandle);
 const start=new Date(run.started_at);
 const displaySeconds=()=>{
   let end=Date.now(), paused=Number(run.paused_seconds||0);
   if(run.paused_at) paused += Math.max(0,(end-new Date(run.paused_at).getTime())/1000);
   return Math.max(0,Math.floor((end-start.getTime())/1000-paused));
 };
 const tick=()=>{let s=displaySeconds();$("#timer").textContent=[Math.floor(s/3600),Math.floor(s%3600/60),s%60].map(x=>String(x).padStart(2,"0")).join(":");$("#timer").classList.toggle("paused",!!run.is_paused)};tick();timerHandle=setInterval(tick,1000);
 $("#pauseBtn").addEventListener("click",async()=>{
   const b=$("#pauseBtn");b.disabled=true;
   const r=await fetch(`/api/run/${run.id}/pause`,{method:"POST"}),j=await r.json();
   if(r.ok){run=j.run;DATA.active=j.run;b.textContent=run.is_paused?"▶ Resume Timer":"⏸ Pause Timer";tick();}
   else alert(j.error||"Could not pause timer.");
   b.disabled=false;
 });
 $("#completeBtn").addEventListener("click",()=>completeRun(run.id));
 $("#cancelBtn").addEventListener("click",()=>deleteRunFromTracker(run.id));
}
function renderSession(){
 const host=$("#sessionStrip");
 if(!DATA.session){host.innerHTML="";return;}
 host.innerHTML=`<div class="session-strip"><div><b>Session #${DATA.session.id}</b> · ${DATA.session.sites} completed sites · ${fmtM(DATA.session.bounty)} bounty</div>${!DATA.active?`<button id="endSessionBtn" class="good">End Session · Add Loot & Salvage</button>`:""}</div>`;
 $("#endSessionBtn")?.addEventListener("click",showEndSession);
}
function renderRecent(){
 const h=$("#recentRuns");
 if(!DATA.recent.length){h.innerHTML='<div class="empty">No completed runs yet.</div>';return;}
 h.innerHTML=`<div class="recent-grid">${DATA.recent.slice(0,8).map(r=>`<div class="recent-card">
 <div><b>${escapeHtml(r.anomaly)}</b><small>${escapeHtml(r.variant||"")}</small></div>
 <div class="recent-meta"><span>${escapeHtml(r.system_name||"—")}</span><span>${r.duration_label}</span><span>${fmtM(r.combined_bounty)}</span></div>
 </div>`).join("")}</div>`;
}
function render(){
 renderStats();renderSession();renderRecent();renderEsiStatus();
 if(DATA.active)runningView(DATA.active);
 else{$("#trackerContent").innerHTML=startForm();setupVariants();$("#startBtn").addEventListener("click",startRun);}
}
async function refreshDashboard(){
 const r=await fetch("/api/dashboard"); if(r.ok){DATA=await r.json();render();}
}
async function refreshBackgroundStatus(){
 try{
  const r=await fetch("/api/dashboard");if(!r.ok)return;
  const fresh=await r.json();
  DATA.esi=fresh.esi;DATA.stats=fresh.stats;DATA.recent=fresh.recent;DATA.session=fresh.session;
  renderStats();renderRecent();renderSession();renderEsiStatus();
 }catch{}
}
async function startRun(){
 const btn=$("#startBtn");btn.disabled=true;setStatus("Starting…");
 const participants=[...document.querySelectorAll(".participant-card input:checked")].map(x=>Number(x.value));
 const payload={anomaly:$("#anomaly").value,variant:$("#variant").value,participants,notes:$("#runNotes").value};
 const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),10000);
 try{
  const r=await fetch("/api/run/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),signal:controller.signal});
  let j={}; try{j=await r.json()}catch{}
  if(!r.ok)throw new Error(j.error||`Could not start (${r.status})`);
  DATA.active=j.run;DATA.session=DATA.session||{id:j.session_id,sites:0,bounty:0};setStatus("Local data saved ✓ · ESI pending");renderSession();runningView(j.run);
 }catch(err){
  alert(err.name==="AbortError"?"Start request timed out. Please try again.":"Could not start site: "+err.message);
  btn.disabled=false;setStatus("");
 }finally{clearTimeout(timer);}
}
async function completeRun(id){
 $("#completeBtn").disabled=true;setStatus("Completing…");
 const r=await fetch(`/api/run/${id}/complete`,{method:"POST"});const j=await r.json();
 if(!r.ok){alert(j.error||"Could not complete.");$("#completeBtn").disabled=false;return;}
 if(timerHandle)clearInterval(timerHandle);localStorage.removeItem("wave_"+id);setStatus("Local data saved ✓ · ESI pending");
 showQuickResult(j.run,j.escalations,j.bounty_pending);
}
function showQuickResult(run,escalations,bountyPending){
 const m=$("#modalContent"), esc=escalations.map(x=>`<option>${escapeHtml(x)}</option>`).join("");
 m.innerHTML=`<div class="modal-head"><div><span class="eyebrow">Site complete</span><h2>${escapeHtml(run.anomaly)}</h2></div><button id="closeResult" class="icon-btn">×</button></div>
 <div class="result-summary"><div><span>Time</span><b>${run.duration_label}</b></div><div><span>Bounty</span><b>${bountyPending?"Pending ESI sync":fmtM(run.combined_bounty)}</b></div><div><span>Bounty ISK/hr</span><b>${bountyPending?"—":fmtM(run.isk_hr)}</b></div></div>
 <p class="hint">Only mark bonuses now. Sale/value details can be added later in History.</p>
 <div class="quick-options">
  <label class="toggle-row"><input id="gotEsc" type="checkbox"><span>Escalation received</span></label>
  <div id="escFields" class="conditional hidden"><select id="escName"><option value="">Select escalation</option>${esc}</select><select id="escStatus"><option>Pending</option><option>Sold</option><option>Ran Myself</option><option>Expired</option></select></div>
  <label class="toggle-row"><input id="gotRare" type="checkbox"><span>Rare spawn</span></label>
  <div id="rareFields" class="conditional hidden"><select id="rareType"><option>Commander</option><option>Dreadnought</option><option>Titan</option><option>Other</option></select></div>
 </div>
 <details><summary>Optional details now</summary><div class="details-grid"><label>Escalation sale value<input id="escValue" class="isk-input" inputmode="numeric" value=""></label><label>Rare loot/value<input id="rareValue" class="isk-input" inputmode="numeric" value=""></label><label class="full">Note<input id="bonusNote"></label></div></details>
 <div class="modal-actions"><button id="saveNext" class="good big">Save & Next Site</button><button id="skipNext" class="secondary">No bonus · Next Site</button></div>`;
 bindIskMask($("#escValue")); bindIskMask($("#rareValue"));
 $("#gotEsc").onchange=e=>$("#escFields").classList.toggle("hidden",!e.target.checked);
 $("#gotRare").onchange=e=>$("#rareFields").classList.toggle("hidden",!e.target.checked);
 $("#closeResult").onclick=()=>finishResult(false,run.id);
 $("#skipNext").onclick=()=>finishResult(false,run.id);
 $("#saveNext").onclick=()=>finishResult(true,run.id);
 showModal();
}
async function finishResult(save,id){
 if(save){
  const btn=$("#saveNext"); if(btn){btn.disabled=true;btn.textContent="Saving…";}
  const payload={
   escalation_name:$("#gotEsc").checked?$("#escName").value:"",
   escalation_status:$("#gotEsc").checked?$("#escStatus").value:"",
   escalation_sale_value:rawIsk($("#escValue").value),
   rare_spawn_type:$("#gotRare").checked?$("#rareType").value:"",
   rare_spawn_value:rawIsk($("#rareValue").value),
   notes:$("#bonusNote").value||""
  };
  try{
   const r=await fetch(`/api/run/${id}/bonus`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
   let j={}; try{j=await r.json()}catch{}
   if(!r.ok)throw new Error(j.error||`Save failed (${r.status})`);
  }catch(err){
   alert("Could not save site result: "+err.message);
   if(btn){btn.disabled=false;btn.textContent="Save & Next Site";}
   return;
  }
 }
 hideModal();await refreshDashboard();setStatus("Local data saved ✓ · ESI pending");
}
function showEndSession(){
 const m=$("#modalContent");
 m.innerHTML=`<div class="modal-head"><div><span class="eyebrow">Finish session</span><h2>Loot & Salvage</h2></div><button id="closeSession" class="icon-btn">×</button></div>
 <p class="hint">One value for everything you collected after the session.</p>
 <div class="details-grid"><label>Loot value (ISK)<input id="lootValue" class="isk-input" inputmode="numeric" value=""></label><label>Salvage value (ISK)<input id="salvageValue" class="isk-input" inputmode="numeric" value=""></label><label class="full">Session note<input id="sessionNote"></label></div>
 <div class="modal-actions"><button id="finishSession" class="good big">Complete Session</button></div>`;
 bindIskMask($("#lootValue")); bindIskMask($("#salvageValue"));
 $("#closeSession").onclick=hideModal;$("#finishSession").onclick=endSession;showModal();
}
async function endSession(){
 const payload={loot_value:rawIsk($("#lootValue").value),salvage_value:rawIsk($("#salvageValue").value),notes:$("#sessionNote").value||""};
 const r=await fetch("/api/session/end",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
 if(r.ok){hideModal();await refreshDashboard();setStatus("Local session saved ✓ · ESI pending");}
}
async function deleteRunFromTracker(id){
 if(!confirm("Delete/cancel this run? Use this for test runs. This cannot be undone."))return;
 const r=await fetch(`/api/run/${id}`,{method:"DELETE"});if(r.ok){if(timerHandle)clearInterval(timerHandle);localStorage.removeItem("wave_"+id);await refreshDashboard();}
}
function showModal(){$("#modalBackdrop").classList.remove("hidden")}
function hideModal(){$("#modalBackdrop").classList.add("hidden")}
$("#modalBackdrop").addEventListener("click",e=>{if(e.target.id==="modalBackdrop")hideModal()});
$("#syncBtn").addEventListener("click",async()=>{
 const b=$("#syncBtn");b.disabled=true;b.textContent="Syncing ESI…";setStatus("Connecting to ESI… local tracker remains available");
 try{
  const r=await fetch("/api/sync",{method:"POST"});let j={};try{j=await r.json()}catch{}
  if(j.dashboard){DATA=j.dashboard;render();}
  if(!r.ok || j.ok===false){
   setStatus("Local data safe ✓ · ESI sync had errors");
   if(j.errors?.length)console.warn("ESI sync:",j.errors);
  }else setStatus("ESI updated ✓");
 }catch(err){
  setStatus("Local data safe ✓ · ESI unavailable");
 }finally{b.disabled=false;b.textContent="↻ Sync ESI";}
});
render();
if(DATA.esi?.pending_runs) setStatus(`${DATA.esi.pending_runs} completed run${DATA.esi.pending_runs===1?"":"s"} pending ESI sync`);
setInterval(refreshBackgroundStatus,60000);

