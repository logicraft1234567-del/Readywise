/* RWFilm: a small engine for cinematic overlays (picture: GSAP timeline, sound: live Web Audio score).
   Films are defined in story.js and guide-film.js. Nothing here loads media files. */
(function () {
  if (window.RWFilm || !window.gsap) return;
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const hasSpeech = "speechSynthesis" in window;
  const Aud = (function () {
    let ctx, master, bed, verb, comp, droneF, an, timer, next = 0, step = 0, intensity = 0, major = false, on = true, started = false;
    const BPM = 96, SIXT = 60 / BPM / 4;
    const MIN = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]], MAJ = [[48, 52, 55], [55, 59, 62], [57, 60, 64], [53, 57, 60]];
    const f = m => 440 * Math.pow(2, (m - 69) / 12);
    function init() {
      if (ctx) return; const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return; ctx = new AC();
      master = ctx.createGain(); master.gain.value = 0; comp = ctx.createDynamicsCompressor(); comp.threshold.value = -16; comp.ratio.value = 5; an = ctx.createAnalyser(); an.fftSize = 512;
      master.connect(comp); comp.connect(an); comp.connect(ctx.destination);
      const len = Math.floor(ctx.sampleRate * 2.8), buf = ctx.createBuffer(2, len, ctx.sampleRate);
      for (let c = 0; c < 2; c++) { const d = buf.getChannelData(c); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.8); }
      verb = ctx.createConvolver(); verb.buffer = buf; const vg = ctx.createGain(); vg.gain.value = .5; verb.connect(vg); vg.connect(master);
      bed = ctx.createGain(); bed.gain.value = 1; bed.connect(master); bed.connect(verb);
      droneF = ctx.createBiquadFilter(); droneF.type = "lowpass"; droneF.frequency.value = 220; const dg = ctx.createGain(); dg.gain.value = .22; droneF.connect(dg); dg.connect(bed);
      [55, 55.35, 110.2].forEach((fr, i) => { const o = ctx.createOscillator(); o.type = i === 2 ? "triangle" : "sawtooth"; o.frequency.value = fr; o.connect(droneF); o.start(); });
    }
    function tone(fr, t, dur, type, g, atk, rel, dest) { const o = ctx.createOscillator(), a = ctx.createGain(); o.type = type; o.frequency.setValueAtTime(fr, t); a.gain.setValueAtTime(0.0001, t); a.gain.linearRampToValueAtTime(g, t + atk); a.gain.exponentialRampToValueAtTime(0.0001, t + dur + rel); o.connect(a); a.connect(dest || bed); o.start(t); o.stop(t + dur + rel + .05); }
    function noise(t, dur, type, f0, f1, g, dest) { const len = Math.floor(ctx.sampleRate * dur), b = ctx.createBuffer(1, len, ctx.sampleRate), d = b.getChannelData(0); for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1; const s = ctx.createBufferSource(); s.buffer = b; const fl = ctx.createBiquadFilter(); fl.type = type; fl.frequency.setValueAtTime(f0, t); fl.frequency.exponentialRampToValueAtTime(f1, t + dur); const a = ctx.createGain(); a.gain.setValueAtTime(0.0001, t); a.gain.linearRampToValueAtTime(g, t + dur * .85); a.gain.exponentialRampToValueAtTime(0.0001, t + dur); s.connect(fl); fl.connect(a); a.connect(dest || bed); s.start(t); }
    function kick(t, g) { const o = ctx.createOscillator(), a = ctx.createGain(); o.type = "sine"; o.frequency.setValueAtTime(130, t); o.frequency.exponentialRampToValueAtTime(42, t + .16); a.gain.setValueAtTime(g, t); a.gain.exponentialRampToValueAtTime(0.0001, t + .5); o.connect(a); a.connect(bed); o.start(t); o.stop(t + .55); }
    function pad(ch, t, dur) { ch.forEach(m => { tone(f(m), t, dur * .9, "sawtooth", .035, 1.1, 1.4); tone(f(m) * 1.004, t, dur * .9, "triangle", .03, 1.1, 1.4); }); }
    function play(s, t) {
      if (!on) return; const beat = s % 16, bar = Math.floor(s / 16), ch = (major ? MAJ : MIN)[bar % 4];
      if (intensity === 1) { if (beat === 0 || beat === 8) kick(t, .7); if (beat === 3 || beat === 11) kick(t, .42); return; }
      if (beat === 0) pad(ch, t, SIXT * 16);
      if (intensity >= 2 && (beat === 0 || beat === 8)) { tone(f(ch[0] - 24), t, SIXT * 6, "sine", .3, .01, .5); }
      if (intensity >= 2 && intensity < 4 && beat % 8 === 0) kick(t, .55);
      if (intensity >= 4 && beat % 4 === 0) kick(t, .75);
      if (intensity >= 3 && beat % 2 === 0) { const nt = ch[(beat / 2) % 3] + (beat % 8 === 6 ? 24 : 12); tone(f(nt), t, SIXT * 1.5, "triangle", .07 + (intensity >= 4 ? .03 : 0), .005, .35); }
      if (intensity >= 3 && beat % 4 === 2) noise(t, .05, "highpass", 7000, 9000, .05);
      if (intensity >= 5 && beat % 4 === 0) tone(f(ch[2] + 24), t, SIXT * 3, "sine", .05, .01, 1);
    }
    function tick() { if (!ctx) return; while (next < ctx.currentTime + .3) { play(step, next); next += SIXT; step++; } }
    return {
      start() { init(); if (!ctx) return; ctx.resume(); if (!started) { started = true; next = ctx.currentTime + .1; step = 0; timer = setInterval(tick, 60); }
        master.gain.cancelScheduledValues(ctx.currentTime); master.gain.setTargetAtTime(on ? .85 : 0, ctx.currentTime, .15); },
      stop() { if (!ctx) return; master.gain.setTargetAtTime(0, ctx.currentTime, .12); setTimeout(() => { if (ctx && !document.querySelector(".film.open")) { clearInterval(timer); started = false; ctx.suspend(); } }, 600); },
      pause() { ctx && ctx.suspend(); }, resume() { ctx && ctx.resume(); },
      mute(m) { on = !m; if (ctx) master.gain.setTargetAtTime(on ? .85 : 0, ctx.currentTime, .1); }, isOn: () => on,
      set(level, isMajor) { if (!ctx) return; const was = major; intensity = level || 1; major = !!isMajor; droneF.frequency.setTargetAtTime(160 + intensity * 260, ctx.currentTime, .6); if (major && !was) { step = Math.ceil(step / 16) * 16; } },
      slam(g) { if (!ctx || !on) return; const t = ctx.currentTime + .01; kick(t, g || .9); noise(t, .35, "lowpass", 2500, 120, (g || .9) * .4); },
      boom() { if (!ctx || !on) return; const t = ctx.currentTime + .01; kick(t, 1.1); tone(36, t, 1.6, "sine", .6, .01, 1.2); noise(t, 1.8, "lowpass", 5000, 90, .45); },
      riser(dur) { if (!ctx || !on) return; const t = ctx.currentTime + .01; noise(t, dur, "bandpass", 300, 7500, .35); tone(110, t, dur, "sawtooth", .0, .01, .1); const o = ctx.createOscillator(), a = ctx.createGain(); o.type = "sawtooth"; o.frequency.setValueAtTime(90, t); o.frequency.exponentialRampToValueAtTime(900, t + dur); a.gain.setValueAtTime(0.0001, t); a.gain.linearRampToValueAtTime(.09, t + dur * .95); a.gain.exponentialRampToValueAtTime(0.0001, t + dur + .08); o.connect(a); a.connect(bed); o.start(t); o.stop(t + dur + .1); },
      hit() { if (!ctx || !on) return; const t = ctx.currentTime + .01; noise(t, .5, "highpass", 6000, 500, .3); tone(f(81), t, .5, "triangle", .12, .005, .4); },
      sparkle() { if (!ctx || !on) return; const t = ctx.currentTime + .02; [76, 83, 88, 91, 95].forEach((m, k) => tone(f(m), t + k * .09, .5, "sine", .08, .01, .9)); },
      level() { if (!an) return 0; const d = new Uint8Array(an.fftSize); an.getByteTimeDomainData(d); let m = 0; d.forEach(v => m = Math.max(m, Math.abs(v - 128))); return m; },
      time: () => ctx ? ctx.currentTime : 0, state: () => ctx ? ctx.state : "none"
    };
  })();
  window.RWAudio = Aud; window.__rwStoryAudio = Aud;

  window.RWFilm = function (cfg) {
    const root = document.getElementById(cfg.id); if (!root) return;
    const stage = root.querySelector(".st-stage"), cam = root.querySelector(".st-cam"), flashEl = root.querySelector(".st-flash"), fx = root.querySelector(".st-fx");
    const segsBox = root.querySelector(".st-segs"), ppBtn = root.querySelector("[data-pp]"), sndBtn = root.querySelector("[data-snd]"), voBtn = root.querySelector("[data-vo]");
    const team = [...document.querySelectorAll("#film-team span")].map(s => ({ n: s.dataset.n, r: s.dataset.r, img: s.dataset.img }));
    const W = t => t.split(" ").map(x => `<span class="w">${x} </span>`).join("");
    const scenes = cfg.make({ team, W, cta: root.dataset.cta });
    const DUR = scenes.map(s => s.d), N = DUR.length, START = DUR.reduce((a, d, i) => (a.push(i ? a[i - 1] + DUR[i - 1] : 0), a), []);
    segsBox.innerHTML = DUR.map((_, i) => `<button type="button" aria-label="Chapter ${i + 1}"><i></i></button>`).join(""); const segs = [...segsBox.children];
    const $q = (e, s) => e.querySelector(s), $$ = (e, s) => [...e.querySelectorAll(s)];
    let voOn = false;
    function speak(i) { if (!voOn || !hasSpeech || !cfg.vo[i]) return; speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(cfg.vo[i]); u.rate = .92; u.pitch = .8; const vs = speechSynthesis.getVoices(); const v = vs.find(v => /en[-_](GB|US)/i.test(v.lang) && /male|daniel|google uk english male|alex|fred/i.test(v.name)) || vs.find(v => /^en/i.test(v.lang)); if (v) u.voice = v; speechSynthesis.speak(u); }

    const g2 = fx.getContext("2d"); let parts = [], fxOn = false, fxLevel = 1, raf = 0;
    function sizeFx() { const r = stage.getBoundingClientRect(), d = Math.min(2, devicePixelRatio || 1); fx.width = r.width * d; fx.height = r.height * d; }
    function loop() { if (!fxOn) return; const w = fx.width, h = fx.height; g2.clearRect(0, 0, w, h); while (parts.length < 110) parts.push({ x: Math.random() * w, y: Math.random() * h, r: Math.random() * 1.8 + .4, v: Math.random() * .4 + .1, a: Math.random() * .6 + .2 });
      parts.forEach(p => { p.y -= p.v * fxLevel * (h / 500); p.x += Math.sin((p.y + p.a * 40) / 60) * .25; if (p.y < -5) { p.y = h + 5; p.x = Math.random() * w; } g2.globalAlpha = p.a * Math.min(1, .35 + fxLevel * .3); g2.fillStyle = fxLevel > 2.5 ? "#c9d3ff" : "#8E9DFF"; g2.beginPath(); g2.arc(p.x, p.y, p.r * (h / 500), 0, 6.283); g2.fill(); });
      raf = requestAnimationFrame(loop); }

    const els = scenes.map((s, i) => { const d = document.createElement("div"); d.className = "sn"; d.dataset.i = i; d.innerHTML = s.html; cam.appendChild(d); return d; });
    const tl = gsap.timeline({ paused: true, defaults: { ease: "power3.out" }, onUpdate: () => segFill(tl.time()), onComplete: () => setPP(false) });
    const shake = (t, amp, dur) => { if (REDUCE) return; tl.fromTo(cam, { x: 0, y: 0 }, { x: () => gsap.utils.random(-amp, amp), y: () => gsap.utils.random(-amp, amp), duration: .045, repeat: Math.max(2, Math.round(dur / .09)), yoyo: true, repeatRefresh: true, ease: "none" }, t).set(cam, { x: 0, y: 0 }, t + dur + .05); };
    const flash = (t, a, d) => tl.fromTo(flashEl, { opacity: a }, { opacity: 0, duration: d || .55, ease: "power2.out" }, t);
    const snd = (t, fn) => tl.call(fn, null, t);
    const typeText = (el, text, t, dur) => { const o = { p: 0 }; el.textContent = ""; tl.to(o, { p: 1, duration: dur, ease: "none", onUpdate: () => { el.textContent = text.slice(0, Math.round(o.p * text.length)); } }, t); };
    const level = i => (cfg.intensity[i] || 2), fxl = i => (cfg.fx[i] || 2), isMajor = i => cfg.majorFrom != null && i >= cfg.majorFrom;
    els.forEach((el, i) => {
      const t0 = START[i], d = DUR[i];
      tl.set(el, { autoAlpha: 1 }, t0).fromTo($q(el, ".in"), { scale: 1.06 }, { scale: 1, duration: d + .6, ease: "none" }, t0);
      if (i < N - 1) tl.to(el, { autoAlpha: 0, duration: .45, ease: "power1.in" }, t0 + d - .45);
      snd(t0, () => { Aud.set(level(i), isMajor(i)); speak(i); fxLevel = fxl(i); });
      const words = $$(el, ".big:not([data-manual]) .w"); if (words.length) tl.from(words, { yPercent: 70, autoAlpha: 0, duration: .7, stagger: .09 }, t0 + .3);
    });
    const H = { tl, $q, $$, shake, flash, snd, typeText, Aud, team, REDUCE, root };
    scenes.forEach((s, i) => s.build && s.build(Object.assign({ el: els[i], t0: START[i], d: DUR[i], i }, H)));

    function segFill(t) { segs.forEach((b, i) => { const p = Math.min(1, Math.max(0, (t - START[i]) / DUR[i])); b.firstElementChild.style.width = (p * 100) + "%"; }); }
    function setPP(playing) { ppBtn.innerHTML = playing ? '<i data-lucide="pause" width="16"></i>' : '<i data-lucide="play" width="16"></i>'; if (window.lucide) lucide.createIcons({ attrs: { "stroke-width": 1.75 } }); }
    function reset() { scenes.forEach((s, i) => s.reset && s.reset(els[i])); if (hasSpeech) speechSynthesis.cancel(); }
    function jump(i) { tl.pause(); reset(); gsap.set(cam, { x: 0, y: 0 }); flashEl.style.opacity = 0; tl.seek(START[i] + (REDUCE ? DUR[i] - .6 : 0)); Aud.set(level(i), isMajor(i)); fxLevel = fxl(i); if (REDUCE) setPP(false); else { tl.play(); Aud.resume(); setPP(true); speak(i); } }
    function open() { document.querySelectorAll(".film.open").forEach(f => f !== root && f.querySelector("[data-close]").click()); root.classList.add("open"); root.setAttribute("aria-hidden", "false"); document.body.style.overflow = "hidden"; sizeFx(); fxOn = !REDUCE; parts = []; cancelAnimationFrame(raf); loop(); gsap.set(els, { autoAlpha: 0 }); tl.seek(0); reset(); if (!REDUCE) Aud.start(); Aud.set(level(0), isMajor(0)); if (REDUCE) jump(0); else { tl.play(); setPP(true); speak(0); } root.focus(); }
    function close() { tl.pause(); fxOn = false; cancelAnimationFrame(raf); root.classList.remove("open"); root.setAttribute("aria-hidden", "true"); if (!document.querySelector(".film.open")) document.body.style.overflow = ""; Aud.stop(); if (hasSpeech) speechSynthesis.cancel(); }
    function idx() { const t = tl.time(); let k = 0; START.forEach((s, i) => { if (t >= s) k = i; }); return k; }
    document.addEventListener("click", e => { const b = e.target.closest("[data-film-open],[data-story-open]"); if (!b) return; const id = b.dataset.filmOpen || "story"; if (id === cfg.id) { e.preventDefault(); open(); } });
    root.querySelector("[data-close]").onclick = close; root.querySelector(".st-skip").onclick = close;
    ppBtn.onclick = () => { if (tl.paused()) { if (tl.progress() >= 1) { reset(); tl.restart(); } else tl.play(); Aud.resume(); setPP(true); } else { tl.pause(); Aud.pause(); if (hasSpeech) speechSynthesis.pause(); setPP(false); } };
    sndBtn.onclick = () => { const wasOn = Aud.isOn(); Aud.mute(wasOn); if (!wasOn) Aud.start(); sndBtn.setAttribute("aria-pressed", String(!wasOn)); sndBtn.innerHTML = `<i data-lucide="${wasOn ? "volume-x" : "volume-2"}" width="16"></i>`; if (window.lucide) lucide.createIcons({ attrs: { "stroke-width": 1.75 } }); };
    voBtn.onclick = () => { voOn = !voOn; voBtn.setAttribute("aria-pressed", String(voOn)); voBtn.classList.toggle("on-air", voOn); if (voOn) speak(idx()); else if (hasSpeech) speechSynthesis.cancel(); };
    root.addEventListener("click", e => { if (e.target.closest("[data-replay]")) { reset(); tl.restart(); Aud.resume(); setPP(true); } });
    segs.forEach((b, i) => b.onclick = () => jump(i));
    addEventListener("keydown", e => { if (!root.classList.contains("open")) return; if (e.key === "Escape") close(); else if (e.key === " ") { e.preventDefault(); ppBtn.click(); } else if (e.key === "ArrowRight") jump(Math.min(N - 1, idx() + 1)); else if (e.key === "ArrowLeft") jump(Math.max(0, idx() - 1)); });
    addEventListener("resize", () => root.classList.contains("open") && sizeFx());
    if (cfg.hash && location.hash === "#" + cfg.hash) setTimeout(open, 600);
  };
})();
