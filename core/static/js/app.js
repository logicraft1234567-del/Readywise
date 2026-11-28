document.addEventListener("DOMContentLoaded",()=>{
  if(window.lucide) lucide.createIcons({attrs:{"stroke-width":1.75}});
  const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
  let demoOn=false;

  /* nav gains a hairline once the page scrolls */
  const nav=document.querySelector(".nav");
  if(nav){const f=()=>nav.classList.toggle("scrolled",scrollY>8);f();addEventListener("scroll",f,{passive:true})}

  /* the one orchestrated moment: the hero lines settle, then the panel frame arrives */
  const hero=document.querySelector(".hero-h");
  let heroTl=null;
  if(window.gsap&&hero&&!reduce&&!document.querySelector("[data-cin]")){  /* the cinematic landing runs its own scene engine (js/cinema.js) */
    heroTl=gsap.timeline({defaults:{ease:"power3.out"},paused:!!window.rwIntro});
    heroTl.from(".hero-h .ln",{yPercent:105,duration:.9,stagger:.1}).from(".hero-fade",{y:14,opacity:0,duration:.7,stagger:.08},"-=.55").from(".hero-frame",{y:28,opacity:0,duration:1,ease:"power2.out"},"-=.8");
  }
  window.rwHeroPlay=()=>{heroTl&&heroTl.play();startPanelDemo()};
  if(!window.rwIntro) startPanelDemo();

  /* hero demo: the panel passes the question between interviewers, one speaker at a time */
  function startPanelDemo(){
    const frame=document.querySelector(".hero-frame");if(!frame||demoOn)return;demoOn=true;
    const tiles=[...frame.querySelectorAll(".pf-tile")],cap=frame.querySelector("[data-cap]"),who=frame.querySelector("[data-speaker]");
    const lines=tiles.map(t=>({who:t.dataset.who,q:t.dataset.q}));if(!tiles.length)return;
    let i=0;
    const show=(k)=>{tiles.forEach((t,j)=>t.classList.toggle("speaking",j===k%tiles.length));const L=lines[k%lines.length];who.textContent=L.who;
      if(reduce){cap.textContent=L.q;return}
      cap.textContent="";let n=0;clearInterval(show.t);show.t=setInterval(()=>{n+=2;cap.textContent=L.q.slice(0,n);if(n>=L.q.length)clearInterval(show.t)},22)};
    show(0);
    if(!reduce){setInterval(()=>{if(document.hidden)return;i++;show(i)},5200)}
  }

  /* reveal long landing blocks once, quietly */
  const rv=[...document.querySelectorAll(".rv")];
  if(rv.length&&"IntersectionObserver" in window&&!reduce){
    rv.forEach(el=>el.classList.add("rv-pre"));
    const io=new IntersectionObserver((es)=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add("rv-in");io.unobserve(e.target)}}),{threshold:.12,rootMargin:"0px 0px -6% 0px"});
    rv.forEach(el=>io.observe(el));
  }

  /* progress bars */
  document.querySelectorAll(".bar>i").forEach(b=>{const w=b.dataset.w;if(w==null)return;b.style.width="0";setTimeout(()=>b.style.width=w+"%",200)});

  /* feature index on the landing page */
  document.querySelectorAll("[data-fx]").forEach(root=>{
    const items=[...root.querySelectorAll("[data-fx-item]")],panes=[...root.querySelectorAll("[data-fx-pane]")];
    const set=k=>{items.forEach(b=>{const on=b.dataset.fxItem===k;b.classList.toggle("on",on);b.setAttribute("aria-selected",on)});panes.forEach(p=>p.classList.toggle("on",p.dataset.fxPane===k))};
    items.forEach(b=>{b.addEventListener("click",()=>set(b.dataset.fxItem));b.addEventListener("mouseenter",()=>{if(matchMedia("(hover:hover)").matches)set(b.dataset.fxItem)});b.addEventListener("focus",()=>set(b.dataset.fxItem))});
    if(items[0])set(items[0].dataset.fxItem);
  });

  /* tabs */
  document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{document.querySelectorAll(".tabs button,.pane").forEach(x=>x.classList.remove("on"));b.classList.add("on");document.getElementById(b.dataset.pane).classList.add("on");history.replaceState(null,"","#"+b.dataset.pane)});
  const h=location.hash.slice(1);if(h&&document.querySelector(`.tabs button[data-pane="${h}"]`))document.querySelector(`.tabs button[data-pane="${h}"]`).click();
});
const csrf=()=>document.cookie.split("; ").find(c=>c.startsWith("csrftoken="))?.split("=")[1]||document.querySelector("[name=csrfmiddlewaretoken]")?.value;
async function post(url,body,isForm){const r=await fetch(url,{method:"POST",headers:Object.assign({"X-CSRFToken":csrf()},isForm?{}:{"Content-Type":"application/json"}),body:isForm?body:JSON.stringify(body||{})});let d={};try{d=await r.json()}catch(e){}if(!r.ok)throw new Error(d.error||"Something went wrong.");return d}
function toast(m,err){const t=document.createElement("div");t.className="toast";t.style.color=err?"var(--bad)":"var(--ink)";t.setAttribute("role","status");t.textContent=m;document.body.appendChild(t);setTimeout(()=>t.remove(),4200)}
async function pollJob(job,done,every){every=every||1200;for(let n=0;;n++){await new Promise(r=>setTimeout(r,n?every:Math.min(600,every)));const r=await (await fetch(job)).json();if(r.state==="error")throw new Error(r.error||"The job failed.");if(r.state==="idle"||r.state==="done")return typeof done==="string"?(location.href=done):done()}}
async function act(btn,url,body,done){btn.classList.add("busy");const old=btn.innerHTML;btn.innerHTML="Working…";try{const d=await post(url,body);if(d.job){await pollJob(d.job,()=>location.reload());return}if(done)done(d);else location.reload()}catch(e){toast(e.message,true);btn.innerHTML=old;btn.classList.remove("busy")}}

/* Stop double submits: lock the submit button once a form is sent. */
document.addEventListener("submit",e=>{const b=e.target.querySelector("button:not([type=button]),input[type=submit]");if(b&&!b.dataset.keep){setTimeout(()=>{b.disabled=true;b.style.opacity=.7},0)}});
addEventListener("pageshow",e=>{if(e.persisted)document.querySelectorAll("button[disabled]").forEach(b=>{b.disabled=false;b.style.opacity=""})});
