/* Workspace journey: switches between the five steps with animation, keeps the connected track, spark and "Next up" marker in sync,
   drives the sticky bar whose big button always does the right next thing, and celebrates a step the moment it is completed. */
(function () {
  const dataEl = document.getElementById("jn-data"); if (!dataEl) return;
  const D = JSON.parse(dataEl.textContent), $ = (s, r) => (r || document).querySelector(s), order = D.order, n = order.length;
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const panes = Object.fromEntries(order.map(id => [id, document.getElementById(id)]));
  const nodes = Object.fromEntries(order.map(id => [id, $(`.jn[data-id="${id}"]`)]));
  const track = $(".jn-track"), fill = $(".jn-fill"), spark = $(".jn-spark"), foot = $("#ws-foot"), go = $("#ft-go"), back = $("#ft-back"), mid = $("#ft-ln"), dots = $("#ft-dots");
  let cur = null, flying = false;
  const anim = (el, f, o) => REDUCE ? { onfinish: null, finished: Promise.resolve() } : el.animate(f, Object.assign({ fill: "both", easing: "cubic-bezier(.2,.8,.2,1)" }, o));
  const idxOf = id => order.indexOf(id);

  function burst() {
    if (REDUCE) return; const c = document.createElement("canvas"); c.style.cssText = "position:fixed;inset:0;z-index:80;pointer-events:none"; document.body.append(c);
    c.width = innerWidth; c.height = innerHeight; const x = c.getContext("2d"), cols = ["#2B44E8", "#6C7DF2", "#12805C", "#D98A0B", "#C93049", "#16203A"];
    const ps = Array.from({ length: 130 }, () => ({ x: innerWidth / 2, y: innerHeight * .35, vx: (Math.random() - .5) * 15, vy: -Math.random() * 13 - 3, s: Math.random() * 8 + 4, r: Math.random() * 6, vr: (Math.random() - .5) * .4, c: cols[Math.random() * cols.length | 0] }));
    let t = 0; (function f() { x.clearRect(0, 0, c.width, c.height); ps.forEach(p => { p.vy += .4; p.x += p.vx; p.y += p.vy; p.r += p.vr; x.save(); x.translate(p.x, p.y); x.rotate(p.r); x.fillStyle = p.c; x.fillRect(-p.s / 2, -p.s / 3, p.s, p.s * .6); x.restore(); }); if (++t < 120) requestAnimationFrame(f); else c.remove(); })();
  }
  function toast(t) { const e = document.createElement("div"); e.className = "jn-toast"; e.textContent = t; document.body.append(e); setTimeout(() => e.remove(), 3500); }

  // ---------- the track ----------
  const nextIdx = idxOf(D.next), allDone = D.done.length === n;
  fill.style.setProperty("--fill", (allDone ? 100 : Math.max(0, nextIdx) / (n - 1) * 100) + "%");
  nodes[D.next] && !allDone ? nodes[D.next].classList.add("next") : null;
  let sparkT = null;
  function moveSpark(i, first) { spark.style.transition = REDUCE ? "none" : "left .8s cubic-bezier(.5,0,.2,1), opacity .3s"; spark.style.left = (i / (n - 1) * 100) + "%"; if (first || REDUCE) return; spark.style.opacity = 1; clearTimeout(sparkT); sparkT = setTimeout(() => spark.style.opacity = 0, 900); }

  // ---------- the bar ----------
  function cta(id) {
    const i = idxOf(id), nx = order[i + 1];
    switch (id) {
      case "research": return D.researched ? { label: "Continue to the panel", short: "Meet the panel", mid: "Research is done. Now meet the people you'll face.", run: () => connect(id, nx) } : { label: "Run research", short: "Research", mid: "About two minutes: I read the web, forums, videos and social media for you.", run: b => window.rsStart && window.rsStart(b) };
      case "panel": return { label: "Looks good, build my plan", short: "Build my plan", mid: D.panel.length ? "Your panel: " + D.panel.join(", ") : "Your interviewers are chosen for you.", run: () => connect(id, nx) };
      case "plan": return D.has_tasks ? { label: "Start practising", short: "Practise", mid: "Tick tasks as you go. The plan adapts to your results.", run: () => connect(id, nx) } : { label: "Generate my plan", short: "Make plan", mid: "A day-by-day plan from your research and panel.", run: b => window.act && act(b, D.plan_url) };
      case "interview": return { label: "Enter the interview room", short: "Enter room", mid: "Camera and mic on. Take a breath, then go.", run: () => { const f = $("#interview form"); f && (f.requestSubmit ? f.requestSubmit() : f.submit()); } };
      default: return { label: "Practise again", short: "Again", mid: "Every session sharpens these scores.", run: () => connect(id, "interview") };
    }
  }
  function drawDots(id) {
    dots.innerHTML = ""; order.forEach((o, i) => { const d = document.createElement("i"); d.className = (D.done.includes(o) ? "done " : "") + (o === id ? "view" : ""); dots.append(d); if (i < n - 1) dots.append(document.createElement("b")); });
  }
  function updateBar(id) {
    const c = cta(id); const i = idxOf(id);
    let lbl = $("#ft-lbl"); if (!lbl) { go.innerHTML = '<span class="lbl" id="ft-lbl"></span><span class="ar" aria-hidden="true">\u2192</span>'; lbl = $("#ft-lbl"); }
    if (lbl.dataset.full !== c.label) { go.classList.remove("swap"); void go.offsetWidth; go.classList.add("swap"); }
    lbl.dataset.full = c.label; lbl.innerHTML = '<span class="bl"></span><span class="bs"></span>'; lbl.firstChild.textContent = c.label; lbl.lastChild.textContent = c.short || c.label; go.setAttribute("aria-label", c.label); mid.textContent = `Step ${i + 1} of ${n}. ${c.mid}`; back.hidden = i === 0; go.onclick = e => { if (go.dataset.shattering) return; window.rwShatter && rwShatter(go, { event: e, restoreAfter: 950 }); setTimeout(() => c.run(go), 230); }; drawDots(id);
  }
  back.onclick = () => { const i = idxOf(cur); if (i > 0) show(order[i - 1]); };

  // ---------- switching steps ----------
  function show(id, instant) {
    if (!panes[id] || id === cur) return; const dir = cur ? Math.sign(idxOf(id) - idxOf(cur)) || 1 : 0, old = cur && panes[cur];
    const enter = () => { Object.values(panes).forEach(p => p && p.classList.remove("on")); panes[id].classList.add("on"); if (dir && !instant) anim(panes[id], [{ opacity: 0, transform: `translateX(${dir * 46}px)` }, { opacity: 1, transform: "none" }], { duration: 520 }); window.lucide && lucide.createIcons(); document.querySelectorAll(".pane.on .bar>i[data-w]").forEach(b => { b.style.width = "0"; setTimeout(() => b.style.width = b.dataset.w + "%", 120); }); };
    if (old && !instant && !REDUCE) { const a = anim(old, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: `translateX(${-dir * 36}px)` }], { duration: 200, easing: "ease-in" }); a.onfinish = enter; } else enter();
    Object.entries(nodes).forEach(([k, el]) => el.classList.toggle("view", k === id));
    cur = id; moveSpark(idxOf(id), instant); updateBar(id); history.replaceState(null, "", "#" + id);
    foot.scrollIntoView && instant !== true && scrollTo({ top: 0, behavior: REDUCE ? "auto" : "smooth" });
  }
  // a spark flies from one step's dot to the next, the dot pops, then the page moves on.
  // The spark follows the dots' LIVE positions every frame, so it lands on the target even while the page is still scrolling back to the top
  // (it used to aim at where the dot was at the moment of the click, and missed it by hundreds of pixels).
  const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2, centre = el => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
  function settle(max) {   // resolves once the page has stopped scrolling, or after `max` ms
    return new Promise(res => { const t0 = performance.now(); let last = -1, still = 0; (function f(now) { const y = window.scrollY; still = y === last ? still + 1 : 0; last = y; if (still >= 3 || now - t0 > max) res(); else requestAnimationFrame(f); })(t0); });
  }
  function connect(from, to) {
    if (!to || flying) return show(to || from); const a = $(".jn-dot", nodes[from]), b = $(".jn-dot", nodes[to]);
    if (REDUCE || !a || !b) return show(to); flying = true; scrollTo({ top: 0, behavior: "smooth" });
    const guard = setTimeout(() => { flying = false; }, 4000);   // the lock can never stay on
    settle(700).then(() => {
      const f = document.createElement("i"); f.className = "fly"; let moved = false; const T0 = performance.now(), DUR = 760;
      (function tick(now) {
        const t = Math.min(1, Math.max(0, (now - T0) / DUR)), e = ease(t), [x1, y1] = centre(a), [x2, y2] = centre(b), arc = Math.sin(Math.PI * e);
        f.style.transform = `translate(${x1 + (x2 - x1) * e}px,${y1 + (y2 - y1) * e - arc * 46}px) scale(${.6 + arc * 1.0 + e * .2})`;
        if (!f.isConnected) document.body.append(f);
        if (!moved && t > .5) { moved = true; show(to); }
        if (t < 1) { requestAnimationFrame(tick); return; }
        f.remove(); nodes[to].classList.add("jn-pop"); setTimeout(() => nodes[to].classList.remove("jn-pop"), 950); flying = false; clearTimeout(guard);
      })(T0);
    });
  }
  order.forEach(id => $(".jn-btn", nodes[id]).onclick = () => show(id));

  // ---------- celebrate what was just completed ----------
  const key = "rw-journey-" + D.ws; let prev = null, celebrated = null;
  try { prev = JSON.parse(localStorage.getItem(key)); } catch (e) { }
  if (Array.isArray(prev)) { const fresh = D.done.filter(x => !prev.includes(x)); if (fresh.length) celebrated = fresh[0]; }
  try { localStorage.setItem(key, JSON.stringify(D.done)); } catch (e) { }

  const hash = location.hash.slice(1), start = panes[hash] ? hash : (celebrated || D.next);
  show(start, true);
  if (celebrated) setTimeout(() => { burst(); nodes[celebrated].classList.add("jn-pop"); setTimeout(() => nodes[celebrated].classList.remove("jn-pop"), 950); toast("✓ " + (D.labels[celebrated] || "Step") + " complete. Nice work!"); }, 500);
  window.rwJourney = { show, connect };
})();
