/* Brand reveal. rwReveal({src, mark, tagline, onDone}).
   Plays the logo film full-screen, muted, once per session. Esc, Space, a click or Skip ends it early.
   If the video cannot start within 3 seconds, or the browser blocks autoplay, the page carries on at once. */
function rwReveal(o){
  o=o||{};
  const next=()=>{o.onDone&&o.onDone()};
  if(matchMedia("(prefers-reduced-motion: reduce)").matches||!o.src){next();return}
  const ov=document.createElement("div");ov.id="rw-reveal";ov.setAttribute("role","dialog");ov.setAttribute("aria-label","ReadyWise intro");
  ov.innerHTML='<video muted playsinline preload="auto" aria-hidden="true"></video><div class="rv-vig"></div><div class="rv-cap"><div class="lock"><img alt=""><span>ReadyWise</span></div><p></p></div><button type="button" class="rv-skip">Skip</button>';
  const v=ov.querySelector("video"),skip=ov.querySelector(".rv-skip");
  if(o.mark)ov.querySelector(".lock img").src=o.mark;else ov.querySelector(".lock img").remove();
  ov.querySelector(".rv-cap p").textContent=o.tagline||"";
  document.body.appendChild(ov);document.documentElement.style.overflow="hidden";
  let dead=false,started=false;const guard=setTimeout(()=>{if(!started)finish()},3000),cap=setTimeout(finish,9000);
  function finish(){if(dead)return;dead=true;clearTimeout(guard);clearTimeout(cap);removeEventListener("keydown",key);
    ov.classList.add("out");next();setTimeout(()=>{ov.remove();document.documentElement.style.overflow=""},900)}
  function key(e){if(e.key==="Escape"||e.key===" ")finish()}
  addEventListener("keydown",key);skip.onclick=finish;ov.onclick=e=>{if(e.target!==skip)finish()};
  v.addEventListener("playing",()=>{started=true;ov.classList.add("go")});
  v.addEventListener("ended",finish);v.addEventListener("error",finish);
  v.muted=true;v.src=o.src;
  const p=v.play();if(p&&p.catch)p.catch(finish);
  try{skip.focus({preventScroll:true})}catch(e){}
}
