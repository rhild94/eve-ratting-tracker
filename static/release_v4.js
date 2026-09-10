(()=>{
'use strict';
function apply(){document.body.classList.add('release-v4')}
window.applyReleaseV4=apply;
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply);else apply();
})();
