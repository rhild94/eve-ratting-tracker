const rows=window.SESSION_CHART_DATA||[],avg=Number(window.SESSION_AVG||0);
const canvas=document.getElementById("sessionChart"),ctx=canvas.getContext("2d"),tip=document.getElementById("sessionTooltip");
let pts=[],dims={W:0,H:330,p:{l:64,r:34,t:30,b:44},max:1};

const isk=v=>(Number(v||0)/1e6).toFixed(1)+"M";
function rgb(hex){return [parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)]}
function lerp(a,b,t){return Math.round(a+(b-a)*t)}
function perfColor(v){
 const vals=rows.map(r=>Number(r.ratting_isk_hr||0)).filter(v=>v>0),lo=Math.min(...vals,0),hi=Math.max(...vals,1);
 const t=hi===lo?.7:Math.max(0,Math.min(1,(v-lo)/(hi-lo)));
 const stops=[[0,"#a65a42"],[.3,"#d98d38"],[.5,"#d7d04b"],[.72,"#58d979"],[1,"#35d9e7"]];
 let a=stops[0],b=stops.at(-1);
 for(let i=1;i<stops.length;i++)if(t<=stops[i][0]){a=stops[i-1];b=stops[i];break}
 const u=(t-a[0])/(b[0]-a[0]||1),ca=rgb(a[1]),cb=rgb(b[1]);
 return {css:`rgb(${lerp(ca[0],cb[0],u)},${lerp(ca[1],cb[1],u)},${lerp(ca[2],cb[2],u)})`,t};
}
function draw(){
 const dpr=devicePixelRatio||1,rect=canvas.getBoundingClientRect(),W=rect.width,H=330,p=dims.p;
 canvas.width=Math.max(1,W*dpr);canvas.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);dims.W=W;
 const vals=rows.map(r=>Number(r.ratting_isk_hr||0)),max=Math.max(...vals,avg,1)*1.15;dims.max=max;
 ctx.font="12px Segoe UI";ctx.lineWidth=1;ctx.strokeStyle="#173249";ctx.fillStyle="#8295ad";
 for(let i=0;i<=4;i++){const y=p.t+(H-p.t-p.b)*i/4,val=max*(1-i/4);ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(W-p.r,y);ctx.stroke();ctx.fillText((val/1e6).toFixed(0)+"M",8,y+4)}
 const inner=Math.max(1,W-p.l-p.r),step=rows.length>1?inner/(rows.length-1):0;
 pts=rows.map((row,i)=>({x:p.l+(rows.length===1?inner/2:i*step),y:H-p.b-(Number(row.ratting_isk_hr||0)/max)*(H-p.t-p.b),row}));
 ctx.fillStyle="#8295ad";pts.forEach((pt,i)=>{ctx.textAlign=i===0?"left":i===pts.length-1?"right":"center";ctx.fillText(pt.row.date||"",pt.x,H-14)});ctx.textAlign="left";
 if(avg>0){const y=H-p.b-(avg/max)*(H-p.t-p.b);ctx.save();ctx.setLineDash([6,6]);ctx.strokeStyle="rgba(190,220,228,.68)";ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(W-p.r,y);ctx.stroke();ctx.restore();ctx.fillStyle="#b7c9d5";ctx.textAlign="right";ctx.fillText("Avg "+isk(avg),W-p.r,Math.max(16,y-7));ctx.textAlign="left";}
 if(!pts.length){ctx.fillStyle="#8295ad";ctx.textAlign="center";ctx.fillText("Complete a ratting session to populate this graph.",W/2,H/2);return}
 const grad=ctx.createLinearGradient(p.l,0,W-p.r,0);pts.forEach(pt=>grad.addColorStop(Math.max(0,Math.min(1,(pt.x-p.l)/inner)),perfColor(pt.row.ratting_isk_hr).css));
 ctx.strokeStyle=grad;ctx.lineWidth=3;ctx.lineJoin="round";ctx.lineCap="round";ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
 for(let i=1;i<pts.length;i++){const a=pts[i-1],b=pts[i],mid=(a.x+b.x)/2;ctx.bezierCurveTo(mid,a.y,mid,b.y,b.x,b.y)}ctx.stroke();
 pts.forEach(pt=>{const c=perfColor(pt.row.ratting_isk_hr);ctx.save();ctx.fillStyle=c.css;ctx.shadowColor=c.css;ctx.shadowBlur=5+10*c.t;ctx.beginPath();ctx.arc(pt.x,pt.y,5,0,Math.PI*2);ctx.fill();ctx.restore()});
}
function hide(){tip.classList.add("hidden")}
function show(pt,e){
 const r=canvas.parentElement.getBoundingClientRect(),x=pt.row,c=perfColor(x.ratting_isk_hr);
 const dur=Math.round(Number(x.duration_seconds||0)/60);
 tip.innerHTML=`<b>Session #${x.id} · ${x.date}</b><strong style="color:${c.css}">${isk(x.ratting_isk_hr)} ISK/hr</strong><span>Participants: ${x.participants||0}</span><span>Sites ran: ${x.sites}</span><span>Duration: ${Math.floor(dur/60)}h ${dur%60}m</span><span>Bounty: ${isk(x.bounty)}</span><span>ESS: ${isk(x.ess)}</span><span>Loot: ${isk(x.loot)}</span><span>Salvage: ${isk(x.salvage)}</span>`;
 tip.classList.remove("hidden");const tw=tip.offsetWidth,th=tip.offsetHeight;tip.style.left=Math.min(Math.max(8,e.clientX-r.left+12),Math.max(8,r.width-tw-8))+"px";tip.style.top=Math.max(8,e.clientY-r.top-th-12)+"px";
}
canvas.addEventListener("mousemove",e=>{if(!pts.length)return hide();const rr=canvas.getBoundingClientRect(),x=e.clientX-rr.left;const p=pts.reduce((a,b)=>Math.abs(b.x-x)<Math.abs(a.x-x)?b:a);if(Math.abs(p.x-x)>50)return hide();show(p,e)});
canvas.addEventListener("mouseleave",hide);draw();addEventListener("resize",()=>{hide();draw()});