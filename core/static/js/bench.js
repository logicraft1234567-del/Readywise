/* ReadyWise hands-on task runner. The candidate's JavaScript runs inside a Web Worker in their own browser (never on the server),
   against the checks the panel wrote. execAll is self-contained so the same function is tested in Node (tests/js/bench.test.js)
   and shipped to the worker as source. Other languages and written tasks are not executed; the panel reviews the text. */
(function (root) {
  "use strict";
  async function execAll(code, tests) {
    const canon = v => Array.isArray(v) ? v.map(canon) : v && typeof v === "object" ? Object.keys(v).sort().reduce((o, k) => (o[k] = canon(v[k]), o), {}) : (typeof v === "number" && Number.isNaN(v)) ? "NaN" : v;
    const same = (a, b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));
    let fn;
    try { fn = (new Function(code + "\n;return typeof solve === 'function' ? solve : undefined;"))(); }
    catch (e) { return { fatal: "Your code has an error: " + (e && e.message || e) }; }
    if (typeof fn !== "function") return { fatal: "Define a function named solve." };
    const out = [];
    for (let i = 0; i < tests.length; i++) {
      const t = tests[i];
      try { const got = await fn(...JSON.parse(JSON.stringify(t.args))); out.push({ ok: same(got, t.expected), args: t.args, expected: t.expected, got: got === undefined ? "undefined" : got }); }
      catch (e) { out.push({ ok: false, args: t.args, expected: t.expected, err: String(e && e.message || e) }); }
    }
    return { results: out };
  }
  function run(code, tests, ms) {
    return new Promise(resolve => {
      let w; try { w = new Worker(URL.createObjectURL(new Blob([`const execAll=${execAll.toString()};onmessage=async e=>postMessage(await execAll(e.data.code,e.data.tests))`], { type: "text/javascript" }))); }
      catch (e) { return resolve({ fatal: "This browser cannot run code here." }); }
      const timer = setTimeout(() => { w.terminate(); resolve({ fatal: "Your code took too long (over " + Math.round((ms || 4000) / 1000) + " s). Check for an infinite loop." }); }, ms || 4000);
      w.onmessage = e => { clearTimeout(timer); w.terminate(); resolve(e.data); }; w.onerror = e => { clearTimeout(timer); w.terminate(); resolve({ fatal: "Your code has an error: " + e.message }); };
      w.postMessage({ code, tests });
    });
  }
  const api = { execAll, run }; if (typeof module !== "undefined" && module.exports) module.exports = api; else root.RWBench = api;
})(typeof window !== "undefined" ? window : globalThis);
