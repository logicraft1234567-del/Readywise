/* Planner: draws task cards (plan page, calendar, bell panel, dashboard), ticks tasks off, shows the notification panel and the once-a-day popup.
   One source of truth: every card is drawn from the same task data by taskHTML(), so a tick shows everywhere at once. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const svg = (p, n = 14) => `<svg width="${n}" height="${n}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
  const I = {
    check: svg('<path d="M20 6 9 17l-5-5"/>', 15),
    lock: svg('<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>', 13),
    book: svg('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'),
    play: svg('<rect x="2" y="5" width="20" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/>'),
    flag: svg('<path d="M4 22V4M4 4h13l-2 4 2 4H4"/>'),
    x: svg('<path d="M18 6 6 18M6 6l12 12"/>', 16),
  };
  const store = {}, KIND = { learn: "Learn", practice: "Practise", mock: "Interview", review: "Review" };
  const today = () => document.body.dataset.today || "";
  const store_ = t => (store[t.id] = t);

  /* ----- one task card ----- */
  function tickBtn(t) {
    const can = (!t.done && t.can) || (t.done && t.due === today());
    const label = t.done ? (can ? "Mark as not done" : "Completed") : t.can ? "Mark as completed" : `Opens ${t.when}`;
    return `<button type="button" class="tick${t.done ? " on" : ""}" data-tick="${t.id}" ${can ? "" : "disabled"} aria-pressed="${t.done}" aria-label="${esc(label)}: ${esc(t.title)}" title="${esc(label)}">${t.done ? I.check : (!t.can ? I.lock : "")}</button>`;
  }
  function linksHTML(t) {
    const L = t.links || {}, a = (x, ic, word) => x ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${ic}<span class="l">${x.found ? `<small>${word}</small> ` : ""}${esc(x.label)}</span></a>` : "";
    let iv = "";
    if (L.interview) iv = t.can && !t.done ? `<button type="button" class="btn sm solid" data-start="${L.interview.workspace}">${I.flag}${esc(L.interview.label)}</button>` : t.done ? "" : `<span class="tk-lock">${I.lock}Interview opens ${esc(t.when)}</span>`;
    return `<div class="tk-links">${a(L.read, I.book, "Read")}${a(L.watch, I.play, "Watch")}${iv}</div>`;
  }
  function taskHTML(t, o = {}) {
    store_(t);
    const chips = [`<span class="chip">${esc(KIND[t.kind] || t.kind)}</span>`];
    if (o.showWs) chips.push(`<span class="chip">${esc(t.workspace)}</span>`);
    if (t.moved) chips.push(`<span class="chip warn">Moved from ${esc(t.moved.label)}</span>`);
    if (t.auto) chips.push(`<span class="chip soft">Added from your results</span>`);
    if (t.state === "later") chips.push(`<span class="chip">Opens ${esc(t.when)}</span>`);
    const body = o.msg ? `<p class="tk-msg">${esc(o.msg)}</p>` : (t.detail ? `<p class="tk-d">${esc(t.detail)}</p>` : "");
    return `<article class="tk ${t.state}${t.moved ? " moved" : ""}" data-card="${t.id}" data-compact="${o.compact ? 1 : 0}" data-showws="${o.showWs ? 1 : 0}" ${o.msg ? `data-msg="${esc(o.msg)}"` : ""}>${tickBtn(t)}<div class="tk-main"><div class="tk-t">${esc(t.title)}</div><div class="tk-meta">${chips.join("")}</div>${body}${linksHTML(t)}</div></article>`;
  }

  /* ----- ticking a task ----- */
  function rerender(id) {
    const t = store[id]; if (!t) return;
    $$(`[data-card="${id}"]`).forEach(el => {
      const tmp = document.createElement("div"); tmp.innerHTML = taskHTML(t, { compact: el.dataset.compact === "1", showWs: el.dataset.showws === "1", msg: el.dataset.msg });
      el.replaceWith(tmp.firstElementChild);
    });
    $$(`[data-pill="${id}"]`).forEach(p => { p.classList.toggle("done", t.done); p.classList.toggle("today", !t.done && t.state === "today" && !t.moved); });
  }
  async function toggle(id, btn) {
    btn.disabled = true;
    try {
      const d = await post(`/task/${id}/toggle/`), t = store[id];
      if (t) { t.done = d.done; t.state = d.done ? "done" : "today"; rerender(id); const nb = $(`[data-tick="${id}"]`); if (nb && d.done) nb.classList.add("pop"); }
      document.dispatchEvent(new CustomEvent("rw:task", { detail: d }));
      toast(d.done ? "Marked as completed." : "Task reopened.");
    } catch (e) { toast(e.message, true); btn.disabled = false; }
  }
  function startInterview(ws) {
    const f = document.createElement("form"); f.method = "post"; f.action = `/w/${ws}/session/`;
    const i = document.createElement("input"); i.type = "hidden"; i.name = "csrfmiddlewaretoken"; i.value = csrf(); f.appendChild(i); document.body.appendChild(f); f.submit();
  }
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-tick]"); if (b && !b.disabled) { toggle(b.dataset.tick, b); return; }
    const s = e.target.closest("[data-start]"); if (s) { s.disabled = true; startInterview(s.dataset.start); return; }
    const np = $("#notif"); if (np && !np.hidden && !e.target.closest(".np-wrap") && !e.target.closest("#rw-pop")) closePanel();
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") { closePanel(); const b = $("#bell"); if (b) b.focus(); } });

  /* ----- the plan page: counters follow every tick ----- */
  document.addEventListener("rw:task", e => {
    const d = e.detail || {}, box = $("#plan-list");
    if (box && String(box.dataset.ws) === String(d.workspace_id)) {
      const c = $("#plan-count"); if (c) c.textContent = `${d.done_count}/${d.total} tasks done`;
      const bar = $("#plan-bar"); if (bar && d.total) bar.style.width = Math.round(100 * d.done_count / d.total) + "%";
    }
    refresh();
  });
  function renderPlan() {
    const box = $("#plan-list"), data = $("#plan-data"); if (!box || !data) return;
    const tasks = JSON.parse(data.textContent || "[]");
    if (!tasks.length) { box.innerHTML = `<div class="plan-empty">No plan yet. Run research and choose a panel first for the best result, then generate.</div>`; return; }
    let out = "", cur = "";
    tasks.forEach(t => {
      if (t.due !== cur) { cur = t.due; const n = tasks.filter(x => x.due === cur); out += `${out ? "</div>" : ""}<h4 class="plan-day">${esc(t.when)}${t.when.length > 9 ? "" : ` <small>${esc(new Date(t.due + "T00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" }))}</small>`}<small>· ${n.filter(x => x.done).length}/${n.length} done</small></h4><div class="plan-list">`; }
      out += taskHTML(t);
    });
    box.innerHTML = out + "</div>";
  }

  /* ----- notifications: bell panel + once-a-day popup ----- */
  let last = null;
  const panel = () => $("#notif"), bell = () => $("#bell");
  function closePanel() { const p = panel(); if (p && !p.hidden) { p.hidden = true; bell().setAttribute("aria-expanded", "false"); } }
  function openPanel() { const p = panel(); p.hidden = false; bell().setAttribute("aria-expanded", "true"); const pop = $("#rw-pop"); if (pop) pop.hidden = true; }
  function noteHTML(it) {
    if (it.task) return taskHTML(it.task, { compact: true, showWs: true, msg: it.message });
    const a = it.type === "interview" ? `<a href="/w/${it.workspace_id}/#interview">Open the practice room</a>` : "";
    return `<article class="np-note ${esc(it.type)}"><b>${esc(it.title)}</b><p>${esc(it.message)}</p>${a}</article>`;
  }
  function render(d) {
    last = d;
    const bd = $("#bell-badge"); if (bd) { bd.textContent = d.count; bd.hidden = !d.count; }
    const side = $("#side-n"); if (side) { side.textContent = d.count; side.hidden = !d.count; }
    const tab = $("#tab-n"); if (tab) { tab.textContent = d.count; tab.hidden = !d.count; }
    const list = $("#np-list"); if (list) list.innerHTML = d.items.length ? d.items.map(noteHTML).join("") : `<div class="np-empty">Nothing to do right now. Your plan is clear.</div>`;
    const f = $("#focus-list");
    if (f) { const t = d.items.filter(i => i.task); f.innerHTML = t.length ? t.slice(0, 6).map(i => taskHTML(i.task, { compact: true, showWs: true, msg: i.message })).join("") : `<p class="text-sm" style="color:var(--mut)">All clear. Start a practice interview to keep your skills sharp.</p>`; }
  }
  async function refresh(first) {
    try { const r = await fetch("/notifications/", { headers: { Accept: "application/json" } }); if (!r.ok) return; const d = await r.json(); render(d); if (first) maybePopup(d); } catch (e) { }
  }
  function seenToday() { try { return localStorage.getItem("rw-pop-" + today()); } catch (e) { return "1"; } }
  function markSeen() { try { localStorage.setItem("rw-pop-" + today(), "1"); } catch (e) { } }
  function maybePopup(d) {
    const tasks = d.items.filter(i => i.task); if (!tasks.length || seenToday()) return; markSeen();
    const moved = tasks.filter(i => i.task.moved).length, pop = $("#rw-pop"); if (!pop) return;
    const title = moved ? `${moved} missed task${moved > 1 ? "s" : ""} moved to today` : `${tasks.length} task${tasks.length > 1 ? "s" : ""} for today`;
    pop.innerHTML = `<div class="pop-h"><b>${esc(title)}</b><button type="button" class="pop-x" data-pop-close aria-label="Dismiss">${I.x}</button></div><ul>${tasks.slice(0, 3).map(i => `<li data-pop-task="${i.task.id}">${tickBtn(i.task)}<span>${esc(i.task.title)}</span></li>`).join("")}</ul>${tasks.length > 3 ? `<p class="text-sm" style="color:var(--mut);margin-top:.5rem">and ${tasks.length - 3} more</p>` : ""}<div class="pop-a"><button type="button" class="btn sm solid" data-pop-open>See details</button><a class="btn sm" href="/calendar/">Open calendar</a></div>`;
    pop.hidden = false;
    try { if ("Notification" in window && Notification.permission === "granted" && document.hidden) new Notification("ReadyWise: " + title, { body: tasks.slice(0, 3).map(i => i.task.title).join("\n") }); } catch (e) { }
  }
  document.addEventListener("click", e => {
    if (e.target.closest("[data-pop-close]")) $("#rw-pop").hidden = true;
    if (e.target.closest("[data-pop-open]")) { $("#rw-pop").hidden = true; openPanel(); }
  });
  document.addEventListener("rw:task", e => {   // a tick inside the popup crosses the task out there too
    const d = e.detail || {}, li = $(`[data-pop-task="${d.id}"]`); if (!li) return; li.classList.toggle("done", !!d.done); const tb = $(".tick", li); if (tb) { tb.disabled = false; tb.classList.toggle("on", !!d.done); tb.innerHTML = d.done ? I.check : ""; }
  });

  document.addEventListener("DOMContentLoaded", () => {
    renderPlan();
    const b = bell(); if (!b) return;
    b.addEventListener("click", () => (panel().hidden ? openPanel() : closePanel()));
    const al = $("#np-alerts");
    if (al) {
      if (!("Notification" in window) || Notification.permission !== "default") al.hidden = true;
      al.addEventListener("click", async () => { try { const p = await Notification.requestPermission(); al.hidden = true; if (p === "granted") toast("Desktop alerts are on."); } catch (e) { } });
    }
    refresh(true);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
    setInterval(() => { if (!document.hidden) refresh(); }, 300000);
  });

  window.RW = { taskHTML, store, rerender, refresh, esc, I };
})();
