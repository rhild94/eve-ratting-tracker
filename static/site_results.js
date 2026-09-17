/* Consolidated site-result compatibility layer: rare spawns + realized income. */
(()=>{
  'use strict';
  const BOOT=window.__BOOTSTRAP__||{};
  const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
  const money=v=>Math.max(0,Number(v||0));
  const realizedStatuses=new Set(['Sold','Ran Myself']);
  const rules=Object.freeze({
    isRealizedEscalation:status=>realizedStatuses.has(status),
    escalationValue:(status,value)=>realizedStatuses.has(status)?money(value):0,
    escalationSale:(status,value)=>status==='Sold'?money(value):0,
    escalationLoot:(status,value)=>status==='Ran Myself'?money(value):0,
    rareLoot:(type,value)=>type?money(value):0
  });
  window.EVE_INCOME_RULES=rules;

  /* Preserve the History table's established ISK display contract. */
  const isk=v=>{
    const n=money(v);
    return n?`${(n/1e6).toFixed(2)}m ISK`:'';
  };

  function enhanceQuickResult(){
    const modal=document.querySelector('#modalContent');
    const rareToggle=modal?.querySelector('#gotRare');
    const rareFields=modal?.querySelector('#rareFields');
    if(!modal||!rareToggle||!rareFields)return;

    const toggleText=rareToggle.closest('.toggle-row')?.querySelector('span');
    if(toggleText&&toggleText.textContent!=='Commander / rare spawn')toggleText.textContent='Commander / rare spawn';
    const lootText=modal.querySelector('#gotRareLoot')?.closest('.mini-toggle')?.querySelector('span');
    if(lootText&&lootText.textContent!=='Rare drop / loot value')lootText.textContent='Rare drop / loot value';

    if(!modal.querySelector('#rareName')){
      const label=document.createElement('label');
      label.id='rareNameRow';
      label.className='rare-name-row';
      label.innerHTML='Rare NPC / note <input id="rareName" placeholder="Optional">';
      rareFields.appendChild(label);
    }
  }

  function historyRunMap(){
    return new Map((BOOT.history?.runs||[]).map(r=>[String(r.id),r]));
  }

  function escalationCell(r){
    if(!r?.escalation_name)return '—';
    const status=r.escalation_status||'Pending';
    const value=rules.escalationValue(status,r.escalation_sale_value);
    return `<div class="topic5-result"><b>${esc(r.escalation_name)}</b><small>${esc(status)}</small>${value?`<strong>${esc(isk(value))}</strong>`:''}</div>`;
  }

  function rareCell(r){
    if(!r?.rare_spawn_type)return '—';
    const name=(r.rare_spawn_name||'').trim();
    const value=rules.rareLoot(r.rare_spawn_type,r.rare_spawn_value);
    return `<div class="topic5-result"><b>${esc(r.rare_spawn_type)}</b>${name?`<small>${esc(name)}</small>`:''}${value?`<strong>${esc(isk(value))}</strong>`:''}</div>`;
  }

  function splitHistoryResults(){
    if(location.pathname!=='/history')return;
    const table=document.querySelector('.history-main table');
    if(!table)return;
    const head=[...table.querySelectorAll('thead th')];
    const escIndex=head.findIndex(th=>th.dataset.topic5Esc==='1'||th.textContent.trim()==='Bonus'||th.textContent.trim()==='Escalation');
    if(escIndex<0)return;
    const escHead=head[escIndex];
    if(escHead.textContent!=='Escalation')escHead.textContent='Escalation';
    escHead.dataset.topic5Esc='1';
    let rareHead=table.querySelector('thead th[data-topic5-rare="1"]');
    if(!rareHead){
      rareHead=document.createElement('th');
      rareHead.dataset.topic5Rare='1';
      rareHead.textContent='Rare Spawn';
      escHead.insertAdjacentElement('afterend',rareHead);
    }

    const runs=historyRunMap();
    table.querySelectorAll('tbody tr[id^="runRow"]').forEach(row=>{
      const run=runs.get(row.id.replace('runRow',''));
      if(!run)return;
      const escCell=[...row.children][escIndex];
      if(!escCell)return;
      const escMarkup=escalationCell(run);
      if(escCell.innerHTML!==escMarkup)escCell.innerHTML=escMarkup;
      let rareCellNode=row.querySelector('td[data-topic5-rare="1"]');
      if(!rareCellNode){
        rareCellNode=document.createElement('td');
        rareCellNode.dataset.topic5Rare='1';
        escCell.insertAdjacentElement('afterend',rareCellNode);
      }
      const rareMarkup=rareCell(run);
      if(rareCellNode.innerHTML!==rareMarkup)rareCellNode.innerHTML=rareMarkup;
    });
  }

  function sanitizeBonusPayload(body){
    const quickName=document.querySelector('#modalContent #rareName');
    if(quickName&&body.rare_spawn_type)body.rare_spawn_name=quickName.value.trim();

    if(!body.escalation_name){
      body.escalation_status='';
      body.escalation_sale_value=0;
    }else{
      body.escalation_sale_value=rules.escalationValue(body.escalation_status,body.escalation_sale_value);
    }

    if(!body.rare_spawn_type){
      body.rare_spawn_name='';
      body.rare_spawn_value=0;
    }else{
      body.rare_spawn_value=rules.rareLoot(body.rare_spawn_type,body.rare_spawn_value);
    }
    return body;
  }

  function installBonusGuard(){
    if(window.__siteResultsFetchInstalled)return;
    window.__siteResultsFetchInstalled=true;
    const native=window.fetch.bind(window);
    window.fetch=async function(input,init){
      const url=typeof input==='string'?input:input?.url||'';
      let opts=init?{...init}:init;
      if(opts?.body&&/\/api\/run\/\d+\/bonus(?:\?|$)/.test(url)){
        try{opts.body=JSON.stringify(sanitizeBonusPayload(JSON.parse(opts.body)))}catch{}
      }
      return native(input,opts);
    };
  }

  function updateDashboardCopy(){
    if(location.pathname!=='/dashboard')return;
    const p=document.querySelector('.performance-panel .muted');
    const text='Ratting ISK/h = Bounty + ESS performance · Total ISK = actual session income including loot, salvage, rare drops and realized escalation value.';
    if(p&&p.textContent!==text)p.textContent=text;
  }

  let scheduled=false;
  const apply=()=>{
    scheduled=false;
    enhanceQuickResult();
    splitHistoryResults();
    updateDashboardCopy();
  };
  const observer=new MutationObserver(()=>{
    if(scheduled)return;
    scheduled=true;
    requestAnimationFrame(apply);
  });

  installBonusGuard();
  observer.observe(document.documentElement,{childList:true,subtree:true});
  apply();
})();
