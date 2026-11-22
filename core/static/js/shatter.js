/* Click effect for the main buttons: the button cracks into irregular glass shards that fly outward and fall, then re-forms.
   window.rwShatter(button, {event, restoreAfter}) returns a promise that resolves when the button is back. Honors reduced motion.
   With {keepHidden: true} the button does NOT come back by itself: the caller shows something else in its place (the AI thinking animation)
   and calls rwShatter.restore(button) when the work is done, and the button re-forms then. */
(function () {
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function triangles(w, h) {
    const cols = Math.max(4, Math.round(w / 34)), rows = Math.max(2, Math.round(h / 22)), P = [];
    for (let r = 0; r <= rows; r++) { P.push([]); for (let c = 0; c <= cols; c++) { const edge = r === 0 || r === rows || c === 0 || c === cols; P[r].push([c / cols * w + (edge ? 0 : (Math.random() - .5) * w / cols * .8), r / rows * h + (edge ? 0 : (Math.random() - .5) * h / rows * .8)]); } }
    const out = [];
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const a = P[r][c], b = P[r][c + 1], d = P[r + 1][c], e = P[r + 1][c + 1];
      if ((r + c) % 2) out.push([a, b, d], [b, e, d]); else out.push([a, b, e], [a, e, d]);
    }
    return out;
  }
  window.rwShatter = function (btn, opts) {
    opts = opts || {};
    if (!btn || btn.dataset.shattering) return Promise.resolve();
    if (REDUCE) { btn.animate([{ opacity: 1 }, { opacity: .5 }, { opacity: 1 }], { duration: 200 }); return Promise.resolve(); }
    const r = btn.getBoundingClientRect(), w = r.width, h = r.height, cx = w / 2, cy = h / 2, restore = opts.restoreAfter == null ? 900 : opts.restoreAfter;
    const ex = opts.event && opts.event.clientX != null && opts.event.clientX > 0 ? opts.event.clientX - r.left : cx, ey = opts.event && opts.event.clientY != null && opts.event.clientY > 0 ? opts.event.clientY - r.top : cy;
    btn.dataset.shattering = "1";
    // impact flash where the button was hit
    const ring = document.createElement("i"); ring.style.cssText = `position:fixed;z-index:9998;left:${r.left + ex}px;top:${r.top + ey}px;width:30px;height:30px;margin:-15px 0 0 -15px;border-radius:50%;pointer-events:none;border:2px solid #2B44E8;box-shadow:0 0 0 6px rgba(43,68,232,.18)`;
    document.body.append(ring); ring.animate([{ transform: "scale(.3)", opacity: 1 }, { transform: "scale(4.2)", opacity: 0 }], { duration: 480, easing: "cubic-bezier(.2,.7,.3,1)" }).onfinish = () => ring.remove();
    const root = document.createElement("div"); root.className = "rw-shards"; root.style.cssText = "position:fixed;inset:0;z-index:9999;pointer-events:none;overflow:hidden"; document.body.append(root);
    triangles(w, h).forEach(t => {
      const s = btn.cloneNode(true); s.removeAttribute("id"); s.querySelectorAll("[id]").forEach(e => e.removeAttribute("id")); delete s.dataset.shattering; s.hidden = false;
      const mx = (t[0][0] + t[1][0] + t[2][0]) / 3, my = (t[0][1] + t[1][1] + t[2][1]) / 3, poly = t.map(p => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(",");
      s.style.cssText += `;position:fixed;left:${r.left}px;top:${r.top}px;width:${w}px;height:${h}px;margin:0;transform:none;animation:none;transition:none;pointer-events:none;clip-path:polygon(${poly});transform-origin:${mx}px ${my}px;visibility:visible;opacity:1`;
      root.append(s);
      const dx = mx - ex, dy = my - ey, len = Math.hypot(dx, dy) || 1, push = 70 + Math.random() * 230, tx = dx / len * push + (Math.random() - .5) * 60, ty = dy / len * push + 90 + Math.random() * 200, rot = (Math.random() - .5) * 620, dur = 700 + Math.random() * 380;
      s.animate([{ transform: "none", opacity: 1 }, { transform: `translate(${tx * .55}px,${ty * .3 - 34}px) rotate(${rot * .5}deg)`, opacity: 1, offset: .4 }, { transform: `translate(${tx}px,${ty}px) rotate(${rot}deg) scale(.45)`, opacity: 0 }], { duration: dur, easing: "cubic-bezier(.25,.6,.35,1)", fill: "forwards" });
    });
    btn._rwVis = btn.style.visibility; btn.style.visibility = "hidden"; setTimeout(() => root.remove(), 1300);
    if (opts.keepHidden) return new Promise(res => setTimeout(res, 700));   // resolves once most shards have flown; the button stays hidden until restore()
    return new Promise(res => setTimeout(() => { window.rwShatter.restore(btn); res(); }, restore));
  };
  window.rwShatter.restore = function (btn) {   // the button re-forms (safe to call at any time, also when it never shattered)
    if (!btn) return; const was = btn.style.visibility === "hidden" || btn.dataset.shattering;
    btn.style.visibility = btn._rwVis || ""; delete btn.dataset.shattering; delete btn._rwVis;
    if (was && !REDUCE) btn.animate([{ transform: "scale(.4)", opacity: 0 }, { transform: "scale(1.08)", opacity: 1, offset: .65 }, { transform: "none", opacity: 1 }], { duration: 460, easing: "cubic-bezier(.3,1.4,.5,1)" });
  };
})();
