/* ReadyWise live voice. With a panel, every interviewer has their own Gemini Live session (own voice, own key where possible). Only ONE speaks at a time:
   the candidate's microphone and camera go to the interviewer who has the floor, and that interviewer hands over by calling hand_over(to). The browser then
   waits for the voice to finish, gives the colleague the floor and catches them up on what was said since they last spoke.
   The microphone goes straight to Google's Gemini Live over a WebSocket, using a one-session token minted by the server
   (the real API key never reaches the browser). Gemini hears the raw audio, answers in audio, and handles turn-taking and interruptions itself.
   Once a second a small camera picture is sent too (sampled frames, not continuous video). The written transcript Gemini returns is saved
   by the server for the report only; it is not what the model reasons from.
   Relies on globals from room.js: $, post, toast, SID, PANEL, buildStage, layoutSquares, setSpeaker, bars, caption, logMsg, setState, camOff, stream, finish. */
const Live = (() => {
  const URL_BASE = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained?access_token=";
  const IN_RATE = 16000, OUT_RATE = 24000, CHUNK = 640;   // 40 ms of 16 kHz audio per message
  let M = [], act = 0, shared = [], switching = false, inCtx = null, outCtx = null, node = null, mic = null, outGain = null, outAn = null, inAn = null;
  let meta = null, lead = null, closing = false, stopping = false, nextT = 0, raf = 0, frameT = null, timers = [];
  let acc = [], pos = 0, out = [], cur = null, pending = [], posting = false, srcs = new Set(), speaking = false;
  let queue = [], awaiting = false, awaitT = 0, lastVoice = 0, ivCount = 0, factUntil = 0, askingTask = false, taskDone = false, taskTries = 0;
  const api = { active: false };
  const sendTo = (i, o) => { const w = M[i] && M[i].ws; if (w && w.readyState === 1) w.send(JSON.stringify(o)); };
  const send = o => sendTo(act, o);   // everything the candidate says or shows goes to the interviewer who has the floor
  const W = () => M[act] && M[act].ws;
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
    if (!cur) cur = { role, text: "", who: lead, node: logMsg(role === "candidate" ? "You" : lead.name + ", " + lead.position, "", role === "candidate" ? "c" : "i") };
    cur.text += text; const t = cur.text.replace(/\s+/g, " ").trim(); cur.node.lastChild.textContent = t; caption(t, role === "candidate"); $("msgs").scrollTop = 1e9;
  }
  /* ---------- did the model hear the right language? ---------- */
  const FOREIGN = new Set("le la les des une est que pour avec dans pas je vous nous sur el los las una es por con para como pero não uma você é que também der die das und ist nicht ich ein eine mit sich auf il di che sono una per ma non".split(" "));
  const ENGLISH = new Set("the and is to of a in that it i you we my for with was on have this are be at as so but not".split(" "));
  function foreign(t) {   // true when an answer that should be in the interview language came back in another one
    const letters = (t.match(/\p{L}/gu) || []).length; if (letters < 4) return false;
    if (meta.latin && (t.match(/\p{Script=Latin}/gu) || []).length / letters < 0.5) return true;   // another alphabet altogether
    if (meta.lang === "English") { const w = t.toLowerCase().match(/\p{L}+/gu) || []; let f = 0, e = 0; w.forEach(x => { if (FOREIGN.has(x)) f++; if (ENGLISH.has(x)) e++; }); return f >= 3 && f > e; }
    return false;
  }
  let lastNudge = 0;
  function nudgeRepeat() {   // the interviewer is told once in a while that what it "heard" was in the wrong language, and asks you to repeat
    if (Date.now() - lastNudge < 20000) return; lastNudge = Date.now();
    enqueue(`Your transcription of the candidate's last answer came out in the wrong language. The candidate speaks ${meta.lang}. Do not respond to what you thought you heard. Say in one short sentence that you did not catch that, and ask them to repeat their last answer.`, "lang", true);
  }
  function endTurn() {
    if (!cur) return; const role = cur.role; let t = cur.text.replace(/\s+/g, " ").trim(); const who = cur.who;
    if (role === "candidate" && t && meta && foreign(t)) { cur.node.lastChild.textContent = "(not understood: please repeat)"; t = ""; nudgeRepeat(); }   // never keep or evaluate a mis-heard answer if (t) { pending.push({ role, text: t, speaker: role === "candidate" ? undefined : who.id }); shared.push({ who: role === "candidate" ? "Candidate" : who.name, text: t }); } cur = null; flush();
    if (t && role === "candidate") factUntil = Date.now() + 45000;   // a verified correction may arrive in the next few seconds
    if (t && role === "interviewer") { ivCount++; maybeTask(); }
  }
  async function flush() {
    if (posting || !pending.length) return; posting = true; const batch = pending.splice(0, 20);
    try { await post(`/room/${SID}/live/turns/`, { turns: batch }); } catch (e) { pending.unshift(...batch); }
    posting = false; if (pending.length && !stopping) setTimeout(flush, 1500);
  }

  /* ---------- messages from Gemini ---------- */
  function onMsg(i, m) {
    if (m.sessionResumptionUpdate && m.sessionResumptionUpdate.newHandle) M[i].handle = m.sessionResumptionUpdate.newHandle;
    if (m.goAway) reconnect(i);
    if (m.toolCall && m.toolCall.functionCalls) m.toolCall.functionCalls.forEach(f => { if (f.name === "end_interview") endByInterviewer(i, f); else if (f.name === "hand_over") handOver(i, f); });
    const c = m.serverContent; if (!c || i !== act) return;   // a colleague who does not have the floor is never heard
    if (c.interrupted) { cutVoice(); endTurn(); }
    if (c.modelTurn && c.modelTurn.parts) c.modelTurn.parts.forEach(p => { if (p.inlineData && p.inlineData.data && !stopping) play(p.inlineData.data); });
    if (c.inputTranscription && c.inputTranscription.text) frag("candidate", c.inputTranscription.text);
    if (c.outputTranscription && c.outputTranscription.text) frag("interviewer", c.outputTranscription.text);
    if (c.turnComplete) { awaiting = false; endTurn(); if (closing) setTimeout(() => { const wait = () => srcs.size ? setTimeout(wait, 300) : finish(); wait(); }, 800); }
  }
  let endCalled = false, startedAt = Date.now();
  function endByInterviewer(i, f) {   // the interviewer decided the interview is over (finished, or the candidate was unprofessional): let the closing words play out, then end it
    const why = String((f.args && f.args.reason) || ""), left = Math.round((meta.limit_s - (Date.now() - startedAt) / 1000) / 60);
    if (why !== "unprofessional" && why !== "candidate_stopped" && left > Math.max(2, meta.limit_s / 60 * 0.15)) {   // "completed" is only accepted near the end of the chosen time
      sendTo(i, { toolResponse: { functionResponses: [{ id: f.id, name: f.name, response: { result: `Refused: about ${left} minutes of the interview are still left. Do not end it. Carry on: probe a weak answer deeper or start a new area from the plan.` } }] } }); return;
    }
    sendTo(i, { toolResponse: { functionResponses: [{ id: f.id, name: f.name, response: { result: "Interview ended. Say nothing more." } }] } });
    if (endCalled) return; endCalled = true; closing = true; queue = [];
    let waited = 0, quiet = 0;
    const t = setInterval(() => { waited += 300; quiet = (speaking || srcs.size) ? 0 : quiet + 300; if ((waited >= 3000 && quiet >= 1500) || waited >= 20000) { clearInterval(t); finish(); } }, 300);
    timers.push(t);
  }
  async function connect(i, resume) {
    const m = M[i];
    return new Promise((res, rej) => {
      const sock = new WebSocket(URL_BASE + encodeURIComponent(m.token)); let ready = false;
      const t = setTimeout(() => { if (!ready) { try { sock.close(); } catch (e) { } rej(new Error("The live voice did not answer in time.")); } }, 10000);
      const useHandle = resume && m.handle; m.fresh = !useHandle;   // a session that could not be resumed has lost its memory: it gets the whole conversation when it next speaks
      sock.onopen = () => sock.send(JSON.stringify({ setup: Object.assign({ model: "models/" + meta.model }, useHandle ? { sessionResumption: { handle: m.handle } } : {}) }));
      sock.onmessage = async ev => {
        let d; try { d = JSON.parse(typeof ev.data === "string" ? ev.data : await ev.data.text()); } catch (e) { return; }
        if (d.setupComplete && !ready) { ready = true; clearTimeout(t); m.ws = sock; res(); return; }
        if (ready) onMsg(i, d);
      };
      sock.onerror = () => { if (!ready) { clearTimeout(t); rej(new Error("The live voice could not connect.")); } };
      sock.onclose = () => { if (!ready) { clearTimeout(t); rej(new Error("The live voice closed the connection.")); } else if (sock === m.ws && !stopping) reconnect(i); };
    });
  }
  const reconnecting = {};
  async function reconnect(i) {
    if (reconnecting[i] || stopping) return; reconnecting[i] = true; const m = M[i]; if (i === act) setState("Reconnecting…");
    try { const old = m.ws; m.ws = null; if (old) { old.onclose = null; try { old.close(); } catch (e) { } } const r = await post(`/room/${SID}/live/token/`, { member: m.iv.id }); m.token = r.members[0].token; await connect(i, true); if (i === act) setState("Listening…"); }
    catch (e) { if (i === act) { toast("The live voice connection was lost. Press End interview to finish; what was said is saved.", true); setState("Connection lost."); } }
    reconnecting[i] = false;
  }

  /* ---------- the floor: one interviewer at a time ---------- */
  function catchUp(m) {   // what was said since this interviewer last spoke (everything, if their session had to start over)
    const from = m.fresh ? 0 : m.lastIdx; let t = shared.slice(from).map(x => x.who + ": " + x.text).join("\n"); if (t.length > 3500) t = "..." + t.slice(-3500); return t;
  }
  function handOver(i, f) {
    const to = String((f.args && f.args.to) || "").trim().toLowerCase();
    const j = M.findIndex((m, k) => k !== i && m.ws && (m.iv.name.toLowerCase() === to || m.iv.name.toLowerCase().split(" ")[0] === to.split(" ")[0]));
    if (i !== act || j < 0 || closing || stopping || switching) { sendTo(i, { toolResponse: { functionResponses: [{ id: f.id, name: f.name, response: { result: "Not possible now. Carry on yourself." } }] } }); return; }
    sendTo(i, { toolResponse: { functionResponses: [{ id: f.id, name: f.name, response: { result: "Handed over. Say nothing more." } }] } });
    switching = true; let waited = 0, quiet = 0;
    const t = setInterval(() => {   // let the handover line finish playing before the colleague speaks
      waited += 250; quiet = (speaking || srcs.size) ? 0 : quiet + 250;
      if ((waited >= 1000 && quiet >= 600) || waited >= 9000) { clearInterval(t); switchTo(j); }
    }, 250); timers.push(t);
  }
  function switchTo(j) {
    endTurn(); const from = M[act]; from.lastIdx = shared.length; act = j; const m = M[j]; lead = m.iv; switching = false;
    const said = catchUp(m); m.fresh = false;
    sendTo(j, { realtimeInput: { text: "YOU HAVE THE FLOOR. Here is what was said since you last spoke (the candidate's words are from the live transcript and may contain small errors):\n" + (said || "(nothing yet)") + "\nContinue the interview from here with your own areas. Reply to what the candidate last said in one sentence if it was directed at you or needs a response, introduce yourself in one short sentence if this is your first turn, then ask ONE question." } });
    awaiting = true; clearTimeout(awaitT); awaitT = setTimeout(() => { awaiting = false; }, 20000); lastVoice = 0;
  }

  /* ---------- written messages to the model, sent only when it is quiet and the candidate is not speaking, so nobody is cut off ---------- */
  function enqueue(text, kind, front, run) { const it = { text, kind, run }; if (front) queue.unshift(it); else queue.push(it); }
  function pump() {
    if (!queue.length || awaiting || speaking || stopping || switching || reconnecting[act] || !W() || W().readyState !== 1 || Date.now() - lastVoice < 1500) return;
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
      if ((typeof camOff !== "undefined" && camOff) || document.hidden || !W() || W().readyState !== 1) return;
      const v = $("me"); if (!v.videoWidth) return; cv.width = 480; cv.height = Math.round(480 * v.videoHeight / v.videoWidth); g.drawImage(v, 0, 0, cv.width, cv.height);
      send({ realtimeInput: { video: { data: cv.toDataURL("image/jpeg", .6).split(",")[1], mimeType: "image/jpeg" } } });
    }, 1000);
  }

  /* ---------- public ---------- */
  api.tryStart = async function () {
    const box = $("liveconsent"); if (!box || !box.checked) return false;
    if (!stream || !stream.getAudioTracks().length) { toast("The live voice needs your microphone. Using the standard interview."); return false; }
    try {
      meta = await post(`/room/${SID}/live/token/`, {});
      M = (meta.members || [Object.assign({ token: meta.token }, meta.lead)]).map(mm => ({ iv: PANEL.find(p => p.id === mm.id) || Object.assign({ gender: "m" }, mm), token: mm.token, ws: null, handle: null, lastIdx: 0, fresh: false }));
      act = 0; shared = []; switching = false; lead = M[0].iv; startedAt = Date.now();
      startOut(); await startMic();
      const rs = await Promise.allSettled(M.map((m, i) => connect(i, false)));
      if (rs[0].status !== "fulfilled") throw rs[0].reason;   // the chair must be live; a colleague who cannot connect simply is not on this panel
      M = M.filter((m, i) => rs[i].status === "fulfilled");
      const ivs = M.map(m => m.iv); if (ivs.length !== PANEL.length || ivs.some((p, k) => p !== PANEL[k])) { PANEL.length = 0; PANEL.push(...ivs); buildStage(); layoutSquares(); }
    } catch (e) { cleanup(); toast((e && e.message ? e.message : "The live voice is unavailable") + " Using the standard interview."); return false; }
    api.active = true; document.body.classList.add("live-on"); setState("Listening…"); if ($("vconsent")) { /* the end-of-interview snapshot consent is separate and unchanged */ }
    send({ realtimeInput: { text: meta.opening } }); startFrames(); raf = requestAnimationFrame(loop); timers.push(setInterval(pump, 600), setInterval(pollFacts, 4000));
    const lim = meta.limit_s; timers.push(setTimeout(() => { closing = true; send({ realtimeInput: { text: "Time check: about 90 seconds remain. Wrap up now: a brief closing remark, thank the candidate, and say what happens next. Ask no new question." } }); }, Math.max(30, lim - 90) * 1000));
    timers.push(setTimeout(() => finish(), (lim + 75) * 1000));   // safety net if the closing never completes
    return true;
  };
  function cleanup() {
    cancelAnimationFrame(raf); clearInterval(frameT); timers.forEach(t => { clearTimeout(t); clearInterval(t); }); timers = []; queue = []; clearTimeout(awaitT);
    M.forEach(m => { if (m.ws) { m.ws.onclose = null; try { m.ws.close(); } catch (e) { } m.ws = null; } });
    try { if (node) node.disconnect(); if (mic) mic.disconnect(); } catch (e) { }
    [inCtx, outCtx].forEach(c => { try { c && c.close(); } catch (e) { } }); inCtx = outCtx = node = mic = null; srcs.clear(); api.active = false; document.body.classList.remove("live-on");
  }
  api.stop = async function () {
    stopping = true; endTurn(); cleanup();
    for (let i = 0; i < 20 && (posting || pending.length); i++) { if (!posting) flush(); await new Promise(r => setTimeout(r, 250)); }   // the last words are saved before the evaluation starts
  };
  return api;
})();
