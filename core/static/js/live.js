/* ReadyWise live voice, with a real panel. Every interviewer has their OWN Gemini Live session (own key where there are enough keys, own voice, own part of the plan).
   The microphone goes straight to Google over a WebSocket using one-session tokens minted by the server (the real keys never reach the browser).
   A small coordinator in this file decides who has the floor, so only ONE interviewer speaks at a time: the candidate's audio and camera pictures go only to the
   interviewer who holds the floor; the others are silent until they are handed the floor with the conversation so far. Interviewers hand over to each other with the
   pass_to tool after saying a short hand-over line, and the coordinator makes sure everybody speaks. The written transcript is saved by the server for the report only.
   Relies on globals from room.js: $, post, toast, SID, PANEL, buildStage, layoutSquares, setSpeaker, bars, caption, logMsg, setState, camOff, stream, finish, t0. */
const Live = (() => {
  const URL_BASE = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained?access_token=";
  const IN_RATE = 16000, OUT_RATE = 24000, CHUNK = 640;   // 40 ms of 16 kHz audio per message
  let inCtx = null, outCtx = null, node = null, mic = null, outGain = null, outAn = null, inAn = null;
  let meta = null, voices = [], active = null, closing = false, stopping = false, nextT = 0, raf = 0, frameT = null, timers = [];
  let acc = [], pos = 0, out = [], cur = null, pending = [], posting = false, srcs = new Set(), speaking = false, history = [];
  let queue = [], awaiting = false, awaitT = 0, lastVoice = 0, ivCount = 0, factUntil = 0, askingTask = false, taskDone = false, taskTries = 0;
  let pendingHand = null, floorAt = 0, floorExch = 0, forced = false, lastOutAt = 0, handGuard = 0, floorWatch = 0, forceGuard = 0, handing = false;
  const api = { active: false };
  const sendV = (v, o) => { if (v && v.ws && v.ws.readyState === 1) v.ws.send(JSON.stringify(o)); };
  const send = o => sendV(active, o);   // the candidate and the system talk only to whoever holds the floor
  const b64 = u8 => { let s = ""; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  /* ---------- microphone: any sample rate in, 16 kHz 16-bit PCM out, sent to the interviewer who holds the floor ---------- */
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

  /* ---------- the interviewers' voices: 24 kHz PCM chunks queued back to back (only the interviewer with the floor is ever played) ---------- */
  function startOut() {
    outCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: OUT_RATE }); outGain = outCtx.createGain(); outAn = outCtx.createAnalyser(); outAn.fftSize = 512;
    outGain.connect(outAn); outAn.connect(outCtx.destination); nextT = 0;
  }
  function play(b64data) {
    const bin = atob(b64data), u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    const i16 = new Int16Array(u8.buffer, 0, Math.floor(u8.length / 2)), buf = outCtx.createBuffer(1, i16.length, OUT_RATE), ch = buf.getChannelData(0);
    for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 0x8000;
    const s = outCtx.createBufferSource(); s.buffer = buf; s.connect(outGain); nextT = Math.max(nextT, outCtx.currentTime + 0.03); s.start(nextT); nextT += buf.duration;
    srcs.add(s); s.onended = () => { srcs.delete(s); if (!srcs.size) idle(); }; lastOutAt = Date.now();
    if (!speaking) { speaking = true; setSpeaker(active.id); setState(active.name + " is speaking"); }
  }
  function idle() { if (!speaking) return; speaking = false; setSpeaker(null); if (!stopping) setState("Listening…"); }
  function cutVoice() { srcs.forEach(s => { s.onended = null; try { s.stop(); } catch (e) { } }); srcs.clear(); nextT = 0; idle(); }   // the candidate spoke over the interviewer
  async function waitQuiet(max) { const end = Date.now() + max; while ((srcs.size || speaking) && Date.now() < end) await sleep(150); }

  /* ---------- the two indicators: speaking and listening ---------- */
  function level(an) { const d = new Uint8Array(an.fftSize); an.getByteTimeDomainData(d); let s = 0; for (const v of d) { const x = (v - 128) / 128; s += x * x; } return Math.sqrt(s / d.length); }
  function loop() {
    if (outAn && active) bars(active.id, speaking ? Math.min(1, level(outAn) * 4) : 0);
    if (inAn) { const lv = typeof muted !== "undefined" && muted ? 0 : level(inAn), on = lv > .04; $("pip").classList.toggle("talking", on); if (on) lastVoice = Date.now(); $("mestate").textContent = on ? "Speaking" : "Listening"; if (typeof levelLive === "function") levelLive(lv); }
    raf = requestAnimationFrame(loop);
  }

  /* ---------- transcript: kept for the report and shown in the side panel; every interviewer turn is saved under the interviewer who spoke it ---------- */
  function frag(role, text) {
    if (!text) return; if (cur && (cur.role !== role || (role === "interviewer" && cur.speaker !== active.id))) endTurn();
    if (!cur) cur = { role, speaker: role === "interviewer" ? active.id : null, who: role === "candidate" ? "Candidate" : active.name, text: "", node: logMsg(role === "candidate" ? "You" : active.name + ", " + active.position, "", role === "candidate" ? "c" : "i") };
    cur.text += text; const t = cur.text.replace(/\s+/g, " ").trim(); cur.node.lastChild.textContent = t; caption(t, role === "candidate"); $("msgs").scrollTop = 1e9;
  }
  function endTurn() {
    if (!cur) return; const role = cur.role, t = cur.text.replace(/\s+/g, " ").trim(), who = cur.who, sp = cur.speaker;
    if (t) { pending.push(role === "interviewer" ? { role, text: t, speaker: sp } : { role, text: t }); history.push({ who, text: t.slice(0, 500) }); if (history.length > 40) history.shift(); } cur = null; flush();
    if (t && role === "candidate") { lastCand = t; floorExch++; factUntil = Date.now() + 45000; if (buildAsked && askSent && !buildAnswered && ivCount > askIv) { buildAnswered = true; askingTask = false; maybeTask(t); } }   // a verified correction may arrive in the next few seconds
    if (t && role === "interviewer") { ivCount++; const v = voices.find(x => x.id === sp); if (v) v.spoke = (v.spoke || 0) + 1; maybeTask(); }
  }
  async function flush() {
    if (posting || !pending.length) return; posting = true; const batch = pending.splice(0, 20);
    try { await post(`/room/${SID}/live/turns/`, { turns: batch }); } catch (e) { pending.unshift(...batch); }
    posting = false; if (pending.length && !stopping) setTimeout(flush, 1500);
  }

  /* ---------- the floor: who speaks next ---------- */
  const others = () => voices.filter(v => v !== active);
  const nextVoice = () => others().find(v => !v.spoke) || voices[(voices.indexOf(active) + 1) % voices.length];
  function handoverText(to, first) {
    const ctx = history.slice(-14).map(h => h.who + ": " + h.text).join("\n").slice(-2200);
    return "YOUR TURN. You now have the floor on the call. Conversation so far (private context, never read it out):\n" + (ctx || "(nothing yet)") + "\n"
      + (first ? "This is the first time you speak: say in ONE short sentence who you are and your role. " : "") + "Then react in a few words to the candidate's last answer if it is relevant and ask ONE question from YOUR areas of the plan. Keep it to one to three short sentences, then stop and listen. You keep the floor until you hand over.";
  }
  async function doHandover(to, textOverride) {   // wait until the speaker has finished, move the microphone and the camera to the next interviewer, and give them the floor with the conversation so far
    if (handing || stopping || !to || to === active) return; handing = true; const from = active; pendingHand = null; clearTimeout(handGuard); clearTimeout(forceGuard);
    try {
      await waitQuiet(8000); if (stopping) return;
      try { await ensureOpen(to); } catch (e) { toast(to.name + " could not join the call. " + from.name + " will carry on.", true); sendV(from, { realtimeInput: { text: "Your colleague could not join. Carry on with the interview yourself." } }); return; }
      active = to; floorAt = Date.now(); floorExch = 0; forced = false; awaiting = true; clearTimeout(awaitT); awaitT = setTimeout(() => { awaiting = false; }, 20000);
      setSpeaker(null); setState(to.name + " is joining the conversation…");
      sendV(to, { realtimeInput: { text: textOverride || handoverText(to, !to.spoke) } });
      clearTimeout(floorWatch); floorWatch = setTimeout(async () => {   // the colleague never answered: take the floor back so the interview does not go silent
        if (stopping || active !== to || lastOutAt > floorAt || closing) return; toast(to.name + " did not respond. " + from.name + " will carry on.", true);
        active = from; floorAt = Date.now(); floorExch = 0; sendV(from, { realtimeInput: { text: "Your colleague could not take the floor. Carry on with the interview yourself, with your next question." } });
      }, 18000);
    } finally { handing = false; }
  }
  function askHandover(why) {   // the coordinator tells the speaker to hand over; if the model does not do it, the coordinator does it
    if (forced || closing || pendingHand || voices.length < 2) return; forced = true; const to = nextVoice();
    send({ realtimeInput: { text: `SYSTEM: ${why} Say ONE short natural line handing over to ${to.name}, who will ask about their areas, then call the pass_to tool with colleague "${to.name}". Do not ask the candidate anything first.` } }); awaiting = true; clearTimeout(awaitT); awaitT = setTimeout(() => { awaiting = false; }, 20000);
    clearTimeout(forceGuard); forceGuard = setTimeout(() => { if (!stopping && !closing && active && !handing && forced) doHandover(to); }, 22000);
  }
  function floorPolicy() {   // every interviewer gets to speak: hand over after a few exchanges, or when somebody still has not spoken
    if (stopping || closing || voices.length < 2 || speaking || awaiting || handing || pendingHand || (typeof BENCH !== "undefined" && BENCH) || Date.now() - lastVoice < 2500) return;
    const held = (Date.now() - floorAt) / 1000, el = (Date.now() - t0) / 1000, unspoken = others().some(v => !v.spoke);
    if (floorExch >= 3 || (held > 170 && floorExch >= 1) || (unspoken && el > meta.limit_s * .25 && floorExch >= 1)) askHandover("Your time with the candidate is up.");
  }

  /* ---------- messages from Gemini ---------- */
  let lastCand = "", endReason = "", endGuard = 0;
  function asksToEnd(t) {   // only a clear request to stop, in a short sentence of their own; "I finished the migration" inside a real answer never counts
    t = String(t || "").replace(/\s+/g, " ").trim(); if (!t || t.split(" ").length > 14) return false;
    return /^\W*(ok(ay)?|alright|so|well|yes|yeah|please)?\W*(i'?m|i am|we'?re|we are)\s+(done|finished)(\s+now|\s+here|\s+for\s+today|\s+with\s+(this|the)\s+(interview|meeting|call))?\W*$/i.test(t) || /\b(end|stop|finish|wrap\s+up)\s+(the|this)\s+(interview|meeting|call|session)\b/i.test(t) || /^\W*(ok(ay)?|alright|so|well|please)?\W*(let'?s|can\s+we|could\s+we|may\s+we|i\s+want\s+to|i\s+would\s+like\s+to|i'?d\s+like\s+to|i\s+need\s+to)\s+(stop|end|finish|wrap\s+up)(\s+now|\s+here|\s+this|\s+for\s+today)?\W*$/i.test(t);
  }
  function onTool(v, calls) {
    for (const fc of calls) {
      const reply = (result, note) => sendV(v, { toolResponse: { functionResponses: [{ id: fc.id, name: fc.name, response: note ? { result, note } : { result } }] } });
      const a = fc.args || {};
      if (fc.name === "pass_to") {   // a colleague is given the floor, but only after the speaker has finished the hand-over line
        const to = voices.find(x => x.name === a.colleague && x !== v);
        if (v !== active || closing || !to) { reply("refused", closing ? "The interview is closing. Do not hand over." : "That colleague is not available. Carry on yourself."); continue; }
        if (floorExch < 1) { reply("refused", "You have not heard the candidate answer yet. Ask your question and listen first."); continue; }
        reply("ok"); pendingHand = to; clearTimeout(handGuard); handGuard = setTimeout(() => { if (pendingHand) doHandover(pendingHand); }, 9000); continue;   // normally the turn ends first; this covers a missing turnComplete
      }
      if (fc.name !== "end_interview") { reply("unknown tool"); continue; }
      const el = (Date.now() - t0) / 1000, wants = asksToEnd(lastCand);
      const ok = a.reason === "finished" ? (wants || el >= meta.limit_s * .8) : a.reason === "unprofessional" ? (a.severe === true || a.warned_before === true) : false;   // the same rules the standard interview uses
      if (!ok || v !== active) { reply("refused", a.reason === "unprofessional" ? "Give the candidate one calm professional warning first, then continue the interview." : "The interview is not finished. Continue with your next question."); continue; }
      reply("ok"); endReason = a.reason; closing = true; pendingHand = null; clearTimeout(endGuard); endGuard = setTimeout(() => finish(false, endReason), 15000);   // normally the end follows the spoken goodbye; this only covers a missing turnComplete
    }
  }
  function onMsg(v, m) {
    if (m.sessionResumptionUpdate && m.sessionResumptionUpdate.newHandle) v.handle = m.sessionResumptionUpdate.newHandle;
    if (m.goAway) { v.stale = true; if (v === active) reconnect(v); return; }
    if (m.toolCall && m.toolCall.functionCalls) onTool(v, m.toolCall.functionCalls);
    if (v !== active) return;   // only the interviewer with the floor is heard, shown and saved
    const c = m.serverContent; if (!c) return;
    if (c.interrupted) { cutVoice(); endTurn(); }
    if (c.modelTurn && c.modelTurn.parts) c.modelTurn.parts.forEach(p => { if (p.inlineData && p.inlineData.data && !stopping) play(p.inlineData.data); });
    if (c.inputTranscription && c.inputTranscription.text) frag("candidate", c.inputTranscription.text);
    if (c.outputTranscription && c.outputTranscription.text) frag("interviewer", c.outputTranscription.text);
    if (c.turnComplete) {
      awaiting = false; endTurn();
      if (closing) setTimeout(() => { const wait = () => srcs.size ? setTimeout(wait, 300) : finish(false, endReason); wait(); }, 800);
      else if (pendingHand) { const to = pendingHand; setTimeout(() => doHandover(to), 400); }
    }
  }
  function connect(v, resume) {
    return new Promise((res, rej) => {
      const sock = new WebSocket(URL_BASE + encodeURIComponent(v.token)); let ready = false;
      const t = setTimeout(() => { if (!ready) { try { sock.close(); } catch (e) { } rej(new Error("The live voice did not answer in time.")); } }, 10000);
      sock.onopen = () => sock.send(JSON.stringify({ setup: Object.assign({ model: "models/" + meta.model }, resume && v.handle ? { sessionResumption: { handle: v.handle } } : {}) }));
      sock.onmessage = async ev => {
        let m; try { m = JSON.parse(typeof ev.data === "string" ? ev.data : await ev.data.text()); } catch (e) { return; }
        if (m.setupComplete && !ready) { ready = true; clearTimeout(t); v.ws = sock; v.stale = false; res(); return; }
        if (ready) onMsg(v, m);
      };
      sock.onerror = () => { if (!ready) { clearTimeout(t); rej(new Error("The live voice could not connect.")); } };
      sock.onclose = () => { if (!ready) { clearTimeout(t); rej(new Error("The live voice closed the connection.")); } else if (sock === v.ws) { v.ws = null; if (v === active && !stopping) reconnect(v); } };   // an idle interviewer reconnects only when they are given the floor
    });
  }
  async function ensureOpen(v) { if (v.ws && v.ws.readyState === 1 && !v.stale) return; await reopen(v); }
  async function reopen(v) {   // a fresh one-session token for this interviewer only, then resume their session
    const old = v.ws; v.ws = null; if (old) { old.onclose = null; try { old.close(); } catch (e) { } }
    const r = await post(`/room/${SID}/live/token/`, { iv: v.id }); const fresh = (r.voices || []).find(x => x.id === v.id); if (!fresh) throw new Error("No token."); v.token = fresh.token; await connect(v, true);
  }
  let reconnecting = false;
  async function reconnect(v) {
    if (reconnecting || stopping) return; reconnecting = true; setState("Reconnecting…");
    try { await reopen(v); setState("Listening…"); }
    catch (e) { toast("The live voice connection was lost. Press End interview to finish; what was said is saved.", true); setState("Connection lost."); }
    reconnecting = false;
  }

  /* ---------- written messages to the model, sent only when it is quiet and the candidate is not speaking, so nobody is cut off ---------- */
  function enqueue(text, kind, front, run) { const it = { text, kind, run }; if (front) queue.unshift(it); else queue.push(it); }
  function pump() {
    if (!queue.length || awaiting || speaking || stopping || handing || pendingHand || reconnecting || !active || !active.ws || active.ws.readyState !== 1 || Date.now() - lastVoice < 1500) return;
    const it = queue.shift(); if (it.run) { try { it.run(); } catch (e) { } }
    send({ realtimeInput: { text: it.text } }); awaiting = true; clearTimeout(awaitT); awaitT = setTimeout(() => { awaiting = false; }, 20000);
  }
  async function pollFacts() {   // the fact-check runs on the server; a wrong or implausible claim is passed to the interviewer who holds the floor, once
    if (stopping || Date.now() > factUntil || queue.some(q => q.kind === "fact")) return;
    try { const r = await post(`/room/${SID}/live/facts/`, {}); if (r && r.text) enqueue(r.text, "fact"); } catch (e) { }
  }

  /* ---------- hands-on task ---------- */
  let buildAsked = false, askSent = false, askIv = 0, buildAnswered = false;
  async function maybeTask(ans) {   // ans: the candidate's reply to "would you like a short coding exercise?" (only when research could not tell and the interviewer asked)
    if (taskDone || askingTask || closing || stopping || (ans === undefined && (ivCount < 4 || buildAsked)) || taskTries >= 6 || (typeof BENCH !== "undefined" && BENCH)) return;
    askingTask = true; taskTries++;
    try {
      const r = await post(`/room/${SID}/live/challenge/`, ans === undefined ? {} : { answer: ans }); if (r.final) taskDone = true;
      if (r.ask && !closing && !stopping) { buildAsked = true; enqueue("OPTIONAL CODING EXERCISE. In your own natural words and in one short sentence, ask the candidate whether they would like a short coding exercise of about five minutes. Say it is optional. Then stop and wait for their answer. If they say no, say a brief friendly okay and carry on with your normal questions.", "task", true, () => { askSent = true; askIv = ivCount; }); }
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

  /* ---------- camera: one small picture per second, only while the camera is on, sent to whoever holds the floor ---------- */
  function startFrames() {
    const cv = document.createElement("canvas"), g = cv.getContext("2d");
    frameT = setInterval(() => {
      if ((typeof camOff !== "undefined" && camOff) || document.hidden || !active || !active.ws || active.ws.readyState !== 1) return;
      const v = $("me"); if (!v.videoWidth) return; cv.width = 480; cv.height = Math.round(480 * v.videoHeight / v.videoWidth); g.drawImage(v, 0, 0, cv.width, cv.height);
      send({ realtimeInput: { video: { data: cv.toDataURL("image/jpeg", .6).split(",")[1], mimeType: "image/jpeg" } } });
    }, 1000);
  }

  /* ---------- the closing: the lead closes the meeting for everyone ---------- */
  async function startClosing() {
    if (closing || stopping) return; closing = true; pendingHand = null; clearTimeout(forceGuard);
    const text = "Time check: about 90 seconds remain. You are closing the interview for the whole panel: wrap up now with a brief closing remark, thank the candidate, say what happens next, and say goodbye. Ask no new question, not even 'do you have any questions'.";
    if (active !== voices[0]) await doHandover(voices[0], "YOUR TURN. " + text); else send({ realtimeInput: { text } });
  }

  /* ---------- public ---------- */
  api.tryStart = async function () {
    const box = $("liveconsent"); if (!box || !box.checked) return false;
    if (!stream || !stream.getAudioTracks().length) { toast("The live voice needs your microphone. Using the standard interview."); return false; }
    try {
      meta = await post(`/room/${SID}/live/token/`, {}); const list = meta.voices && meta.voices.length ? meta.voices : [Object.assign({}, meta.lead, { token: meta.token })];
      voices = list.map(x => Object.assign({ spoke: 0, ws: null, handle: null, stale: false }, x));
      startOut(); await startMic();
      const res = await Promise.allSettled(voices.map(v => connect(v, false)));
      if (res[0].status === "rejected") throw res[0].reason;   // the lead must be there; a colleague who cannot join is simply left out
      voices = voices.filter((v, i) => res[i].status === "fulfilled"); active = voices[0];
      const keep = voices.map(v => PANEL.find(p => p.id === v.id) || Object.assign({ gender: "m" }, v)); PANEL.length = 0; keep.forEach(p => PANEL.push(p)); buildStage(); layoutSquares();
    } catch (e) { cleanup(); toast((e && e.message ? e.message : "The live voice is unavailable") + " Using the standard interview."); return false; }
    api.active = true; document.body.classList.add("live-on"); setState("Listening…"); floorAt = Date.now(); floorExch = 0; active.spoke = 0;
    send({ realtimeInput: { text: meta.opening } }); startFrames(); raf = requestAnimationFrame(loop); timers.push(setInterval(pump, 600), setInterval(pollFacts, 4000), setInterval(floorPolicy, 4000));
    const lim = meta.limit_s; timers.push(setTimeout(startClosing, Math.max(30, lim - 90) * 1000));
    timers.push(setTimeout(() => finish(), (lim + 75) * 1000));   // safety net if the closing never completes
    return true;
  };
  function cleanup() {
    cancelAnimationFrame(raf); clearInterval(frameT); timers.forEach(t => { clearTimeout(t); clearInterval(t); }); timers = []; queue = []; [awaitT, handGuard, floorWatch, forceGuard, endGuard].forEach(clearTimeout);
    voices.forEach(v => { if (v.ws) { v.ws.onclose = null; try { v.ws.close(); } catch (e) { } v.ws = null; } });
    try { if (node) node.disconnect(); if (mic) mic.disconnect(); } catch (e) { }
    [inCtx, outCtx].forEach(c => { try { c && c.close(); } catch (e) { } }); inCtx = outCtx = node = mic = null; srcs.clear(); api.active = false; document.body.classList.remove("live-on");
  }
  api.stop = async function () {
    stopping = true; endTurn(); cleanup();
    for (let i = 0; i < 20 && (posting || pending.length); i++) { if (!posting) flush(); await sleep(250); }   // the last words are saved before the evaluation starts
  };
  return api;
})();
