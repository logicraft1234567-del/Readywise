/* ReadyWise guided flow engine. One question at a time, every step skippable unless it is truly required, with a living guide orb,
   word-by-word questions, reactions, a progress bar, confetti and a review screen. Real <form> inputs are filled at the end, so the server
   receives exactly the same fields as before. Config comes from the page (see welcome.html and ws_new.html). No external libraries. */
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isIcon = v => typeof v === "string" && /^[a-z][a-z-]*$/.test(v);
  const icon = v => isIcon(v) ? h("i", { "data-lucide": v, class: "ic" }) : (v || "");
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) { const v = attrs[k]; if (v == null || v === false) continue; if (k === "class") e.className = v; else if (k === "html") e.innerHTML = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? "" : v); }
    kids.flat().forEach(c => { if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c)); });
    return e;
  }
  const anim = (el, frames, opts) => REDUCE ? null : el.animate(frames, Object.assign({ fill: "both", easing: "cubic-bezier(.2,.8,.2,1)" }, opts));
  const PAL = [["#2f80ff", "#14c9c9", "#6aa0ff"], ["#7b5cff", "#38bdf8", "#e879f9"], ["#10b981", "#22d3ee", "#84cc16"], ["#ff7a45", "#ff3d8b", "#ffc247"], ["#6366f1", "#f5b942", "#8b5cf6"], ["#2dd4bf", "#a78bfa", "#60a5fa"]];
  const LINES = ["Take your time, there are no wrong answers.", "Short is fine. A few words is enough.", "Skip anything you are not sure about.", "You are doing great.", "The more real it is, the better your practice."];
  const REACT = ["Nice!", "Got it", "Perfect", "That helps", "Great", "Love it", "Thanks"];

  function confetti() {
    if (REDUCE) return;
    const c = h("canvas", { class: "wz-conf" }); document.body.append(c); c.width = innerWidth; c.height = innerHeight; const x = c.getContext("2d");
    const cols = ["#2B44E8", "#6C7DF2", "#12805C", "#D98A0B", "#C93049", "#16203A"];
    const ps = Array.from({ length: 150 }, () => ({ x: innerWidth / 2, y: innerHeight * .55, vx: (Math.random() - .5) * 17, vy: -Math.random() * 16 - 4, s: Math.random() * 9 + 4, r: Math.random() * 6, vr: (Math.random() - .5) * .4, c: cols[Math.random() * cols.length | 0] }));
    let t = 0; (function f() { x.clearRect(0, 0, c.width, c.height); ps.forEach(p => { p.vy += .42; p.x += p.vx; p.y += p.vy; p.r += p.vr; x.save(); x.translate(p.x, p.y); x.rotate(p.r); x.fillStyle = p.c; x.fillRect(-p.s / 2, -p.s / 3, p.s, p.s * .6); x.restore(); }); if (++t < 140) requestAnimationFrame(f); else c.remove(); })();
  }
  window.rwConfetti = confetti;

  // ---------- adaptive question helpers (pure, tested in tests/js/wizard.test.js) ----------
  function rwSegment(steps) { const from = steps.findIndex(x => x.adapt); if (from < 0) return { from: -1, to: -1 }; let to = from; while (to < steps.length && steps[to].adapt) to++; return { from, to }; }
  const STOPW = new Set("a an the and or of to in on for with at by from as is are was were be been it its this that these those you your yours me my we our could would can will please just so then than into about do does did have has had what which who how when where tell us more share give describe explain".split(" "));
  function rwMergePlan(steps, idx, d, A) {
    const seg = rwSegment(steps), kind = A.kind, rest = steps.slice(idx + 1, seg.to), byId = {};
    rest.filter(x => !(x.custom && !String(A[x.name] || "").trim())).forEach(x => { byId[x.id] = x; });   // an unanswered follow-up from an earlier plan is replaced by the new plan
    const ordered = []; (d.order || []).forEach(id => { if (byId[id]) { ordered.push(byId[id]); delete byId[id]; } });
    Object.values(byId).forEach(x => { if (x.req || x.custom) ordered.push(x); });                          // not mentioned = skipped, except required questions and answered follow-ups
    Object.keys(d.rewrite || {}).forEach(id => { const x = ordered.find(o => o.id === id); if (x && d.rewrite[id]) { x.q0 = x.q0 || x.q; x.q = d.rewrite[id]; } });
    const norm = t => String(t || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").split(/\s+/).filter(w => w.length > 1 && !STOPW.has(w)), docy = /\b(cv|resume|r[eé]sum[eé]|upload|attach|paste|pitch deck|job description|document)\b/i;
    const same = (a, b) => { const x = new Set(norm(a)), y = new Set(norm(b)); if (!x.size || !y.size) return false; let n = 0; x.forEach(w => { if (y.has(w)) n++; }); return n / (x.size + y.size - n) >= 0.5 || (n >= 3 && n / Math.min(x.size, y.size) >= 0.75); };
    const seenQ = [...steps.slice(0, idx + 1), ...ordered].flatMap(x => [x.q, x.q0, x.label]).filter(Boolean);   // everything already asked, or still to be asked: a follow-up never repeats it
    const fresh = (d.ask || []).filter(a => { const q = String((a && a.q) || ""); if (!q || docy.test(q) || seenQ.some(o => same(q, o))) return false; seenQ.push(q); return true; });
    const ref = steps[idx], adds = fresh.map(a => {
      const st = { id: a.key, name: kind + "__" + a.key, type: a.type || "text", label: a.short, q: a.q, eg: a.ph || "", chapter: ref && ref.chapter, custom: true, adapt: true };
      if (st.type === "select") st.options = (a.options || []).map(o => ({ value: o, label: o })); A[kind + "__xq" + a.key.slice(1)] = a.short; return st;
    });
    const first = adds[0] || ordered[0]; if (first && d.say && first.type !== "review") first.say = d.say;
    const out = [...steps.slice(0, idx + 1), ...adds, ...ordered, ...steps.slice(seg.to)], got = new Set();
    return out.filter(x => { if (!x.id || got.has(x.id)) return !x.id; got.add(x.id); return true; });   // whatever happens, a question appears once
  }
  window.rwMergePlan = rwMergePlan; window.rwSegment = rwSegment;

  window.RWWizard = function (cfg) {
    const root = $(cfg.root), form = $(cfg.form), A = Object.assign({}, cfg.values || {}), nodate = { v: !!A.__nodate };
    let steps = [], idx = 0, busy = false, thinking = false, typer = null, returnTo = null, palI = 0, afterRender = null, thinkTimer = null, watchdog = null;
    const first = () => (A.full_name || cfg.user || "").trim().split(/\s+/)[0] || "";
    const fmt = s => (s || "").replace(/\{name\}/g, first() || "there").replace(/\{kind\}/g, (cfg.kinds && cfg.kinds[A.kind] && cfg.kinds[A.kind].label || "interview").toLowerCase());
    const kindObj = () => cfg.kinds && cfg.kinds[A.kind];

    function build() {
      let s = cfg.kinds ? [...cfg.head, ...(kindObj() ? kindObj().steps : []), ...cfg.tail, ...(kindObj() && kindObj().docSteps ? kindObj().docSteps.map(x => Object.assign({}, x)) : [])] : [...cfg.steps];
      s.push(cfg.review ? { id: "review", type: "review" } : { id: "done", type: "done" });
      steps = s;
    }

    // ---------- skeleton ----------
    root.innerHTML = ""; let nav;
    const orb = h("div", { class: "orb" }, h("i", { class: "b b1" }), h("i", { class: "b b2" }), h("i", { class: "b b3" }), h("i", { class: "core" }));
    const bubbleT = h("span", { class: "t" }), bubble = h("div", { class: "wz-bubble", "aria-live": "polite" }, bubbleT, h("span", { class: "caret" }));
    const card = h("div", { class: "wz-card" }), bar = h("i"), lab1 = h("span"), lab2 = h("span");
    const skipAll = cfg.skipAll ? h("button", { class: "wz-skipall", type: "button", onclick: () => finish({ next: cfg.skipAll.next }) }, cfg.skipAll.label) : h("span");
    const back = h("button", { class: "wz-btn ghost", type: "button", onclick: () => move(-1) }, "← Back");
    const skip = h("button", { class: "wz-btn ghost", type: "button", onclick: () => {
      const s = steps[idx];
      if (required(s)) { refuseSkip(s); return; }   // an important question is never skipped: the guide says so and stays on it
      if (s.name) A[s.name] = ""; move(1, true);
    } }, "Skip");
    const shat = (btn, fn, e) => { window.rwShatter && rwShatter(btn, { event: e }); setTimeout(fn, 230); };  // the button shatters, then the next question arrives
    const go = h("button", { class: "wz-btn go", type: "button", onclick: e => { const s = steps[idx]; if (thinking) return; if (s.type !== "review" && !valid(s)) return; if (wantsAdapt(s)) next(e); else shat(go, () => next(e), e); } });
    // the AI thinking animation: it takes the place of the buttons from the moment the button shatters until the next question is ready
    const thinkTx = h("span", { class: "tx" }, "Thinking…");
    const think = h("div", { class: "wz-think", role: "status", "aria-live": "polite", hidden: true }, h("span", { class: "ring" }), h("span", { class: "dots" }, h("i"), h("i"), h("i")), thinkTx);
    const THINK = ["Reading your answer…", "Seeing what I already know…", "Choosing your next question…", "Almost there…"];
    const hint = h("div", { class: "wz-hint" });
    const dots = h("div", { class: "wz-bg" });
    for (let i = 0; i < 22; i++) dots.append(h("i", { class: "fl-dot", style: `--x:${Math.random() * 100}%;--s:${6 + Math.random() * 16}px;--d:${12 + Math.random() * 14}s;--dl:${-Math.random() * 20}s;--dx:${(Math.random() - .5) * 120}px` }));
    root.append(dots,
      h("header", { class: "wz-top" }, h("a", { class: "logo", href: cfg.home || "/" }, cfg.logo ? h("img", { src: cfg.logo, alt: "" }) : null, "ReadyWise"), h("div", { class: "wz-prog" }, h("div", { class: "lab" }, lab1, lab2), h("div", { class: "wz-bar" }, bar)), skipAll),
      h("main", { class: "wz-stage" }, h("div", { class: "wz-guide" }, orb, bubble), card),
      (nav = h("footer", { class: "wz-nav" }, back, skip, go, think, hint)));

    // ---------- helpers ----------
    function palette(s) {
      const k = kindObj(); const p = (s && s.pal) || (k && k.palette) || PAL[idx % PAL.length];
      [0, 1, 2].forEach(i => orb.style.setProperty("--c" + (i + 1), p[i])); root.style.setProperty("--c1", p[0]); root.style.setProperty("--c2", p[1]); root.style.setProperty("--c3", p[2]);
    }
    function say(text) {
      clearInterval(typer); bubbleT.textContent = ""; const t = fmt(text); if (!t) return; let i = 0;
      if (REDUCE) { bubbleT.textContent = t; return; }
      typer = setInterval(() => { bubbleT.textContent = t.slice(0, ++i); if (i >= t.length) clearInterval(typer); }, 16);
    }
    function talk() { orb.classList.remove("talk"); void orb.offsetWidth; orb.classList.add("talk"); }
    function react(near) {
      const r = near.getBoundingClientRect(), e = h("div", { class: "wz-react" }, REACT[Math.random() * REACT.length | 0]);
      e.style.left = Math.max(8, r.left + r.width / 2 - 40) + "px"; e.style.top = (r.top - 30) + "px"; document.body.append(e); setTimeout(() => e.remove(), 1500);
    }
    const val = s => (A[s.name] == null ? "" : String(A[s.name]));
    const required = s => !!s.req;
    const fileOf = s => { const i = s.file && form.querySelector(`input[type=file][name="${s.file}"]`); return i && i.files && i.files[0] ? i.files[0] : null; };
    const has = s => !!val(s).trim() || ((s.type === "doc" || s.type === "file") && !!fileOf(s));   // a required document is answered by pasted text OR a chosen file

    // ---------- step renderers ----------
    function words(text) { const q = h("h2", { class: "wz-q" }); fmt(text).split(/(\s+)/).forEach((w, i) => { if (!w) return; const sp = h("span", { class: "w" }, w); q.append(sp); if (!REDUCE && w.trim()) anim(sp, [{ opacity: 0, transform: "translateY(16px)" }, { opacity: 1, transform: "none" }], { duration: 480, delay: 120 + i * 22 }); }); return q; }
    function head(s) { return [s.chapter ? h("div", { class: "wz-chapter" }, s.chapter) : null, words(s.q), s.help ? h("p", { class: "wz-help" }, fmt(s.help)) : null]; }
    function example(s) { return s.eg ? h("div", { class: "wz-eg" }, h("b", {}, "e.g."), h("span", {}, s.eg)) : null; }
    const msg = h("div", { class: "wz-msg" });

    function rText(s, area) {
      const inp = h(area ? "textarea" : "input", { class: "wz-in", placeholder: s.ph || "", rows: area ? 4 : null, maxlength: s.max || (area ? 900 : 200), autocomplete: "off", "aria-label": s.q });
      inp.value = val(s);
      const cnt = h("div", { class: "wz-count" });
      const upd = () => { A[s.name] = inp.value; talk(); if (area) { inp.style.height = "auto"; inp.style.height = Math.min(inp.scrollHeight, 260) + "px"; cnt.textContent = inp.value.length + " / " + (s.max || 900); } };
      inp.addEventListener("input", () => { upd(); inp.classList.remove("wz-err"); msg.textContent = ""; });
      inp.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); next(); } });
      setTimeout(() => { inp.focus(); if (area) upd(); }, 420);
      return [h("div", { class: "wz-field" }, inp, area ? cnt : null, msg), example(s)];
    }
    function rSelect(s) {
      const chips = s.options.every(o => !o.desc && !o.icon);
      const wrap = h("div", { class: "wz-opts" + (chips ? " chips" : "") });
      s.options.forEach((o, i) => {
        const b = h("button", { type: "button", class: "wz-opt" + (chips ? " chip" : "") + (val(s) === o.value ? " sel" : ""), style: "--i:" + i },
          !chips ? h("div", { class: "oi" }, icon(o.icon) || "★") : null, h("b", {}, o.label), o.desc ? h("small", {}, o.desc) : null, h("span", { class: "ck" }, "✓"));
        tilt(b); b.onclick = () => { A[s.name] = o.value; wrap.querySelectorAll(".wz-opt").forEach(x => x.classList.toggle("sel", x === b)); talk(); if (s.auto !== false) setTimeout(() => next(), 420); };
        wrap.append(b);
      });
      return [h("div", { class: "wz-field" }, wrap, msg)];
    }
    function rKind(s) {
      const wrap = h("div", { class: "wz-opts kinds" });
      Object.keys(cfg.kinds).forEach((k, i) => {
        const o = cfg.kinds[k], b = h("button", { type: "button", class: "wz-opt" + (A.kind === k ? " sel" : ""), style: "--i:" + i }, h("div", { class: "oi" }, icon(o.icon) || o.emoji || "★"), h("b", {}, o.label), h("small", {}, o.blurb), h("span", { class: "ck" }, "✓"));
        tilt(b); b.onclick = () => {
          if (A.kind !== k) { A.kind = k; A.duration = o.duration; build(); }
          wrap.querySelectorAll(".wz-opt").forEach(x => x.classList.toggle("sel", x === b)); palette(); talk(); say(o.hello); setTimeout(() => next(), 520);
        };
        wrap.append(b);
      });
      return [h("div", { class: "wz-field" }, wrap, msg)];
    }
    function rTags(s) {
      const list = (A[s.name] || "").split(",").map(x => x.trim()).filter(Boolean), box = h("div", { class: "wz-tags" }), inp = h("input", { placeholder: list.length ? "" : (s.ph || "Type and press Enter"), "aria-label": s.q });
      const sync = () => { A[s.name] = list.join(", "); };
      const add = t => { t = t.trim().replace(/,$/, ""); if (!t || list.some(x => x.toLowerCase() === t.toLowerCase()) || list.length >= 30) return; list.push(t); sync(); draw(); talk(); };
      const draw = () => { box.querySelectorAll(".wz-tag").forEach(x => x.remove()); list.forEach((t, i) => box.insertBefore(h("span", { class: "wz-tag" }, t, h("button", { type: "button", "aria-label": "Remove " + t, onclick: () => { list.splice(i, 1); sync(); draw(); } }, "×")), inp)); inp.placeholder = list.length ? "" : (s.ph || "Type and press Enter"); };
      box.append(inp); box.onclick = () => inp.focus();
      inp.addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === ",") && !e.isComposing) { e.preventDefault(); if (inp.value.trim()) { add(inp.value); inp.value = ""; } else if (e.key === "Enter") next(); } else if (e.key === "Backspace" && !inp.value && list.length) { list.pop(); sync(); draw(); } });
      inp.addEventListener("blur", () => { if (inp.value.trim()) { add(inp.value); inp.value = ""; } });
      const sg = h("div", { class: "wz-sugg" }, (s.suggest || []).map(t => h("button", { type: "button", onclick: () => add(t) }, "+ " + t)));
      draw(); setTimeout(() => inp.focus(), 420);
      return [h("div", { class: "wz-field" }, box, sg, msg), example(s)];
    }
    function fileBox(name, accept, label, onfile) {
      let input = form.querySelector(`input[type=file][name="${name}"]`); const out = h("div"); if (!input && name) { input = h("input", { type: "file", name, accept: accept || ".pdf,.docx,.txt" }); form.append(input); } if (!input) return h("p", { class: "wz-help" }, "File upload is not available here.");
      const show = () => { out.innerHTML = ""; if (input.files && input.files[0]) out.append(h("div", { class: "wz-file" }, h("span", {}, "File:"), h("b", {}, input.files[0].name), h("button", { type: "button", onclick: () => { input.value = ""; show(); } }, "Remove"))); };
      const drop = h("button", { type: "button", class: "wz-drop", onclick: () => input.click() }, h("div", { class: "big" }, "⬆"), h("b", {}, label || "Drop a file here, or click to choose"), h("small", { style: "color:var(--mut)" }, "PDF, Word or text"));
      ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
      ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
      drop.addEventListener("drop", e => { if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; show(); talk(); onfile && input.files[0] && onfile(input.files[0]); } });
      input.onchange = () => { show(); talk(); onfile && input.files[0] && onfile(input.files[0]); }; show();
      return h("div", {}, drop, out);
    }
    function rFile(s) { return [h("div", { class: "wz-field" }, fileBox(s.file, s.accept, s.dropLabel))]; }
    function rDoc(s) {
      const ta = h("textarea", { class: "wz-in", rows: 5, placeholder: s.ph || "", maxlength: 6000 }); ta.value = val(s);
      const status = h("div", { class: "wz-read" });
      let good = ta.value;   // the last text that was pasted (or read from a file): typing is undone back to it
      const OK = /^(insertFromPaste|insertFromDrop|delete|history)/;
      ta.addEventListener("input", e => {
        if (s.pasteOnly && e.inputType && !OK.test(e.inputType)) { ta.value = good; msg.textContent = PASTE_MSG; return; }   // a keyboard that slipped past beforeinput (some phones)
        good = ta.value; A[s.name] = ta.value; talk(); ta.classList.remove("wz-err"); msg.textContent = "";
      });
      const PASTE_MSG = "Typing is switched off here. Copy your CV and paste it in (Ctrl+V, or the Paste button).";
      if (s.pasteOnly) {
        ta.addEventListener("beforeinput", e => { if (e.inputType && !OK.test(e.inputType)) { e.preventDefault(); msg.textContent = PASTE_MSG; ta.classList.remove("wz-err"); void ta.offsetWidth; ta.classList.add("wz-err"); } });
        ta.addEventListener("keydown", e => { if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); msg.textContent = PASTE_MSG; } else if (e.key === "Enter") { e.stopPropagation(); e.preventDefault(); next(); } });
        ta.addEventListener("drop", e => e.preventDefault());
        ta.setAttribute("autocapitalize", "off"); ta.setAttribute("autocorrect", "off"); ta.setAttribute("spellcheck", "false");
      }
      // a chosen file is read by the server and its text is put in the box: the guide sees it and the person can check and fix what was read
      const read = async f => {
        if (!cfg.docUrl) return; status.className = "wz-read busy"; status.textContent = "Reading " + f.name + "…"; ta.classList.remove("wz-err"); msg.textContent = "";
        try {
          const fd = new FormData(); fd.append("file", f); const r = await fetch(cfg.docUrl, { method: "POST", headers: { "X-CSRFToken": token() }, body: fd }), d = await r.json().catch(() => ({}));
          if (!r.ok || !d.text) throw new Error(d.error || "I could not read that file.");
          ta.value = d.text; good = d.text; A[s.name] = d.text; status.className = "wz-read ok"; status.textContent = "Read it. I put the text above so you can check it" + (d.truncated ? " (the first part, it was long)." : ".");
        } catch (e) { status.className = "wz-read bad"; status.textContent = (e && e.message) || "I could not read that file."; }
      };
      const pasteBtn = s.pasteOnly ? h("button", { type: "button", class: "wz-btn ghost", style: "margin:.6rem 0 0", onclick: async () => {
        try { const t = (await navigator.clipboard.readText()) || ""; if (!t.trim()) { msg.textContent = "Your clipboard is empty. Copy your CV first, then paste."; return; } ta.value = t.slice(0, 6000); good = ta.value; A[s.name] = good; talk(); ta.classList.remove("wz-err"); msg.textContent = ""; }
        catch (e) { msg.textContent = "Your browser blocked the Paste button. Click in the box and press Ctrl+V (or Cmd+V) instead."; ta.focus(); }
      } }, "Paste from clipboard") : null;
      return [h("div", { class: "wz-field" }, ta, pasteBtn, msg, h("p", { class: "wz-help", style: "margin:.9rem 0 .5rem" }, "Or upload it instead:"), fileBox(s.file, s.accept, s.dropLabel, read), status), example(s)];
    }
    function applyDocs(s, d) {   // the quick check found these documents: ask for each one, right after the main document
      s.ready = true; s.docs = (d && d.docs) || []; s.src = d && d.source; const kd = kindObj() || {};
      A.docs_manifest = JSON.stringify(s.docs.map(x => ({ key: x.key, label: x.label, why: x.why, must: x.must })));
      for (let i = steps.length - 1; i >= 0; i--) if (steps[i].dyn) steps.splice(i, 1);
      const dyn = s.docs.map(x => ({ id: "xd_" + x.key, dyn: true, name: A.kind + "__doc_" + x.key, file: "xdoc_" + x.key, type: "doc", accept: ".pdf,.docx,.txt", chapter: s.chapter, label: x.label, q: "Do you have your " + x.label.toLowerCase() + "?",
        help: (x.why ? x.why + " " : "") + "Paste the text or upload it. No problem if you do not have it yet: skip it and add it later from your workspace.", ph: "Paste the text here, or upload a file below.", dropLabel: "Drop a file here, or click to choose", eg: "" }));
      const at = steps.findIndex(x => x.id === kd.docKey); steps.splice(at >= 0 ? at + 1 : idx + 1, 0, ...dyn);
    }
    function rResearch(s) {
      const status = h("div", { class: "wz-scan-s busy" }), list = h("div", { class: "wz-scan-l" }), wrap = h("div", { class: "wz-scan" }, status, list);
      const co = (A[s.company] || "").trim() || "this organisation";
      const show = () => {
        const n = s.docs.length; status.className = "wz-scan-s ok";
        status.textContent = n ? `I found ${n} document${n > 1 ? "s" : ""} this interview usually expects${s.src === "web" ? ", checked online" : ""}. I'll ask for the main one first.` : "Nothing extra is needed for this one. We can carry on.";
        list.innerHTML = ""; s.docs.forEach(d => list.append(h("div", { class: "wz-doc" }, h("div", {}, h("b", {}, d.label), d.must ? h("span", { class: "chip" }, "Usually required") : null), d.why ? h("small", {}, d.why) : null)));
        go.disabled = false; talk();
      };
      if (s.ready) { show(); return [wrap]; }
      go.disabled = true; const msgs = [`Looking up what ${co} asks applicants for…`, "Checking the official guidance…", "Choosing what matters most…"]; let i = 0; status.textContent = msgs[0];
      const t = setInterval(() => { if (!card.contains(status) || s.ready) { clearInterval(t); return; } status.textContent = msgs[Math.min(++i, msgs.length - 1)]; }, 1400);
      const body = { kind: A.kind, company: A[s.company] || "", position: A[s.position] || "", jd: A[A.kind + "__jd"] || "" };
      fetch(cfg.docsUrl, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": token() }, body: JSON.stringify(body) })
        .then(r => r.json()).then(d => d && !d.error ? d : { docs: [], source: "default" }).catch(() => ({ docs: [], source: "default" }))
        .then(d => { clearInterval(t); applyDocs(s, d); if (steps[idx] === s && card.contains(status)) show(); });
      return [wrap];
    }
    function rRange(s) {
      const big = h("div", { class: "wz-big" }), r = h("input", { type: "range", class: "wz-range", min: s.min, max: s.max, step: s.step || 1 }), pre = h("div", { class: "wz-presets" });
      r.value = A[s.name] || s.def || s.min;
      const set = v => { A[s.name] = String(v); r.value = v; big.innerHTML = v + "<small>" + (s.unit || "") + "</small>"; pre.querySelectorAll("button").forEach(b => b.classList.toggle("sel", b.dataset.v === String(v))); talk(); };
      (s.presets || []).forEach(p => pre.append(h("button", { type: "button", "data-v": p, onclick: () => set(p) }, p + (s.unit || ""))));
      r.oninput = () => set(+r.value); set(+r.value);
      return [h("div", { class: "wz-field" }, big, r, pre)];
    }
    function rDate(s) {
      const d = h("input", { type: "date", class: "wz-in" }); d.value = A.date || ""; d.oninput = () => { A.date = d.value; talk(); };
      const pd = h("div", { class: "wz-presets", style: "margin-top:.9rem" }), tg = h("div", { class: "wz-toggle" + (nodate.v ? " on" : ""), role: "switch", tabindex: 0 }, h("i"), h("span", {}, "I don't have a date yet, just help me prepare"));
      const upd = () => { pd.style.display = nodate.v ? "" : "none"; d.style.display = nodate.v ? "none" : ""; tg.classList.toggle("on", nodate.v); if (nodate.v) A.date = ""; };
      [3, 7, 14, 30].forEach(n => pd.append(h("button", { type: "button", "data-v": n, class: String(A.prep_days || 7) === String(n) ? "sel" : "", onclick: () => { A.prep_days = String(n); pd.querySelectorAll("button").forEach(b => b.classList.toggle("sel", b.dataset.v == n)); talk(); } }, n + " days")));
      tg.onclick = () => { nodate.v = !nodate.v; A.__nodate = nodate.v; upd(); talk(); }; tg.onkeydown = e => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); tg.click(); } };
      if (!A.prep_days) A.prep_days = "7"; upd();
      return [h("div", { class: "wz-field" }, d, pd, tg)];
    }
    function rReview(s) {
      const rows = steps.filter(x => x.name && x.label && !["file", "doc"].includes(x.type) || x.type === "doc");
      const list = h("div", { class: "wz-rev" });
      rows.forEach((x, i) => { const v = x.type === "date" ? (A.date || (A.prep_days ? "No date, prepare over " + A.prep_days + " days" : "")) : (x.type === "select" || x.type === "kind") ? ((x.options || []).find(o => o.value === A[x.name]) || {}).label || (x.type === "kind" ? (kindObj() || {}).label : "") || "" : x.type === "doc" ? (val(x).trim() ? val(x).trim().replace(/\s+/g, " ").slice(0, 140) + (val(x).trim().length > 140 ? "…" : "") : (fileOf(x) ? "File: " + fileOf(x).name : "")) : val(x);
        const si = steps.indexOf(x); list.append(h("button", { type: "button", class: "wz-ri" + (v ? "" : " skipped"), style: "--i:" + i, onclick: () => { returnTo = steps.length - 1; jump(si); } }, h("span", { class: "k" }, x.label), h("span", { class: "v" }, v || "Skipped"), h("span", { class: "ed" }, v ? "Edit" : "Add"))); });
      const plan = kindObj() && kindObj().plan;
      return [h("div", { class: "wz-field" }, list), plan ? h("div", { class: "wz-next" }, h("b", {}, "Next, I'll research:"), plan.map(p => h("span", { class: "chip" }, p))) : null];
    }
    function tilt(b) { b.addEventListener("mousemove", e => { const r = b.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height; b.style.setProperty("--mx", x * 100 + "%"); b.style.setProperty("--my", y * 100 + "%"); });  }

    function intro(s) {
      return h("div", { class: "wz-intro" }, ...head(s), h("div", { class: "acts" }, h("button", { type: "button", class: "wz-btn go", onclick: e => shat(e.currentTarget, () => next(), e) }, s.cta || "Let's go", h("span", { class: "ar" }, "→")), cfg.skipAll ? h("button", { type: "button", class: "wz-btn ghost", onclick: () => finish({ next: cfg.skipAll.next }) }, cfg.skipAll.label) : null));
    }
    function done(s) {
      confetti(); const acts = h("div", { class: "acts" });
      (cfg.finish.buttons || []).forEach(b => acts.append(h("button", { type: "button", class: "wz-btn " + (b.primary ? "go" : "ghost"), onclick: e => b.primary ? shat(e.currentTarget, () => finish({ next: b.next }), e) : finish({ next: b.next }) }, b.label)));
      return h("div", { class: "wz-done" }, words(cfg.finish.title), h("p", { class: "wz-help" }, fmt(cfg.finish.text)), acts);
    }

    // ---------- flow ----------
    function render(dir) {
      const s = steps[idx]; palette(s); msg.textContent = ""; go.disabled = false;
      card.innerHTML = ""; const type = s.type;
      if (type === "intro") card.append(intro(s));
      else if (type === "done") card.append(done(s));
      else {
        const body = { text: () => rText(s, false), textarea: () => rText(s, true), select: () => rSelect(s), kind: () => rKind(s), tags: () => rTags(s), file: () => rFile(s), doc: () => rDoc(s), range: () => rRange(s), date: () => rDate(s), review: () => rReview(s), research: () => rResearch(s) }[type]();
        card.append(...[...head(s), ...body].filter(Boolean));
      }
      const total = steps.length - 1, shown = Math.min(idx, total);
      bar.style.width = ((cfg.kinds && !kindObj()) ? 6 : (total ? shown / total * 100 : 100)) + "%"; lab1.textContent = type === "done" ? "All done" : type === "review" ? "Last look" : type === "intro" ? "Getting started" : (cfg.kinds && !kindObj()) ? "Choose your interview" : "Question " + (idx - (cfg.kinds ? 1 : 0)) + " of " + (total - 1 - (cfg.kinds ? 1 : 0)); lab2.textContent = ((cfg.kinds && !kindObj()) ? 6 : Math.round(shown / Math.max(total, 1) * 100)) + "%";
      const mid = idx === Math.floor(total / 2) && !s.say && !["intro", "done", "review"].includes(type);
      say(s.say || (mid ? "Halfway there. You're doing great." : type === "review" ? "Here's everything. Tap anything to change it." : type === "done" ? "" : LINES[idx % LINES.length]));
      const isIntro = type === "intro", isDone = type === "done", isReview = type === "review";
      back.hidden = idx === 0 || isDone; skip.hidden = isIntro || isDone || isReview || s.noSkip; go.hidden = isIntro || isDone || (select(type) && s.auto !== false);
      go.innerHTML = ""; go.append(isReview ? cfg.review.button : (s.next || (idx === total - 1 ? "Finish" : "Continue")), h("span", { class: "ar" }, "→"));
      hint.innerHTML = ["text", "textarea", "tags", "doc"].includes(type) ? "Press <kbd>Enter</kbd> to continue" + (type === "textarea" ? " · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line" : "") : "";
      if (dir && !REDUCE) anim(card, [{ opacity: 0, transform: `translateX(${dir * 46}px) scale(.98)` }, { opacity: 1, transform: "none" }], { duration: 520 });
      busy = false; talk();
      if (afterRender) { const f = afterRender; afterRender = null; f(); }
    }
    const select = t => t === "select" || t === "kind";
    function refuseSkip(s) {
      const why = (s.reqMsg || "I need this one to do a good job.").replace(/\s+$/, ""), t = "This one is important, so I can't skip it. " + why;
      msg.textContent = t; say(t); talk();
      const el = card.querySelector(".wz-in,.wz-tags,.wz-opts"); if (el) { el.classList.remove("wz-err"); void el.offsetWidth; el.classList.add("wz-err"); if (el.focus && el.tagName !== "DIV") el.focus(); }
      anim(skip, [{ transform: "translateX(0)" }, { transform: "translateX(-6px)" }, { transform: "translateX(6px)" }, { transform: "translateX(0)" }], { duration: 300 });
    }
    function valid(s) {
      if (!required(s) || !s.name) return true;
      const short = !!s.minLen && !fileOf(s) && val(s).trim().length > 0 && val(s).trim().length < s.minLen;
      const ok = has(s) && !short; if (!ok) { const el = card.querySelector(".wz-in,.wz-tags"); if (el) { el.classList.remove("wz-err"); void el.offsetWidth; el.classList.add("wz-err"); el.focus && el.focus(); } msg.textContent = short ? "That looks too short to be your whole CV. Paste all of it." : (s.reqMsg || "I need this one to do a good job. A few words is enough."); }
      return ok;
    }
    function jump(i) { if (busy) return; busy = true; const dir = i > idx ? 1 : -1; leave(dir, () => { idx = i; render(dir); }); }
    function leave(dir, cb) { const a = anim(card, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: `translateX(${-dir * 40}px) scale(.98)` }], { duration: 220, easing: "ease-in" }); a ? (a.onfinish = cb) : cb(); }
    function next(ev) {
      const s = steps[idx]; if (thinking) return; if (s.type === "review") return finish({}); if (s.type === "research") { if (s.ready) move(1); return; } if (!valid(s)) return;
      if (s.name && has(s) && ![ "intro", "done" ].includes(s.type)) react(go.hidden ? card : go);
      if (wantsAdapt(s)) { think_(ev); return; }   // the guide decides what to ask next from what was just said
      move(1);
    }
    // ---------- adaptive questions: skip what is already covered, reword, add a follow-up, reorder ----------
    const token = () => ((document.cookie.split("; ").find(c => c.startsWith("csrftoken=")) || "").split("=")[1]) || ($("[name=csrfmiddlewaretoken]", form) || {}).value || "";
    const segment = () => rwSegment(steps);
    function planRequest() {   // what to ask the guide, or null when there is nothing to adapt after this step
      if (!cfg.adaptUrl) return null; const seg = segment(); if (seg.from < 0 || idx < seg.from || idx >= seg.to) return null;
      const answers = {}; steps.forEach((x, i) => { if (x.adapt && i <= idx && x.name && !x.custom) answers[x.id] = A[x.name] || ""; });
      const remaining = []; for (let i = idx + 1; i < seg.to; i++) if (steps[i].adapt && !steps[i].custom) remaining.push(steps[i].id);
      if (!remaining.length && steps.filter(x => x.custom).length >= 6) return null;
      const custom = steps.filter(x => x.custom).map(x => ({ key: x.id, q: x.q, answered: !!(A[x.name] || "").trim() }));
      return { kind: A.kind, answers, remaining, custom };
    }
    const wantsAdapt = s => !!(cfg.adaptUrl && s && s.adapt && returnTo == null && planRequest());
    async function adapt() {   // asks the guide; any trouble (slow, busy, rate limited, offline) just means the normal order carries on
      const body = planRequest(); if (!body) return; const ctl = new AbortController(), to = setTimeout(() => ctl.abort(), 6000);
      try {
        const r = await fetch(cfg.adaptUrl, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": token() }, body: JSON.stringify(body), signal: ctl.signal });
        const d = await r.json().catch(() => null); if (r.ok && d && !d.error && !d.fallback) applyPlan(d);
      } catch (e) { /* no answer in time: carry on with the normal order */ }
      finally { clearTimeout(to); }
    }
    function showThinking() {
      clearInterval(thinkTimer); let i = 0; thinkTx.textContent = THINK[0]; think.hidden = false; nav.classList.add("is-thinking"); card.classList.add("wz-wait"); orb.classList.add("think");
      thinkTimer = setInterval(() => { i = Math.min(i + 1, THINK.length - 1); thinkTx.textContent = THINK[i]; }, 900);
    }
    function hideThinking() {   // the buttons come back, re-forming, now that the next question is on screen
      clearInterval(thinkTimer); clearTimeout(watchdog); think.hidden = true; nav.classList.remove("is-thinking"); card.classList.remove("wz-wait"); orb.classList.remove("think"); thinking = false; go.disabled = false;
      window.rwShatter && rwShatter.restore(go); [back, skip].forEach(b => { if (!b.hidden) anim(b, [{ opacity: 0, transform: "scale(.85)" }, { opacity: 1, transform: "none" }], { duration: 420 }); });
    }
    async function think_(ev) {
      thinking = true; const t0 = Date.now(), here = idx;
      if (!go.hidden && window.rwShatter) rwShatter(go, { event: ev, keepHidden: true });   // the button shatters and does NOT come back yet
      showThinking(); say("Let me think about that…"); talk();
      watchdog = setTimeout(() => { afterRender = null; hideThinking(); }, 8000);          // whatever happens, the buttons always come back
      try { await adapt(); } catch (e) { /* ignored: the normal order carries on */ }
      const rest = (REDUCE ? 0 : 450) - (Date.now() - t0); if (rest > 0) await new Promise(r => setTimeout(r, rest));   // long enough to see it think, and for the shards to clear
      if (idx !== here) { hideThinking(); return; }                                          // the person moved on in the meantime
      afterRender = hideThinking; move(1); if (!busy) { afterRender = null; hideThinking(); }
    }
    function applyPlan(d) { const next = rwMergePlan(steps, idx, d, A); steps.splice(0, steps.length, ...next); }
    function move(d, skipped) {
      if (busy) return; const s = steps[idx]; if (d > 0 && !skipped && !valid(s)) return;
      let t = idx + d; if (returnTo != null && d > 0) { t = returnTo; returnTo = null; }
      t = Math.max(0, Math.min(steps.length - 1, t)); if (t === idx) return; jump(t);
    }
    function finish(extra) {
      const miss = steps.findIndex(s => required(s) && !has(s)); if (miss >= 0 && !(extra && extra.next && cfg.skipAll && extra.next === cfg.skipAll.next)) { returnTo = steps.length - 1; jump(miss); return; }
      const box = $("#wz-hidden", form) || form; box.innerHTML = "";
      Object.keys(A).forEach(k => { if (k.startsWith("__") || A[k] === "" || A[k] == null) return; box.append(h("input", { type: "hidden", name: k, value: A[k] })); });
      Object.keys(extra || {}).forEach(k => box.append(h("input", { type: "hidden", name: k, value: extra[k] })));
      launch(); setTimeout(() => form.submit(), REDUCE ? 0 : 900);
    }
    function launch() {
      const lines = cfg.launch || ["Saving everything…", "Getting things ready…"], p = h("p", {}, lines[0]);
      const k = kindObj(), pal = (k && k.palette) || PAL[0];
      const o = h("div", { class: "orb", style: `--c1:${pal[0]};--c2:${pal[1]};--c3:${pal[2]}` }, h("i", { class: "b b1" }), h("i", { class: "b b2" }), h("i", { class: "b b3" }), h("i", { class: "core" }));
      const el = h("div", { class: "wz-launch" }, h("div", {}, o, h("h2", {}, cfg.launchTitle || "One moment"), p)); document.body.append(el); let i = 0; setInterval(() => { p.textContent = lines[++i % lines.length]; }, 1800);
    }
    document.addEventListener("keydown", e => {
      if (e.key !== "Enter" || e.isComposing || e.defaultPrevented) return; const t = e.target, s = steps[idx];
      if (t.tagName === "BUTTON" || t.tagName === "TEXTAREA" || t.tagName === "INPUT" || !s) return; if (["intro", "review", "text", "textarea", "tags", "doc", "range", "date", "file"].includes(s.type)) { e.preventDefault(); next(); }
    });

    build(); const k0 = cfg.kinds && A.kind && cfg.kinds[A.kind]; if (cfg.kinds && !k0) delete A.kind;
    idx = k0 && cfg.startAfterKind ? cfg.head.length : 0; palette(steps[idx]); render(0);
    if (!REDUCE) anim(card, [{ opacity: 0, transform: "translateY(30px) scale(.97)" }, { opacity: 1, transform: "none" }], { duration: 700 });
    return { answers: A, go: i => jump(i) };
  };
})();
