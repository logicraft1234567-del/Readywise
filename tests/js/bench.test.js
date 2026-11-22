// Run: node tests/js/bench.test.js   (the on-site code runner: pass, fail, errors, async, bad code)
const { execAll } = require("../../core/static/js/bench.js");
const ok = (c, m) => { if (!c) { console.error("FAIL:", m); process.exitCode = 1 } else console.log("ok  :", m) };
const T = [{ args: [[1, 2, 3]], expected: 6 }, { args: [[]], expected: 0 }, { args: [[-1, 1]], expected: 0 }];
(async () => {
  let r = await execAll("function solve(a){return a.reduce((x,y)=>x+y,0)}", T); ok(r.results.every(x => x.ok) && r.results.length === 3, "correct solution passes all 3 checks");
  r = await execAll("function solve(a){return a.length?a[0]:0}", T); ok(r.results.map(x => x.ok).join() === "false,true,false", "wrong solution fails the right checks: " + r.results.map(x => x.ok));
  r = await execAll("function solve(a){ return a.x.y }", T); ok(r.results.every(x => !x.ok && /undefined|Cannot read/.test(x.err)), "a runtime error is reported per check, not thrown");
  r = await execAll("function solve(a){ return ", T); ok(/error/.test(r.fatal), "a syntax error gives a readable message: " + r.fatal);
  r = await execAll("const f = 1;", T); ok(/solve/.test(r.fatal), "missing solve() is explained");
  r = await execAll("async function solve(a){ return a.reduce((x,y)=>x+y,0) }", T); ok(r.results.every(x => x.ok), "async solutions are awaited");
  r = await execAll("function solve(o){ return {b:o.b,a:o.a} }", [{ args: [{ a: 1, b: 2 }], expected: { a: 1, b: 2 } }]); ok(r.results[0].ok, "object key order does not matter");
  const args = [[1]]; await execAll("function solve(a){ a.push(9); return 1 }", [{ args, expected: 1 }]); ok(args[0].length === 1, "the checks' own data is not mutated by the candidate's code");
})();
