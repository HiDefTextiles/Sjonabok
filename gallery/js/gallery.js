// Sjónabók gallery: client-side filters and the detail (zoom) view.
// Data: patterns/patterns.json, written by scripts/build_gallery.py.
(() => {
  "use strict";

  const BASE = "patterns/";
  // HI palette (honnun.hi.is): [label, pattern colour, background]
  const COLOURS = [
    ["HI blue", "#10099F", "#ffffff"],
    ["HI pink", "#d61f69", "#ffffff"],
    ["HI teal", "#10099F", "#2DD2C0"],
    ["Light pink", "#d61f69", "#F4B8CE"],
    ["Inverse", "#ffffff", "#10099F"],
  ];
  const KIND_LABELS = {
    border: "Border band",
    edging: "Narrow edging",
    rosette: "Rosette / star",
    motif: "Motif",
    "vertical band": "Vertical band",
  };
  const SYM = [
    ["mirror_lr", "Left–right mirror"],
    ["mirror_tb", "Top–bottom mirror"],
    ["turn180", "Half-turn"],
    ["turn90", "Quarter-turn"],
    ["diagonal", "Diagonal mirror"],
    ["glide", "Glide (bands)"],
    ["none", "No symmetry"],
  ];
  const RANGES = [
    ["trim_width", "Width (cells)"],
    ["trim_height", "Height (cells)"],
    ["density", "Density (share of filled cells)"],
  ];

  const $ = (id) => document.getElementById(id);
  const state = { kind: new Set(), sym: new Set(), group: new Set(), source: new Set(), range: {}, q: "", sort: "name" };
  let data = [];
  let byId = {};
  let current = null;

  const isAsym = (p) => !(p.mirror_lr || p.mirror_tb || p.turn180 || p.turn90 || p.diagonal || p.glide);
  const group = (p) => p.frieze || p.point || "—";

  // ── filter controls ────────────────────────────────────────────────────
  function chips(el, key, entries) {
    el.innerHTML = "";
    for (const [value, label] of entries) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.dataset.value = value;
      b.setAttribute("aria-pressed", "false");
      b.innerHTML = `${label} <span class="n"></span>`;
      b.addEventListener("click", () => {
        state[key].has(value) ? state[key].delete(value) : state[key].add(value);
        update();
      });
      el.appendChild(b);
    }
  }

  function ranges(el) {
    for (const [key, label] of RANGES) {
      const vals = data.map((p) => p[key]);
      const step = key === "density" ? 0.01 : 1;
      const lo = Math.floor(Math.min(...vals) / step) * step;
      const hi = Math.ceil(Math.max(...vals) / step) * step;
      state.range[key] = [lo, hi];
      const wrap = document.createElement("div");
      wrap.className = "range";
      wrap.innerHTML = `<span class="lbl">${label}: <output></output></span>
        <input type="range" min="${lo}" max="${hi}" step="${step}" value="${lo}" aria-label="${label} minimum">
        <input type="range" min="${lo}" max="${hi}" step="${step}" value="${hi}" aria-label="${label} maximum">`;
      const [a, b] = wrap.querySelectorAll("input");
      const out = wrap.querySelector("output");
      const fmt = (v) => (key === "density" ? Math.round(v * 100) + "%" : v);
      const sync = () => {
        let x = +a.value, y = +b.value;
        if (x > y) [x, y] = [y, x];
        state.range[key] = [x, y];
        out.textContent = `${fmt(x)}–${fmt(y)}`;
      };
      a.addEventListener("input", () => { sync(); update(); });
      b.addEventListener("input", () => { sync(); update(); });
      wrap.reset = () => { a.value = lo; b.value = hi; sync(); };
      sync();
      el.appendChild(wrap);
    }
  }

  // ── filtering ──────────────────────────────────────────────────────────
  function passes(p, skip) {
    if (state.q && !p.id.toLowerCase().includes(state.q) && !p.source_label.toLowerCase().includes(state.q)) return false;
    if (skip !== "kind" && state.kind.size && !state.kind.has(p.kind)) return false;
    if (skip !== "source" && state.source.size && !state.source.has(p.source)) return false;
    if (skip !== "group" && state.group.size && !state.group.has(group(p))) return false;
    if (skip !== "sym") {
      for (const s of state.sym) if (s === "none" ? !isAsym(p) : !p[s]) return false;
    }
    for (const [key, [lo, hi]] of Object.entries(state.range)) {
      if (p[key] < lo - 1e-9 || p[key] > hi + 1e-9) return false;
    }
    return true;
  }

  const SORTS = {
    name: (a, b) => a.source.localeCompare(b.source) || a.number - b.number || (a.part || 0) - (b.part || 0),
    cells: (a, b) => b.cells - a.cells,
    "cells-asc": (a, b) => a.cells - b.cells,
    density: (a, b) => b.density - a.density,
    "density-asc": (a, b) => a.density - b.density,
    pieces: (a, b) => b.pieces - a.pieces,
    float: (a, b) => b.float_fg - a.float_fg,
  };

  // counts on each chip show how many patterns it would add, given the other filters
  function counts(el, key, fn) {
    const c = {};
    for (const p of data) if (passes(p, key)) for (const v of [].concat(fn(p))) c[v] = (c[v] || 0) + 1;
    for (const b of el.querySelectorAll(".chip")) {
      const on = state[key].has(b.dataset.value);
      b.setAttribute("aria-pressed", on);
      b.querySelector(".n").textContent = c[b.dataset.value] || 0;
      b.classList.toggle("empty", !c[b.dataset.value] && !on);
    }
  }

  function update() {
    const shown = data.filter((p) => passes(p)).sort(SORTS[state.sort]);
    const grid = $("grid");
    const frag = document.createDocumentFragment();
    for (const p of shown) frag.appendChild(p.card);
    // dense packing keeps wide band tiles from leaving holes in the grid
    grid.style.gridAutoFlow = state.sort === "name" ? "row dense" : "row";
    grid.replaceChildren(frag);
    $("count").textContent = `Showing ${shown.length} of ${data.length} patterns`;
    counts($("f-kind"), "kind", (p) => p.kind);
    counts($("f-source"), "source", (p) => p.source);
    counts($("f-group"), "group", group);
    counts($("f-sym"), "sym", (p) => (isAsym(p) ? ["none"] : SYM.map((s) => s[0]).filter((k) => p[k])));
    const active = ["kind", "sym", "group", "source"].reduce((n, k) => n + state[k].size, 0) + (state.q ? 1 : 0);
    $("active-n").textContent = active ? `(${active} on) · ${shown.length} shown` : `· ${shown.length} patterns`;
    saveUrl();
  }

  function card(p) {
    const a = document.createElement("a");
    a.className = p.trim_width >= 2.5 * p.trim_height ? "tile wide" : "tile";
    a.href = `#${p.id}`;
    a.title = `${p.id}: ${KIND_LABELS[p.kind]}, ${p.trim_width}×${p.trim_height}`;
    a.innerHTML = `<span class="thumb"><img loading="lazy" src="${BASE}thumb/${p.id}.png" alt="Pattern ${p.id}"></span>
      <span class="cap"><b>${p.source_label}</b> ${p.number}${p.part ? "." + p.part : ""}<br>
      <small>${KIND_LABELS[p.kind]} · ${p.trim_width}×${p.trim_height}</small></span>`;
    return a;
  }

  // ── URL state (shareable filters) ──────────────────────────────────────
  function saveUrl() {
    const u = new URLSearchParams();
    for (const k of ["kind", "sym", "group", "source"]) if (state[k].size) u.set(k, [...state[k]].join(","));
    if (state.q) u.set("q", state.q);
    if (state.sort !== "name") u.set("sort", state.sort);
    const qs = u.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
  }

  function loadUrl() {
    const u = new URLSearchParams(location.search);
    for (const k of ["kind", "sym", "group", "source"]) if (u.get(k)) u.get(k).split(",").forEach((v) => state[k].add(v));
    state.q = (u.get("q") || "").toLowerCase();
    state.sort = SORTS[u.get("sort")] ? u.get("sort") : "name";
    $("q").value = state.q;
    $("sort").value = state.sort;
  }

  // ── detail view ────────────────────────────────────────────────────────
  const view = { zoom: 8, grid: true, colour: 0, tile: false, matrix: null };

  function draw() {
    const m = view.matrix;
    if (!m) return;
    const [fg, bg] = COLOURS[view.colour].slice(1);
    const reps = view.tile ? 3 : 1;
    const z = view.zoom, h = m.length, w = m[0].length;
    const cv = $("d-canvas");
    cv.width = w * z * reps;
    cv.height = h * z * (view.tile && current.kind !== "border" && current.kind !== "edging" ? reps : 1);
    const ctx = cv.getContext("2d");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = fg;
    for (let ty = 0; ty * h * z < cv.height; ty++)
      for (let tx = 0; tx < reps; tx++)
        for (let y = 0; y < h; y++)
          for (let x = 0; x < w; x++)
            if (m[y][x] === "1") ctx.fillRect((tx * w + x) * z, (ty * h + y) * z, z, z);
    if (view.grid && z >= 4) {
      ctx.strokeStyle = "rgba(38,38,38,0.18)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x <= cv.width; x += z) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, cv.height); }
      for (let y = 0; y <= cv.height; y += z) { ctx.moveTo(0, y + 0.5); ctx.lineTo(cv.width, y + 0.5); }
      ctx.stroke();
      // every tenth line darker, as on a printed chart
      ctx.strokeStyle = "rgba(38,38,38,0.45)";
      ctx.beginPath();
      for (let x = 0; x <= cv.width; x += 10 * z) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, cv.height); }
      for (let y = 0; y <= cv.height; y += 10 * z) { ctx.moveTo(0, y + 0.5); ctx.lineTo(cv.width, y + 0.5); }
      ctx.stroke();
    }
  }

  function fact(label, value) {
    return value === null || value === undefined || value === "" ? "" : `<dt>${label}</dt><dd>${value}</dd>`;
  }

  const pct = (v) => Math.round(v * 100) + "%";

  async function openDetail(id) {
    const p = byId[id];
    if (!p) return;
    current = p;
    $("d-source").textContent = p.source_label;
    $("d-title").textContent = p.id;
    const syms = SYM.filter(([k]) => k !== "none" && p[k]).map((s) => s[1]).join(", ") || "None found";
    const grp = p.frieze ? `${p.frieze} (${p.frieze_name})` : p.point ? `${p.point} (${p.point_name})` : "—";
    $("d-facts").innerHTML =
      fact("Source", `${p.source_label}, no. ${p.number}${p.part ? `, part ${p.part}` : ""}`) +
      fact("Type", KIND_LABELS[p.kind]) +
      fact("Chart size", `${p.width} × ${p.height} cells`) +
      fact("Pattern size", `${p.trim_width} × ${p.trim_height} cells (margins trimmed)`) +
      fact("Repeat", p.period ? `every ${p.period} cells` : null) +
      fact("Filled cells", `${p.ones} (${pct(p.density)})`) +
      fact("Symmetry", syms) +
      fact("Symmetry group", grp) +
      fact("Separate pieces", p.pieces) +
      fact("Longest float", `${p.float_fg} filled, ${p.float_bg} empty cells in a row`);
    $("d-txt").href = `${BASE}txt/${p.id}.txt`;
    $("d-png").href = `${BASE}png/${p.id}.png`;
    $("d-link").href = `#${p.id}`;
    $("d-similar").innerHTML = p.similar
      .map((s) => `<a href="#${s}" title="${s}"><img loading="lazy" src="${BASE}thumb/${s}.png" alt="${s}"></a>`)
      .join("");
    const room = Math.min(560, $("detail").clientWidth ? $("detail").clientWidth - 70 : innerWidth - 70);
    view.zoom = Math.max(2, Math.min(24, Math.floor(Math.max(room, 200) / p.width), Math.floor(560 / p.height)));
    $("d-zoom").value = view.zoom;
    view.matrix = null;
    if (!$("detail").open) {
      $("detail").showModal();
      const fit = $("detail").clientWidth - 70;  // re-fit now the dialog has its real size
      view.zoom = Math.max(2, Math.min(24, Math.floor(Math.min(fit, 560) / p.width), Math.floor(560 / p.height)));
    }
    $("d-zoom").value = view.zoom;
    $("detail").scrollTop = 0;
    const txt = await fetch(`${BASE}txt/${p.id}.txt`).then((r) => r.text());
    if (current !== p) return;
    view.matrix = txt.split(/\r?\n/).filter((r) => r.trim());
    draw();
  }

  function setupDetail() {
    const sw = $("d-colours");
    COLOURS.forEach(([label, fg, bg], i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "swatch";
      b.title = label;
      b.setAttribute("aria-label", label);
      b.style.background = `linear-gradient(135deg, ${fg} 50%, ${bg} 50%)`;
      b.addEventListener("click", () => {
        view.colour = i;
        sw.querySelectorAll(".swatch").forEach((s, j) => s.setAttribute("aria-pressed", i === j));
        draw();
      });
      b.setAttribute("aria-pressed", i === 0);
      sw.appendChild(b);
    });
    $("d-zoom").addEventListener("input", (e) => { view.zoom = +e.target.value; draw(); });
    $("d-grid").addEventListener("change", (e) => { view.grid = e.target.checked; draw(); });
    $("d-tile").addEventListener("change", (e) => { view.tile = e.target.checked; draw(); });
    const cellAt = (e) => {
      if (!view.matrix) return;
      const r = e.target.getBoundingClientRect();
      const scale = e.target.width / r.width;
      const h = view.matrix.length, w = view.matrix[0].length;
      const x = Math.floor(((e.clientX - r.left) * scale) / view.zoom) % w;
      const y = Math.floor(((e.clientY - r.top) * scale) / view.zoom) % h;
      if (view.matrix[y]) $("d-cell").textContent = `Row ${y + 1} of ${h}, column ${x + 1} of ${w}: ${view.matrix[y][x] === "1" ? "filled" : "empty"}`;
    };
    $("d-canvas").addEventListener("pointermove", cellAt);
    $("d-canvas").addEventListener("pointerdown", cellAt);
    $("detail").addEventListener("close", () => {
      current = null;
      history.replaceState(null, "", location.pathname + location.search);
    });
    $("detail").addEventListener("click", (e) => { if (e.target === $("detail")) $("detail").close(); });
    window.addEventListener("hashchange", () => openDetail(decodeURIComponent(location.hash.slice(1))));
  }

  // ── start ──────────────────────────────────────────────────────────────
  async function init() {
    const json = await fetch(`${BASE}patterns.json`).then((r) => r.json());
    data = json.patterns;
    for (const p of data) { byId[p.id] = p; p.card = card(p); }
    const kinds = Object.keys(KIND_LABELS).filter((k) => json.kinds[k]);
    chips($("f-kind"), "kind", kinds.map((k) => [k, KIND_LABELS[k]]));
    chips($("f-sym"), "sym", SYM);
    const groups = [...new Set(data.map(group))].sort();
    chips($("f-group"), "group", groups.map((g) => [g, g]));
    const sources = [...new Map(data.map((p) => [p.source, p.source_label]))].sort((a, b) => a[1].localeCompare(b[1], "is"));
    chips($("f-source"), "source", sources);
    ranges($("f-range"));
    loadUrl();
    $("q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); update(); });
    $("sort").addEventListener("change", (e) => { state.sort = e.target.value; update(); });
    $("reset").addEventListener("click", () => {
      for (const k of ["kind", "sym", "group", "source"]) state[k].clear();
      state.q = ""; $("q").value = "";
      document.querySelectorAll(".range").forEach((r) => r.reset());
      update();
    });
    $("toggle-filters").addEventListener("click", (e) => {
      const open = document.querySelector(".filters").classList.toggle("open");
      e.currentTarget.setAttribute("aria-expanded", open);
    });
    setupDetail();
    update();
    if (location.hash.length > 1) openDetail(decodeURIComponent(location.hash.slice(1)));
  }

  // inside an iframe (e.g. on hideftextiles.github.io) drop the site chrome
  try { if (window.self !== window.top) document.documentElement.classList.add("embedded"); }
  catch (e) { document.documentElement.classList.add("embedded"); }

  document.addEventListener("DOMContentLoaded", init);
})();
