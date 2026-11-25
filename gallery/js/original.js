// Sjónabók gallery: "Original" view. Shows a pattern on a photo of the
// manuscript page, with the digitised 0/1 chart laid over it.
//
// Two sources of "original":
//   mockup : a simulated page drawn here from the chart itself (paper, ink,
//            grid, a tilt). Works for every pattern, holds no museum image.
//   sarpur : a museum photo on sarpur.is. Shown only when
//            original/config.json has "sarpur_photos": true, i.e. once
//            Þjóðminjasafn Íslands has given permission (issue #33).
//            Otherwise the view links to the photo on Sarpur instead.
//
// Alignment: original/overlays.csv gives, per pattern and photo, the four
// photo-pixel corners of the chart (top-left, top-right, bottom-right,
// bottom-left). A projective map (homography) through those corners places
// the chart on the page; CSS matrix3d applies it. gallery/tools/align.html
// writes those rows.
(() => {
  "use strict";

  // ── geometry ────────────────────────────────────────────────────────────
  class Homography {
    // Map of the unit square (0,0) (1,0) (1,1) (0,1) to the quad p[0..3]
    // (Heckbert 1989, square-to-quad).
    constructor(p) {
      const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = p;
      const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3;
      const dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3;
      let g = 0, h = 0;
      if (Math.abs(dx3) > 1e-9 || Math.abs(dy3) > 1e-9) {
        const den = dx1 * dy2 - dx2 * dy1;
        g = (dx3 * dy2 - dx2 * dy3) / den;
        h = (dx1 * dy3 - dx3 * dy1) / den;
      }
      this.m = [x1 - x0 + g * x1, x3 - x0 + h * x3, x0,
                y1 - y0 + g * y1, y3 - y0 + h * y3, y0,
                g, h, 1];
    }
    // (u, v) in the unit square -> photo pixels
    map(u, v) {
      const [a, b, c, d, e, f, g, h, i] = this.m;
      const w = g * u + h * v + i;
      return [(a * u + b * v + c) / w, (d * u + e * v + f) / w];
    }
    // CSS matrix3d for an element of size W x H placed at the origin
    css(W, H) {
      const [a, b, c, d, e, f, g, h, i] = this.m;
      const n = (v) => +v.toFixed(8);
      return `matrix3d(${[a / W, d / W, 0, g / W, b / H, e / H, 0, h / H, 0, 0, 1, 0, c, f, 0, i].map(n).join(",")})`;
    }
  }

  // Small seeded random numbers, so a pattern's mockup is always the same
  function rng(seedText) {
    let s = 2166136261;
    for (const ch of seedText) s = Math.imul(s ^ ch.charCodeAt(0), 16777619);
    return () => {
      s = (s + 0x6d2b79f5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ── simulated page (mockup) ─────────────────────────────────────────────
  class MockPage {
    // Draws a pretend photo of a manuscript page holding the chart m.
    // Returns the canvas and the four corners of the chart on it.
    static draw(m, id) {
      const rand = rng(id);
      const w = m[0].length, h = m.length;
      const cell = Math.max(6, Math.min(16, Math.floor(620 / Math.max(w, h))));
      const margin = 4;                                   // cells of paper round the chart
      const pw = (w + 2 * margin) * cell, ph = (h + 2 * margin) * cell;
      const W = Math.round(pw * 1.25), H = Math.round(ph * 1.25);
      const ox = (W - pw) / 2, oy = (H - ph) / 2;
      // the chart's rectangle on a flat page, then tilted a little
      const rect = [[ox + margin * cell, oy + margin * cell], [ox + (margin + w) * cell, oy + margin * cell],
        [ox + (margin + w) * cell, oy + (margin + h) * cell], [ox + margin * cell, oy + (margin + h) * cell]];
      const ang = (rand() - 0.5) * 0.07, cx = W / 2, cy = H / 2;
      const jit = () => (rand() - 0.5) * cell * 1.6;
      const corners = rect.map(([x, y]) => {
        const dx = x - cx, dy = y - cy;
        return [cx + dx * Math.cos(ang) - dy * Math.sin(ang) + jit(), cy + dx * Math.sin(ang) + dy * Math.cos(ang) + jit()];
      });
      const H1 = new Homography(corners);
      const at = (cxCell, cyCell) => H1.map(cxCell / w, cyCell / h);   // chart cell coords -> pixels

      const cv = document.createElement("canvas");
      cv.width = W; cv.height = H;
      const ctx = cv.getContext("2d");
      ctx.fillStyle = "#2b2622";                         // dark backdrop, as in museum shots
      ctx.fillRect(0, 0, W, H);
      // paper: the same tilt, a margin of cells beyond the chart
      const paper = [at(-margin, -margin), at(w + margin, -margin), at(w + margin, h + margin), at(-margin, h + margin)];
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(W, H) * 0.6);
      grad.addColorStop(0, "#e2d2b0");
      grad.addColorStop(1, "#bfa77c");
      ctx.fillStyle = grad;
      MockPage.poly(ctx, paper);
      ctx.fill();
      ctx.save();
      MockPage.poly(ctx, paper);
      ctx.clip();
      for (let k = 0; k < 6; k++) {                       // stains
        const sx = rand() * W, sy = rand() * H, r = (0.05 + rand() * 0.12) * W;
        const s = ctx.createRadialGradient(sx, sy, 0, sx, sy, r);
        s.addColorStop(0, "rgba(120,85,40,0.18)");
        s.addColorStop(1, "rgba(120,85,40,0)");
        ctx.fillStyle = s;
        ctx.fillRect(0, 0, W, H);
      }
      // faint ruled grid
      ctx.strokeStyle = "rgba(90,60,30,0.25)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x <= w; x++) { const [a, b] = [at(x, 0), at(x, h)]; ctx.moveTo(...a); ctx.lineTo(...b); }
      for (let y = 0; y <= h; y++) { const [a, b] = [at(0, y), at(w, y)]; ctx.moveTo(...a); ctx.lineTo(...b); }
      ctx.stroke();
      // ink, a little uneven
      for (let y = 0; y < h; y++)
        for (let x = 0; x < w; x++)
          if (m[y][x] === "1") {
            ctx.fillStyle = `rgba(52,34,20,${0.62 + rand() * 0.3})`;
            const e = () => (rand() - 0.5) * 0.18;
            MockPage.poly(ctx, [at(x + e(), y + e()), at(x + 1 + e(), y + e()), at(x + 1 + e(), y + 1 + e()), at(x + e(), y + 1 + e())]);
            ctx.fill();
          }
      for (let k = 0; k < W * H / 900; k++) {            // paper grain
        ctx.fillStyle = `rgba(70,50,25,${rand() * 0.12})`;
        ctx.fillRect(rand() * W, rand() * H, 1 + rand() * 2, 1 + rand() * 2);
      }
      ctx.restore();
      ctx.fillStyle = "rgba(255,255,255,0.75)";
      ctx.font = `600 ${Math.max(12, Math.round(W / 45))}px Jost, sans-serif`;
      ctx.fillText("MOCKUP: simulated page, not a museum photo", 12, H - 12);
      return { canvas: cv, corners, W, H };
    }

    static poly(ctx, pts) {
      ctx.beginPath();
      pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
    }
  }

  // ── data ────────────────────────────────────────────────────────────────
  function parseCsv(text) {
    const rows = [];
    let row = [], f = "", q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"' && text[i + 1] === '"') { f += '"'; i++; }
        else if (c === '"') q = false;
        else f += c;
      } else if (c === '"') q = true;
      else if (c === ",") { row.push(f); f = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(f); f = "";
        if (row.length > 1 || row[0]) rows.push(row);
        row = [];
      } else f += c;
    }
    if (f || row.length) { row.push(f); rows.push(row); }
    const [head, ...body] = rows;
    return body.map((r) => Object.fromEntries(head.map((k, j) => [k, r[j] ?? ""])));
  }

  class OverlayData {
    constructor(base) { this.base = base; this.ready = this.load(); }
    async load() {
      const get = (f) => fetch(this.base + f).then((r) => (r.ok ? r.text() : "")).catch(() => "");
      const [cfg, csv] = await Promise.all([get("config.json"), get("overlays.csv")]);
      try { this.config = JSON.parse(cfg); } catch { this.config = {}; }
      this.rows = csv ? parseCsv(csv) : [];
    }
    photosAllowed() { return this.config.sarpur_photos === true; }
    forPattern(id) { return this.rows.filter((r) => r.pattern_id === id && r.status !== "rejected"); }
  }

  // ── the view in the detail dialog ───────────────────────────────────────
  class OriginalView {
    constructor(base) {
      this.data = new OverlayData(base);
      this.$ = (id) => document.getElementById(id);
      this.mode = "chart";
      this.src = "mockup";
      this.wire();
    }

    wire() {
      const $ = this.$;
      if (!$("d-original")) return;
      $("d-mode-chart").addEventListener("click", () => this.setMode("chart"));
      $("d-mode-orig").addEventListener("click", () => this.setMode("original"));
      $("o-overlay").addEventListener("change", () => this.style());
      $("o-fill").addEventListener("change", () => this.style());
      $("o-opacity").addEventListener("input", () => this.style());
      $("o-source").addEventListener("change", (e) => { this.src = e.target.value; this.render(); });
      window.addEventListener("resize", () => this.mode === "original" && this.render());
    }

    // called by gallery.js each time a pattern opens
    async show(pattern, matrix) {
      this.p = pattern;
      this.m = matrix;
      await this.data.ready;
      if (this.p !== pattern) return;
      this.rows = this.data.forPattern(pattern.id);
      const sarpur = this.rows.filter((r) => r.source === "sarpur");
      const sel = this.$("o-source");
      sel.innerHTML = `<option value="mockup">Mockup (simulated page)</option>` +
        sarpur.map((r, i) => `<option value="sarpur:${i}">Sarpur photo ${r.image_id}</option>`).join("");
      this.src = sarpur.length ? "sarpur:0" : "mockup";
      sel.value = this.src;
      this.$("d-mode-orig").title = sarpur.length
        ? "The manuscript page, with the chart laid over it"
        : "No museum photo aligned yet: shows a simulated page";
      this.setMode(this.mode);
    }

    setMode(mode) {
      const $ = this.$;
      this.mode = mode;
      $("d-mode-chart").setAttribute("aria-pressed", mode === "chart");
      $("d-mode-orig").setAttribute("aria-pressed", mode === "original");
      document.querySelectorAll(".d-chart-only").forEach((el) => (el.hidden = mode !== "chart"));
      $("d-original").hidden = mode !== "original";
      if (mode === "original") this.render();
    }

    render() {
      const $ = this.$;
      if (!this.m || this.mode !== "original") return;
      const stage = $("o-stage");
      stage.innerHTML = "";
      const w = this.m[0].length, h = this.m.length;
      let photo, corners, W, H, caption;
      if (this.src.startsWith("sarpur:")) {
        const r = this.rows.filter((x) => x.source === "sarpur")[+this.src.split(":")[1]];
        const rec = `https://sarpur.is/is/collection/item/${r.sarpur_oid}/`;
        const url = `https://sarpur.is/multimedia/${r.image_id.slice(-1)}/multimedia-${r.image_id}.large.jpg`;
        if (!this.data.photosAllowed()) {
          stage.style.height = "auto";
          stage.innerHTML = `<div class="o-locked"><p>This pattern is aligned to a museum photo, but photos from Sarpur are not shown here until Þjóðminjasafn Íslands has given permission.</p>
            <p><a href="${url}" target="_blank" rel="noopener">See the photo on Sarpur</a> · <a href="${rec}" target="_blank" rel="noopener">Museum record</a></p>
            <p>Switch to <b>Mockup</b> to see how the overlay works.</p></div>`;
          $("o-caption").textContent = "";
          return;
        }
        photo = new Image();
        photo.src = url;
        photo.alt = `Manuscript page, ${this.p.source_label}`;
        W = +r.image_w; H = +r.image_h;
        corners = [[+r.tl_x, +r.tl_y], [+r.tr_x, +r.tr_y], [+r.br_x, +r.br_y], [+r.bl_x, +r.bl_y]];
        caption = `Original: Þjóðminjasafn Íslands, ${this.p.source_label}, photo via <a href="${rec}" target="_blank" rel="noopener">Sarpur</a>. Overlay aligned by ${r.aligned_by || "HiDef Textiles"}.`;
      } else {
        const mock = MockPage.draw(this.m, this.p.id);
        ({ canvas: photo, corners, W, H } = mock);
        caption = "Mockup: a page simulated from the chart, to show how the overlay works. Not a museum photo.";
      }
      if (photo instanceof HTMLImageElement) { photo.width = W; photo.height = H; }   // (resizing a canvas would wipe it)
      photo.className = "o-photo";
      // crop to the chart with a margin, fit the width of the stage
      const xs = corners.map((c) => c[0]), ys = corners.map((c) => c[1]);
      const pad = 0.12 * Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
      const x0 = Math.max(0, Math.min(...xs) - pad), y0 = Math.max(0, Math.min(...ys) - pad);
      const x1 = Math.min(W, Math.max(...xs) + pad), y1 = Math.min(H, Math.max(...ys) + pad);
      const room = Math.min($("d-original").clientWidth || 560, 720);
      const s = Math.min(room / (x1 - x0), (innerHeight * 0.62) / (y1 - y0));
      stage.style.height = `${Math.round((y1 - y0) * s)}px`;
      stage.style.width = `${Math.round((x1 - x0) * s)}px`;
      const inner = document.createElement("div");
      inner.className = "o-inner";
      inner.style.transform = `scale(${s}) translate(${-x0}px, ${-y0}px)`;
      inner.appendChild(photo);
      const NS = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("class", "o-chart");
      svg.setAttribute("width", w);
      svg.setAttribute("height", h);
      svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
      let d = "";
      this.m.forEach((row, y) => { for (let x = 0; x < w; x++) if (row[x] === "1") d += `M${x} ${y}h1v1h-1z`; });
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
      const frame = document.createElementNS(NS, "rect");
      Object.entries({ x: 0, y: 0, width: w, height: h, class: "o-frame" }).forEach(([k, v]) => frame.setAttribute(k, v));
      svg.appendChild(frame);
      svg.style.transform = new Homography(corners).css(w, h);
      inner.appendChild(svg);
      stage.appendChild(inner);
      if (!this.src.startsWith("sarpur:")) stage.insertAdjacentHTML("beforeend", '<span class="o-badge">Mockup</span>');
      $("o-caption").innerHTML = caption;
      this.style();
    }

    style() {
      const svg = document.querySelector("#o-stage .o-chart");
      if (!svg) return;
      svg.style.display = this.$("o-overlay").checked ? "" : "none";
      svg.style.opacity = this.$("o-opacity").value / 100;
      svg.classList.toggle("filled", this.$("o-fill").checked);
    }
  }

  window.SjonabokOriginal = { OriginalView, Homography, MockPage, parseCsv };
  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("d-original")) window.SjonabokOriginal.view = new OriginalView("original/");
  });
})();
