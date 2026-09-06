function updateEveClock(){
 const el=document.querySelector("[data-eve-clock]");
 if(!el)return;
 const d=new Date();
 const hh=String(d.getUTCHours()).padStart(2,"0"),mm=String(d.getUTCMinutes()).padStart(2,"0"),ss=String(d.getUTCSeconds()).padStart(2,"0");
 el.textContent=`${hh}:${mm}:${ss}`;
}
updateEveClock();setInterval(updateEveClock,1000);