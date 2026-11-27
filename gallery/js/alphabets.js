// Alphabets page: one tab per region (gallery/regions.csv, via patterns.json),
// each with the region's overview sheet, a source legend and every alphabet
// sheet as one tile. Tiles open the pattern in the gallery's detail view.
(() => {
  "use strict";

  const BASE = "patterns/";
  const el = (tag, attrs = {}, html = "") => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    e.innerHTML = html;
    return e;
  };

  function pane(region, items, active) {
    const p = el("div", {
      class: "tab-pane fade" + (active ? " show active" : ""), id: `pane-${region.region}`,
      role: "tabpanel", "aria-labelledby": `tab-${region.region}`,
    });
    if (region.note) p.appendChild(el("p", { class: "hint" }, region.note));
    if (!items.length) {
      p.appendChild(el("p", {}, `No alphabets from ${region.label} are digitised yet. ` +
        `Printed books with alphabet pages are listed on the <a href="about.html#books">About page</a>; ` +
        `their alphabets will be added here, and as fonts in <a href="https://github.com/HiDefTextiles/Sjonabok-stafrof">Sjónabókarstafróf</a>.`));
      return p;
    }
    const sources = new Map();
    for (const a of items) {
      if (!sources.has(a.source)) sources.set(a.source, { label: a.source_label, color: a.color, n: 0 });
      sources.get(a.source).n++;
    }
    p.appendChild(el("ul", { class: "source-legend" }, [...sources].map(([s, d]) =>
      `<li><a href="index.html?kind=alphabet&source=${encodeURIComponent(s)}"><span class="swatch" style="background:${d.color}"></span>${d.label} (${d.n})</a></li>`).join("")));
    const img = `${BASE}overview-alphabets-${region.region}.png`;
    p.appendChild(el("div", { class: "overview-sheet" },
      `<a href="${img}"><img src="${img}" alt="Every alphabet sheet from ${region.label}, packed together, one colour per source"></a>`));
    const grid = el("div", { class: "tiles" });
    for (const a of items) {
      const font = a.font_page
        ? `<a href="${a.font_page}" target="_blank" rel="noopener">font</a>`
        : `<span title="${a.font_note || ""}">no font</span>`;
      const t = el("div", { class: a.show[0] >= 2.5 * a.show[1] ? "tile wide" : "tile" },
        `<a class="thumb" href="index.html#${a.id}" title="${a.id}"><img loading="lazy" src="${BASE}thumb/${a.id}.png" alt="Alphabet ${a.id}"></a>
         <span class="cap"><b>${a.source_label}</b> ${a.printed ? "pl." : "p."} ${a.number}<br>
         <small>${a.trim_width}×${a.trim_height} · <a href="index.html#${a.id}">chart</a> · ${font}</small></span>`);
      grid.appendChild(t);
    }
    p.appendChild(grid);
    return p;
  }

  async function init() {
    const json = await fetch(`${BASE}patterns.json`).then((r) => r.json());
    const alphabets = json.patterns.filter((p) => p.kind === "alphabet");   // already in source order
    const regions = json.regions || [];
    const tabs = document.getElementById("alpha-tabs");
    const panes = document.getElementById("alpha-panes");
    panes.innerHTML = "";
    const wanted = (location.hash || "").slice(1);
    const first = regions.find((r) => r.region === wanted) ? wanted : (regions[0] || {}).region;
    for (const r of regions) {
      const items = alphabets.filter((a) => a.collection === r.region);
      const on = r.region === first;
      const li = el("li", { class: "nav-item", role: "presentation" });
      const b = el("button", {
        class: "nav-link" + (on ? " active" : ""), id: `tab-${r.region}`, type: "button", role: "tab",
        "data-bs-toggle": "tab", "data-bs-target": `#pane-${r.region}`, "aria-controls": `pane-${r.region}`,
        "aria-selected": on,
      }, `${r.label} <span class="n">${items.length}</span>`);
      b.addEventListener("shown.bs.tab", () => history.replaceState(null, "", `#${r.region}`));
      li.appendChild(b);
      tabs.appendChild(li);
      panes.appendChild(pane(r, items, on));
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
