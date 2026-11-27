/* Header search: type to find your interviews, prep tasks, reports and interviewers (server), and jump to any page (local).
   Up/Down to move, Enter to open, Esc to close, "/" or Ctrl/Cmd+K to focus. */
(() => {
  const inp = document.getElementById("gsearch"), box = document.getElementById("srch"); if (!inp || !box) return;
  const PAGES = [
    ["Dashboard", "Today's focus and your interviews", "/dashboard/", "layout-dashboard", "home overview"],
    ["Analysis", "Scores, skills and progress", "/analysis/", "chart-column", "progress charts skills score stats"],
    ["Tasks", "Everything to do to get ready", "/tasks/", "list-checks", "todo due prep homework"],
    ["Calendar", "Your interview dates", "/calendar/", "calendar-days", "schedule dates interview day"],
    ["Interviewers", "Browse and create interviewers", "/interviewers/", "users", "panel people"],
    ["Profile and CV", "Your details and CV", "/profile/", "user-round", "account cv resume settings"],
    ["New interview", "Start a new workspace", "/w/new/", "plus", "create add start"],
    ["How to use ReadyWise", "A short guide", "/guide/", "book-open", "help guide tutorial"]];
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const mark = (s, q) => { const t = esc(s); if (!q) return t; const i = String(s).toLowerCase().indexOf(q.toLowerCase()); if (i < 0) return t;
    return esc(String(s).slice(0, i)) + "<mark>" + esc(String(s).slice(i, i + q.length)) + "</mark>" + esc(String(s).slice(i + q.length)); };
  let items = [], sel = -1, seq = 0, timer = 0;
  const open = o => { box.hidden = !o; inp.setAttribute("aria-expanded", o); };
  function paint(groups, q) {
    items = []; let h = "";
    groups.forEach(g => { if (!g.items.length) return; h += `<div class="srch-h">${esc(g.label)}</div>`;
      g.items.forEach(it => { items.push(it); h += `<a class="srch-i" role="option" id="sr-${items.length - 1}" href="${esc(it.url)}" data-i="${items.length - 1}"><i data-lucide="${esc(it.icon)}" width="16"></i><span class="srch-t"><b>${mark(it.title, q)}</b><small>${mark(it.sub || "", q)}</small></span></a>`; }); });
    if (!items.length) h = `<div class="srch-e"><b>No matches for "${esc(q)}"</b>Try a company, a role or a task name.</div>`;
    box.innerHTML = h; sel = -1; if (window.lucide) lucide.createIcons({ attrs: { "stroke-width": 1.75 }, nameAttr: "data-lucide" }); open(true);
  }
  function pages(q) { const k = q.toLowerCase(); return PAGES.filter(p => !k || (p[0] + " " + p[4]).toLowerCase().includes(k)).map(p => ({ title: p[0], sub: p[1], url: p[2], icon: p[3] })); }
  async function run() {
    const q = inp.value.trim(), my = ++seq; let groups = [];
    try { const r = await fetch(inp.dataset.url + "?q=" + encodeURIComponent(q), { headers: { Accept: "application/json" }, credentials: "same-origin" }); if (r.ok) groups = (await r.json()).groups || []; } catch (e) { }
    if (my !== seq) return;   // a newer search is already on its way
    groups.push({ label: "Pages", items: pages(q).slice(0, 4) }); paint(groups, q);
  }
  function move(d) { if (!items.length) return; const all = box.querySelectorAll(".srch-i"); if (all[sel]) all[sel].classList.remove("on"); sel = (sel + d + items.length) % items.length; all[sel].classList.add("on"); all[sel].scrollIntoView({ block: "nearest" }); inp.setAttribute("aria-activedescendant", "sr-" + sel); }
  inp.addEventListener("focus", run);
  inp.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 160); });
  inp.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (box.hidden) run(); else move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") { const it = items[sel >= 0 ? sel : 0]; if (it && !box.hidden) { e.preventDefault(); location.href = it.url; } }
    else if (e.key === "Escape") { open(false); inp.blur(); }
  });
  box.addEventListener("mousemove", e => { const a = e.target.closest(".srch-i"); if (!a) return; box.querySelectorAll(".srch-i.on").forEach(x => x.classList.remove("on")); a.classList.add("on"); sel = +a.dataset.i; });
  document.addEventListener("mousedown", e => { if (!e.target.closest(".hdr-sw")) open(false); });
  document.addEventListener("keydown", e => {
    const typing = /^(input|textarea|select)$/i.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if ((e.key === "/" && !typing) || (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey))) { e.preventDefault(); inp.focus(); inp.select(); }
  });
})();
