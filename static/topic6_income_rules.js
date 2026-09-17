/* Topic 6: one client-side source of truth for realized site income.
   The backend remains authoritative; this layer prevents stale/invalid UI payloads. */
(()=>{
  'use strict';
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

  if(window.__topic6IncomeFetchInstalled)return;
  window.__topic6IncomeFetchInstalled=true;
  const native=window.fetch.bind(window);
  window.fetch=async function(input,init){
    const url=typeof input==='string'?input:input?.url||'';
    let opts=init?{...init}:init;
    if(opts?.body&&/\/api\/run\/\d+\/bonus(?:\?|$)/.test(url)){
      try{
        const body=JSON.parse(opts.body);
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
        opts.body=JSON.stringify(body);
      }catch{}
    }
    return native(input,opts);
  };

  const updateCopy=()=>{
    if(location.pathname!=='/dashboard')return;
    const p=document.querySelector('.performance-panel .muted');
    if(p)p.textContent='Ratting ISK/h = Bounty + ESS performance · Total ISK = actual session income including loot, salvage, rare drops and realized escalation value.';
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',updateCopy);else updateCopy();
})();
