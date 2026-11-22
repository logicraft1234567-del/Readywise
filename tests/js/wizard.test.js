// Run: node tests/js/wizard.test.js   (how the new-interview flow applies the guide's plan to its list of questions)
const vm = require("vm"), fs = require("fs"); const win = {}; 
vm.runInNewContext(fs.readFileSync(__dirname + "/../../core/static/js/wizard.js", "utf8"), { window: win, document: {}, matchMedia: () => ({ matches: false }), setTimeout, console });
const { rwMergePlan, rwSegment } = win; const ok = (c, m) => { if (!c) { console.error("FAIL:", m); process.exitCode = 1 } else console.log("ok  :", m) };
const mk = () => [{ id: "intro" }, { id: "kind" }, { id: "company", name: "k__company", adapt: true, req: true, q: "Company?" }, { id: "position", name: "k__position", adapt: true, req: true, q: "Role?" },
  { id: "stage", name: "k__stage", adapt: true, q: "Stage?" }, { id: "team", name: "k__team", adapt: true, q: "Team?" }, { id: "why", name: "k__why", adapt: true, req: true, q: "Why?" }, { id: "known" }, { id: "date" }];
const ids = s => s.map(x => x.id).join(",");
ok(JSON.stringify(rwSegment(mk())) === '{"from":2,"to":7}', "the interview-specific questions are found as one block");
let A = { kind: "k", k__company: "Acme", k__position: "Backend engineer" }, s = mk();
let r = rwMergePlan(s, 3, { order: ["why", "team"] }, A);
ok(ids(r) === "intro,kind,company,position,why,team,known,date", "an unneeded question is skipped, the rest reordered: " + ids(r));
r = rwMergePlan(s, 3, { order: [] }, A); ok(ids(r) === "intro,kind,company,position,why,known,date", "required questions survive even if the guide leaves them out: " + ids(r));
r = rwMergePlan(mk(), 3, { order: ["stage", "why"], rewrite: { stage: "Which funding stage is Acme at?" }, ask: [{ key: "x1", q: "You said career change. What drove it?", short: "Career change", type: "textarea", ph: "e.g. moved from finance" }], say: "Interesting move." }, A);
ok(ids(r) === "intro,kind,company,position,x1,stage,why,known,date", "a follow-up is inserted right after the current question: " + ids(r));
ok(r[4].custom && r[4].name === "k__x1" && A.k__xq1 === "Career change" && r[4].say === "Interesting move.", "the follow-up carries its label and the guide's reaction");
ok(r[5].q === "Which funding stage is Acme at?" && r[5].q0 === "Stage?", "a question can be reworded (the original is kept)");
A.k__x1 = "Burnout in finance"; r = rwMergePlan(r, 4, { order: ["why"], ask: [{ key: "x2", q: "Another one for you?", short: "Other", type: "text" }] }, A);
ok(r.some(x => x.id === "x1") && r.some(x => x.id === "x2"), "an answered follow-up stays when the plan changes");
const A2 = { kind: "k" }; let s2 = rwMergePlan(mk(), 3, { order: ["why"], ask: [{ key: "x1", q: "Question one here?", short: "One", type: "text" }] }, A2);
s2 = rwMergePlan(s2, 3, { order: ["why"], ask: [{ key: "x1", q: "Different question here?", short: "Two", type: "text" }] }, A2);
ok(s2.filter(x => x.custom).length === 1 && s2.find(x => x.custom).q === "Different question here?", "going back and answering again replaces an unanswered follow-up instead of piling up");
ok(r.slice(-2).map(x => x.id).join() === "known,date", "the interview-length and date questions at the end are untouched");
// a follow-up must never repeat a question that is already in the flow, and never ask for a document
{
  const A3 = { kind: "k" }, base = mk(); base[2].q = "What is the company?"; base.splice(7, 0, { id: "cv", name: "k__cv", type: "doc", adapt: true, req: true, q: "Can I see your CV?" }); base[6].q = "Why this startup, and why now?";
  const r3 = rwMergePlan(base, 3, { order: ["stage", "why", "cv"], ask: [
    { key: "x1", q: "Could you paste your CV here?", short: "CV", type: "text" },
    { key: "x2", q: "Why do you want this startup right now?", short: "Why", type: "text" },
    { key: "x3", q: "Which database have you scaled the most?", short: "Database", type: "text" }] }, A3);
  ok(!r3.some(x => x.id === "x1"), "a follow-up that asks for the CV again is dropped");
  ok(!r3.some(x => x.id === "x2"), "a follow-up that rewords an existing question is dropped");
  ok(r3.some(x => x.id === "x3"), "a genuinely new follow-up is kept");
  ok(r3.filter(x => x.id === "cv").length === 1, "the CV step appears exactly once");
  const dup = rwMergePlan(base, 3, { order: ["stage", "stage", "cv"] }, A3); ok(dup.filter(x => x.id === "stage").length === 1, "a question named twice in the plan is asked once");
}
