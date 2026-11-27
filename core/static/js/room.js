/* ReadyWise interview room controller.
   Turn cycle:  thinking (server writes the next question) -> speaking (voice, interviewer photo lights up) -> answering (we record the candidate)
                -> transcribing (server speech-to-text) -> thinking ...
   The interviewer only ever receives text that the transcription service returned (or that the candidate typed). If nothing was
   heard, no answer is sent: the interviewer asks to hear it again. Config (PANEL_ALL, LIMIT, SID, DUR, ...) comes from room.html. */
const $ = id => document.getElementById(id);
let PANEL = [], stream = null, cap = null, rec = null, chunks = [], FRAMES = [], t0 = 0, clockT = null, answerTimer = null;
let phase = "idle", token = 0, current = null, lastSpeaker = null, ending = false, interrupted = false, miss = 0, answerStart = 0, retryNext = false;
let camOff = false;
let BENCH = null, benchEnd = 0, benchT = null, lastRun = null, ALLOW_INT = false, AUTO = true, PAUSE = 1000, muted = false, wantRec = false, qCount = 0, speechAudio = null;
const SHORT = { retry: "I did not catch an answer. Please go ahead when you are ready." };
const words = t => (t.toLowerCase().match(/[a-z0-9']+/g) || []);
const icons = () => window.lucide && lucide.createIcons({ attrs: { "stroke-width": 1.75 } });
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function echoLike(t) { if (!current) return false; const w = words(t); if (!w.length) return true; const set = new Set(words(current.text)); return w.length >= 3 && w.filter(x => set.has(x)).length / w.length >= .75; }

/* ---------- setup ---------- */
PANEL = PANEL_ALL;   // the system picks the panel (1 to 3 interviewers) from the interview type and role
function row(id, state, text) { const r = $(id); r.className = "rm-row" + (state ? " " + state : ""); const t = r.querySelector("span.grow,.grow>span"); if (t) t.textContent = text; }

/* ---------- devices ---------- */
async function checkDevices() {
  try {
    if (cap) { cap.destroy(); cap = null; } if (stream) stream.getTracks().forEach(t => t.stop());
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch (e) {
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); row("chk-cam", "bad", "Camera unavailable. You can still interview with your microphone."); }
    catch (e2) { stream = null; row("chk-mic", "bad", "Microphone blocked: you can still answer by typing. Allow the microphone in your browser's address bar to speak."); row("chk-cam", "bad", "Camera and microphone blocked."); return; }
  }
  if (stream.getVideoTracks().length) {
    $("pre").srcObject = stream; const s = stream.getVideoTracks()[0].getSettings(), w = s.width || 0;
    row("chk-cam", w >= 640 ? "ok" : "", "Camera: " + (w ? w + "x" + s.height : "working") + (w && w < 640 ? " (low quality: use better light)" : ""));
    Vis.once($("pre")).then(r => { if (r !== null) row("chk-cam", r === true ? "ok" : "", $("chk-cam").textContent + (r === true ? ". Face found." : r === "dark" ? ". It is too dark to see you: turn on a light in front of you." : ". No face found yet: sit centred, with light on your face.")); });
  }
  let peak = 0;
  cap = new RWVoice.Capture(stream, {
    onLevel: l => { peak = Math.max(peak, l); $("meter") && ($("meter").style.width = Math.min(100, l * 260) + "%"); if (phase === "idle") $("mic-t").textContent = peak < .03 ? "Microphone: say a few words" : peak < .08 ? "Microphone: very quiet, move closer" : peak > .7 ? "Microphone: too loud, move back" : "Microphone: level is good"; if (phase === "answering" || phase === "speaking") levelLive(l); },
    onEnd: (blob, ms) => { if (phase === "idle") testSTT(blob); else if (phase === "answering") submitBlob(blob); },
    onStart: () => { if (phase === "answering") { $("pip").classList.add("talking"); $("mestate").textContent = "Speaking"; $("state").textContent = "Listening…"; } },
    onConfirm: () => { if (phase === "speaking" && ALLOW_INT) bargeIn(false); },
    onDiscard: () => { },
  });
  cap.open("answer", 1400); row("chk-mic", "ok", "Microphone: connected");
  row("chk-stt", "", "Speech to text: say a few words to test it");
}
async function testSTT(blob) {
  row("chk-stt", "", "Speech to text: transcribing…");
  try { const fd = new FormData(); fd.append("audio", blob, "test.webm"); const r = await post(`/room/${SID}/stt/`, fd, true);
    row("chk-stt", r.heard ? "ok" : "bad", r.heard ? "Heard: “" + r.text.slice(0, 80) + "”" : "Nothing was heard. Speak closer to the microphone, or you can type your answers."); }
  catch (e) { row("chk-stt", "bad", "Speech to text failed: " + e.message + " You can still type your answers."); }
  if (cap && phase === "idle") cap.open("answer", 1400);
}
function levelLive(l) { $("micbtn").style.setProperty("--lv", Math.min(1, l * 5).toFixed(2)); }

/* ---------- seeing the candidate: face, eye contact, expression (all in the browser) ---------- */
const Vis={ready:false,loading:null,run:false,v:null,s:{n:0,present:0,look:0,lookN:0,away:0,expr:{}},cur:{present:false,look:null,expr:"neutral"},lastSeen:0,absentSince:0,awayCounted:false,nudgeAt:0,cv:null,lum:128,base:null,cal:[],
 init(){if(this.loading)return this.loading;this.loading=(async()=>{try{for(let i=0;i<50&&!window.faceapi;i++)await new Promise(r=>setTimeout(r,100));if(!window.faceapi)return false;await Promise.all([faceapi.nets.tinyFaceDetector.loadFromUri(VMODEL),faceapi.nets.faceLandmark68TinyNet.loadFromUri(VMODEL),faceapi.nets.faceExpressionNet.loadFromUri(VMODEL)]);this.ready=true}catch(e){console.warn("Face tracking unavailable",e)}return this.ready})();return this.loading},
 /* One look at the camera. Detection and the finer measurements are separate: a face that is found always counts as "in frame", even when the landmarks fail. Dim rooms are brightened first, and a second, more sensitive pass runs before a face is declared missing. */
 frame(video){const W=320,H=Math.round(320*video.videoHeight/video.videoWidth)||240,c=this.cv||(this.cv=document.createElement("canvas"));if(c.width!==W||c.height!==H){c.width=W;c.height=H}const x=c.getContext("2d",{willReadFrequently:true});x.filter="none";x.drawImage(video,0,0,W,H);
  let lum=128;try{const d=x.getImageData(0,0,W,H).data;let t=0,n=0;for(let i=0;i<d.length;i+=64){t+=d[i]*.3+d[i+1]*.59+d[i+2]*.11;n++}lum=t/Math.max(1,n)}catch(e){}this.lum=lum;
  if(lum<100&&"filter"in x){x.filter="brightness("+Math.min(2.4,115/Math.max(25,lum)).toFixed(2)+") contrast(1.2)";x.drawImage(video,0,0,W,H);x.filter="none"}return c},
 async detect(video){const c=this.frame(video);
  for(const o of[{inputSize:320,scoreThreshold:.3},{inputSize:416,scoreThreshold:.2}]){const opt=new faceapi.TinyFaceDetectorOptions(o);let d=null;
   try{d=await faceapi.detectSingleFace(c,opt).withFaceLandmarks(true).withFaceExpressions()}catch(e){try{if(await faceapi.detectSingleFace(c,opt))return{present:true,look:null,expr:"neutral"}}catch(e2){}continue}
   if(!d)continue;const p=d.landmarks.positions,nose=p[30],le=p[36],re=p[45],chin=p[8],ed=Math.hypot(re.x-le.x,re.y-le.y)||1,yaw=(nose.x-(le.x+re.x)/2)/ed,my=(le.y+re.y)/2,pitch=(nose.y-my)/((chin.y-my)||1);
   const top=Object.entries(d.expressions).sort((a,b)=>b[1]-a[1])[0];return{present:true,yaw,pitch,look:this.facing(yaw,pitch),expr:top&&top[1]>.5?top[0]:"neutral"}}
  return{present:false,look:null,expr:"neutral"}},
 /* "Facing the screen" is measured against how THIS person sits, not against a fixed ideal: laptop cameras sit below the eyes and people read the screen from slightly off-centre. The first ~6 seconds set the baseline. */
 facing(yaw,pitch){if(!this.base){this.cal.push([yaw,pitch]);if(this.cal.length>=24){const m=a=>a.slice().sort((x,y)=>x-y)[a.length>>1];this.base={yaw:m(this.cal.map(a=>a[0])),pitch:m(this.cal.map(a=>a[1]))}}return Math.abs(yaw)<.45&&pitch>.12&&pitch<.95}
  return Math.abs(yaw-this.base.yaw)<.32&&Math.abs(pitch-this.base.pitch)<.24},
 async once(video){if(!await this.init())return null;try{for(let i=0;i<10;i++){await new Promise(r=>setTimeout(r,400));if(!video.videoWidth||video.readyState<2)continue;const r=await this.detect(video);if(r.present)return true}return this.lum<45?"dark":false}catch(e){return null}},
 async start(video){if(!await this.init()){$("vchip").textContent="Face tracking unavailable";return}this.v=video;this.run=true;this.lastSeen=Date.now();this.tick()},
 async tick(){if(!this.run)return;const t0=performance.now();
  try{if(this.v.videoWidth&&this.v.readyState>=2&&!document.hidden){const r=await this.detect(this.v),now=Date.now();
    if(r.present)this.lastSeen=now;
    const grace=now-this.lastSeen<3000,    /* a face seen in the last 3 seconds still counts: one missed frame, a blink or a glance down is not leaving the room */
          shown=r.present||grace;this.cur=shown?{present:true,look:r.present?r.look:this.cur.look,expr:r.present?r.expr:this.cur.expr}:{present:false,look:null,expr:"neutral"};
    this.s.n++;
    if(shown){this.s.present++;this.absentSince=0;this.awayCounted=false;if(r.present){this.s.expr[r.expr]=(this.s.expr[r.expr]||0)+1;if(r.look!==null){this.s.lookN++;if(r.look)this.s.look++}}}
    else{if(!this.absentSince)this.absentSince=this.lastSeen;if(!this.awayCounted&&now-this.absentSince>6000){this.s.away++;this.awayCounted=true}}
    this.react()}
  else if(document.hidden){this.lastSeen=Date.now()}}catch(e){}
  setTimeout(()=>this.tick(),Math.max(80,300-(performance.now()-t0)))},
 react(){const c=this.cur,chip=$("vchip"),gone=!c.present&&this.absentSince&&Date.now()-this.absentSince>4000,dark=this.lum<45;chip.className="chip"+(gone?" warn":"");
  chip.textContent=!c.present?(gone?(dark?"Too dark to see you":"Not in view"):"Looking for you…"):"In frame"+(c.look===null?"":" · "+(c.look?"facing screen":"looking away"))+" · "+c.expr;
  if(gone&&phase==="answering"&&Date.now()-this.absentSince>12000&&Date.now()-this.nudgeAt>45000){this.nudgeAt=Date.now();$("state").textContent="The panel can't see you. Please come back into the frame.";if(current)browserSay(current.speaker,"Are you still there?",()=>{})}},
 summary(){const s=this.s;if(!s.n)return null;const e={};for(const[k,v]of Object.entries(s.expr)){const pc=Math.round(100*v/Math.max(1,s.present));if(pc>=5)e[k]=pc}return{samples:s.n,present_pct:Math.round(1000*s.present/s.n)/10,eye_contact_pct:s.lookN?Math.round(1000*s.look/s.lookN)/10:0,away_events:s.away,expressions:e}},
 stop(){this.run=false}};
/* ---------- the stage ---------- */
function buildStage() {
  const st = $("stage"); st.dataset.n = PANEL.length; st.innerHTML = "";
  layoutSquares(); PANEL.forEach(p => { const d = document.createElement("div"); d.className = "rm-tile"; d.id = "tile" + p.id;
    d.innerHTML = `<img class="photo" src="${esc(p.image)}" alt=""><div class="rm-bars"><i></i><i></i><i></i><i></i><i></i></div><div class="rm-plate"><div class="who"><b>${esc(p.name)}</b><small>${esc(p.position)}</small></div><span class="rm-state">Listening</span></div>`;
    st.appendChild(d); });
}
/* Everyone in the room, the interviewers and you, sits in an equal square, like a video call. The size is the biggest square that fits all of them in the space available. */
function layoutSquares() {
  const a = document.querySelector(".rm-arena"); if (!a) return; const host = a.parentElement, cs = getComputedStyle(host);
  const n = PANEL.length + 1, gap = 12, W = host.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight), H = a.clientHeight; if (W <= 0 || !H) return;
  let best = 80, cols = n; for (let c = 1; c <= n; c++) { const r = Math.ceil(n / c), s = Math.min((W - gap * (c - 1)) / c, (H - gap * (r - 1)) / r); if (s > best + 1) { best = s; cols = c; } }
  a.style.setProperty("--sq", Math.floor(Math.min(best, 440)) + "px"); a.style.setProperty("--cols", cols);   // the grid is exactly as wide as its columns, so the squares form clean rows
}
window.addEventListener("resize", layoutSquares);
if (window.ResizeObserver) { const _a = document.querySelector(".rm-arena"); if (_a) { new ResizeObserver(layoutSquares).observe(_a); new ResizeObserver(layoutSquares).observe(_a.parentElement); } }
function setSpeaker(id, label) {
  document.querySelectorAll(".rm-tile").forEach(t => { const on = id && t.id === "tile" + id; t.classList.toggle("on", !!on); if (!on) t.classList.remove("talking"); t.querySelector(".rm-state").textContent = on ? (label || "Speaking") : "Listening"; });
}
function bars(id, lv) { const t = $("tile" + id); if (!t) return; t.classList.toggle("talking", lv > .04); t.querySelectorAll(".rm-bars i").forEach((b, i) => b.style.height = (4 + Math.min(1, lv * (1 + i % 3 * .35)) * 12) + "px"); }
function caption(text, me) { const p = $("cap"); p.textContent = text || ""; p.className = me ? "me" : ""; }
function logMsg(who, text, cls) { const d = document.createElement("div"); d.className = "rm-msg " + cls; d.innerHTML = "<b></b><div></div>"; d.firstChild.textContent = who; d.lastChild.textContent = text; $("msgs").appendChild(d); $("msgs").scrollTop = 1e9; return d; }
function setState(t) { $("state").textContent = t; }
function progress(d) {   // the length of the interview is the clock, not a number of questions
  const k = (d.n || qCount) - PANEL.length;
  $("qlabel").textContent = BENCH ? "Hands-on task" : d.intro || k < 1 ? "Introductions" : d.end ? "Closing" : `Question ${k}`;
  tickBar();
}
function tickBar() { if (t0) $("pbar").style.width = Math.min(100, (Date.now() - t0) / (DUR * 60000) * 100) + "%"; }

/* ---------- the interviewer's voice ---------- */
function voiceFor(p) { const v = speechSynthesis.getVoices().filter(x => x.lang.startsWith("en")), f = v.filter(x => /female|samantha|zira|susan|aria|jenny/i.test(x.name)), m = v.filter(x => !f.includes(x)), pool = p.gender === "f" ? f : m; return (pool.length ? pool : v)[p.id % Math.max(1, pool.length || v.length)]; }
function browserSay(p, text, cb) {
  const u = new SpeechSynthesisUtterance(text), vo = voiceFor(p); if (vo) u.voice = vo; u.pitch = p.pitch; u.rate = p.rate;
  let pulse = 0; u.onboundary = e => { if (e.name === "word") { bars(p.id, .5 + (pulse++ % 3) * .15); clearTimeout(browserSay.t); browserSay.t = setTimeout(() => bars(p.id, 0), 220); } };   // the browser voice gives no audio to analyse: a small pulse per real word
  u.onend = cb; u.onerror = cb; speechSynthesis.cancel(); speechSynthesis.speak(u);
}
let actx = null;
async function playVoice(p, body, text, fin) {
  const my = ++token; let done = false, started = false; const end = () => { if (done || my !== token) return; done = true; fin(); };
  const getPart = async i => { const r = await fetch(`/room/${SID}/tts/`, { method: "POST", headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json" }, body: JSON.stringify({ ...body, part: i }) }); if (!r.ok) throw 0; return { blob: await r.blob(), n: +(r.headers.get("X-Parts") || 1) }; };
  const playBlob = blob => new Promise((res, rej) => {   // one piece of the reply, with the mouth-bars following the real audio
    const a = new Audio(URL.createObjectURL(blob)); speechAudio = a; const an = actx.createAnalyser(); an.fftSize = 256; const b = new Uint8Array(an.fftSize); actx.createMediaElementSource(a).connect(an); an.connect(actx.destination);
    a.onended = () => { bars(p.id, 0); res(); }; a.onerror = () => rej(new Error("audio")); a.play().catch(rej);
    (function loop() { if (a.ended || a.paused) return; an.getByteTimeDomainData(b); let m = 0; for (const v of b) m = Math.max(m, Math.abs(v - 128) / 128); bars(p.id, m * 2); requestAnimationFrame(loop); })();
  });
  try {
    if (NON_EN) throw 0;
    const first = await getPart(0); if (my !== token) return;   // the first sentence arrives on its own, so the voice starts at once
    const rest = []; for (let i = 1; i < Math.max(1, first.n); i++) rest.push(getPart(i).catch(() => null));   // the other pieces are being made while the first one plays
    phase = "speaking"; setSpeaker(p.id); if (cap && ALLOW_INT) cap.open("watch"); actx = actx || new AudioContext(); await actx.resume(); started = true;
    await playBlob(first.blob);
    for (const pr of rest) { if (my !== token) return; const r = await pr; if (!r || my !== token) break; await playBlob(r.blob); }
    end();
  } catch (e) {
    if (my !== token) return; if (started) { end(); return; }   // a later piece failed: never say the first part twice
    phase = "speaking"; setSpeaker(p.id); if (cap && ALLOW_INT) cap.open("watch"); browserSay(p, text, end);
  }
}
function stopSpeech() { token++; try { speechSynthesis.cancel(); } catch (e) { } if (speechAudio) { try { speechAudio.pause(); } catch (e) { } speechAudio = null; } document.querySelectorAll(".rm-tile").forEach(t => t.classList.remove("talking")); }

/* ---------- the conversation ---------- */
async function next(answer, tag) {
  phase = "thinking"; setState("The panel is thinking…"); setSpeaker(null); $("send").disabled = true; $("pip").classList.remove("talking"); $("mestate").textContent = "Ready";
  try {
    const d = await post(`/room/${SID}/turn/`, { answer, tag }); if (ending) return; retryNext = false; current = d; lastSpeaker = d.speaker; qCount = d.n; progress(d);
    logMsg(d.speaker.name + ", " + d.speaker.position, d.text, "i"); caption(d.text); setSpeaker(d.speaker.id); setState(d.speaker.name + " is speaking" + (ALLOW_INT && cap ? " (start talking to interrupt)" : ""));
    if (d.challenge) openBench(d.challenge);
    playVoice(d.speaker, { turn_id: d.turn_id }, d.text, () => { setSpeaker(null); if (d.end) { setState(d.reason === "unprofessional" ? "The interviewer is ending the interview…" : "The panel is closing the meeting…"); setTimeout(() => finish(false, d.reason), 900); return; } if (d.intro) { next(null); return; } startAnswer(); });
  } catch (e) { toast(e.message, true); phase = "error"; retryNext = true; $("send").disabled = false; setState("Something failed. Press Done answering to retry."); }
}
function startAnswer(fromBarge) {
  phase = "answering"; answerStart = Date.now(); $("send").disabled = false; setSpeaker(null); setState("Your turn. Speak, the panel is listening."); $("typed").value = ""; $("live-text").textContent = "";
  if (cap && !muted) { if (fromBarge) cap.promote(AUTO && !BENCH ? PAUSE : 6e8); else cap.open("answer", AUTO && !BENCH ? PAUSE : 6e8); }
  else { setState("Type your answer below."); $("typebox").classList.add("show"); $("typed").focus(); }
  if (BENCH) setState("Hands-on task: talk through your thinking if you like, and press Submit solution when you are ready.");
  if (LIMIT && !BENCH) { let left = LIMIT; $("limitbox").textContent = left + "s"; clearInterval(answerTimer); answerTimer = setInterval(() => { left--; $("limitbox").textContent = left + "s"; if (left <= 0) { clearInterval(answerTimer); doneAnswering(); } }, 1000); }
}
function bargeIn(manual) {
  if (phase !== "speaking" || (current && current.end)) return;   // the closing words are never interrupted const who = lastSpeaker; stopSpeech(); interrupted = true;
  startAnswer(!manual); setState("You have the floor."); if (manual && !cap) toast("Type your answer, then press Send.");
}
async function doneAnswering() {
  if (phase === "error" && retryNext) { next(null); return; }
  if (phase !== "answering") return; clearInterval(answerTimer); $("limitbox").textContent = "";
  const typedText = $("typed").value.trim(); if (typedText) { sendTyped(); return; }
  const blob = cap ? await cap.close() : null; submitBlob(blob);
}
function sendTyped() {
  const t = $("typed").value.trim(); if (!t || (phase !== "answering" && phase !== "idle")) return; if (cap) cap.close(); clearInterval(answerTimer); $("limitbox").textContent = "";
  $("typed").value = ""; phase = "thinking"; logMsg("You", t, "c"); caption(t, true); const tg = interrupted ? "interrupted" : undefined; interrupted = false; miss = 0; next(t, tg);
}
async function submitBlob(blob) {
  if (phase !== "answering") return; phase = "transcribing"; $("pip").classList.remove("talking"); $("mestate").textContent = "Ready"; clearInterval(answerTimer); $("limitbox").textContent = "";
  if (!blob || blob.size < 1500) return noSpeech();
  setState("Transcribing what you said…"); const pend = logMsg("You", "Transcribing…", "c pend");
  try {
    const fd = new FormData(); fd.append("audio", blob, "answer.webm"); const r = await post(`/room/${SID}/stt/`, fd, true);
    if (!r.heard || echoLike(r.text)) { pend.remove(); return noSpeech(); }
    pend.classList.remove("pend"); pend.lastChild.textContent = r.text; caption(r.text, true); miss = 0;
    const tg = interrupted ? "interrupted" : (answerStart && Date.now() - answerStart > 150000 ? "cut_off" : undefined); interrupted = false; next(r.text, tg);
  } catch (e) {
    pend.remove(); phase = "answering"; toast(e.message, true); setState("I couldn't transcribe that. Type your answer below, or press Done answering to retry.");
    $("typebox").classList.add("show"); $("typed").focus();
  }
}
async function noSpeech() {
  /* Nothing usable was heard. This is never written into the transcript. If a stray noise cut the interviewer off, the same question is simply played again;
     if the candidate really said nothing, the interviewer asks once, politely, and after three misses the panel moves on. */
  miss++; const p = lastSpeaker || PANEL[0], noise = interrupted;
  if (miss > 2) { miss = 0; next("", interrupted ? "interrupted" : undefined); interrupted = false; return; }
  interrupted = false; setSpeaker(p.id); setState(p.name + " is speaking");
  if (noise && current && current.turn_id) { caption(current.text); playVoice(p, { turn_id: current.turn_id }, current.text, () => { setSpeaker(null); startAnswer(); }); return; }
  caption(SHORT.retry); playVoice(p, { say: "retry", speaker_id: p.id }, SHORT.retry, () => { setSpeaker(null); startAnswer(); });
}
function toggleMute() {
  muted = !muted; if (stream) stream.getAudioTracks().forEach(t => t.enabled = !muted); if (cap) cap.muted = muted;
  const b = $("micbtn"); b.classList.toggle("muted", muted); b.setAttribute("aria-label", muted ? "Unmute microphone" : "Mute microphone"); b.innerHTML = `<i data-lucide="${muted ? "mic-off" : "mic"}" width="18"></i><span>${muted ? "Unmute" : "Mute"}</span>`; icons();
  if (muted) $("typebox").classList.add("show");
}
function toggleCam() {
  const vt = stream ? stream.getVideoTracks() : [];
  if (!vt.length) { toast("No camera is connected."); return; }
  camOff = !camOff; vt.forEach(t => t.enabled = !camOff);
  $("pip").classList.toggle("nocam", camOff);
  const b = $("cambtn"); b.classList.toggle("off", camOff); b.setAttribute("aria-pressed", String(camOff));
  b.setAttribute("aria-label", camOff ? "Turn camera on" : "Turn camera off"); b.title = camOff ? "Turn camera on" : "Turn camera off";
  b.innerHTML = `<i data-lucide="${camOff ? "video-off" : "video"}" width="18"></i><span>Camera</span>`; icons();
  if (camOff) { Vis.stop(); $("vchip").textContent = "Camera off"; }   // a switched-off camera sends black frames: do not read them as "not in view"
  else if ($("vtrack").checked) Vis.start($("me"));
}
function toggleType() { $("typebox").classList.toggle("show"); if ($("typebox").classList.contains("show")) $("typed").focus(); }
$("typed").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendTyped(); } });


/* ---------- hands-on task: the panel sets something to build, done on this page ---------- */
const LANG_NOTE = { javascript: "Checks run in your browser", python: "Not run here: the panel reads it", java: "Not run here: the panel reads it", cpp: "Not run here: the panel reads it", sql: "Not run here: the panel reads it", other: "Not run here: the panel reads it" };
function openBench(ch) {
  BENCH = ch; lastRun = null; const code = ch.format === "code"; $("live").classList.add("build"); $("b-title").textContent = ch.title; renderBrief(ch); $("b-res").innerHTML = "";
  $("b-code").value = ch.starter || ""; $("b-code").classList.toggle("prose", !code); $("b-code").placeholder = code ? "// Write your solution here" : "Write your answer here";
  $("b-lang").style.display = $("b-run").style.display = code ? "" : "none"; $("b-lang").value = "javascript"; langNote(); $("b-run").disabled = false;
  benchEnd = Date.now() + ch.minutes * 60000; clearInterval(benchT);
  benchT = setInterval(() => { const left = Math.max(0, Math.round((benchEnd - Date.now()) / 1000)), c = $("b-clock"); c.textContent = "Suggested time left: " + Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0"); c.classList.toggle("low", left < 60); if (left <= 0) { clearInterval(benchT); toast("Time is up for the task. Submit what you have."); } }, 500);
  setTimeout(() => $("b-code").focus(), 600); icons();
}
function renderBrief(ch) {   // the task as short labelled lines, easy to scan: Scenario, Your task, Input, Output, Example, Note
  const box = $("b-brief"); box.textContent = "";
  const parts = ch.parts && ch.parts.length ? ch.parts : [{ label: "", text: ch.brief }];
  parts.forEach(p => { const row = document.createElement("div"); row.className = "b-row"; if (p.label) { const l = document.createElement("b"); l.textContent = p.label; row.appendChild(l); } const t = document.createElement(/^(Input|Output|Example)$/.test(p.label) ? "code" : "span"); t.textContent = p.text; row.appendChild(t); box.appendChild(row); });
}
function langNote() { const l = $("b-lang").value, js = l === "javascript"; $("b-note").textContent = BENCH && BENCH.format === "code" ? LANG_NOTE[l] : "Written task: the panel reads your answer"; $("b-run").disabled = !js || !(BENCH && BENCH.tests && BENCH.tests.length); }
$("b-lang").addEventListener("change", langNote);
$("b-code").addEventListener("input", () => { lastRun = null; });
$("b-code").addEventListener("keydown", e => { if (e.key === "Tab" && !$("b-code").classList.contains("prose")) { e.preventDefault(); const t = e.target, a = t.selectionStart; t.value = t.value.slice(0, a) + "  " + t.value.slice(t.selectionEnd); t.selectionStart = t.selectionEnd = a + 2; lastRun = null; } });
const show = v => { try { const s = JSON.stringify(v); return s.length > 60 ? s.slice(0, 57) + "…" : s; } catch (e) { return String(v); } };
async function runChecks() {
  if (!BENCH || BENCH.format !== "code" || $("b-lang").value !== "javascript") return; $("b-run").disabled = true; $("b-res").innerHTML = '<span class="n">Running…</span>';
  const r = await RWBench.run($("b-code").value, BENCH.tests); $("b-run").disabled = false;
  if (r.fatal) { lastRun = { fatal: r.fatal }; $("b-res").innerHTML = '<span class="f"></span>'; $("b-res").firstChild.textContent = r.fatal; return; }
  const n = r.results.filter(x => x.ok).length; lastRun = { n, total: r.results.length, fails: r.results.filter(x => !x.ok).slice(0, 3) };
  $("b-res").innerHTML = ""; const head = document.createElement("div"); head.className = n === r.results.length ? "p" : "n"; head.textContent = n + " of " + r.results.length + " checks passed"; $("b-res").appendChild(head);
  r.results.forEach(x => { const d = document.createElement("div"); d.className = x.ok ? "p" : "f"; d.textContent = (x.ok ? "✓ " : "✗ ") + "solve(" + x.args.map(show).join(", ") + ")" + (x.ok ? "" : x.err ? ": " + x.err : ": expected " + show(x.expected) + ", got " + show(x.got)); $("b-res").appendChild(d); });
}
async function submitBuild() {
  if (!BENCH) return; const code = $("b-code").value.trim(); if (code.length < 5) { toast("Write something first."); return; }
  const LV = typeof Live !== "undefined" && Live.active;   // live voice mode: the conversation never stops, so there is no turn to wait for
  if (!LV) { if (phase === "speaking") stopSpeech(); if (phase !== "answering" && phase !== "speaking" && phase !== "error") { toast("Wait for the panel to finish speaking."); return; } }
  clearInterval(answerTimer); clearInterval(benchT); if (cap) { try { await cap.close(); } catch (e) { } }
  if ($("b-lang").value === "javascript" && BENCH.format === "code" && BENCH.tests.length && !lastRun) await runChecks();
  const lang = BENCH.format === "code" ? $("b-lang").selectedOptions[0].textContent.split(" ")[0] : "written";
  const checks = lastRun && !lastRun.fatal ? `Automatic checks (run in the candidate's browser): ${lastRun.n} of ${lastRun.total} passed.` + (lastRun.fails.length ? " Failed: " + lastRun.fails.map(x => "solve(" + x.args.map(show).join(", ") + ") expected " + show(x.expected) + (x.err ? " but threw " + x.err : " got " + show(x.got))).join("; ") : "") : lastRun && lastRun.fatal ? "Automatic checks could not run: " + lastRun.fatal : "Automatic checks were not run.";
  const text = `Task: ${BENCH.title}\nFormat: ${lang}\n${checks}\n\n${code}`.slice(0, 8500);
  logMsg("You, submitted solution (" + lang + ")", code.length > 400 ? code.slice(0, 400) + "…" : code, "c"); BENCH = null; $("live").classList.remove("build"); caption("Thanks, let me look at that.", false);
  if (LV) { Live.submit(text); return; } phase = "thinking"; miss = 0; interrupted = false; next(text, "build");
}

/* ---------- start and finish ---------- */
function enterRoom() {   // the interview takes the whole screen: only the panel, you, the transcript and the controls
  document.body.classList.add("in-room");
  try { const el = document.documentElement; if (!document.fullscreenElement && el.requestFullscreen) el.requestFullscreen().catch(() => { }); } catch (e) { }
}
async function begin() {
  enterRoom();   // first, while the click still counts as a user gesture (browsers only allow full screen from one)
  $("go").disabled = true; $("go").lastChild.textContent = "Joining…";
  if (!stream && !cap) await checkDevices();
  ALLOW_INT = $("allowint").checked && !!cap; AUTO = $("autosend").checked; PAUSE = +$("pause").value; wantRec = $("consent").checked && !!stream;
  $("setup").classList.add("hidden"); $("live").classList.remove("hidden"); buildStage(); setState("Your panel is joining…");
  if (stream && stream.getVideoTracks().length) { $("me").srcObject = stream; if ($("vtrack").checked) Vis.start($("me")); else $("vchip").textContent = "Face tracking off"; } else $("pip").classList.add("nocam");
  if (wantRec && window.MediaRecorder) { rec = new MediaRecorder(stream); rec.ondataavailable = e => e.data.size && chunks.push(e.data); rec.start(1000); }
  if ($("vconsent").checked && stream && stream.getVideoTracks().length) { const cv = document.createElement("canvas"), snap = () => { const v = $("me"); if (camOff || FRAMES.length >= 5 || !v.videoWidth) return; cv.width = 320; cv.height = Math.round(320 * v.videoHeight / v.videoWidth); cv.getContext("2d").drawImage(v, 0, 0, cv.width, cv.height); FRAMES.push(cv.toDataURL("image/jpeg", .6).split(",")[1]); }; setTimeout(snap, 8000); setInterval(snap, 40000); }
  if (cap) cap.close();  // the setup test window is done
  rwCountdown({ title: "Interview starting", sub: "Your panel is joining the room. Take a breath.", onDone: () => { t0 = Date.now(); clockT = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); $("clock").textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); tickBar(); }, 1000); speechSynthesis.getVoices(); Live.tryStart().then(ok => { if (!ok) next(null); }); } });
}
/* ---------- closing the meeting: everyone leaves, then the AI works while an animation plays until the report is ready ---------- */
const sleep = ms => new Promise(r => setTimeout(r, ms));
const END_MSGS = ["Reading back through your answers…", "Checking the facts you stated…", "Scoring each area…", "Writing your feedback…", "Almost ready…"];
let endT = null;
async function leaveRoom() {   // the interviewers leave one by one, like people leaving a video call
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  for (const p of PANEL) {
    const t = $("tile" + p.id); if (!t) continue; t.classList.remove("on", "talking"); t.classList.add("left");
    const st = t.querySelector(".rm-state"); if (st) st.textContent = "Left the meeting"; caption(p.name + " left the meeting"); await sleep(calm ? 250 : 850);
  }
  await sleep(calm ? 150 : 600);
}
function showEnding(title) {
  if ($("rm-end")) return; const o = document.createElement("div"); o.id = "rm-end"; o.setAttribute("role", "status"); o.setAttribute("aria-live", "polite");
  o.innerHTML = '<div class="orb"><span class="ring"></span><span class="ring r2"></span><span class="core"></span></div><b id="rm-end-h"></b><p id="rm-end-tx"></p><div class="dots"><i></i><i></i><i></i></div>';
  document.body.appendChild(o); $("rm-end-h").textContent = title || "The interview has ended"; requestAnimationFrame(() => o.classList.add("on"));
  let i = 0; const tx = $("rm-end-tx"); tx.textContent = "The panel is preparing your report…";
  clearInterval(endT); endT = setInterval(() => { tx.textContent = END_MSGS[i % END_MSGS.length]; i++; }, 2600);
}
function hideEnding() { clearInterval(endT); const o = $("rm-end"); if (o) { o.classList.remove("on"); setTimeout(() => o.remove(), 500); } }
function endByUser() { finish(true); }   // End interview: the panel leaves, then the animation plays until the report is ready
async function finish(byUser, reason) {   // reason: why the interviewer ended it ("finished" or "unprofessional"), empty when the clock or the candidate did
  if (ending) return; ending = true; phase = "idle"; Vis.stop(); clearInterval(answerTimer); clearInterval(benchT); stopSpeech(); setSpeaker(null); $("limitbox").textContent = ""; $("live").classList.remove("build");
  document.querySelectorAll(".rm-ctl .rm-btn").forEach(b => b.disabled = true); $("typebox").classList.remove("show");
  setState(byUser ? "You ended the interview." : reason === "unprofessional" ? "The interviewer ended the interview." : "The interview has ended.");
  const liveStop = (typeof Live !== "undefined" && Live.active) ? Live.stop() : Promise.resolve();   // saves the last words while the panel leaves
  await leaveRoom(); showEnding(byUser ? "The interview has ended" : reason === "unprofessional" ? "The interviewer ended the interview" : "The interview has ended"); const shown = sleep(4000); await liveStop; clearInterval(clockT);
  if (cap) { try { await cap.close(); } catch (e) { } cap.destroy(); }
  const stop = new Promise(r => { if (rec && rec.state !== "inactive") { rec.onstop = r; rec.stop(); } else r(); }); await stop;
  let upload = Promise.resolve();   // the recording uploads while the evaluation runs; the report opens as soon as both are done (the upload is waited for at most 3 s more)
  if (chunks.length) { const f = new FormData(); f.append("rec", new Blob(chunks, { type: "video/webm" }), "session.webm"); upload = post(`/room/${SID}/recording/`, f, true).catch(() => { }); }
  if (stream) stream.getTracks().forEach(t => t.stop());
  try {
    const d = await post(`/room/${SID}/finish/`, { frames: FRAMES, camera: Vis.summary(), reason: reason || "" });
    if (d.job) await pollJob(d.job, () => { }, 350); await Promise.race([upload, new Promise(r => setTimeout(r, 3000))]);
    await shown; $("rm-end").classList.add("done"); await sleep(700); location.href = d.url;   // the animation always plays to its end before the report opens
  } catch (e) { toast(e.message, true); hideEnding(); ending = false; document.querySelectorAll(".rm-ctl .rm-btn").forEach(b => b.disabled = false); }
}
