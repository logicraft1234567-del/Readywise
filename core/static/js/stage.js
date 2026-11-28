/* Product film player. The page ships a plain <video controls>; this swaps the native bar for a play button on the poster,
   then hands control back to the native bar once it starts so seeking, volume and full screen all work. */
document.querySelectorAll("[data-stage]").forEach(st=>{
  const v=st.querySelector("video"),b=st.querySelector("[data-stage-play]");if(!v||!b)return;
  v.controls=false;st.classList.add("ready");
  b.addEventListener("click",()=>{v.preload="auto";v.controls=true;st.classList.add("playing");v.play().catch(()=>{v.controls=true})});
  v.addEventListener("ended",()=>{v.controls=false;st.classList.remove("playing");v.load()});
});
