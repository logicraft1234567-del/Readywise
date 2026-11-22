/* Dot-matrix 3-2-1 intro. rwCountdown({title, sub, onDone}). Esc, click or Skip ends it early. */
function rwCountdown(o){
  o=o||{};
  if(matchMedia("(prefers-reduced-motion: reduce)").matches){o.onDone&&o.onDone();return}
  const ov=document.createElement("div");ov.id="rw-intro";
  ov.innerHTML='<canvas></canvas><button class="rw-skip">Skip</button><div class="rw-dots"><i></i><i></i><i></i></div><div class="rw-card"><svg width="26" height="26" viewBox="0 0 24 24" fill="#fff"><path d="M12 2l2.2 6.3L20.5 10l-6.3 1.7L12 18l-2.2-6.3L3.5 10l6.3-1.7z"/></svg><div><b></b><p></p></div></div>';
  ov.querySelector("b").textContent=o.title||"ReadyWise";ov.querySelector("p").textContent=o.sub||"";
  document.body.appendChild(ov);document.documentElement.style.overflow="hidden";
  const cv=ov.querySelector("canvas"),ctx=cv.getContext("2d"),dots=ov.querySelectorAll(".rw-dots i"),dpr=Math.min(2,devicePixelRatio||1);
  let W,H,dead=false,raf,P=[],digit=-1,t0=performance.now(),burstDone=false;
  const SLOT=1100,DIG=["3","2","1"],COL=["#9db4ff","#c9d6ff","#6f8dff","#ffffff","#4f7bff","#ff7a59"],rnd=(a,b)=>a+Math.random()*(b-a);
  function size(){W=innerWidth;H=innerHeight;cv.width=W*dpr;cv.height=H*dpr;cv.style.width=W+"px";cv.style.height=H+"px";ctx.setTransform(dpr,0,0,dpr,0,0)}size();
  function pointsFor(ch){const c2=document.createElement("canvas");c2.width=W;c2.height=H;const c=c2.getContext("2d"),fs=Math.min(W*.9,H*.8);
    c.font="700 "+fs+"px Geist,Arial,sans-serif";c.textAlign="center";c.textBaseline="middle";c.fillStyle="#fff";c.fillText(ch,W/2,H*.46);
    const d=c.getImageData(0,0,W,H).data,step=Math.max(8,Math.round(fs/32)),pts=[];
    for(let y=0;y<H;y+=step)for(let x=0;x<W;x+=step)if(d[(y*W+x)*4+3]>140)pts.push([x+rnd(-1.5,1.5),y+rnd(-1.5,1.5)]);
    for(let i=pts.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[pts[i],pts[j]]=[pts[j],pts[i]]}return pts}
  function mk(){const a=rnd(0,6.28),R=Math.max(W,H)*rnd(.5,.75),side=Math.random()<.5?-1:1;
    return {x:rnd(0,W),y:rnd(0,H),vx:0,vy:0,tx:0,ty:0,on:false,burst:0,ph:rnd(0,6.28),c:COL[Math.random()<.04?5:Math.floor(rnd(0,5))],
      ax:W/2+side*rnd(W*.28,W*.55),ay:H*.5+Math.sin(a)*H*.42,r:rnd(.9,1.6)}}
  function setDigit(i){digit=i;burstDone=false;dots.forEach((d,k)=>d.classList.toggle("on",k===i));const pts=pointsFor(DIG[i]);
    while(P.length<pts.length)P.push(mk());
    P.forEach((p,j)=>{if(j<pts.length){p.on=true;p.tx=pts[j][0];p.ty=pts[j][1];p.r=rnd(1.8,2.9)*Math.max(.8,W/1100)}else{p.on=false;p.r=rnd(.9,1.6)}})}
  function burst(){P.forEach(p=>{const a=Math.atan2(p.y-H*.46,p.x-W/2)+rnd(-.6,.6),s=rnd(7,17);p.vx=Math.cos(a)*s;p.vy=Math.sin(a)*s;p.burst=11})}
  function finish(){if(dead)return;dead=true;cancelAnimationFrame(raf);removeEventListener("keydown",key);ov.classList.add("out");o.onDone&&o.onDone();
    setTimeout(()=>{ov.remove();document.documentElement.style.overflow=""},700)}
  function key(e){if(e.key==="Escape"||e.key===" ")finish()}
  addEventListener("keydown",key);ov.querySelector(".rw-skip").onclick=finish;ov.onclick=e=>{if(e.target===ov||e.target===cv)finish()};
  function frame(now){if(dead)return;const el=now-t0,i=Math.floor(el/SLOT),ph=(el%SLOT)/SLOT;
    if(i>=DIG.length){burst();ctx.clearRect(0,0,W,H);finish();return}
    if(i!==digit)setDigit(i);
    if(ph>.8&&!burstDone){burstDone=true;burst()}
    ctx.clearRect(0,0,W,H);ctx.globalCompositeOperation="lighter";
    for(const p of P){
      const tx=p.on?p.tx:p.ax+Math.sin(now*.0006+p.ph)*16,ty=p.on?p.ty:H*.5+(p.ay-H*.5)+Math.cos(now*.0005+p.ph)*16;
      if(p.burst>0)p.burst--;else{p.vx+=(tx-p.x)*.05;p.vy+=(ty-p.y)*.05}
      p.vx*=.86;p.vy*=.86;p.x+=p.vx;p.y+=p.vy;
      const tw=.65+.35*Math.sin(now*.004+p.ph),al=(p.on?.95:.35)*tw*(ph>.9?1-(ph-.9)*4:1);
      ctx.fillStyle=p.c;ctx.globalAlpha=al*.16;ctx.beginPath();ctx.arc(p.x,p.y,p.r*3,0,6.283);ctx.fill();
      ctx.globalAlpha=al;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,6.283);ctx.fill()}
    ctx.globalAlpha=1;raf=requestAnimationFrame(frame)}
  const go=()=>{t0=performance.now();raf=requestAnimationFrame(frame)};
  (document.fonts&&document.fonts.load?Promise.race([document.fonts.load("700 100px Geist"),new Promise(r=>setTimeout(r,700))]):Promise.resolve()).then(go,go);
  addEventListener("resize",()=>{if(!dead){size();if(digit>=0)setDigit(digit)}});
}
