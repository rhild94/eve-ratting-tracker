(()=>{
'use strict';
function updateEveClock(){document.querySelectorAll('[data-eve-clock]').forEach(el=>el.textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'UTC',hour12:false}))}
function apply(){window.applyNextUpdateV2?.();window.applyProdUpdateV3?.();window.applyReleaseV4?.()}
window.applyEveShell=apply;
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',apply):apply();
setInterval(updateEveClock,1000);updateEveClock();
})();
