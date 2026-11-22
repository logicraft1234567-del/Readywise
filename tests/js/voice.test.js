// Run: node tests/js/voice.test.js   (turn-taking logic: when does the room think the candidate started / finished talking?)
const { Vad } = require("../../core/static/js/voice.js");
const ok = (c, m) => { if (!c) { console.error("FAIL:", m); process.exitCode = 1 } else console.log("ok  :", m) };
function play(v, segs) { const ev = []; let t = 0; for (const [ms, lv] of segs) for (let i = 0; i < ms; i += 20) { for (const e of v.feed(lv + (Math.random() - .5) * 0.002, 20)) ev.push([e, t]); t += 20 } return ev }
const names = e => e.map(x => x[0]).join(",");

let v = new Vad(); ok(names(play(v, [[5000, 0.004]])) === "", "room noise alone produces no events");
v = new Vad(); ok(names(play(v, [[1200, 0.004], [60, 0.2], [2000, 0.004]])) === "", "a 60 ms click is ignored");
v = new Vad(); let e = play(v, [[1200, 0.004], [200, 0.2], [1500, 0.004]]); ok(names(e) === "start,discard", "a 200 ms cough is started then discarded: " + names(e));
v = new Vad(); e = play(v, [[1200, 0.004], [2500, 0.15], [2000, 0.004]]); ok(names(e) === "start,confirm,end", "a 2.5 s answer gives start, confirm, end: " + names(e));
ok(Math.abs(v.lastMs - 2500) < 200, "measured speech length " + v.lastMs + " ms (true 2500)");
const conf = e.find(x => x[0] === "confirm")[1] - e.find(x => x[0] === "start")[1]; ok(conf < 400, "barge-in is confirmed " + conf + " ms after the voice starts, so the interviewer yields quickly");
v = new Vad(); e = play(v, [[1200, 0.004], [1500, 0.15], [1000, 0.004], [1500, 0.15], [2000, 0.004]]); ok(names(e) === "start,confirm,end", "a 1.0 s thinking pause mid-answer does not end the turn (one 'end' only)");
ok(Math.abs(e.find(x => x[0] === "end")[1] - (1200 + 1500 + 1000 + 1500 + 1500)) < 100, "turn ends 1.5 s after the last word");
v = new Vad(); e = play(v, [[3000, 0.02], [1500, 0.25], [2000, 0.02]]); ok(names(e) === "start,confirm,end", "in a noisy room (level 0.02) normal speech (0.25) is still detected: " + names(e));
v = new Vad(); v.setEnd(2500); e = play(v, [[1200, .004], [1500, .15], [2000, .004]]); ok(names(e) === "start,confirm", "a longer end-of-turn setting waits longer (no end after 2 s)");
v = new Vad(); e = play(v, [[1200, 0.004], [2500, 0.15], [1600, 0.004], [1500, 0.15], [1600, 0.004]]); ok(names(e) === "start,confirm,end,start,confirm,end", "the detector re-arms after a finished answer and keeps its noise estimate: " + names(e));
