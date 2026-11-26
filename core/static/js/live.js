/* ReadyWise live voice. The microphone goes straight to Google's Gemini Live over a WebSocket, using a one-session token minted by the server
   (the real API key never reaches the browser). Gemini hears the raw audio, answers in audio, and handles turn-taking and interruptions itself.
   Once a second a small camera picture is sent too (sampled frames, not continuous video). The written transcript Gemini returns is saved
   by the server for the report only; it is not what the model reasons from.
   Relies on globals from room.js: $, post, toast, SID, PANEL, buildStage, layoutSquares, setSpeaker, bars, caption, logMsg, setState, camOff, stream, finish. */
const Live = (() => {
  const URL_BASE = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained?access_token=";
  const IN_RATE = 16000, OUT_RATE = 24000, CHUNK = 640;   // 40 ms of 16 kHz audio per message
  let ws = null, inCtx = null, outCtx = null, node = null, mic = null, outGain = null, outAn = null, inAn = null;
  let meta = null, lead = null, handle = null, closing = false, stopping = false, nextT = 0, raf = 0, frameT = null, timers = [];
  let acc = [], pos = 0, out = [], cur = null, pending = [], posting = false, srcs = new Set(), speaking = false;
  let queue = [], awaiting = false, awaitT = 0, lastVoice = 0, ivCount = 0, factUntil = 0, askingTask = false, taskDone = false, taskTries = 0;
  const api = { active: false };
  const send = o => { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); };
  const b64 = u8 => { let s = ""; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };

  /* ---------- microphone: any sample rate in, 16 kHz 16-bit PCM out ---------- */
  function onMic(f32) {
    for (let i = 0; i < f32.length; i++) acc.push(f32[i]);
    const ratio = inCtx.sampleRate / IN_RATE;
    while (pos + ratio <= acc.length) {
      const a = Math.floor(pos), b = Math.max(a + 1, Math.floor(pos + ratio)); let s = 0; for (let i = a; i < b; i++) s += acc[i];
      out.push(s / (b - a)); pos += ratio;
    }
    const k = Math.floor(pos); if (k > 0) { acc = acc.slice(k); pos -= k; }
    while (out.length >= CHUNK) {
      const pcm = new Int16Array(CHUNK); for (let i = 0; i < CHUNK; i++) { const v = Math.max(-1, Math.min(1, out[i])); pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff; }
      out = out.slice(CHUNK);
      send({ realtimeInput: { audio: { data: b64(new Uint8Array(pcm.buffer)), mimeType: "audio/pcm;rate=16000" } } });
    }
  }
  async function startMic() {
    inCtx = new (window.AudioContext || window.webkitAudioContext)(); if (inCtx.state === "suspended") await inCtx.resume();
    const code = `class C extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor("rw-cap",C)`;
    await inCtx.audioWorklet.addModule(URL.createObjectURL(new Blob([code], { type: "text/javascript" })));
    mic = inCtx.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));   // the same tracks as the Mute button controls
    node = new AudioWorkletNode(inCtx, "rw-cap"); node.port.onmessage = e => onMic(e.data);
    inAn = inCtx.createAnalyser(); inAn.fftSize = 512; const mute = inCtx.createGain(); mute.gain.value = 0;
    mic.connect(node); mic.connect(inAn); node.connect(mute); mute.connect(inCtx.destination);
  }

  /* ---------- the interviewer's voice: 24 kHz PCM chunks queued back to back ---------- */
  function startOut() {
    outCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: OUT_RATE }); outGain = outCtx.createGain(); outAn = outCtx.createAnalyser(); outAn.fftSize = 512;
    outGain.connect(outAn); outAn.connect(outCtx.destination); nextT = 0;
  }
  function play(b64data) {
    const bin = atob(b64data), u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    const i16 = new Int16Array(u8.buffer, 0, Math.floor(u8.length / 2)), buf = outCtx.createBuffer(1, i16.length, OUT_RATE), ch = buf.getChannelData(0);
    for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 0x8000;
    const s = outCtx.createBufferSource(); s.buffer = buf; s.connect(outGain); nextT = Math.max(nextT, outCtx.currentTime + 0.03); s.start(nextT); nextT += buf.duration;
    srcs.add(s); s.onended = () => { srcs.delete(s); if (!srcs.size) idle(); };
    if (!speaking) { speaking = true; setSpeaker(lead.id); setState(lead.name + " is speaking"); }
  }
  function idle() { if (!speaking) return; speaking = false; setSpeaker(null); if (!stopping) setState("Listening…"); }
  function cutVoice() { srcs.forEach(s => { s.onended = null; try { s.stop(); } catch (e) { } }); srcs.clear(); nextT = 0; idle(); }   // the candidate spoke over the interviewer

  /* ---------- the two indicators: speaking and listening ---------- */
  function level(an) { const d = new Uint8Array(an.fftSize); an.getByteTimeDomainData(d); let s = 0; for (const v of d) { const x = (v - 128) / 128; s += x * x; } return Math.sqrt(s / d.length); }
  function loop() {
    if (outAn && lead) bars(lead.id, speaking ? Math.min(1, level(outAn) * 4) : 0);
    if (inAn) { const lv = typeof muted !== "undefined" && muted ? 0 : level(inAn), on = lv > .04; $("pip").classList.toggle("talking", on); if (on) lastVoice = Date.now(); $("mestate").textContent = on ? "Speaking" : "Listening"; if (typeof levelLive === "function") levelLive(lv); }
    raf = requestAnimationFrame(loop);
  }

  /* ---------- transcript: kept for the report and shown in the side panel ---------- */
  function frag(role, text) {
    if (!text) return; if (cur && cur.role !== role) endTurn();
    if (!cur) cur = { role, text: "", node: logMsg(role === "candidate" ? "You" : lead.name + ", " + lead.position, "", role === "candidate" ? "c" : "i") };
    cur.text += text; const t = cur.text.replace(/\s+/g, " ").trim(); cur.node.lastChild.textContent = t; caption(t, role === "candidate"); $("msgs").scrollTop = 1e9;
  }
  function endTurn() {
    if (!cur) return; const role = cur.role, t = cur.text.replace(/\s+/g, " ").trim(); if (t) pending.push({ role, text: t }); cur = null; flush();
    if (t && role === "candidate") { lastCand = t; factUntil = Date.now() + 45000; }   // a verified correction may arrive in the next few seconds
    if (t && role === "interviewer") { ivCount++; maybeTask(); }
  }
  async function flush() {
    if (posting || !pending.length) return; posting = true; const batch = pending.splice(0, 20);
    try { await post(`/room/${SID}/live/turns/`, { turns: batch }); } catch (e) { pending.unshift(...batch); }
    posting = false; if (pending.length && !stopping) setTimeout(flush, 1500);
  }

  /* ---------- messages from Gemini ---------- */
  let lastCand = "", endReason = "", endGuard = 0;
  function onTool(calls) {   // the interviewer asked to end the interview: allowed only under the same rules the standard interview uses
    for (const fc of calls) {
      if (fc.name !== "end_interview") { send({ toolResponse: { functionResponses: [{ id: fc.id, name: fc.name, response: { result: "unknown tool" } }] } }); continue; }
      const a = fc.args || {}, el = (Date.now() - t0) / 1000, wants = /\b(i'?m|i am|we'?re|we are) (done|finished)|\b(let'?s|can we|could we) (stop|end|finish)|\bi (want|need|would like) to (stop|end|leave)|end (the|this) (interview|call|meeting)/i.test(lastCand);
      let ok = a.reason === "finished" ? (wants || el >= meta.limit_s * .8) : a.reason === "unprofessional" ? (a.severe === true || a.warned_before === true) : false;
      if (!ok) { send({ toolResponse: { functionResponses: [{ id: fc.id, name: fc.name, response: { result: "refused", note: a.reason === "unprofessional" ? "Give the candidate one calm professional warning first, then continue the interview." : "The interview is not finished. Continue with your next question." } }] } }); continue; }
      send({ toolResponse: { functionResponses: [{ id: fc.id, name: fc.name, response: { result: "ok" } }] } });
      endReason = a.reason; closing = true; clearTimeout(endGuard); endGuard = setTimeout(() => finish(false, endReason), 15000);   // normally the end follows the spoken goodbye; this only covers a missing turnComplete
    }
  }
  function onMsg(m) {
    if (m.toolCall && m.toolCall.functionCalls) onTool(m.toolCall.functionCalls);
    if (m.sessionResumptionUpdate && m.sessionResumptionUpdate.newHandle) handle = m.sessionResumptionUpdate.newHandle;
    if (m.goAway) reconnect();
    const c = m.serverContent; if (!c) return;
    if (c.interrupted) { cutVoice(); endTurn(); }
    if (c.modelTurn && c.modelTurn.parts) c.modelTurn.parts.forEach(p => { if (p.inlineData && p.inlineData.data && !stopping) play(p.inlineData.data); });
    if (c.inputTranscription && c.inputTranscription.text) frag("candidate", c.inputTranscription.text);
    if (c.outputTranscription && c.outputTranscription.text) frag("interviewer", c.outputTranscription.text);
    if (c.turnComplete) { awaiting = false; endTurn(); if (closing) setTimeout(() => { const wait = () => srcs.size ? setTimeout(wait, 300) : finish(false, endReason); wait(); }, 800); }
  }
  async function connect(resume) {
    return new Promise((res, rej) => {
      const sock = new WebSocket(URL_BASE + encodeURIComponent(meta.token)); let ready = false;
      const t = setTimeout(() => { if (!ready) { try { sock.close(); } catch (e) { } rej(new Error("The live voice did not answer in time.")); } }, 10000);
      sock.onopen = () => sock.send(JSON.stringify({ setup: Object.assign({ model: "models/" + meta.model }, resume && handle ? { sessionResumption: { handle } } : {}) }));
      sock.onmessage = async ev => {
        let m; try { m = JSON.parse(typeof ev.data === "string" ? ev.data : await ev.data.text()); } catch (e) { return; }
        if (m.setupComplete && !ready) { ready = true; clearTimeout(t); ws = sock; res(); return; }
        if (ready) onMsg(m);
      };
      sock.onerror = () => { if (!ready) { clearTimeout(t); rej(new Error("The live voice could not connect.")); } };
      sock.onclose = () => { if (!ready) { clearTimeout(t); rej(new Error("The live voice closed the connection.")); } else if (sock === ws && !stopping) reconnect(); };
    });
  }
  let reconnecting = false;
  async function reconnect() {
    if (reconnecting || stopping) return; reconnecting = true; setState("Reconnecting…");
    try { const old = ws; ws = null; if (old) { old.onclose = null; try { old.close(); } catch (e) { } } meta = Object.assign(meta, await post(`/room/${SID}/live/token/`, {})); await connect(true); setState("Listening…"); }
    catch (e) { toast("The live voice connection was lost. Press End interview to finish; what was said is saved.", true); setState("Connection lost."); }
    reconnecting = false;
  }

  /* ---------- written messages to the model, sent only when it is quiet and the candidate is not speaking, so nobody is cut off ---------- */
  function enqueue(text, kind, front, run) { const it = { text, kind, run }; if (front) queue.unshift(it); else queue.push(it); }
  function pump() {
    if (!queue.length || awaiting || speaking || stopping || reconnecting || !ws || ws.readyState !== 1 || Date.now() - lastVoice < 1500) return;
    const it = queue.shift(); if (it.run) { try { it.run(); } catch (e) { } }
    send({ realtimeInput: { text: it.text } }); awaiting = true; clearTimeout(awaitT); awaitT = setTimeout(() => { awaiting = false; }, 20000);
  }
  async function pollFacts() {   // the fact-check runs on the server; a wrong or implausible claim is passed to the interviewer once
    if (stopping || Date.now() > factUntil || queue.some(q => q.kind === "fact")) return;
    try { const r = await post(`/room/${SID}/live/facts/`, {}); if (r && r.text) enqueue(r.text, "fact"); } catch (e) { }
  }

  /* ---------- hands-on task ---------- */
  async function maybeTask() {
    if (taskDone || askingTask || closing || stopping || ivCount < 4 || taskTries >= 3 || (typeof BENCH !== "undefined" && BENCH)) return;
    askingTask = true; taskTries++;
    try {
      const r = await post(`/room/${SID}/live/challenge/`, {}); if (r.final) taskDone = true;
      const ch = r.challenge; if (ch && !closing && !stopping) {
        enqueue(`HANDS-ON TASK. You are now giving the candidate a hands-on task. It has just appeared on their screen (title: "${ch.title}"). Say this to them in your own natural words, at most 50 words, and do not read the task out: ${ch.spoken}\nThen stop talking and stay quiet while they work. Ask no question until they submit.`,
          "task", true, () => openBench(ch));
      }
    } catch (e) { }
    askingTask = false;
  }
  api.submit = async function (text) {   // the candidate pressed Submit solution
    try { await post(`/room/${SID}/live/turns/`, { turns: [{ role: "candidate", text, build: true }] }); } catch (e) { toast("Your solution could not be saved. Press Submit again.", true); return; }
    enqueue("THE CANDIDATE SUBMITTED THEIR SOLUTION to the hands-on task. Their work, exactly as submitted, including the result of any automatic checks:\n" + text.slice(0, 3500)
      + "\nReview it like a real interviewer: react to something concrete in it and ask ONE question about a trade-off, an edge case or how they would improve it. Do not praise it and do not rewrite it for them.", "submit", true);
  };

/* ---------- camera: one small picture per second, only while the camera is on ---------- */
  function startFrames() {
    const cv = document.createElement("canvas"), g = cv.getContext("2d");
    frameT = setInterval(() => {
      if ((typeof camOff !== "undefined" && camOff) || document.hidden || !ws || ws.readyState !== 1) return;
      const v = $("me"); if (!v.videoWidth) return; cv.width = 480; cv.height = Math.round(480 * v.videoHeight / v.videoWidth); g.drawImage(v, 0, 0, cv.width, cv.height);
      send({ realtimeInput: { video: { data: cv.toDataURL("image/jpeg", .6).split(",")[1], mimeType: "image/jpeg" } } });
    }, 1000);
  }

  /* ---------- public ---------- */
  api.tryStart = async function () {
    const box = $("liveconsent"); if (!box || !box.checked) return false;
    if (!stream || !stream.getAudioTracks().length) { toast("The live voice needs your microphone. Using the standard interview."); return false; }
    try {
      meta = await post(`/room/${SID}/live/token/`, {}); lead = meta.lead;
      const mine = PANEL.find(p => p.id === lead.id) || Object.assign({ gender: "m" }, lead); PANEL.length = 0; PANEL.push(mine); lead = mine; buildStage(); layoutSquares();   // one interviewer speaks in live mode
      startOut(); await startMic(); await connect(false);
    } catch (e) { cleanup(); toast((e && e.message ? e.message : "The live voice is unavailable") + " Using the standard interview."); return false; }
    api.active = true; document.body.classList.add("live-on"); setState("Listening…"); if ($("vconsent")) { /* the end-of-interview snapshot consent is separate and unchanged */ }
    send({ realtimeInput: { text: meta.opening } }); startFrames(); raf = requestAnimationFrame(loop); timers.push(setInterval(pump, 600), setInterval(pollFacts, 4000));
    const lim = meta.limit_s; timers.push(setTimeout(() => { closing = true; send({ realtimeInput: { text: "Time check: about 90 seconds remain. Wrap up now: a brief closing remark, thank the candidate, and say what happens next. Ask no new question." } }); }, Math.max(30, lim - 90) * 1000));
    timers.push(setTimeout(() => finish(), (lim + 75) * 1000));   // safety net if the closing never completes
    return true;
  };
  function cleanup() {
    cancelAnimationFrame(raf); clearInterval(frameT); timers.forEach(t => { clearTimeout(t); clearInterval(t); }); timers = []; queue = []; clearTimeout(awaitT);
    if (ws) { ws.onclose = null; try { ws.close(); } catch (e) { } ws = null; }
    try { if (node) node.disconnect(); if (mic) mic.disconnect(); } catch (e) { }
    [inCtx, outCtx].forEach(c => { try { c && c.close(); } catch (e) { } }); inCtx = outCtx = node = mic = null; srcs.clear(); api.active = false; document.body.classList.remove("live-on");
  }
  api.stop = async function () {
    stopping = true; endTurn(); cleanup();
    for (let i = 0; i < 20 && (posting || pending.length); i++) { if (!posting) flush(); await new Promise(r => setTimeout(r, 250)); }   // the last words are saved before the evaluation starts
  };
  return api;
})();
