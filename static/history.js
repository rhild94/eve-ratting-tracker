const data=window.CHART_DATA||[];
const canvas=document.getElementById("chart"),ctx=canvas.getContext("2d"),tooltip=document.getElementById("chartTooltip");
let points=[],metrics={W:0,H:280,p:{l:58,r:20,t:22,b:38},max:1};

const total=row=>["bounty","ess","loot","salvage","bonus"].reduce((a,k)=>a+Number(row[k]||0),0);
const isk=v=>(Number(v||0)/1e6).toFixed(2)+"m ISK";

function draw(){
 const dpr=window.devicePixelRatio||1,rect=canvas.getBoundingClientRect(),W=rect.width,H=280,p=metrics.p;
 canvas.width=Math.max(1,W*dpr);canvas.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
 metrics.W=W;metrics.H=H;
 const totals=data.map(total),max=Math.max(...totals,1)*1.08;metrics.max=max;
 ctx.font="12px Segoe UI";ctx.lineWidth=1;ctx.strokeStyle="#183149";ctx.fillStyle="#8295ad";
 for(let i=0;i<=4;i++){
   const y=p.t+(H-p.t-p.b)*i/4,val=max*(1-i/4);
   ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(W-p.r,y);ctx.stroke();
   ctx.fillText((val/1e6).toFixed(1)+"m",5,y+4);
 }
 const inner=Math.max(1,W-p.l-p.r),step=data.length>1?inner/(data.length-1):0;
 points=data.map((row,i)=>({x:p.l+(data.length===1?inner/2:i*step),y:H-p.b-(total(row)/max)*(H-p.t-p.b),row,total:total(row)}));
 ctx.fillStyle="#8295ad";
 points.forEach((pt,i)=>{
   const label=(pt.row.date||"").slice(5);
   ctx.textAlign=i===0?"left":i===points.length-1?"right":"center";
   ctx.fillText(label,pt.x,H-12);
 });
 ctx.textAlign="left";
 if(!points.length)return;
 ctx.strokeStyle="#74b7ec";ctx.lineWidth=3;ctx.lineJoin="round";ctx.lineCap="round";ctx.beginPath();
 ctx.moveTo(points[0].x,points[0].y);
 for(let i=1;i<points.length;i++){
   const prev=points[i-1],cur=points[i],mid=(prev.x+cur.x)/2;
   ctx.bezierCurveTo(mid,prev.y,mid,cur.y,cur.x,cur.y);
 }
 ctx.stroke();
 points.forEach(pt=>{
   ctx.beginPath();ctx.arc(pt.x,pt.y,4,0,Math.PI*2);ctx.fillStyle="#74b7ec";ctx.fill();
   ctx.beginPath();ctx.arc(pt.x,pt.y,7,0,Math.PI*2);ctx.strokeStyle="#0c1422";ctx.lineWidth=2;ctx.stroke();
 });
}
function hideTip(){tooltip?.classList.add("hidden")}
function showTip(pt,clientX,clientY){
 if(!tooltip)return;
 const r=canvas.parentElement.getBoundingClientRect(),row=pt.row;
 tooltip.innerHTML=`<b>${row.date}</b><strong>${isk(pt.total)}</strong><span>Bounty: ${isk(row.bounty)}</span><span>ESS: ${isk(row.ess)}</span><span>Loot: ${isk(row.loot)}</span><span>Salvage: ${isk(row.salvage)}</span><span>Bonus: ${isk(row.bonus)}</span>`;
 tooltip.classList.remove("hidden");
 const tw=tooltip.offsetWidth,th=tooltip.offsetHeight;
 tooltip.style.left=Math.min(Math.max(8,clientX-r.left+12),Math.max(8,r.width-tw-8))+"px";
 tooltip.style.top=Math.max(8,clientY-r.top-th-12)+"px";
}
canvas.addEventListener("mousemove",e=>{
 if(!points.length)return hideTip();
 const rect=canvas.getBoundingClientRect(),x=e.clientX-rect.left;
 let nearest=points.reduce((a,b)=>Math.abs(b.x-x)<Math.abs(a.x-x)?b:a);
 if(Math.abs(nearest.x-x)>Math.max(28,(metrics.W-metrics.p.l-metrics.p.r)/Math.max(1,points.length-1)/2))return hideTip();
 showTip(nearest,e.clientX,e.clientY);
});
canvas.addEventListener("mouseleave",hideTip);
draw();window.addEventListener("resize",()=>{hideTip();draw()});
