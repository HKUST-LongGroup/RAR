(function () {
  "use strict";

  const VIDEO_ROOT = "static/videos";
  const POSTER_ROOT = "static/posters";
  // target-FPS curves of the rate-switching clips, built from the two fixed schedules (smooth / abrupt)
  const SCHEDULES = (window.RAR_SCHEDULES && window.RAR_SCHEDULES.clips) || {};

  /* -------------------- data -------------------- */
  const ENV_NAME = { doom: "Doom", cs2: "CS2", fpv: "FPV" };
  const FIXED = {
    doom: { rates: [[14, "train", 15.1], [28, "interp", 7.6], [35, "train", 6.1], [49, "interp", 4.3], [70, "train", 3.0]], def: 49 },
    cs2:  { rates: [[16, "train", 15.0], [24, "interp", 10.0], [32, "train", 7.5], [48, "interp", 5.0], [64, "train", 3.8]], def: 24 },
    fpv:  { rates: [[20, "train", 12.0], [30, "train", 8.0], [40, "interp", 6.0], [50, "interp", 4.8], [60, "train", 4.0]], def: 40 },
  };
  const SANA = { rates: [[10, "train"], [16, "interp", true], [20, "train"], [24, "interp"], [30, "train"]], def: 16 };

  // chart value range (FPS)
  const Y_MIN = 12, Y_MAX = 68, Y_TICKS = [20, 40, 60];

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
  let uid = 0;

  function segmented(cls, items, active, onPick) {
    const seg = el("div", { class: "seg " + cls, role: "tablist" });
    items.forEach(({ v, label }) => {
      const b = el("button", { type: "button", "data-v": String(v), role: "tab" }, label);
      if (String(v) === String(active)) b.classList.add("active");
      b.addEventListener("click", () => {
        seg.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
        onPick(v);
      });
      seg.appendChild(b);
    });
    return seg;
  }

  function group(label, seg) {
    const g = el("div", { class: "g-group" });
    g.appendChild(el("span", { class: "g-label" }, label));
    g.appendChild(seg);
    return g;
  }

  /* -------------------- lazy video loading: only play when visible -------------------- */
  function applySrc(v) {
    if (v.dataset.src && v.getAttribute("src") !== v.dataset.src) {
      v.src = v.dataset.src;
    }
    if (v.dataset.userPaused !== "1") v.play().catch(() => {});
  }

  const visObserver = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
        entries.forEach(({ target: v, isIntersecting }) => {
          v.dataset.visible = isIntersecting ? "1" : "0";
          if (isIntersecting) applySrc(v);
          else v.pause();
        });
      }, { threshold: 0.2 })
    : null;

  function watch(v) {
    if (visObserver) visObserver.observe(v);
    else { v.dataset.visible = "1"; applySrc(v); }
  }

  function setVideo(v, rel) {
    const src = `${VIDEO_ROOT}/${rel}.mp4`;
    if (v.dataset.src === src) return;
    v.dataset.src = src;
    v.dataset.userPaused = "0";
    v.poster = `${POSTER_ROOT}/${rel}.jpg`;
    if (v.dataset.visible === "1" || v.getAttribute("src")) applySrc(v);
  }

  function makeVideo(controls) {
    const v = el("video", { muted: "", loop: "", playsinline: "", preload: "metadata" });
    if (controls) v.setAttribute("controls", "");
    v.muted = true;
    watch(v);
    return v;
  }

  /* -------------------- rate player: video + live target-FPS chart -------------------- */
  const players = new Set();

  // target FPS at x (= playback time / duration) on a polyline [[x, fps], ...];
  // a repeated x encodes a vertical step (abrupt schedule): the later point wins
  function valueAt(curve, x) {
    let lo = 0, hi = curve.length - 1;
    if (x <= curve[0][0]) return curve[0][1];
    if (x >= curve[hi][0]) return curve[hi][1];
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (curve[mid][0] <= x) lo = mid; else hi = mid;
    }
    const [x0, y0] = curve[lo], [x1, y1] = curve[hi];
    return x1 === x0 ? y1 : y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
  }

  class RatePlayer {
    constructor({ env, kind, sample = 1, label = true, loop = true, onRender = null }) {
      this.id = ++uid;
      this.onRender = onRender;
      this.root = el("div", { class: "rp", "data-env": env });

      // media
      const media = el("div", { class: "rp-media", title: "Click to play / pause" });
      this.video = makeVideo(false);
      if (!loop) { this.video.loop = false; this.video.removeAttribute("loop"); }
      this.labelEl = el("span", { class: "rp-label" });
      this.hud = el("div", { class: "rp-hud" }, '<span class="rp-fps">--</span><span class="rp-unit">FPS target</span>');
      this.speed = el("div", { class: "rp-speed", title: "Apparent world speed at the fixed playback frame rate" }, "&times;1.00");
      media.append(this.video, this.labelEl, this.hud, this.speed, el("div", { class: "rp-paused" }));
      if (!label) this.labelEl.style.display = "none";
      media.addEventListener("click", () => this.togglePlay());

      // chart
      this.chart = el("div", { class: "rp-chart", title: "Click or drag to scrub" });
      const svg = svgEl("svg", { viewBox: "0 0 1000 200", preserveAspectRatio: "none" });
      const defs = svgEl("defs");
      const grad = svgEl("linearGradient", { id: `rpg${this.id}`, x1: "0", y1: "0", x2: "0", y2: "1" });
      grad.append(
        svgEl("stop", { offset: "0", style: "stop-color: var(--env); stop-opacity: .32" }),
        svgEl("stop", { offset: "1", style: "stop-color: var(--env); stop-opacity: 0" }),
      );
      const clip = svgEl("clipPath", { id: `rpc${this.id}` });
      this.clipRect = svgEl("rect", { x: "0", y: "-20", width: "0", height: "240" });
      clip.appendChild(this.clipRect);
      defs.append(grad, clip);
      svg.appendChild(defs);
      Y_TICKS.forEach((v) => {
        const y = this.yPos(v) * 2;
        svg.appendChild(svgEl("line", { class: "grid", x1: "0", x2: "1000", y1: y, y2: y, "vector-effect": "non-scaling-stroke" }));
        this.chart.appendChild(el("span", { class: "rp-ytick", style: `top:${this.yPos(v)}%` }, String(v)));
      });
      this.areaPath = svgEl("path", { class: "area", fill: `url(#rpg${this.id})`, "clip-path": `url(#rpc${this.id})` });
      this.bgPath = svgEl("path", { class: "line-bg", "vector-effect": "non-scaling-stroke" });
      this.fgPath = svgEl("path", { class: "line-fg", "clip-path": `url(#rpc${this.id})`, "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round" });
      svg.append(this.areaPath, this.bgPath, this.fgPath);
      this.head = el("div", { class: "rp-head" });
      this.dot = el("div", { class: "rp-dot" });
      this.chart.prepend(svg);
      this.chart.append(this.head, this.dot);
      this.bindScrub();

      const foot = el("div", { class: "rp-foot" },
        '<span>Target rollout rate (FPS) &rarr; time</span><span class="rp-play-note"></span>');
      this.playNote = $(".rp-play-note", foot);

      this.root.append(media, this.chart, foot);
      this.video.addEventListener("pause", () => this.root.classList.toggle("is-paused", this.video.dataset.userPaused === "1"));
      this.video.addEventListener("play", () => this.root.classList.remove("is-paused"));
      players.add(this);
      this.load(env, kind, sample);
    }

    yPos(v) { return ((Y_MAX - v) / (Y_MAX - Y_MIN)) * 100; }

    load(env, kind, sample) {
      this.env = env; this.kind = kind; this.sample = sample;
      this.root.dataset.env = env;
      this.labelEl.textContent = `${ENV_NAME[env]} \u00b7 ${kind}`;
      this.sched = SCHEDULES[`${env}/${kind}/${sample}`];
      if (this.sched) {
        this.curve = this.sched.pts;
        const pts = this.curve.map(([x, v]) => `${(x * 1000).toFixed(2)} ${(this.yPos(v) * 2).toFixed(2)}`);
        const line = "M" + pts.join(" L");
        this.bgPath.setAttribute("d", line);
        this.fgPath.setAttribute("d", line);
        this.areaPath.setAttribute("d", `${line} L1000 200 L0 200 Z`);
        this.playbackFps = Math.round(1 / this.sched.dt);
        this.playNote.innerHTML = `played at a fixed <b>${this.playbackFps} FPS</b>`;
      }
      setVideo(this.video, `${env}/switch/${env}_${kind}_switch_video${sample}`);
      this.render(0);
    }

    duration() {
      const d = this.video.duration;
      if (Number.isFinite(d) && d > 0) return d;
      return this.sched ? this.sched.frames * this.sched.dt : 1;
    }

    togglePlay() {
      const v = this.video;
      if (!v.getAttribute("src")) applySrc(v);
      if (v.paused) { v.dataset.userPaused = "0"; v.play().catch(() => {}); }
      else { v.dataset.userPaused = "1"; v.pause(); }
    }

    bindScrub() {
      let dragging = false;
      const seek = (e) => {
        const r = this.chart.getBoundingClientRect();
        const frac = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
        const v = this.video;
        if (!v.getAttribute("src")) applySrc(v);
        const go = () => { const d = this.duration(); v.currentTime = Math.min(frac * d, d - 0.1); this.render(v.currentTime); };
        if (v.readyState >= 1) go(); else v.addEventListener("loadedmetadata", go, { once: true });
      };
      this.chart.addEventListener("pointerdown", (e) => { dragging = true; this.chart.setPointerCapture(e.pointerId); seek(e); });
      this.chart.addEventListener("pointermove", (e) => { if (dragging) seek(e); });
      const end = () => { dragging = false; };
      this.chart.addEventListener("pointerup", end);
      this.chart.addEventListener("pointercancel", end);
    }

    render(t) {
      if (!this.sched) return;
      const frac = Math.min(1, Math.max(0, t / this.duration()));
      const fps = valueAt(this.curve, frac);
      this.clipRect.setAttribute("width", (frac * 1000).toFixed(1));
      this.head.style.left = `${frac * 100}%`;
      this.dot.style.left = `${frac * 100}%`;
      this.dot.style.top = `${this.yPos(fps)}%`;
      $(".rp-fps", this.hud).textContent = Math.round(fps);
      const sp = this.playbackFps / fps;
      const arrow = sp >= 1.05 ? "&#9650;" : sp <= 0.95 ? "&#9660;" : "&#8226;";
      const word = sp >= 1.05 ? "faster" : sp <= 0.95 ? "slower" : "speed";
      this.speed.innerHTML = `<span class="arr">${arrow}</span>${word} &times;${sp.toFixed(2)}`;
      if (this.onRender) this.onRender(frac);
    }
  }

  function tick() {
    players.forEach((p) => {
      if (p.video.dataset.visible === "1" || p.video.seeking) p.render(p.video.currentTime || 0);
    });
    requestAnimationFrame(tick);
  }

  /* -------------------- teaser -------------------- */
  // One large player + environment thumbnails. It auto-advances Doom -> CS2 -> FPV at the end
  // of each clip until the user picks an environment, scrubs, or pauses.
  function buildTeaser() {
    const main = $("#teaser-main");
    const thumbsRoot = $("#teaser-envs");
    if (!main || !thumbsRoot) return;
    const ENVS = ["doom", "cs2", "fpv"];
    const st = { env: ENVS[0], kind: "smooth", auto: true };

    const thumbs = ENVS.map((env) => {
      const b = el("button", { type: "button", class: "tz-thumb", "data-env": env, "aria-label": ENV_NAME[env] },
        `<span class="tz-frame"><img class="tz-img" alt="" loading="lazy"><span class="tz-bar"></span></span>` +
        `<span class="tz-name">${ENV_NAME[env]}</span>`);
      b.addEventListener("click", () => { st.auto = false; select(env); });
      thumbsRoot.appendChild(b);
      return { env, b, img: $(".tz-img", b), bar: $(".tz-bar", b) };
    });

    const player = new RatePlayer({
      env: st.env, kind: st.kind, sample: 1, loop: false,
      onRender: (frac) => thumbs.forEach((t) => { t.bar.style.width = t.env === st.env ? `${frac * 100}%` : "0"; }),
    });
    main.appendChild(player.root);

    function paintThumbs() {
      thumbs.forEach((t) => {
        t.b.classList.toggle("active", t.env === st.env);
        t.img.src = `${POSTER_ROOT}/${t.env}/switch/${t.env}_${st.kind}_switch_video1.jpg`;
      });
    }
    let finishing = false;
    function select(env) {
      st.env = env;
      finishing = false;
      player.load(env, st.kind, 1);
      paintThumbs();
    }

    // end of clip: next environment (auto mode) or replay. `timeupdate` near the end is a fallback
    // for browsers / headless runs that do not fire `ended` reliably.
    function onClipEnd() {
      if (finishing) return;
      finishing = true;
      if (st.auto) select(ENVS[(ENVS.indexOf(st.env) + 1) % ENVS.length]);
      else {
        const v = player.video;
        v.currentTime = 0;
        v.play().catch(() => {});
        setTimeout(() => { finishing = false; }, 300);
      }
    }
    player.video.addEventListener("ended", onClipEnd);
    player.video.addEventListener("timeupdate", () => {
      const v = player.video;
      if (!v.paused && Number.isFinite(v.duration) && v.duration > 0 && v.duration - v.currentTime < 0.06) onClipEnd();
    });
    player.chart.addEventListener("pointerdown", () => { st.auto = false; });
    player.video.addEventListener("pause", () => { if (player.video.dataset.userPaused === "1") st.auto = false; });

    const seg = $("#teaser-schedule");
    seg.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      seg.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
      st.kind = b.dataset.v;
      select(st.env);
    }));
    paintThumbs();
  }

  /* -------------------- multi-rate comparison (shared physical clock) -------------------- */
  const ICON_PLAY = '<svg viewBox="0 0 16 16"><path d="M4.5 2.5v11l9-5.5z" fill="currentColor"/></svg>';
  const ICON_PAUSE = '<svg viewBox="0 0 16 16"><path d="M4 2.5h3v11H4zM9 2.5h3v11H9z" fill="currentColor"/></svg>';

  function buildMultirate(root) {
    const META = window.RAR_MULTIRATE || {};
    const envs = Object.keys(META);
    if (!root || !envs.length) return;
    const st = { env: envs[0] };

    const controls = el("div", { class: "g-controls" });
    const stage = el("div", { class: "mr-stage", title: "Click to play / pause" });
    const video = makeVideo(false);
    const overlay = el("div", { class: "mr-overlay" });
    stage.append(video, overlay, el("div", { class: "rp-paused" }));

    const bar = el("div", { class: "mr-bar" });
    const playBtn = el("button", { class: "mr-play", type: "button", "aria-label": "Play / pause" }, ICON_PAUSE);
    const track = el("div", { class: "mr-track", title: "Click or drag to scrub" });
    const rail = el("div", { class: "mr-rail" });
    const fill = el("div", { class: "mr-fill" });
    const knob = el("div", { class: "mr-knob" });
    track.append(rail, fill, knob);
    const timeEl = el("div", { class: "mr-time" });
    bar.append(playBtn, track, timeEl);
    const checks = el("div", { class: "mr-checks" });

    let cells = [];
    let ticks = [];
    let checkBtns = [];

    const meta = () => META[st.env];
    const frameOf = (k, f, m) => Math.min(Math.floor(((m.frames - 1) * f) / m.fps + 0.5), Math.floor((k * f) / m.fps + 0.5));

    function load(env) {
      st.env = env;
      const m = meta();
      setVideo(video, `multirate/${env}`);
      stage.style.aspectRatio = `${m.width} / ${m.height}`;
      overlay.style.gridTemplateColumns = m.rates.map(() => `${m.panelW}fr`).join(` ${m.gap}fr `);
      overlay.innerHTML = "";
      cells = m.rates.map((r, i) => {
        const c = el("div", { class: "mr-cell" },
          `<span class="mr-chip">${r.f} FPS<span class="mr-dt">&Delta;t ${(1000 / r.f).toFixed(1)} ms</span>` +
          `${r.type === "interp" ? '<span class="tag">Interp.</span>' : ""}</span>` +
          `<span class="mr-frame">frame <b>000</b></span>`);
        overlay.appendChild(c);
        if (i < m.rates.length - 1) overlay.appendChild(el("div"));
        return { f: r.f, out: $(".mr-frame b", c) };
      });
      ticks.forEach((t) => t.remove());
      ticks = m.checkpoints.map((cp) => {
        const t = el("div", { class: "mr-tick", style: `left:${(cp / m.duration) * 100}%` });
        track.insertBefore(t, fill);
        return t;
      });
      checks.innerHTML = '<span class="g-label">Matched physical times</span>';
      checkBtns = m.checkpoints.map((cp) => {
        const b = el("button", { type: "button" }, `${cp.toFixed(2)} s`);
        b.addEventListener("click", () => seek(cp + 0.3 / m.fps, true));
        checks.appendChild(b);
        return { cp, b };
      });
      render(0);
    }

    function render(t) {
      const m = meta();
      const k = Math.max(0, Math.min(m.frames - 1, Math.floor(t * m.fps + 1e-6)));
      const tk = k / m.fps;
      cells.forEach(({ f, out }) => { out.textContent = String(frameOf(k, f, m)).padStart(3, "0"); });
      const frac = Math.min(1, t / m.duration);
      fill.style.width = `${frac * 100}%`;
      knob.style.left = `${frac * 100}%`;
      const tLast = (m.frames - 1) / m.fps;
      timeEl.innerHTML = `t = <b>${tk.toFixed(2)}</b> / ${tLast.toFixed(2)} s`;
      checkBtns.forEach(({ cp, b }) => b.classList.toggle("active", video.paused && Math.abs(cp - tk) < 0.6 / m.fps));
      const paused = video.paused;
      if (playBtn.dataset.state !== String(paused)) {
        playBtn.dataset.state = String(paused);
        playBtn.innerHTML = paused ? ICON_PLAY : ICON_PAUSE;
      }
      root.classList.toggle("is-paused", paused && video.dataset.userPaused === "1");
    }

    function seek(time, pause) {
      const m = meta();
      if (!video.getAttribute("src")) applySrc(video);
      if (pause) { video.dataset.userPaused = "1"; video.pause(); }
      const go = () => { video.currentTime = Math.max(0, Math.min(time, m.duration - 1e-3)); render(video.currentTime); };
      if (video.readyState >= 1) go(); else video.addEventListener("loadedmetadata", go, { once: true });
    }

    function toggle() {
      if (!video.getAttribute("src")) applySrc(video);
      if (video.paused) { video.dataset.userPaused = "0"; video.play().catch(() => {}); }
      else { video.dataset.userPaused = "1"; video.pause(); }
      render(video.currentTime || 0);
    }

    let dragging = false;
    const scrub = (e) => {
      const r = track.getBoundingClientRect();
      seek(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * meta().duration, false);
    };
    track.addEventListener("pointerdown", (e) => { dragging = true; track.setPointerCapture(e.pointerId); scrub(e); });
    track.addEventListener("pointermove", (e) => { if (dragging) scrub(e); });
    track.addEventListener("pointerup", () => { dragging = false; });
    track.addEventListener("pointercancel", () => { dragging = false; });
    stage.addEventListener("click", toggle);
    playBtn.addEventListener("click", toggle);
    video.addEventListener("pause", () => render(video.currentTime || 0));
    video.addEventListener("play", () => render(video.currentTime || 0));

    const envSeg = segmented("env", envs.map((k) => ({ v: k, label: ENV_NAME[k] })), st.env, (v) => load(v));
    const speedSeg = segmented("", [{ v: 1, label: "1&times;" }, { v: 0.5, label: "0.5&times;" }, { v: 0.25, label: "0.25&times;" }], 1,
      (v) => { video.playbackRate = Number(v); video.defaultPlaybackRate = Number(v); });
    video.addEventListener("loadeddata", () => {
      const a = speedSeg.querySelector("button.active");
      if (a) video.playbackRate = Number(a.dataset.v);
    });
    controls.append(group("Env", envSeg), group("Playback", speedSeg));
    root.append(controls, stage, bar, checks);
    players.add({ video, render });
    load(st.env);
  }

  /* -------------------- gallery: fixed-rate -------------------- */
  function buildFixed(root) {
    const st = { env: "doom", rate: FIXED.doom.def, sample: 1 };
    const controls = el("div", { class: "g-controls" });
    const stage = el("div", { class: "g-stage" });
    const video = makeVideo(true);
    const meta = el("div", { class: "g-meta" });
    stage.appendChild(video);

    let rateSlot = el("div");
    const envSeg = segmented("env", Object.keys(FIXED).map((k) => ({ v: k, label: ENV_NAME[k] })), st.env, (v) => {
      st.env = v; st.rate = FIXED[v].def; renderRates(); update();
    });
    const sampleSeg = segmented("", [{ v: 1, label: "#1" }, { v: 2, label: "#2" }], 1, (v) => { st.sample = v; update(); });

    function renderRates() {
      const items = FIXED[st.env].rates.map(([f, t]) => ({
        v: f, label: `${f} FPS${t === "interp" ? ' <span class="tag">Interp.</span>' : ""}`,
      }));
      const g = group("Rate", segmented("", items, st.rate, (v) => { st.rate = v; update(); }));
      rateSlot.replaceWith(g);
      rateSlot = g;
    }

    function update() {
      const [f, t, h] = FIXED[st.env].rates.find((r) => r[0] === st.rate);
      setVideo(video, `${st.env}/fixed/${st.env}_${f}fps_video${st.sample}`);
      const badge = t === "interp" ? '<span class="badge badge-interp">Interp.</span>' : '<span class="badge badge-train">Train</span>';
      meta.innerHTML =
        `<span><span class="k">Environment:</span> <b>${ENV_NAME[st.env]}</b></span>` +
        `<span><span class="k">Target rate:</span> <b>${f} FPS</b> ${badge}</span>` +
        `<span><span class="k">Physical horizon:</span> <b>${h.toFixed(1)} s</b></span>` +
        `<span><span class="k">Layout:</span> GT (left) | RAR (right)</span>`;
    }

    controls.append(group("Env", envSeg), rateSlot, group("Sample", sampleSeg));
    root.append(controls, stage, meta);
    renderRates();
    update();
  }

  /* -------------------- rate switching: shared environment selection -------------------- */
  // The switching videos and the stride-tracking plots below them always show the same environment.
  const switchEnvHooks = [];
  const setSwitchEnv = (env) => switchEnvHooks.forEach((h) => h(env));
  const markSeg = (seg, v) => seg.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.v === String(v)));

  /* -------------------- gallery: rate switching -------------------- */
  function buildSwitch(root) {
    const st = { env: "doom", sample: 1 };
    const controls = el("div", { class: "g-controls" });
    const split = el("div", { class: "g-split" });
    const pair = ["smooth", "abrupt"].map((kind) => {
      const p = new RatePlayer({ env: st.env, kind, sample: st.sample });
      split.appendChild(p.root);
      return p;
    });
    const update = () => pair.forEach((p) => p.load(st.env, p.kind, st.sample));
    const envSeg = segmented("env", Object.keys(ENV_NAME).map((k) => ({ v: k, label: ENV_NAME[k] })), st.env, (v) => setSwitchEnv(v));
    const sampleSeg = segmented("", [{ v: 1, label: "#1" }, { v: 2, label: "#2" }], 1, (v) => { st.sample = v; update(); });
    switchEnvHooks.push((v) => { if (v === st.env) return; st.env = v; markSeg(envSeg, v); update(); });
    controls.append(group("Env", envSeg), group("Sample", sampleSeg));
    root.append(controls, split);
  }

  /* -------------------- stride tracking: info (left) + smooth / abrupt plots (right) -------------------- */
  const TRACK_PEARSON = {          // from the paper (main text: FPV; appendix: Doom, CS2)
    doom: { smooth: 0.941, abrupt: 0.938 },
    cs2: { smooth: 0.899, abrupt: 0.963 },
    fpv: { smooth: 0.998, abrupt: 0.970 },
  };

  function buildTrack(root) {
    if (!root) return;
    let env = "doom";
    const side = el("div", { class: "track-side" });
    side.appendChild(el("p", {},
      "Effective stride recovered from calibrated optical flow, plotted against the rollout latent index. " +
      "The measured response follows the target schedule in every environment."));
    const envSeg = segmented("env", Object.keys(ENV_NAME).map((k) => ({ v: k, label: ENV_NAME[k] })), env, (v) => setSwitchEnv(v));
    side.appendChild(envSeg);
    const stats = el("div", { class: "track-stats" });
    const val = {};
    ["smooth", "abrupt"].forEach((k) => {
      const box = el("div", { class: "ts" },
        `<div class="ts-k">${k}</div><div class="ts-v">-</div><div class="ts-u">Pearson r</div>`);
      val[k] = $(".ts-v", box);
      stats.appendChild(box);
    });
    side.appendChild(stats);

    const right = el("div", { class: "track-main" });
    const plots = el("div", { class: "track-plots" });
    const img = {};
    ["smooth", "abrupt"].forEach((k) => {
      const fig = el("figure", { class: "tp" }, `<figcaption class="tp-title">${k === "smooth" ? "Smooth schedule" : "Abrupt schedule"}</figcaption>`);
      img[k] = el("img", { class: "zoom-src", alt: "", loading: "lazy" });
      fig.appendChild(img[k]);
      plots.appendChild(fig);
    });
    const legend = el("div", { class: "track-legend" },
      '<span class="lg"><svg viewBox="0 0 34 10"><line x1="1" y1="5" x2="33" y2="5" class="lg-target"/></svg>Target stride</span>' +
      '<span class="lg"><svg viewBox="0 0 34 10"><line x1="1" y1="5" x2="33" y2="5" class="lg-pred"/></svg>Regressed stride (mean)</span>' +
      '<span class="lg"><span class="ci-swatch"></span>95% CI</span>');
    right.append(plots, legend);
    root.append(side, right);

    function show(v) {
      env = v;
      root.dataset.env = v;
      markSeg(envSeg, v);
      ["smooth", "abrupt"].forEach((k) => {
        img[k].src = `static/images/switch/${v}_${k}.png`;
        img[k].alt = `${ENV_NAME[v]}, ${k} schedule: target vs. regressed stride`;
        val[k].textContent = TRACK_PEARSON[v][k].toFixed(3);
      });
    }
    switchEnvHooks.push((v) => { if (v !== env) show(v); });
    show(env);
  }

  /* -------------------- gallery: SANA-WM -------------------- */
  function buildSana(root) {
    const st = { rate: SANA.def, sample: 1 };
    const controls = el("div", { class: "g-controls" });
    const stage = el("div", { class: "g-stage" });
    const video = makeVideo(true);
    const meta = el("div", { class: "g-meta" });
    stage.appendChild(video);

    const items = SANA.rates.map(([f, t]) => ({
      v: f, label: `${f} FPS${t === "interp" ? ' <span class="tag">Interp.</span>' : ""}`,
    }));
    const rateSeg = segmented("", items, st.rate, (v) => { st.rate = v; update(); });
    const sampleSeg = segmented("", [{ v: 1, label: "#1" }, { v: 2, label: "#2" }], 1, (v) => { st.sample = v; update(); });

    function update() {
      const [f, t] = SANA.rates.find((r) => r[0] === st.rate);
      setVideo(video, `sanawm/sanawm_${f}fps_video${st.sample}`);
      const badge = t === "interp" ? '<span class="badge badge-interp">Interp.</span>' : '<span class="badge badge-train">Train</span>';
      meta.innerHTML =
        `<span><span class="k">Model:</span> <b>SANA-WM + RAR</b></span>` +
        `<span><span class="k">Target rate:</span> <b>${f} FPS</b> ${badge}</span>` +
        `<span><span class="k">Note:</span> opening portion of each rollout</span>`;
    }

    controls.append(group("Rate", rateSeg), group("Sample", sampleSeg));
    root.append(controls, stage, meta);
    update();
  }

  /* -------------------- math -------------------- */
  function renderMath() {
    if (!window.katex) return;
    document.querySelectorAll(".math").forEach((n) => {
      try { katex.render(n.textContent, n, { throwOnError: false }); } catch (_) {}
    });
    document.querySelectorAll(".math-display").forEach((n) => {
      try { katex.render(n.textContent, n, { throwOnError: false, displayMode: true }); } catch (_) {}
    });
  }

  /* -------------------- typography: no 1-2 word last lines -------------------- */
  // Glue the last three words of each text block with non-breaking spaces, so the final line
  // always carries at least three words. KaTeX output is skipped; long tails are left alone.
  const TIE_SEL = "p, figcaption, .lead, .hint, .figure-note, .equation-note";
  function tieLastWords(root = document) {
    root.querySelectorAll(TIE_SEL).forEach((el) => {
      if (el.closest("pre, .katex")) return;
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
        acceptNode: (n) => (n.parentElement.closest(".katex") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
      });
      const nodes = [];
      for (let n = walker.nextNode(); n; n = walker.nextNode()) nodes.push(n);
      let ties = 2, tail = 0, started = false;
      for (let i = nodes.length - 1; i >= 0 && ties > 0; i--) {
        const chars = nodes[i].data.split("");
        for (let j = chars.length - 1; j >= 0 && ties > 0; j--) {
          const ws = /\s/.test(chars[j]) && chars[j] !== "\u00a0";
          if (!started) { if (!ws) started = true; else continue; }
          if (ws) {
            let k = j;
            while (k > 0 && /\s/.test(chars[k - 1]) && chars[k - 1] !== "\u00a0") k--;
            chars.splice(k, j - k + 1, "\u00a0");
            j = k;
            ties--;
          } else if (++tail > 32) { ties = 0; }
        }
        nodes[i].data = chars.join("");
      }
    });
  }

  /* -------------------- misc UI -------------------- */
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove("show"), 1800);
  }

  function initTheme() {
    const btn = $("#theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("rar-theme", next); } catch (_) {}
    });
  }

  function initCopy() {
    const btn = $("#copy-bib");
    btn.addEventListener("click", async () => {
      const text = $("#bibtex-text").textContent;
      try {
        await navigator.clipboard.writeText(text);
      } catch (_) {
        const ta = el("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        document.execCommand("copy"); ta.remove();
      }
      btn.textContent = "Copied!";
      setTimeout(() => (btn.textContent = "Copy"), 1500);
    });
  }

  function initPendingLinks() {
    document.querySelectorAll("a[data-pending]").forEach((a) => {
      if (a.getAttribute("href") !== "#") return;
      a.addEventListener("click", (e) => { e.preventDefault(); toast(`${a.dataset.pending} link coming soon`); });
    });
  }

  function initLightbox() {
    const box = $("#lightbox");
    const img = $("img", box);
    document.querySelectorAll(".zoomable img, img.zoom-src").forEach((im) => {
      im.addEventListener("click", () => { img.src = im.src; img.alt = im.alt; box.classList.add("open"); });
    });
    box.addEventListener("click", () => box.classList.remove("open"));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") box.classList.remove("open"); });
  }

  function initNav() {
    const nav = $("#topnav");
    const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    if (!("IntersectionObserver" in window)) return;
    const links = [...document.querySelectorAll(".nav-links a")];
    const map = new Map(links.map((a) => [a.getAttribute("href").slice(1), a]));
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting && map.has(en.target.id)) {
          links.forEach((a) => a.classList.toggle("active", a === map.get(en.target.id)));
        }
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    map.forEach((_, id) => { const s = document.getElementById(id); if (s) io.observe(s); });
  }

  /* -------------------- boot -------------------- */
  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    renderMath();
    buildTeaser();
    buildMultirate($("#mr-viewer"));
    buildTrack($("#track-viewer"));
    tieLastWords();
    const builders = { fixed: buildFixed, switch: buildSwitch, sana: buildSana };
    document.querySelectorAll(".gallery[data-kind]").forEach((g) => builders[g.dataset.kind](g));
    requestAnimationFrame(tick);
    initCopy();
    initPendingLinks();
    initLightbox();
    initNav();
  });
})();
