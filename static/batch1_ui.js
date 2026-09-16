/* Batch 1: normalize the visible Tracker ESI status without changing tracker data flow. */
(()=>{
  let writing=false;

  const relativePast=(value)=>{
    if(!value)return null;
    const seconds=Math.max(0,Math.floor((Date.now()-new Date(value).getTime())/1000));
    if(seconds<60)return "just now";
    if(seconds<3600)return `${Math.floor(seconds/60)}m ago`;
    if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`;
    return `${Math.floor(seconds/86400)}d ago`;
  };

  const expectedStatus=()=>{
    const e=window.DATA?.esi||window.__BOOTSTRAP__?.data?.esi||{};
    const last=e.last_success||e.last_sync;
    if(e.configured===false)return "ESI not configured";
    if(e.last_error)return "ESI sync issue";
    if(last)return `Synced ${relativePast(last)}`;
    return "Not synced yet";
  };

  const normalizeTrackerStatus=()=>{
    const status=document.querySelector("#systemStatus");
    if(!status)return;
    const expected=expectedStatus();
    if(status.textContent!==expected){
      writing=true;
      status.textContent=expected;
      writing=false;
    }
  };

  /* eve_shell.js appends compatibility styles dynamically. Keep the Batch 1
     stylesheet last in the cascade so its alignment rules stay authoritative. */
  const keepBatchCssLast=()=>{
    const link=[...document.querySelectorAll('link[rel="stylesheet"]')].find(x=>x.href.includes('/static/batch1_ui.css'));
    if(link&&link.parentNode===document.head&&link!==document.head.lastElementChild)document.head.appendChild(link);
  };

  const observer=new MutationObserver(()=>{
    if(writing)return;
    normalizeTrackerStatus();
    keepBatchCssLast();
  });
  observer.observe(document.documentElement,{childList:true,subtree:true,characterData:true});

  normalizeTrackerStatus();
  keepBatchCssLast();
  setTimeout(()=>{normalizeTrackerStatus();keepBatchCssLast()},100);
  setTimeout(()=>{normalizeTrackerStatus();keepBatchCssLast()},500);
  setInterval(normalizeTrackerStatus,30000);
})();
