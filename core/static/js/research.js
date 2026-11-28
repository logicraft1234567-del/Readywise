/* Research overlay: a stage that shows the work being done for the step that is running (reading official pages, scanning candidate accounts, watching interview videos, writing the briefing, choosing the panel), with the real research steps ticking off.
   Needs post() from app.js and the #rs overlay + #rs-ui data rendered by workspace.html. */
(function () {
  const dataEl = document.getElementById("rs-ui"), root = document.getElementById("rs");
  if (!dataEl || !root) return;
  const ui = JSON.parse(dataEl.textContent), $ = id => document.getElementById(id), R = (a, b) => a + Math.random() * (b - a);
  const stage = $("rs-stage"), scenes = {}; stage.querySelectorAll(".sc").forEach(n => { scenes[[...n.classList].find(c => c.startsWith("sc-")).slice(3)] = n; });
  const seen = new Set(); let timer = null, startedAt = 0, noteTimer = null, cycle = null, typer = null;
  /* what each type reads on the web: shown in the browser scene */
  const WEB = { hackathon: "event site, Devpost, past winners, judges", startup: "company site, founders, funding news", employment: "company site, careers, role pages", internship: "programme page, eligibility, deadlines", graduate: "graduate scheme, assessment stages", admission: "admissions page, course requirements", scholarship: "scholarship page, selection criteria", visa: "official government guidance", fellowship: "fellowship page, selection process", pitch: "investor profile, portfolio, market data", certification: "exam syllabus, format, competencies" };
  /* which scene a step belongs to: the last two steps are fixed, the two before them are forums and videos, everything else is the web */
  function sceneFor(i) { const n = ui.steps.length; return i === n - 1 ? "panel" : i === n - 2 ? "write" : i === n - 3 ? "video" : i === n - 4 ? "voices" : "web"; }
  function typeUrl(text) { clearInterval(typer); const u = $("sc-url"); let n = 0; u.textContent = ""; typer = setInterval(() => { n += 1; u.textContent = text.slice(0, n); if (n >= text.length) clearInterval(typer); }, 28); }
  let current = "";
  function setScene(name, label) {
    if (name === "web") { $("sc-web-label").textContent = label || ""; if (current !== "web") typeUrl(WEB[ui.kind] || "official sources"); }
    if (current === name) return; current = name;
    Object.entries(scenes).forEach(([k, n]) => n.classList.toggle("on", k === name));
  }
  let lastKey = "";
  function play(active, step) {
    const idx = (active && active.length) ? active.slice().sort((a, b) => a - b) : [step || 0], key = idx.join(",");
    if (key === lastKey) return; lastKey = key; clearInterval(cycle);
    const go = k => setScene(sceneFor(idx[k % idx.length]), ui.steps[idx[k % idx.length]]);
    let k = 0; go(0); if (idx.length > 1) cycle = setInterval(() => go(++k), 4200);
  }

  function setup() {
    root.dataset.kind = ui.kind; stage.style.setProperty("--acc", (ui.colors && ui.colors[0]) || "#8E9DFF"); current = ""; lastKey = ""; setScene("web", ui.steps[0]);
    $("rs-title").textContent = ui.title + (ui.name ? ": " + ui.name : "");
    $("rs-steps").innerHTML = ui.steps.map(s => `<li>${s.replace(/</g, "&lt;")}</li>`).join("");
    $("rs-found").innerHTML = ""; $("rs-note").textContent = ""; $("rs-close").hidden = true; if ($("rs-again")) $("rs-again").hidden = true; seen.clear();
  }
  function show(step, found, pr) {
    const lis = $("rs-steps").children, done = new Set((pr && pr.done) || []), active = new Set((pr && pr.active) || []), multi = pr && pr.done;
    for (let i = 0; i < lis.length; i++) lis[i].className = multi ? (done.has(i) ? "done" : active.has(i) ? "on" : "") : (i < step ? "done" : i === step ? "on" : "");
    const names = multi ? [...active].sort((a, b) => a - b).map(i => ui.steps[i]).filter(Boolean) : [ui.steps[step]].filter(Boolean);
    if (names.length) $("rs-step").textContent = names.join("  ·  ");
    play(multi ? [...active] : [step], step);
    (found || []).forEach(d => { if (seen.has(d)) return; seen.add(d); const s = document.createElement("span"); s.textContent = d; $("rs-found").appendChild(s); });
  }
  function notes() {
    const t = (Date.now() - startedAt) / 1000;
    $("rs-note").textContent = t > 150 ? "Still working. Search is slower than usual right now, hang on." : t > 50 ? "Good research takes a minute or two: each angle is searched and checked separately." : "";
  }
  function open() { setup(); startedAt = Date.now(); root.hidden = false; document.body.style.overflow = "hidden"; show(0, [], null); clearInterval(noteTimer); noteTimer = setInterval(notes, 3000); }
  function fail(msg) {
    clearTimeout(timer); clearInterval(noteTimer); clearInterval(cycle); $("rs-step").textContent = "Research could not finish"; $("rs-note").textContent = msg || "Something went wrong. Please try again.";
    $("rs-steps").querySelectorAll("li.on").forEach(l => l.className = ""); $("rs-close").hidden = false;
    $("rs-close").onclick = () => { root.hidden = true; document.body.style.overflow = ""; location.reload(); };
    let again = $("rs-again");   // finished angles are kept on the server, so trying again only redoes what is missing
    if (!again) { again = document.createElement("button"); again.type = "button"; again.id = "rs-again"; again.className = "btn rs-close"; again.style.marginLeft = ".6rem"; again.textContent = "Try again"; $("rs-close").after(again); }
    again.hidden = false; again.onclick = () => { again.hidden = true; window.rsStart(); };
  }
  function finish() {
    clearInterval(noteTimer); clearInterval(cycle); setScene("write", ""); show(ui.steps.length, [], null); $("rs-step").textContent = "Your briefing is ready"; $("rs-note").textContent = "";
    setTimeout(() => location.reload(), 1300);
  }
  async function poll() {
    try {
      const d = await (await fetch(ui.job, { headers: { Accept: "application/json" } })).json(), pr = d.progress || {};
      if (d.state === "error") return fail(d.error);
      if (d.stale) return fail("The last research run stopped unexpectedly. Close this and run research again.");
      if (pr.steps && typeof pr.step === "number") show(pr.step, pr.found, pr);
      if (d.state === "running") timer = setTimeout(poll, 1400); else finish();
    } catch (e) { timer = setTimeout(poll, 3000); }
  }
  window.rsStart = async function (btn) {
    open();
    try { const d = await post(ui.run, {}); if (d.job) poll(); else finish(); }
    catch (e) { fail(e.message); }
  };
  if (ui.running) { open(); poll(); }  // a run is already going (page reloaded): pick it up again
})();
