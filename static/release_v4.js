(()=>{
'use strict';
function installHistoryAnalyticsFetch(){
 if(window.__releaseV4HistoryFetch)return;window.__releaseV4HistoryFetch=true;
 const native=window.fetch.bind(window);
 window.fetch=function(input,init){
  try{
   const raw=typeof input==='string'?input:input?.url||'';
   if(/^\/history\?days=\d+(?:$|&)/.test(raw)&&!/[?&](analytics|run_page|session_page)=/.test(raw)){
    const next=raw+(raw.includes('?')?'&':'?')+'analytics=1';
    return native(next,init);
   }
  }catch{}
  return native(input,init);
 };
}
function apply(){document.body.classList.add('release-v4');installHistoryAnalyticsFetch()}
window.applyReleaseV4=apply;
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply);else apply();
})();
