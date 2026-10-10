/* Motivation section: two interactive figures that animate the paper's motivation figure.
   Artwork is extracted from figs/RAR_problem.pptx (scripts/extract_motivation_assets.py).
   Both figures show every configuration at the same time (no mode switching).

   (a) Rate-throughput mismatch: three machines generate r = 60 / 30 / 15 frames per wall-clock second.
       Each frame advances the world by 1 / f_rollout. Every road has two lanes on the same machine:
       upper lane = fixed-rate model (f_rollout = 30, world runs at rho = r / 30 of real time),
       lower lane = RAR (f_rollout = r, rho = 1).
   (b) Rate-horizon trade-off: a car drives a bend in 0.4 s of physical time. A sample at rate f holds
       N = 7 frames at t_k = k / f, i.e. a window of (N - 1) / f seconds. The three fixed rates and RAR
       (one model trained on all three strides) are drawn together on the map and on the timeline. */
(function () {
  "use strict";

  const IMG = "static/images/motivation";
  const RATE_STYLE = {       // shared by (a) machines and (b) sampling rates
    60: { c: "var(--top)", ink: "var(--top-ink)", car: "pink", gpus: 4 },
    30: { c: "var(--mid)", ink: "var(--mid-ink)", car: "blue", gpus: 2 },
    15: { c: "var(--bottom)", ink: "var(--bottom-ink)", car: "green", gpus: 1 },
  };
  const REDUCED = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const ICON_PLAY = '<svg viewBox="0 0 16 16"><path d="M4.5 2.5v11l9-5.5z" fill="currentColor"/></svg>';
  const ICON_PAUSE = '<svg viewBox="0 0 16 16"><path d="M4 2.5h3v11H4zM9 2.5h3v11H9z" fill="currentColor"/></svg>';

  /* -------------------- helpers -------------------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, attrs = {}, html = "") => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (html) n.innerHTML = html;
    return n;
  };
  const svgEl = (tag, attrs = {}) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };

  function watchVisible(elm, st) {
    if (!("IntersectionObserver" in window)) { st.visible = true; return; }
    new IntersectionObserver((es) => es.forEach((e) => { st.visible = e.isIntersecting; }), { threshold: 0.1 }).observe(elm);
  }

  // play / pause + scrubber (same look as the multi-rate viewer)
  function transportBar(slowLabel, onToggle, onScrub) {
    const bar = el("div", { class: "mr-bar mot-bar" });
    const play = el("button", { class: "mr-play", type: "button", "aria-label": "Play / pause" }, ICON_PAUSE);
    const track = el("div", { class: "mr-track", title: "Click or drag to scrub" });
    const fill = el("div", { class: "mr-fill" });
    const knob = el("div", { class: "mr-knob" });
    track.append(el("div", { class: "mr-rail" }), fill, knob);
    const time = el("div", { class: "mr-time" });
    bar.append(play, track, time);
    if (slowLabel) bar.appendChild(el("span", { class: "mot-slow", title: "Animation speed relative to real time" }, slowLabel));
    play.addEventListener("click", onToggle);
    let drag = false;
    const at = (e) => {
      const r = track.getBoundingClientRect();
      onScrub(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)));
    };
    track.addEventListener("pointerdown", (e) => { drag = true; track.setPointerCapture(e.pointerId); at(e); });
    track.addEventListener("pointermove", (e) => { if (drag) at(e); });
    track.addEventListener("pointerup", () => { drag = false; });
    track.addEventListener("pointercancel", () => { drag = false; });
    return {
      bar,
      set(frac, html, playing) {
        fill.style.width = `${frac * 100}%`;
        knob.style.left = `${frac * 100}%`;
        if (time._h !== html) { time.innerHTML = html; time._h = html; }
        if (play._p !== playing) { play.innerHTML = playing ? ICON_PAUSE : ICON_PLAY; play._p = playing; }
      },
    };
  }

  // clock in [0, 1]: advances while visible, holds at the end, then restarts
  function loop(st, speed, hold, render) {
    let last = 0;
    const step = (now) => {
      const dt = last ? Math.min(0.1, (now - last) / 1000) : 0;
      last = now;
      if (st.visible) {
        if (st.playing) {
          if (st.p < 1) st.p = Math.min(1, st.p + dt * speed);
          else if ((st.hold += dt) > hold) { st.hold = 0; st.p = 0; }
        }
        render();
      }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function attachTransport(card, st) {
    const foot = $(".mot-foot", card);
    const tb = transportBar(foot.dataset.slow,
      () => { st.playing = !st.playing; if (st.playing && st.p >= 1) { st.p = 0; st.hold = 0; } },
      (frac) => { st.p = frac; st.hold = 0; st.playing = false; });
    foot.appendChild(tb.bar);
    return tb;
  }

  const verdictOf = (rho) => (rho > 1.01 ? ["", "runs ahead \u25b6"] : rho < 0.99 ? ["", "\u25c0 lags behind"] : ["ok", "\u2713 real time"]);

  /* ==================== (a) rate-throughput mismatch ==================== */
  function buildMismatch(card) {
    if (!card) return;
    const F_TRAIN = 30, TAU_MAX = 2, CAR_W = 10.5;
    const st = { p: REDUCED ? 1 : 0, hold: 0, playing: !REDUCED, visible: false };
    const xOf = (tau) => (Math.min(tau, TAU_MAX) / TAU_MAX) * (100 - CAR_W);     // car's left edge, % of the lane track
    const grid = $(".mm", card);

    grid.appendChild(el("div", { class: "mm-head" },
      '<span class="mm-hcap">machine</span>' +
      `<span class="mm-legend"><img src="${IMG}/car_ghost.png" alt="">where the world should be (real time)</span>` +
      '<span class="mm-hcap r">world speed <i>&rho;</i></span>'));

    const lanes = [60, 30, 15].map((r) => {
      const S = RATE_STYLE[r];
      const row = el("div", { class: "mm-lane", style: `--lc:${S.c};--li:${S.ink}` });
      const gpus = Array.from({ length: S.gpus }, () => `<img src="${IMG}/gpu.png" alt="">`).join("");
      const hw = el("div", { class: "mm-hw" },
        `<span class="mm-gpus" title="${S.gpus} GPU${S.gpus > 1 ? "s" : ""}">${gpus}<em>${S.gpus}&times; GPU</em></span>` +
        `<span class="mm-r"><b>r = ${r}</b> updates/s</span><span class="mm-cnt"></span>`);

      const road = el("div", { class: "mm-road" }, '<div class="mm-tags"><span>FIXED</span><span>RAR</span></div>');
      road.style.backgroundImage = `url(${IMG}/road.jpg)`;
      const track = el("div", { class: "mm-track" }, `<span class="mm-exp" style="left:${xOf(1) + CAR_W}%"></span>`);
      const ghost = el("img", { class: "mm-ghost", src: `${IMG}/car_ghost.png`, alt: "" });
      const gap = el("span", { class: "mm-gap" });
      const carF = el("img", { class: "mm-car up", src: `${IMG}/car_${S.car}.png`, alt: `fixed-rate model on the r = ${r} machine` });
      const carR = el("img", { class: "mm-car lo", src: `${IMG}/car_${S.car}.png`, alt: `RAR on the r = ${r} machine` });
      track.append(ghost, gap, carF, carR);
      road.appendChild(track);

      const rho = r / F_TRAIN;
      const [vc, vt] = verdictOf(rho);
      const stat = el("div", { class: "mm-stat" },
        `<div class="mm-s"><span class="mm-who">Fixed</span><b class="mm-rho">\u00d7${rho.toFixed(1)}</b><span class="mm-verdict ${vc}">${vt}</span></div>` +
        '<div class="mm-s"><span class="mm-who">RAR</span><b class="mm-rho">\u00d71.0</b><span class="mm-verdict ok">\u2713 real time</span></div>');

      row.append(hw, road, stat);
      grid.appendChild(row);
      return { r, carF, carR, ghost, gap, cnt: $(".mm-cnt", hw) };
    });

    const axisRow = el("div", { class: "mm-lane mm-axis-row" });
    const axis = el("div", { class: "mm-axis" });
    [0, 0.5, 1, 1.5, 2].forEach((tau) => axis.appendChild(el("span",
      { class: `mm-tick${tau === 1 ? " exp" : ""}${tau % 1 ? " minor" : ""}`, style: `left:${xOf(tau) + CAR_W}%` },
      tau === 1 ? "1 s (expected)" : `${tau} s`)));
    axisRow.append(el("div", { class: "mm-axis-cap" }, "world time"), axis, el("div"));
    grid.appendChild(axisRow);

    const tb = attachTransport(card, st);

    function render() {
      const t = st.p;                                   // wall-clock seconds
      lanes.forEach((L) => {
        const n = Math.floor(t * L.r + 1e-6);           // frames finished so far (counter only)
        // cars are drawn at the continuous world time, so they glide instead of jumping frame by frame
        const xf = xOf((t * L.r) / F_TRAIN), xr = xOf(t);
        L.carF.style.left = `${xf}%`;
        L.carR.style.left = `${xr}%`;
        L.ghost.style.left = `${xr}%`;
        const d = Math.abs(xf - xr);
        L.gap.style.left = `${Math.min(xf, xr) + CAR_W}%`;
        L.gap.style.width = `${d}%`;
        L.gap.style.opacity = d > 1.5 ? "1" : "0";
        const txt = `frame ${String(n).padStart(2, "0")} / ${L.r}`;
        if (L.cnt._t !== txt) { L.cnt.textContent = txt; L.cnt._t = txt; }
      });
      tb.set(t, `wall-clock <b>${t.toFixed(2)}</b> / 1.00 s`, st.playing);
    }

    render();
    watchVisible(card, st);
    loop(st, 0.4, 2.2, render);
  }

  /* ==================== (b) rate-horizon trade-off ==================== */
  function buildHorizon(card) {
    if (!card) return;
    const N = 7, T = 0.4, RATES = [60, 30, 15];
    // car path in map-crop pixels (map.jpg is a 1130 x 880 crop of the paper artwork)
    const P = { W: 1130, H: 880, x0: 265, y0: 780, yA: 330, cx: 425, R: 160, x1: 1030 };   // ends keep the car inside
    const L1 = P.y0 - P.yA, L2 = (Math.PI / 2) * P.R, LEN = L1 + L2 + (P.x1 - P.cx);
    const TURN = [L1 / LEN, (L1 + L2) / LEN];
    const at = (u) => {
      const s = Math.max(0, Math.min(1, u)) * LEN;
      if (s <= L1) return { x: P.x0, y: P.y0 - s, a: 0 };
      if (s <= L1 + L2) {
        const th = (s - L1) / P.R;
        return { x: P.cx - P.R * Math.cos(th), y: P.yA - P.R * Math.sin(th), a: (th * 180) / Math.PI };
      }
      return { x: P.cx + (s - L1 - L2), y: P.yA - P.R, a: 90 };
    };
    const horizon = (f) => Math.min(T, (N - 1) / f);
    const pct = (p) => ({ left: `${(p.x / P.W) * 100}%`, top: `${(p.y / P.H) * 100}%` });
    const st = { p: REDUCED ? 1 : 0, hold: 0, playing: !REDUCED, visible: false };
    const timed = [];                                   // elements that light up once tau >= their sample time

    // --- four small maps (2 x 2): 60 / 30 / 15 FPS and RAR. Each shows its 7-frame window(s) as a band
    //     along the road, the sample positions, and the car (faded once it leaves every window).
    const d = `M${P.x0} ${P.y0} L${P.x0} ${P.yA} A${P.R} ${P.R} 0 0 1 ${P.cx} ${P.yA - P.R} L${P.x1} ${P.yA - P.R}`;
    const CASES = [
      { key: "60", rates: [60], label: "60 FPS", sub: "T = 0.10 s", c: RATE_STYLE[60].c },
      { key: "30", rates: [30], label: "30 FPS", sub: "T = 0.20 s", c: RATE_STYLE[30].c },
      { key: "15", rates: [15], label: "15 FPS", sub: "T = 0.40 s", c: RATE_STYLE[15].c },
      { key: "rar", rates: [15, 30, 60], label: "RAR", sub: "all three strides", c: "" },
    ];
    const BAND_ONE = 78, BAND_RAR = { 15: 110, 30: 74, 60: 38 };   // map units (the map is drawn ~4.5x smaller)
    const DOT_ONE = 13, DOT_RAR = { 15: 17, 30: 12, 60: 7 };
    const maps = CASES.map((C) => {
      const map = el("div", { class: `hz-map${C.key === "rar" ? " rar" : ""}`, style: C.c ? `--lc:${C.c}` : "" });
      map.style.backgroundImage = `url(${IMG}/map.jpg)`;
      const multi = C.rates.length > 1;
      const back = svgEl("svg", { viewBox: `0 0 ${P.W} ${P.H}`, preserveAspectRatio: "none" });
      back.appendChild(svgEl("path", { d, class: "hz-trail" }));
      C.rates.forEach((f) => back.appendChild(svgEl("path", {     // longest window drawn first (widest)
        d, class: "hz-cover", pathLength: "1", style: `--lc:${RATE_STYLE[f].c}`,
        "stroke-dasharray": `${horizon(f) / T} 3`, "stroke-width": multi ? BAND_RAR[f] : BAND_ONE,
      })));
      const car = el("img", { class: "hz-car", src: `${IMG}/car_top.png`, alt: "" });
      const front = svgEl("svg", { viewBox: `0 0 ${P.W} ${P.H}`, preserveAspectRatio: "none" });
      C.rates.forEach((f) => {                          // concentric markers where sample times coincide
        for (let k = 0; k < N; k++) {
          const p = at(k / f / T);
          const c = svgEl("circle", { cx: p.x, cy: p.y, r: multi ? DOT_RAR[f] : DOT_ONE, class: "hz-mark", style: `--lc:${RATE_STYLE[f].c}` });
          front.appendChild(c);
          timed.push({ tau: k / f, el: c });
        }
      });
      const tag = el("span", { class: "hz-pill hz-tag" }, `<b>${C.label}</b><span>${C.sub}</span>`);
      const out = el("span", { class: "hz-pill hz-out" }, "outside the window");
      map.append(back, car, front, tag, out);
      return { map, car, out, win: Math.max(...C.rates.map(horizon)) };
    });
    const grid = $(".hz-maps", card);
    maps.forEach((m) => grid.appendChild(m.map));

    // --- sampling timeline: one row per fixed rate + one RAR row, shared physical-time axis, shaded turn
    const tl = $(".hz-tl", card);
    tl.style.setProperty("--t0", TURN[0]);
    tl.style.setProperty("--t1", TURN[1]);
    tl.appendChild(el("div", { class: "hz-turn" }, "<span>turn</span>"));
    const INFO = {
      60: ["16.7 ms", "0.10 s", "", "\u2715 ends before the turn"],
      30: ["33.3 ms", "0.20 s", "", "\u25d0 only reaches the turn"],
      15: ["66.7 ms", "0.40 s", "", "\u25d0 whole turn, coarse steps"],
      rar: ["17\u201367 ms", "0.1\u20130.4 s", "ok", "\u2713 fine steps and the whole turn"],
    };
    const meta = (k) => el("div", { class: "hz-meta" },
      `<span>\u0394t ${INFO[k][0]} &middot; T ${INFO[k][1]}</span><span class="mm-verdict hz-v ${INFO[k][2]}">${INFO[k][3]}</span>`);
    const curs = [];
    const samples = (holder, f) => {                    // horizon bar + N sample dots of one rate
      holder.appendChild(el("span", { class: "hz-bar", style: `width:${(horizon(f) / T) * 100}%` }));
      for (let k = 0; k < N; k++) {
        const s = el("span", { class: "hz-tdot", style: `left:${(k / f / T) * 100}%` });
        holder.appendChild(s);
        timed.push({ tau: k / f, el: s });
      }
    };
    const addRow = (key, label, track, extraCls = "", style = "") => {
      const cur = el("span", { class: "hz-cur" });
      track.appendChild(cur);
      curs.push(cur);
      const cell = el("div", { class: "hz-cell" });
      cell.append(track, meta(key));
      const row = el("div", { class: `hz-row ${extraCls}`, style });
      row.append(el("span", { class: "hz-lab" }, label), cell);
      tl.appendChild(row);
    };

    RATES.forEach((f) => {
      const track = el("div", { class: "hz-track" });
      samples(track, f);
      addRow(f, `${f} FPS`, track, "", `--lc:${RATE_STYLE[f].c};--li:${RATE_STYLE[f].ink}`);
    });
    tl.appendChild(el("div", { class: "hz-sep" }));
    const multi = el("div", { class: "hz-track multi", title: "One RAR model is trained on all three strides" });
    RATES.forEach((f) => {
      const sub = el("div", { class: "hz-sub", style: `--lc:${RATE_STYLE[f].c}` });
      samples(sub, f);
      multi.appendChild(sub);
    });
    addRow("rar", "RAR", multi, "rar");

    const axRow = el("div", { class: "hz-row" });
    const axis = el("div", { class: "hz-axis" });
    [0, 0.1, 0.2, 0.3, 0.4].forEach((v) => axis.appendChild(el("span", { class: "hz-tick", style: `left:${(v / T) * 100}%` }, v.toFixed(1))));
    axRow.append(el("span", { class: "hz-lab hz-unit" }, "time (s)"), axis);
    tl.appendChild(axRow);

    const tb = attachTransport(card, st);

    function render() {
      const tau = st.p * T;                             // physical seconds
      timed.forEach((m) => m.el.classList.toggle("on", tau >= m.tau - 1e-9));
      curs.forEach((c) => { c.style.left = `${st.p * 100}%`; });
      const p = at(st.p), pos = pct(p);
      maps.forEach((m) => {
        Object.assign(m.car.style, pos);
        m.car.style.setProperty("--a", `${p.a}deg`);
        const outside = tau > m.win + 1e-6;
        m.car.classList.toggle("out", outside);
        m.out.classList.toggle("on", outside);
      });
      tb.set(st.p, `physical time <b>${tau.toFixed(2)}</b> / ${T.toFixed(2)} s`, st.playing);
    }

    render();
    watchVisible(card, st);
    loop(st, 0.25, 1.4, render);
  }

  document.addEventListener("DOMContentLoaded", () => {
    buildMismatch($("#mot-a"));
    buildHorizon($("#mot-b"));
  });
})();
