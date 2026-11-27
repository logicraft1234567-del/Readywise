/* Header search: type to find your interviews, prep tasks, reports and interviewers, or jump to any page. Press / or Ctrl+K to focus it; Up/Down to move, Enter to open, Esc to close. */
(() => {
  const box = document.getElementById("hs"), inp = document.getElementById("gsearch"), pop = document.getElementById("hs-list"); if (!box || !inp) return;
  const PAGES = [["Dashboard", "/dashboard/", "layout-dashboard", "home overview"], ["Calendar", "/calendar/", "calendar-days", "tasks schedule plan"], ["Analytics", "/analytics/", "chart-column", "progress skills score stats"],
    ["Interviewers", "/interviewers/", "users", "panel people"], ["Profile and CV", "/profile/", "user-round", "account cv resume settings"], ["How to use ReadyWise", "/guide/", "book-open", "help guide faq"], ["New interview", "/w/new/", "plus", "create start workspace"]];
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const mark = (s, q) => { s = esc(s); if (!q) return s; const i = s.toLowerCase().indexOf(esc(q).toLowerCase()); return i < 0 ? s : s.slice(0, i) + "<mark>" + s.slice(i, i + esc(q).length) + "</mark>" + s.slice(i + esc(q).length); };
  let items = [], at = -1, timer = 0, seq = 0;
  const open = o => { pop.hidden = !o; inp.setAttribute("aria-expanded", o); if (!o) at = -1; };
  function paint(groups, q) {
    items = []; let h = "";
    for (const g of groups) { h += `<div class="hs-g" role="presentation">${esc(g.label)}</div>`; for (const it of g.items) { h += `<a class="hs-i" role="option" id="hs-${items.length}" href="${esc(it.url)}" data-i="${items.length}"><span class="hs-ic"><i data-lucide="${esc(it.icon)}" width="16"></i></span><span class="hs-tx"><b>${mark(it.title, q)}</b><small>${mark(it.sub || "", q)}</small></span></a>`; items.push(it); } }
    if (!items.length) h = `<div class="hs-empty"><b>No matches for “${esc(q)}”</b><small>Try a company, a role, a task name or a skill.</small></div>`;
    pop.innerHTML = h; at = items.length ? 0 : -1; mv(0, true); if (window.lucide) lucide.createIcons(); open(true);
  }
  function mv(d, abs) { const els = pop.querySelectorAll(".hs-i"); if (!els.length) return; at = abs ? d : (at + d + els.length) % els.length; els.forEach((e, i) => { e.classList.toggle("on", i === at); e.setAttribute("aria-selected", i === at); }); inp.setAttribute("aria-activedescendant", "hs-" + at); els[at].scrollIntoView({ block: "nearest" }); }
  function pages(q) { const l = q.toLowerCase(); return PAGES.filter(p => !l || (p[0] + " " + p[3]).toLowerCase().includes(l)).slice(0, l ? 3 : 4).map(p => ({ icon: p[2], title: p[0], sub: "Go to page", url: p[1] })); }
  async function run() {
    const q = inp.value.trim(), me = ++seq;
    try {
      const r = await fetch("/search/?q=" + encodeURIComponent(q), { headers: { Accept: "application/json" }, credentials: "same-origin" }); if (!r.ok) throw 0; const d = await r.json(); if (me !== seq) return;
      const groups = d.groups.slice(); const pg = pages(q); if (pg.length) groups.push({ label: q ? "Pages" : "Go to", items: pg }); paint(groups, q);
    } catch (e) { if (me !== seq) return; const pg = pages(q); paint(pg.length ? [{ label: "Pages", items: pg }] : [], q); }
  }
  inp.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 160); });
  inp.addEventListener("focus", () => { if (!pop.hidden) return; run(); });
  inp.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (pop.hidden) run(); else mv(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mv(-1); }
    else if (e.key === "Enter") { const els = pop.querySelectorAll(".hs-i"); if (!pop.hidden && els[at]) { e.preventDefault(); location.href = els[at].getAttribute("href"); } }
    else if (e.key === "Escape") { if (!pop.hidden) { e.preventDefault(); open(false); } else inp.blur(); }
  });
  pop.addEventListener("mousemove", e => { const a = e.target.closest(".hs-i"); if (a) mv(+a.dataset.i, true); });
  pop.addEventListener("mousedown", e => e.preventDefault());   // keeps focus in the box so a click on a result still counts
  document.addEventListener("click", e => { if (!box.contains(e.target)) open(false); });
  document.addEventListener("keydown", e => {
    const typing = /^(input|textarea|select)$/i.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if ((e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) { e.preventDefault(); inp.focus(); inp.select(); }
  });
})();
