/* Speak-to-fill. A small microphone button sits inside every text box and text area on forms: tap it, talk, and your words are
   typed into the box for you. Typing always still works (nothing is replaced or hidden), and you can edit what was heard.
   Stops by itself when you pause, or tap the button again. Uses the same server-side speech-to-text as the interview room. */
(function () {
  "use strict";
  // voice.js loads first (both are deferred, in order). Without a microphone API the buttons are simply not added, and the form works as before.
  function init() {
    if (window.__rwDictate || !window.RWVoice || !navigator.mediaDevices) return; window.__rwDictate = true;
    const css = document.createElement("style");
    css.textContent = `.dict-a{position:relative;display:block;height:0;width:100%}.dict-b{position:absolute;right:.55rem;bottom:.55rem;width:34px;height:34px;border-radius:50%;border:1px solid var(--line,#ccd);background:var(--surface,#fff);color:var(--mut,#667);display:grid;place-items:center;cursor:pointer;padding:0;z-index:3;transition:background .15s,color .15s,transform .1s}
.dict-b:hover{color:var(--ink,#123)}.dict-b svg{width:17px;height:17px}.dict-b.rec{background:#c93049;border-color:#c93049;color:#fff;box-shadow:0 0 0 calc(var(--lv,0)*9px) rgba(201,48,73,.28)}.dict-b.busy{opacity:.6;cursor:progress}.dict-b.bad{color:#c93049}
.dict-f{padding-right:3rem!important}.dict-msg{position:fixed;left:50%;bottom:1.2rem;transform:translateX(-50%);background:#16203a;color:#fff;padding:.5rem .9rem;border-radius:10px;font-size:.88rem;z-index:99;max-width:90vw}`;
    document.head.append(css);
    const SKIP = "input[type=password],input[type=email],input[type=file],input[type=hidden],input[type=checkbox],input[type=radio],input[type=number],input[type=date],input[type=url],[data-nodictate],#gsearch,#typed,.hdr-search input,[name=username],[name=csrfmiddlewaretoken]";
    const MIC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
    const STOP = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>';
    const say = t => { const m = document.createElement("div"); m.className = "dict-msg"; m.setAttribute("role", "status"); m.textContent = t; document.body.append(m); setTimeout(() => m.remove(), 3800); };
    const csrf = () => document.cookie.split("; ").find(c => c.startsWith("csrftoken="))?.split("=")[1] || document.querySelector("[name=csrfmiddlewaretoken]")?.value;
    let active = null;

    function label(f) { const l = f.id && document.querySelector(`label[for="${f.id}"]`); return (l && l.textContent) || f.getAttribute("aria-label") || f.placeholder || f.name || ""; }
    function insert(f, text) {
      const a = f.selectionStart, b = f.selectionEnd, v = f.value, hasCaret = document.activeElement === f && typeof a === "number";
      const add = (text || "").trim(); if (!add) return;
      if (hasCaret) { const pre = v.slice(0, a), post = v.slice(b); f.value = pre + (pre && !/\s$/.test(pre) ? " " : "") + add + (post && !/^\s/.test(post) ? " " : "") + post; }
      else f.value = v + (v && !/\s$/.test(v) ? " " : "") + add;
      f.dispatchEvent(new Event("input", { bubbles: true })); f.dispatchEvent(new Event("change", { bubbles: true }));
    }
    async function toggle(f, btn) {
      if (active && active.btn === btn) { active.stop(); return; } if (active) active.stop();
      let stream; try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
      catch (e) { btn.classList.add("bad"); say("Microphone not available. You can type here instead."); return; }
      let cap, done = false;
      const finish = async blob => {
        if (done) return; done = true; active = null; btn.classList.remove("rec"); btn.style.removeProperty("--lv"); btn.innerHTML = MIC; try { cap.destroy(); } catch (e) { } stream.getTracks().forEach(t => t.stop());
        if (!blob || blob.size < 1500) { say("I didn't hear anything. Try again, or type."); return; }
        btn.classList.add("busy"); const fd = new FormData(); fd.append("audio", blob, "field.webm"); fd.append("label", label(f));
        try { const r = await fetch("/stt/", { method: "POST", headers: { "X-CSRFToken": csrf() }, body: fd }), d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || "Could not transcribe.");
          if (d.heard) { insert(f, d.text); btn.classList.remove("bad"); } else say("I didn't hear anything. Try again, or type."); }
        catch (e) { btn.classList.add("bad"); say(e.message + " You can type instead."); }
        btn.classList.remove("busy");
      };
      cap = new RWVoice.Capture(stream, { onLevel: l => btn.style.setProperty("--lv", Math.min(1, l * 5).toFixed(2)), onEnd: (blob) => finish(blob), onStart() { }, onConfirm() { }, onDiscard() { } });
      cap.vad.calib = 400; cap.open("answer", f.tagName === "TEXTAREA" ? 2600 : 1800);
      active = { btn, stop: async () => finish(await cap.close()) };
      btn.classList.add("rec"); btn.innerHTML = STOP; f.focus();
    }
    function attach(f) {
      if (f.dataset.dict || f.matches(SKIP) || f.closest("#rm") || f.readOnly || f.disabled) return;
      if (f.tagName === "INPUT" && !["text", "search", "tel", ""].includes((f.getAttribute("type") || "").toLowerCase())) return;
      f.dataset.dict = "1"; f.classList.add("dict-f");
      const a = document.createElement("span"), b = document.createElement("button"); a.className = "dict-a"; b.type = "button"; b.className = "dict-b"; b.innerHTML = MIC;
      b.setAttribute("aria-label", "Speak your answer"); b.title = "Speak instead of typing";
      b.addEventListener("click", e => { e.preventDefault(); toggle(f, b); }); a.append(b); f.insertAdjacentElement("afterend", a);
    }
    const scan = root => (root.querySelectorAll ? root.querySelectorAll("textarea,input") : []).forEach(attach);
    scan(document); let t; new MutationObserver(() => { clearTimeout(t); t = setTimeout(() => scan(document), 80); }).observe(document.body, { childList: true, subtree: true });
  }
  init();
})();
