/* Cinematic landing engine: plays each scene when it enters view, replays it when you scroll back, keeps the scene rail,
   and eases the hero video as you scroll. Without JS a noscript rule in landing.html shows every scene in its final state. */
(() => {
  const root = document.querySelector("[data-cin]"); if (!root) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const scenes = [...root.querySelectorAll(".sc")];
  const rail = root.querySelector("[data-rail]");
  const seen = new Set();
  scenes.forEach(s => { if (!s.id || seen.has(s.dataset.sc)) return; seen.add(s.dataset.sc);
    const a = document.createElement("a"); a.href = "#" + s.id; a.innerHTML = `<i></i><span>${s.dataset.sc}</span>`; a.dataset.for = s.id; rail.appendChild(a); });
  const dots = [...rail.querySelectorAll("a")];
  if (reduce) { scenes.forEach(s => s.classList.add("in")); }
  else {
    const play = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) e.target.classList.add("in");
      else if (e.intersectionRatio === 0) e.target.classList.remove("in");   // fully off screen: reset so it plays again next time
    }), { threshold: [0, .3] });
    scenes.forEach(s => play.observe(s));
    requestAnimationFrame(() => document.getElementById("top").classList.add("in"));
  }
  const mark = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) dots.forEach(d => d.classList.toggle("on", d.dataset.for === e.target.id)); }), { rootMargin: "-45% 0px -45% 0px" });
  scenes.forEach(s => s.id && mark.observe(s));
  const hero = document.querySelector(".hero-bg video");
  if (hero && !reduce) {
    let tick = false;
    addEventListener("scroll", () => { if (tick) return; tick = true; requestAnimationFrame(() => { const y = Math.min(1, scrollY / innerHeight); hero.style.setProperty("--zoom", (1.04 + y * .12).toFixed(3)); hero.style.opacity = (.9 - y * .6).toFixed(2); tick = false; }); }, { passive: true });
  }
  if (reduce && hero) { hero.removeAttribute("autoplay"); hero.pause(); }
  if (window.lucide) lucide.createIcons();
})();
