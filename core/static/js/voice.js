/* ReadyWise voice capture: records what the candidate says and tells the room when they start and stop talking.

   Vad is a pure state machine (testable in Node: node tests/js/voice.test.js). Capture wires it to the microphone:
   an AnalyserNode supplies the loudness, a MediaRecorder keeps the audio of each answer. The recording, not the browser's
   dictation, is what gets transcribed on the server, so it works in every browser that has a microphone. */
(function (root) {
  "use strict";

  class Vad {
    /* feed(level 0..1, dtMs) -> list of events: "start" (voice began), "confirm" (it is sustained, not a click), "end" (they stopped; carries ms of speech), "discard" (too short to be speech) */
    constructor(o) { this.o = Object.assign({ startMs: 110, confirmMs: 380, endMs: 1500, minSpeechMs: 320, minThreshold: 0.012, ratio: 3.2 }, o || {}); this.floor = 0.006; this.calib = 1000; this.reset(); }
    // reset() starts a new listening window but keeps what was learned about the room's noise; the first second after the mic opens is spent learning it
    reset() { this.state = "idle"; this.voiced = 0; this.quiet = 0; this.speech = 0; this.loud = 0; this.confirmed = false; }
    get threshold() { return Math.max(this.o.minThreshold, this.floor * this.o.ratio); }
    setEnd(ms) { this.o.endMs = ms; }
    feed(level, dt) {
      const ev = [];
      if (this.calib > 0) { this.calib -= dt; this.floor += (level - this.floor) * Math.min(1, dt / 250); return ev; }
      const loud = level > this.threshold;
      if (!loud && this.state === "idle") this.floor += (level - this.floor) * Math.min(1, dt / 800);   // learn the room noise only while nobody is talking
      if (this.state === "idle") {
        this.voiced = loud ? this.voiced + dt : 0;
        if (this.voiced >= this.o.startMs) { this.state = "speech"; this.speech = this.voiced; this.loud = this.voiced; this.quiet = 0; this.confirmed = false; ev.push("start"); }
      } else {
        this.speech += dt; if (loud) this.loud += dt; this.quiet = loud ? 0 : this.quiet + dt;
        if (!this.confirmed && this.loud >= this.o.confirmMs) { this.confirmed = true; ev.push("confirm"); }
        if (this.quiet >= this.o.endMs || (!this.confirmed && this.quiet >= 240)) {
          const ms = this.speech - this.quiet; this.state = "idle"; this.voiced = 0;
          ev.push(this.loud >= this.o.minSpeechMs ? "end" : "discard"); this.lastMs = ms;
        }
      }
      return ev;
    }
  }

  const MIMES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  const pickMime = () => (root.MediaRecorder && MediaRecorder.isTypeSupported) ? (MIMES.find(m => MediaRecorder.isTypeSupported(m)) || "") : "";

  class Capture {
    /* handlers: onLevel(level), onStart(), onConfirm(), onEnd(blob, ms), onDiscard() */
    constructor(stream, h) {
      this.h = h || {}; this.vad = new Vad(); this.rec = null; this.parts = []; this.on = false; this.mime = pickMime();
      this.audio = new MediaStream(stream.getAudioTracks()); const AC = root.AudioContext || root.webkitAudioContext; this.ctx = new AC();
      this.an = this.ctx.createAnalyser(); this.an.fftSize = 1024; this.buf = new Uint8Array(this.an.fftSize); this.ctx.createMediaStreamSource(this.audio).connect(this.an);
      this.last = performance.now(); this.keepRolling = false; this.since = 0; this.muted = false;
      this.timer = setInterval(() => this.tick(), 40);
    }
    level() { this.an.getByteTimeDomainData(this.buf); let s = 0; for (const v of this.buf) { const x = (v - 128) / 128; s += x * x } return Math.sqrt(s / this.buf.length); }
    startRec() { if (this.rec || !root.MediaRecorder) return; this.parts = []; try { this.rec = new MediaRecorder(this.audio, this.mime ? { mimeType: this.mime } : undefined); } catch (e) { this.rec = null; return; }
      this.rec.ondataavailable = e => e.data && e.data.size && this.parts.push(e.data); this.rec.start(250); }
    stopRec() { return new Promise(res => { const r = this.rec; this.rec = null; if (!r || r.state === "inactive") return res(null);
      r.onstop = () => res(this.parts.length ? new Blob(this.parts, { type: (r.mimeType || this.mime || "audio/webm").split(";")[0] }) : null); try { r.stop() } catch (e) { res(null) } }); }
    /* window: "answer" records from now on (the candidate's turn). "watch" only listens for them talking over the interviewer. */
    open(mode, endMs) { this.mode = mode; this.on = true; this.vad.reset(); this.vad.setEnd(endMs || 1500); this.since = 0; this.ctx.resume && this.ctx.resume();
      this.ratio = 3.2; this.minT = 0.012;
      /* watch mode (candidate talking over the interviewer) is very strict so a cough, a click, a fan or the interviewer's own voice leaking from the speakers never counts:
         clearly louder than the room, for a full second and a half of real speech, and never in the first 1.8 s of the interviewer's sentence. */
      if (mode === "watch") Object.assign(this.vad.o, { ratio: 9, minThreshold: 0.07, startMs: 350, confirmMs: 1500, minSpeechMs: 1200 }); else Object.assign(this.vad.o, { ratio: 3.2, minThreshold: 0.012, startMs: 110, confirmMs: 380, minSpeechMs: 320 });
      if (mode === "answer") this.startRec(); }
    /* the candidate started talking over the interviewer: the clip already running becomes their answer (no words lost) */
    promote(endMs) { this.mode = "answer"; this.vad.setEnd(endMs || 1500); Object.assign(this.vad.o, { ratio: 3.2, minThreshold: 0.012, startMs: 110, confirmMs: 380, minSpeechMs: 320 }); this.since = 0; }
    async close() { this.on = false; const b = await this.stopRec(); return b; }
    async tick() {
      const now = performance.now(), dt = Math.min(120, now - this.last); this.last = now; const lv = this.muted ? 0 : this.level(); if (this.h.onLevel) this.h.onLevel(lv);
      if (!this.on) return; this.since += dt;
      if (this.mode === "watch" && this.since < 1800) { this.vad.reset(); return; }   // grace period at the start of every interviewer sentence
      for (const e of this.vad.feed(lv, dt)) {
        if (e === "start") { if (this.mode === "watch") this.startRec(); if (this.h.onStart) this.h.onStart(); }
        else if (e === "confirm") { if (this.h.onConfirm) this.h.onConfirm(); }
        else if (e === "discard") { if (this.mode === "watch") { await this.stopRec(); } if (this.h.onDiscard) this.h.onDiscard(); }
        else if (e === "end") { const ms = this.vad.lastMs, b = await this.stopRec(); this.on = false; if (this.h.onEnd) this.h.onEnd(b, ms); }
      }
      // a long wait with no speech: drop the silent audio so the next clip stays small and Whisper never sees minutes of nothing
      if (this.on && this.mode === "answer" && this.vad.state === "idle" && this.since > 9000) { await this.stopRec(); this.startRec(); this.since = 0; }
    }
    destroy() { clearInterval(this.timer); this.on = false; try { this.rec && this.rec.stop() } catch (e) {} try { this.ctx.close() } catch (e) {} }
  }

  const api = { Vad, Capture }; if (typeof module !== "undefined" && module.exports) module.exports = api; else root.RWVoice = api;
})(typeof window !== "undefined" ? window : globalThis);
