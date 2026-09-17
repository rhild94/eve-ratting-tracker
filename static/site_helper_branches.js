/* Topic 3: branch-aware helper for Angel Hidden Hideaway.
   This is intentionally separate from the normal linear wave helper. */
(()=>{
  const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]));
  const accountId=window.__BOOTSTRAP__?.account?.id||"browser";
  const stateKey=`eve-ratting:hidden-hideaway-helper:${accountId}`;
  const readState=()=>{try{return JSON.parse(sessionStorage.getItem(stateKey)||"{}")}catch{return {}}};
  const saveState=s=>{try{sessionStorage.setItem(stateKey,JSON.stringify(s))}catch{}};

  function rowsHtml(rows){
    let rare=false,out="";
    for(const r of rows||[]){
      if(!rare&&r[0]==="commander"){
        rare=true;
        out+='<div class="rare-separator"><span>Possible Rare Spawn</span></div>';
      }
      const icon=window.ICON_URLS?.[r[0]]||window.ICON_URLS?.frigate||"";
      out+=`<div class="rat-row ${rare?"rare-row":""}">
        <img class="eve-icon" src="${esc(icon)}" alt="">
        <b>${esc(r[1])}× ${esc(r[2])}</b>
        <span>${esc(r[3])}</span>
      </div>`;
    }
    return out;
  }

  function triggerHtml(note){
    const isTrigger=String(note||"").startsWith("TRIGGER:");
    return `<aside class="trigger-card ${isTrigger?"has-trigger":"no-trigger"}">
      <span class="small-title">Trigger</span>
      ${isTrigger
        ?`<b>⚠ ${esc(String(note).replace(/^TRIGGER:\s*/,""))}</b><small>Use this class-level trigger for the current branch wave.</small>`
        :`<b>No confirmed follow-up trigger</b><small>${esc(note||"This branch ends here in the verified helper data.")}</small>`}
    </aside>`;
  }

  function render(box){
    const data=window.HIDDEN_HIDEAWAY_BRANCHES;
    if(!data)return;
    const state=readState();
    const selected=state.branch&&data.branches[state.branch]?state.branch:"initial";
    const branchButtons=[
      `<button type="button" class="button secondary ${selected==="initial"?"selected":""}" data-hh-branch="initial">Initial Group</button>`,
      ...Object.entries(data.branches).map(([id,b])=>`<button type="button" class="button secondary ${selected===id?"selected":""}" data-hh-branch="${esc(id)}">${esc(b.label)}</button>`)
    ].join("");

    if(selected==="initial"){
      const choices=data.initial.choices.map(c=>`<div class="trigger-card has-trigger"><span class="small-title">${esc(c.label)}</span><b>⚠ ${esc(c.trigger)}</b><small>This branch can trigger independently from the others.</small></div>`).join("");
      box.innerHTML=`
        <div class="helper-card">
          <div class="helper-head"><div><span class="small-title">Branching site helper</span><h3>Angel Hidden Hideaway</h3></div><b>Parallel branches</b></div>
          <p class="hint">This site is not a linear wave chain. From the Initial Group, different kills can open different branches.</p>
          <div class="helper-nav">${branchButtons}</div>
        </div>
        <div class="wave-detail-grid">
          <div class="helper-card wave-composition">
            <div class="helper-head"><div><span class="small-title">Current group</span><h3>${esc(data.initial.title)}</h3></div></div>
            ${rowsHtml(data.initial.rows)}
          </div>
          <div class="helper-card"><span class="small-title">Branch triggers</span><div class="wave-detail-grid">${choices}</div></div>
        </div>`;
    }else{
      const branch=data.branches[selected];
      const max=Math.max(0,branch.waves.length-1);
      const index=Math.max(0,Math.min(Number(state.wave||0),max));
      const current=branch.waves[index];
      const steps=branch.waves.map((w,i)=>`<button class="wave-step ${i===index?"current":i<index?"past":""}" data-hh-wave="${i}" title="${esc(w[0])}">${i+1}</button>`).join("");
      box.innerHTML=`
        <div class="helper-card">
          <div class="helper-head"><div><span class="small-title">Branching site helper</span><h3>${esc(branch.label)}</h3></div><b>${index+1}/${branch.waves.length}</b></div>
          <p class="hint">Hidden Hideaway branches can coexist. Switch branches whenever another trigger path spawns.</p>
          <div class="helper-nav">${branchButtons}</div>
        </div>
        <div class="wave-progress-card"><div class="wave-progress-head"><span>Branch Progress</span><b>${esc(current[0])}</b></div><div class="wave-stepper">${steps}</div></div>
        <div class="wave-detail-grid">
          <div class="helper-card wave-composition"><div class="helper-head"><div><span class="small-title">Current branch wave</span><h3>${esc(current[0])}</h3></div></div>${rowsHtml(current[1])}</div>
          ${triggerHtml(current[2])}
        </div>
        <div class="helper-nav wave-nav"><button id="hhPrev" ${index===0?"disabled":""}>← Previous Wave</button><button id="hhNext" class="good" ${index===max?"disabled":""}>${index===max?"End of Branch":"Next Wave →"}</button></div>`;

      box.querySelectorAll("[data-hh-wave]").forEach(btn=>btn.addEventListener("click",()=>{saveState({branch:selected,wave:Number(btn.dataset.hhWave)});render(box)}));
      box.querySelector("#hhPrev")?.addEventListener("click",()=>{if(index>0){saveState({branch:selected,wave:index-1});render(box)}});
      box.querySelector("#hhNext")?.addEventListener("click",()=>{if(index<max){saveState({branch:selected,wave:index+1});render(box)}});
    }

    box.querySelectorAll("[data-hh-branch]").forEach(btn=>btn.addEventListener("click",()=>{
      const branch=btn.dataset.hhBranch;
      saveState(branch==="initial"?{branch:"initial",wave:0}:{branch,wave:0});
      render(box);
    }));
  }

  function mount(){
    const heading=document.querySelector("#trackerContent .running-head h2");
    const box=document.querySelector("#waveBox");
    if(!heading||!box||!heading.textContent.includes("Angel Hidden Hideaway"))return;
    if(box.dataset.hiddenHideawayBranchHelper==="1")return;
    box.dataset.hiddenHideawayBranchHelper="1";
    render(box);
  }

  const root=document.querySelector("#trackerContent")||document.body;
  new MutationObserver(mount).observe(root,{childList:true,subtree:true});
  mount();
})();
