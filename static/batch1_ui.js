/* Batch 1: keep the legacy Tracker header status consistent with React tabs. */
(()=>{
  const relativePast=(value)=>{
    if(!value)return null;
    const seconds=Math.max(0,Math.floor((Date.now()-new Date(value).getTime())/1000));
    if(seconds<60)return "just now";
    if(seconds<3600)return `${Math.floor(seconds/60)}m ago`;
    if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`;
    return `${Math.floor(seconds/86400)}d ago`;
  };

  const install=()=>{
    if(typeof renderEsiStatus!=="function" || typeof DATA==="undefined" || !document.querySelector("#systemStatus"))return false;

    renderEsiStatus=()=>{
      const e=DATA.esi||{};
      const last=e.last_success||e.last_sync;
      const status=document.querySelector("#systemStatus");
      const sync=document.querySelector("#syncBtn");
      const alert=document.querySelector("#esiAlert");

      if(status){
        status.textContent=e.configured===false
          ? "ESI not configured"
          : e.last_error
            ? "ESI sync issue"
            : last
              ? `Synced ${relativePast(last)}`
              : "Not synced yet";
      }

      if(sync){
        sync.disabled=e.configured===false;
        sync.title=e.configured===false?"Connect/configure EVE first to use ESI":"";
      }

      if(alert){
        if(e.last_error){
          alert.textContent="⚠ ESI sync issue — ESI-based values may be stale. Local tracker data is safe.";
          alert.title=e.last_error;
          alert.classList.remove("hidden");
        }else{
          alert.textContent="";
          alert.title="";
          alert.classList.add("hidden");
        }
      }
    };

    renderEsiStatus();
    return true;
  };

  if(install())return;
  let attempts=0;
  const timer=setInterval(()=>{
    attempts+=1;
    if(install()||attempts>=100)clearInterval(timer);
  },50);
})();
