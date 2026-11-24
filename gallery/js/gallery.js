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

  // Facets measured from the chart itself (scripts/facets.py) and look-alike families
  // (analysis/subjects/families.R): no labels, see the Methods page.
  const FACETS = [["family", "Look-alike family"], ["fit", "Fit on 85 needles"], ["outline", "Outline"], ["stroke", "Stroke"], ["open", "Openness"]];
  const FILTER_KEYS = ["kind", "theme", "subject", "sym", "group", "source", ...FACETS.map((f) => f[0])];

  const $ = (id) => document.getElementById(id);
  const state = { range: {}, q: "", sort: "name" };
  for (const k of FILTER_KEYS) state[k] = new Set();
  let FACET_LABELS = {};
  let FAMILIES = {};
  let data = [];
  let THEMES = {};     // main group key -> label (Animals, Plants, Ornament)
  let SUBJECTS = {};   // subject key -> label, only those reviewed so far
  let byId = {};
  let current = null;

  const isAsym = (p) => !(p.mirror_lr || p.mirror_tb || p.turn180 || p.turn90 || p.diagonal || p.glide);
  const group = (p) => p.frieze || p.point || "—";
  // a chart reviewed as "not sure" has subjects but no group: it is reviewed, not unsorted
  const themes = (p) => (p.themes && p.themes.length ? p.themes : p.subjects && p.subjects.length ? ["unclear"] : ["unsorted"]);
  const subjects = (p) => (p.subjects && p.subjects.length ? p.subjects : ["unsorted"]);
  const facet = (k) => (p) => (k === "family" ? p.family || "—" : (p.facets || {})[k] || "—");

  // ── filter controls ────────────────────────────────────────────────────
  function chips(el, key, entries) {
    el.innerHTML = "";
    for (const [value, label, thumb, title] of entries) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.dataset.value = value;
      b.setAttribute("aria-pressed", "false");
      b.innerHTML = (thumb ? `<img src="${BASE}thumb/${thumb}.png" alt="" loading="lazy">` : "") + `${label} <span class="n"></span>`;
      if (title) b.title = title;
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
    if (skip !== "theme" && state.theme.size && !themes(p).some((s) => state.theme.has(s))) return false;
    if (skip !== "subject" && state.subject.size && !subjects(p).some((s) => state.subject.has(s))) return false;
    if (skip !== "source" && state.source.size && !state.source.has(p.source)) return false;
    if (skip !== "group" && state.group.size && !state.group.has(group(p))) return false;
    for (const [k] of FACETS) if (skip !== k && state[k].size && !state[k].has(facet(k)(p))) return false;
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
    // along the look-alike tree: neighbours look alike (motifs first, then bands)
    alike: (a, b) => (a.order || 1e9) - (b.order || 1e9),
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
    // in look-alike order, mark where one family ends and the next begins
    let last = null;
    for (const p of shown) { p.card.classList.toggle("family-start", state.sort === "alike" && p.family !== last); p.card.dataset.family = p.family || ""; last = p.family; }
    grid.replaceChildren(frag);
    $("count").textContent = `Showing ${shown.length} of ${data.length} patterns`;
    counts($("f-kind"), "kind", (p) => p.kind);
    counts($("f-source"), "source", (p) => p.source);
    counts($("f-theme"), "theme", themes);
    counts($("f-subject"), "subject", subjects);
    counts($("f-group"), "group", group);
    for (const [k] of FACETS) if ($("f-" + k)) counts($("f-" + k), k, facet(k));
    counts($("f-sym"), "sym", (p) => (isAsym(p) ? ["none"] : SYM.map((s) => s[0]).filter((k) => p[k])));
    const active = FILTER_KEYS.reduce((n, k) => n + state[k].size, 0) + (state.q ? 1 : 0);
    $("active-n").textContent = active ? `(${active} on) · ${shown.length} shown` : `· ${shown.length} patterns`;
    saveUrl();
  }

  function card(p) {
    const a = document.createElement("a");
    a.className = p.trim_width >= 2.5 * p.trim_height ? "tile wide" : "tile";
    a.href = `#${p.id}`;
    a.title = `${p.id}: ${KIND_LABELS[p.kind]}, ${p.trim_width}×${p.trim_height}`;
    a.innerHTML = `<span class="thumb"><img loading="lazy" src="${BASE}thumb/${p.id}.png" alt="Pattern ${p.id}"></span>
      <span class="cap"><b>${p.source_label}</b> p. ${p.number}${p.part ? ` · ${p.part}/${p.on_page}` : ""}<br>
      <small>${KIND_LABELS[p.kind]} · ${p.trim_width}×${p.trim_height}</small></span>`;
    return a;
  }

  // ── URL state (shareable filters) ──────────────────────────────────────
  function saveUrl() {
    const u = new URLSearchParams();
    for (const k of FILTER_KEYS) if (state[k].size) u.set(k, [...state[k]].join(","));
    if (state.q) u.set("q", state.q);
    if (state.sort !== "name") u.set("sort", state.sort);
    const qs = u.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
  }

  function loadUrl() {
    const u = new URLSearchParams(location.search);
    for (const k of FILTER_KEYS) if (u.get(k)) u.get(k).split(",").forEach((v) => state[k].add(v));
    state.q = (u.get("q") || "").toLowerCase();
    state.sort = SORTS[u.get("sort")] ? u.get("sort") : "name";
    $("q").value = state.q;
    $("sort").value = state.sort;
  }

  // ── detail view ────────────────────────────────────────────────────────
  const view = { zoom: 8, grid: true, colour: 0, tile: false, matrix: null };

  // Bounds of the filled area (charts can carry empty margins)
  function inkBounds(m) {
    let x0 = Infinity, x1 = -1, y0 = Infinity, y1 = -1;
    m.forEach((row, y) => {
      const f = row.indexOf("1"), l = row.lastIndexOf("1");
      if (f >= 0) { x0 = Math.min(x0, f); x1 = Math.max(x1, l); y0 = Math.min(y0, y); y1 = y; }
    });
    return x1 < 0 ? { x0: 0, x1: m[0].length - 1, y0: 0, y1: m.length - 1 } : { x0, x1, y0, y1 };
  }

  // Repeat view. A band with a known repeat keeps the chart's own start
  // (its edge piece) and then continues from the last full repeat, so the
  // seam always falls in phase. Other patterns are tiled whole.
  function repeatLayout(m) {
    const h = m.length, w = m[0].length, p = current.period;
    const along = current.kind === "vertical band" ? "y" : "x";
    const layout = (W, H, src, extra = {}) =>
      ({ W, H, src, at: (x, y) => { const [sx, sy] = src(x, y); return m[sy][sx]; }, ...extra });
    if (!view.tile) return layout(w, h, (x, y) => [x, y]);
    if (!p || !["border", "edging", "vertical band"].includes(current.kind))
      return current.kind === "border" || current.kind === "edging"
        ? layout(3 * w, h, (x, y) => [x % w, y])
        : layout(3 * w, 3 * h, (x, y) => [x % w, y % h]);
    const b = inkBounds(m);
    if (along === "x") {
      const end = b.x1 + 1;
      return layout(end + Math.max(2 * p, end), h,
        (x, y) => [x < end ? x : end - p + ((x - end) % p), y], { seam: end });
    }
    const end = b.y1 + 1;
    return layout(w, end + Math.max(2 * p, end),
      (x, y) => [x, y < end ? y : end - p + ((y - end) % p)], { seamY: end });
  }

  function draw() {
    const m = view.matrix;
    if (!m) return;
    const [fg, bg] = COLOURS[view.colour].slice(1);
    const z = view.zoom;
    const L = view.layout = repeatLayout(m);
    const cv = $("d-canvas");
    cv.width = L.W * z;
    cv.height = L.H * z;
    const ctx = cv.getContext("2d");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = fg;
    for (let y = 0; y < L.H; y++)
      for (let x = 0; x < L.W; x++)
        if (L.at(x, y) === "1") ctx.fillRect(x * z, y * z, z, z);
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
    if (L.seam || L.seamY) {   // where the original chart ends
      ctx.strokeStyle = "#2DD2C0";
      ctx.lineWidth = 2;
      ctx.setLineDash([z, z]);
      ctx.beginPath();
      if (L.seam) { ctx.moveTo(L.seam * z, 0); ctx.lineTo(L.seam * z, cv.height); }
      else { ctx.moveTo(0, L.seamY * z); ctx.lineTo(cv.width, L.seamY * z); }
      ctx.stroke();
      ctx.setLineDash([]);
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
    $("d-title").textContent = p.source_label;
    const syms = SYM.filter(([k]) => k !== "none" && p[k]).map((s) => s[1]).join(", ") || "None found";
    const grp = p.frieze ? `${p.frieze} (${p.frieze_name})` : p.point ? `${p.point} (${p.point_name})` : "—";
    $("d-facts").innerHTML =
      fact("Page", `${p.number} in <i>Íslensk sjónabók</i> (2009)`) +
      fact("Motif", p.part ? `${p.part} of ${p.on_page} on this page` : null) +
      fact("File", `<code>${p.id}</code>`) +
      fact("Type", KIND_LABELS[p.kind]) +
      fact("Main group", p.themes && p.themes.length ? p.themes.map((k) => THEMES[k] || k).join(", ") : null) +
      fact("Subject", p.subjects && p.subjects.length ? p.subjects.map((k) => SUBJECTS[k] || k).join(", ") : null) +
      fact("Look-alike family", p.family ? `${p.family} (${(FAMILIES[p.family] || {}).n || "?"} charts; close family ${p.close})` : null) +
      fact("Look", p.facets ? ["outline", "stroke", "open", "fit"].map((k) => (FACET_LABELS[k] || {})[p.facets[k]] || p.facets[k]).join(", ") : null) +
      fact("Chart size", `${p.width} × ${p.height} cells`) +
      fact("Pattern size", `${p.trim_width} × ${p.trim_height} cells (margins trimmed)`) +
      fact("Repeat", p.period ? `every ${p.period} cells` + (p.repeat_status
        ? ` (${p.repeat_status === "ok" ? "checked" : "check"}: ${(p.repeat_mismatch * 100).toFixed(1)}% of cells differ)` : "") : null) +
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
      const vx = Math.floor(((e.clientX - r.left) * scale) / view.zoom);
      const vy = Math.floor(((e.clientY - r.top) * scale) / view.zoom);
      if (!view.layout || vx >= view.layout.W || vy >= view.layout.H) return;
      const [x, y] = view.layout.src(vx, vy);
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
    // how many motifs share a page (same source and page number)
    const perPage = {};
    for (const p of data) { const k = p.source + "_" + p.number; perPage[k] = (perPage[k] || 0) + 1; }
    for (const p of data) p.on_page = perPage[p.source + "_" + p.number];
    for (const p of data) { byId[p.id] = p; p.card = card(p); }
    const kinds = Object.keys(KIND_LABELS).filter((k) => json.kinds[k]);
    chips($("f-kind"), "kind", kinds.map((k) => [k, KIND_LABELS[k]]));
    chips($("f-sym"), "sym", SYM);
    THEMES = json.themes || {};
    if (Object.keys(THEMES).length) {
      chips($("f-theme"), "theme", [...Object.entries(THEMES), ["unclear", "Not sure"], ["unsorted", "Not yet sorted"]]);
      $("f-theme-box").hidden = false;
    }
    SUBJECTS = json.subjects || {};
    if (Object.keys(SUBJECTS).length) {
      chips($("f-subject"), "subject", [...Object.entries(SUBJECTS), ["unsorted", "Not yet sorted"]]);
      $("f-subject-box").hidden = false;
    }
    FACET_LABELS = json.facets || {};
    FAMILIES = json.families || {};
    for (const [k] of FACETS) {
      const box = $("f-" + k + "-box");
      if (!box) continue;
      const entries = k === "family"
        ? Object.entries(FAMILIES).map(([f, v]) => [f, `${f}`, v.example, v.label])
        : Object.entries(FACET_LABELS[k] || {});
      if (!entries.length) continue;
      chips($("f-" + k), k, entries);
      box.hidden = false;
    }
    if (!Object.keys(FAMILIES).length) $("sort").querySelector('option[value="alike"]')?.remove();
    const groups = [...new Set(data.map(group))].sort();
    chips($("f-group"), "group", groups.map((g) => [g, g]));
    const sources = [...new Map(data.map((p) => [p.source, p.source_label]))].sort((a, b) => a[1].localeCompare(b[1], "is"));
    chips($("f-source"), "source", sources);
    ranges($("f-range"));
    loadUrl();
    // drop filter values from an old link that no chip offers any more
    for (const k of FILTER_KEYS) {
      const el = $("f-" + k);
      if (!el) { state[k].clear(); continue; }
      const offered = new Set([...el.querySelectorAll(".chip")].map((b) => b.dataset.value));
      for (const v of [...state[k]]) if (!offered.has(v)) state[k].delete(v);
    }
    if (![...$("sort").options].some((o) => o.value === state.sort)) { state.sort = "name"; $("sort").value = "name"; }
    $("q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); update(); });
    $("sort").addEventListener("change", (e) => { state.sort = e.target.value; update(); });
    $("reset").addEventListener("click", () => {
      for (const k of FILTER_KEYS) state[k].clear();
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
