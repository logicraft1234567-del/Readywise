/* The ReadyWise story: nine chapters, 65 seconds. Engine and score live in film.js. */
if (window.RWFilm) RWFilm({
  id: "story", hash: "story", majorFrom: 8,
  intensity: [1, 1, 2, 3, 3, 3, 4, 4, 5], fx: [1, 1.6, 2.2, 2, 2.4, 2.4, 3, 3.4, 4],
  vo: ["Nine a.m. Thirty minutes. That is all you get.", "Nervous. Blank. Rehearsed for the wrong questions. No second chance.", "It does not have to be you.", "Three people. Three agendas. All aimed at you.", "Now imagine you have already faced them. Again, and again, until it is easy.", "ReadyWise researched the room before you.", "A plan that adapts. Replays that show you exactly what to fix.", "Same room. Same questions. A different you.", "Walk in already ready. Start free today."],
  make({ team, W, cta }) {
    const Q = ["Start with the decision you are proudest of. What did it cost you?", "You said the team shipped it. What exactly did you own?", "Before we finish, what would you want to know about this role?"];
    return [
      { d: 5, html: `<div class="in"><div class="st-meta" data-m>9:00 a.m.</div><h2 class="big" data-manual>${W("Thirty minutes.")}</h2><h2 class="big" data-manual data-hit style="opacity:0">${W("That is all you get.")}</h2></div>`,
        build({ tl, el, t0, $q, $$, snd, shake, flash, Aud }) { tl.from($q(el, "[data-m]"), { autoAlpha: 0, duration: 1 }, t0 + .2).from($$($$(el, ".big")[0], ".w"), { yPercent: 70, autoAlpha: 0, duration: .8, stagger: .15 }, t0 + .9);
          const h = $q(el, "[data-hit]"); tl.set(h, { autoAlpha: 1, opacity: 1 }, t0 + 2.9).from($$(h, ".w"), { scale: 1.8, autoAlpha: 0, duration: .35, stagger: .2, ease: "power4.out" }, t0 + 2.9);
          snd(t0 + 2.9, () => Aud.slam(1)); snd(t0 + 3.3, () => Aud.slam(1)); snd(t0 + 3.7, () => Aud.boom()); flash(t0 + 3.7, .55); shake(t0 + 3.7, 10, .5); } },
      { d: 6, html: `<div class="in"><div class="fl">Nervous.</div><div class="fl">Blank.</div><div class="fl sm">Rehearsed for the wrong questions.</div><div class="fl"><em>No second chance.</em></div></div>`,
        build({ tl, el, t0, $$, snd, shake, flash, Aud }) { $$(el, ".fl").forEach((f, k) => { const a = t0 + .4 + k * 1.35; tl.set(f, { autoAlpha: 1 }, a).fromTo(f, { scale: 1.55, opacity: 0 }, { scale: 1, opacity: 1, duration: .28, ease: "power4.out" }, a).to(f, { autoAlpha: 0, duration: .2 }, a + 1.1); snd(a, () => Aud.slam(.8)); shake(a, 7, .22); flash(a, .18, .3); }); } },
      { d: 6, html: `<div class="in"><div class="streaks"><i></i><i></i><i></i><i></i><i></i><i></i></div><h2 class="big">${W("It does not have to be you.")}</h2></div>`,
        build({ tl, el, t0, $q, snd, shake, Aud }) { tl.to($q(el, ".streaks"), { opacity: .9, duration: 1.2 }, t0 + 1.2); snd(t0 + 1.9, () => Aud.riser(4.1)); tl.call(() => { const b = $q(el, ".big"); b.classList.remove("gl"); void b.offsetWidth; b.classList.add("gl"); }, null, t0 + 3.2); shake(t0 + 4.4, 3, 1.4); } },
      { d: 10, html: `<div class="in"><div class="flare"></div><h2 class="big sm">${W("Three people. Three agendas.")}</h2><div class="pts">${team.slice(0, 3).map(t => `<div class="pt"><img src="${t.img}" alt=""><span>${t.n}<small>${t.r}</small></span></div>`).join("")}</div><p class="cap" id="st-cap"></p></div>`,
        build({ tl, el, t0, d, $q, $$, snd, shake, flash, Aud, team }) { const pts = $$(el, ".pt"), cap = $q(el, "#st-cap"), fl = $q(el, ".flare");
          snd(t0, () => Aud.boom()); flash(t0, 1, .9); shake(t0, 12, .6); tl.fromTo(fl, { opacity: 1, scale: .1 }, { opacity: 0, scale: 1.4, duration: 1.6, ease: "power2.out" }, t0);
          tl.from(pts, { y: 70, autoAlpha: 0, duration: .9, stagger: .16 }, t0 + 1.2);
          pts.forEach((p, k) => { const a = t0 + 2.9 + k * 2.2; tl.call(() => { pts.forEach((x, j) => x.classList.toggle("lit", j === k)); cap.textContent = `${team[k] ? team[k].n : ""}: ${Q[k]}`; }, null, a); tl.fromTo(cap, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: .45 }, a); snd(a, () => Aud.hit()); });
          tl.call(() => pts.forEach(x => x.classList.remove("lit")), null, t0 + d - .6); },
        reset(el) { el.querySelectorAll(".pt").forEach(x => x.classList.remove("lit")); el.querySelector("#st-cap").textContent = ""; } },
      { d: 7, html: `<div class="in"><h2 class="big sm" data-intro>${W("Now imagine you have already faced them.")}</h2><div class="fl" style="top:52%">Again.</div><div class="fl" style="top:52%">And again.</div><div class="fl" style="top:52%"><em>Until it is easy.</em></div></div>`,
        build({ tl, el, t0, $q, $$, snd, shake, flash, Aud }) { tl.to($q(el, "[data-intro]"), { autoAlpha: 0, y: -20, duration: .4 }, t0 + 2.6);
          $$(el, ".fl").forEach((f, k) => { const a = t0 + 3 + k * 1.3; tl.set(f, { autoAlpha: 1 }, a).fromTo(f, { scale: 1.5, opacity: 0 }, { scale: 1, opacity: 1, duration: .26, ease: "power4.out" }, a); if (k < 2) tl.to(f, { autoAlpha: 0, duration: .15 }, a + 1.05); snd(a, () => Aud.slam(.9)); shake(a, 8, .25); flash(a, .2, .3); }); snd(t0 + 5.6, () => Aud.sparkle()); } },
      { d: 7, html: `<div class="in"><h2 class="big sm">${W("ReadyWise researched the room before you.")}</h2><div class="board">
          <div class="bc" style="left:0;top:0">The process has a take-home task before the panel round.<br><span class="tag t-confirmed">confirmed</span></div>
          <div class="bc" style="left:24.5cqw;top:5cqh">Candidates describe a system design round about queues.<br><span class="tag t-candidate_reported">candidate-reported</span></div>
          <div class="bc" style="left:49cqw;top:0">Expect questions on ownership and prioritisation.<br><span class="tag t-inferred">inferred</span></div></div></div>`,
        build({ tl, el, t0, $$, snd, Aud }) { const cards = $$(el, ".bc"); tl.from(cards, { x: i => (i - 1) * 90, y: 70, autoAlpha: 0, rotate: i => (i - 1) * 7, duration: .8, stagger: .4 }, t0 + 1.7); cards.forEach((c, k) => snd(t0 + 1.7 + k * .4 + .4, () => Aud.hit())); } },
      { d: 7, html: `<div class="in"><h2 class="big sm">${W("A plan that adapts. Replays that show what to fix.")}</h2><div class="two">
          <div class="col"><h4>Your plan</h4><div class="pr done"><span class="d">Mon</span><span class="ck"></span>Rewrite your two strongest stories</div><div class="pr"><span class="d">Wed</span><span class="ck"></span>System design, out loud</div><div class="pr" data-add><span class="d">Thu</span><span class="ck"></span>Added after your last session</div></div>
          <div class="col"><h4>Replay</h4><div class="nt" style="opacity:1"><b>02:14</b>Clear opening, one concrete result.</div><div class="nt" style="opacity:1"><b>07:41</b>Drifted into the team's work.</div><div class="nt better" style="opacity:1"><b>Stronger</b>I owned it. I built it and measured it.</div></div></div></div>`,
        build({ tl, el, t0, $q, $$, snd, Aud }) { const add = $q(el, "[data-add]"); tl.from($$(el, ".col"), { y: 50, autoAlpha: 0, duration: .8, stagger: .25 }, t0 + 1.5); tl.call(() => add.classList.add("done"), null, t0 + 4); snd(t0 + 4, () => Aud.hit()); },
        reset(el) { el.querySelectorAll(".pr").forEach((r, k) => r.classList.toggle("done", k === 0)); } },
      { d: 7, html: `<div class="in"><h2 class="big sm" data-same>${W("Same room. Same questions.")}</h2><div class="meter"><svg viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="45"/><circle class="fg" cx="50" cy="50" r="45"/></svg><b data-n>0%</b><small>Readiness, example</small></div><h2 class="big" data-manual data-diff style="opacity:0"><em>${W("A different you.")}</em></h2></div>`,
        build({ tl, el, t0, $q, $$, snd, shake, flash, Aud }) { const ring = $q(el, ".fg"), num = $q(el, "[data-n]"), same = $q(el, "[data-same]"), box = $q(el, ".meter"), diff = $q(el, "[data-diff]"), o = { v: 0 };
          tl.from(box, { scale: .6, autoAlpha: 0, duration: .7 }, t0 + 1.4);
          tl.to(ring, { strokeDashoffset: 0, duration: 3.2, ease: "power2.inOut" }, t0 + 1.8).to(o, { v: 100, duration: 3.2, ease: "power2.inOut", onUpdate: () => { num.textContent = Math.round(o.v) + "%"; } }, t0 + 1.8);
          tl.to(same, { autoAlpha: .35, duration: .4 }, t0 + 4.9); tl.set(diff, { autoAlpha: 1, opacity: 1 }, t0 + 5.1).from($$(diff, ".w"), { scale: 1.6, autoAlpha: 0, duration: .4, stagger: .18, ease: "power4.out" }, t0 + 5.1);
          snd(t0 + 1.8, () => Aud.riser(3.2)); snd(t0 + 5.1, () => Aud.slam(1)); shake(t0 + 5.1, 8, .3); flash(t0 + 5.1, .35, .5); },
        reset(el) { el.querySelector("[data-n]").textContent = "0%"; } },
      { d: 10, html: `<div class="in fin"><h2 class="big" data-manual>${W("Walk in")}<br>${W("already")} <em>${W("ready.")}</em></h2><p class="sub" data-late>Start free. Your first workspace takes about a minute.</p><div class="st-row"><a class="st-btn pri pulse" href="${cta}"><span class="bl">Create my interview workspace</span><span class="bs">Create workspace</span></a><button class="st-btn" type="button" data-replay>Watch again</button></div></div>`,
        build({ tl, el, t0, $q, $$, snd, shake, flash, Aud }) { snd(t0, () => { Aud.boom(); Aud.sparkle(); }); flash(t0, 1, 1.1); shake(t0, 14, .7);
          tl.fromTo($$(el, ".big .w"), { scale: 1.5, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .6, stagger: .22, ease: "power4.out" }, t0 + .3);
          tl.from($q(el, "[data-late]"), { autoAlpha: 0, y: 14, duration: .8 }, t0 + 2.3).to($q(el, ".st-row"), { autoAlpha: 1, y: 0, duration: .8 }, t0 + 3.2); } }
    ];
  }
});
