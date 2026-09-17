/* Topic 5: keep commander / rare-spawn tracking distinct from escalations. */
(()=>{
  'use strict';
  const BOOT=window.__BOOTSTRAP__||{};
  const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
  const money=v=>Number(v||0);
  const isk=v=>{
    const n=money(v);
    if(!n)return '';
    if(n>=1e9)return `${(n/1e9).toFixed(2)}B ISK`;
    if(n>=1e6)return `${Math.round(n/1e6)}M ISK`;
    if(n>=1e3)return `${Math.round(n/1e3)}K ISK`;
    return `${Math.round(n)} ISK`;
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
    const runs=BOOT.history?.runs||[];
    return new Map(runs.map(r=>[String(r.id),r]));
  }

  function escalationCell(r){
    if(!r?.escalation_name)return '—';
    const status=r.escalation_status||'Pending';
    const value=['Sold','Ran Myself'].includes(status)?isk(r.escalation_sale_value):'';
    return `<div class="topic5-result"><b>${esc(r.escalation_name)}</b><small>${esc(status)}</small>${value?`<strong>${esc(value)}</strong>`:''}</div>`;
  }

  function rareCell(r){
    if(!r?.rare_spawn_type)return '—';
    const name=(r.rare_spawn_name||'').trim();
    const value=isk(r.rare_spawn_value);
    return `<div class="topic5-result"><b>${esc(r.rare_spawn_type)}</b>${name?`<small>${esc(name)}</small>`:''}${value?`<strong>${esc(value)}</strong>`:''}</div>`;
  }

  function splitHistoryResults(){
    if(location.pathname!=='/history')return;
    const table=document.querySelector('.history-main table');
    if(!table)return;
    const head=[...table.querySelectorAll('thead th')];
    let escIndex=head.findIndex(th=>th.dataset.topic5Esc==='1'||th.textContent.trim()==='Bonus'||th.textContent.trim()==='Escalation');
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
      const id=row.id.replace('runRow','');
      const run=runs.get(id);
      if(!run)return;
      const cells=[...row.children];
      const escCell=cells[escIndex];
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

  function installBonusGuard(){
    if(window.__topic5RareFetchInstalled)return;
    window.__topic5RareFetchInstalled=true;
    const native=window.fetch.bind(window);
    window.fetch=async function(input,init){
      const url=typeof input==='string'?input:input?.url||'';
      let opts=init?{...init}:init;
      if(opts?.body&&/\/api\/run\/\d+\/bonus(?:\?|$)/.test(url)){
        try{
          const body=JSON.parse(opts.body);
          const quickName=document.querySelector('#modalContent #rareName');
          if(quickName&&body.rare_spawn_type)body.rare_spawn_name=quickName.value.trim();
          if(!body.rare_spawn_type){
            body.rare_spawn_name='';
            body.rare_spawn_value=0;
          }
          opts.body=JSON.stringify(body);
        }catch{}
      }
      return native(input,opts);
    };
  }

  let scheduled=false;
  const apply=()=>{
    scheduled=false;
    enhanceQuickResult();
    splitHistoryResults();
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
