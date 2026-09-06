const data=window.CHART_DATA||[];
const canvas=document.getElementById("chart"),ctx=canvas.getContext("2d"),tooltip=document.getElementById("chartTooltip");
let points=[],metrics={W:0,H:280,p:{l:58,r:28,t:24,b:40},max:1,avg:0};

const total=row=>["bounty","ess","loot","salvage","bonus"].reduce((a,k)=>a+Number(row[k]||0),0);
const isk=v=>(Number(v||0)/1e6).toFixed(2)+"m ISK";
const activeTotals=()=>data.map(total).filter(v=>v>0);
function lerp(a,b,t){return Math.round(a+(b-a)*t)}
function rgb(hex){return [parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)]}
function incomeColor(v){
 const vals=activeTotals(),lo=Math.min(...vals,0),hi=Math.max(...vals,1),t=hi===lo?0.7:Math.max(0,Math.min(1,(v-lo)/(hi-lo)));
 const stops=[[0,"#7f554f"],[.28,"#d4873d"],[.5,"#d4cf49"],[.72,"#54d977"],[1,"#31d8e5"]];
 let a=stops[0],b=stops[stops.length-1];
 for(let i=1;i<stops.length;i++){if(t<=stops[i][0]){a=stops[i-1];b=stops[i];break;}}
 const local=(t-a[0])/(b[0]-a[0]||1),ca=rgb(a[1]),cb=rgb(b[1]);
 return {css:`rgb(${lerp(ca[0],cb[0],local)},${lerp(ca[1],cb[1],local)},${lerp(ca[2],cb[2],local)})`,t};
}

function draw(){
 const dpr=window.devicePixelRatio||1,rect=canvas.getBoundingClientRect(),W=rect.width,H=280,p=metrics.p;
 canvas.width=Math.max(1,W*dpr);canvas.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
 metrics.W=W;metrics.H=H;
 const totals=data.map(total),max=Math.max(...totals,1)*1.1;metrics.max=max;
 const active=totals.filter(v=>v>0);metrics.avg=active.length?active.reduce((a,b)=>a+b,0)/active.length:0;
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
 if(metrics.avg>0){
  const ay=H-p.b-(metrics.avg/max)*(H-p.t-p.b);
  ctx.save();ctx.setLineDash([6,6]);ctx.strokeStyle="rgba(130,205,220,.55)";ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(p.l,ay);ctx.lineTo(W-p.r,ay);ctx.stroke();ctx.restore();
  ctx.fillStyle="#86a9b9";ctx.textAlign="right";ctx.fillText("Avg "+(metrics.avg/1e6).toFixed(1)+"m",W-p.r,Math.max(12,ay-6));ctx.textAlign="left";
 }
 if(!points.length)return;
 const grad=ctx.createLinearGradient(p.l,0,W-p.r,0);
 points.forEach(pt=>grad.addColorStop(Math.max(0,Math.min(1,(pt.x-p.l)/inner)),incomeColor(pt.total).css));
 ctx.strokeStyle=grad;ctx.lineWidth=3;ctx.lineJoin="round";ctx.lineCap="round";ctx.beginPath();ctx.moveTo(points[0].x,points[0].y);
 for(let i=1;i<points.length;i++){const prev=points[i-1],cur=points[i],mid=(prev.x+cur.x)/2;ctx.bezierCurveTo(mid,prev.y,mid,cur.y,cur.x,cur.y);}
 ctx.stroke();
 points.forEach(pt=>{
  const c=incomeColor(pt.total);
  ctx.save();ctx.shadowColor=c.css;ctx.shadowBlur=pt.total>0?4+12*c.t:0;ctx.fillStyle=c.css;
  ctx.beginPath();ctx.arc(pt.x,pt.y,pt.total>0?4.5:3,0,Math.PI*2);ctx.fill();ctx.restore();
  ctx.beginPath();ctx.arc(pt.x,pt.y,7,0,Math.PI*2);ctx.strokeStyle="#0c1422";ctx.lineWidth=2;ctx.stroke();
 });
}
function hideTip(){tooltip?.classList.add("hidden")}
function showTip(pt,clientX,clientY){
 if(!tooltip)return;
 const r=canvas.parentElement.getBoundingClientRect(),row=pt.row,c=incomeColor(pt.total);
 tooltip.innerHTML=`<b>${row.date}</b><strong style="color:${c.css}">${isk(pt.total)}</strong><span>${Number(row.sites||0)} site${Number(row.sites||0)===1?"":"s"} · ${row.isk_hr?isk(row.isk_hr)+"/hr":"—"}</span><span>Bounty: ${isk(row.bounty)}</span><span>ESS: ${isk(row.ess)}</span><span>Loot: ${isk(row.loot)}</span><span>Salvage: ${isk(row.salvage)}</span><span>Bonus: ${isk(row.bonus)}</span>`;
 tooltip.classList.remove("hidden");
 const tw=tooltip.offsetWidth,th=tooltip.offsetHeight;
 tooltip.style.left=Math.min(Math.max(8,clientX-r.left+12),Math.max(8,r.width-tw-8))+"px";
 tooltip.style.top=Math.max(8,clientY-r.top-th-12)+"px";
}
canvas.addEventListener("mousemove",e=>{
 if(!points.length)return hideTip();
 const rect=canvas.getBoundingClientRect(),x=e.clientX-rect.left;
 const nearest=points.reduce((a,b)=>Math.abs(b.x-x)<Math.abs(a.x-x)?b:a);
 if(Math.abs(nearest.x-x)>Math.max(28,(metrics.W-metrics.p.l-metrics.p.r)/Math.max(1,points.length-1)/2))return hideTip();
 showTip(nearest,e.clientX,e.clientY);
});
canvas.addEventListener("mouseleave",hideTip);
draw();window.addEventListener("resize",()=>{hideTip();draw()});
