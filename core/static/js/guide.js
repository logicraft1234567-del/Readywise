/* Highlights the current section in the guide's table of contents. */
document.addEventListener("DOMContentLoaded",()=>{const links=[...document.querySelectorAll(".gd-toc a")];if(!links.length||!("IntersectionObserver" in window))return;const map=new Map(links.map(a=>[a.getAttribute("href").slice(1),a]));
const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){links.forEach(l=>l.classList.remove("on"));const a=map.get(e.target.id);a&&a.classList.add("on")}})},{rootMargin:"-20% 0px -70% 0px"});
map.forEach((a,id)=>{const s=document.getElementById(id);s&&io.observe(s)})});
