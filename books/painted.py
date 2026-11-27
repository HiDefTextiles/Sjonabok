#!/usr/bin/env python3
"""Colour charts painted on millimetre graph paper (weaving and embroidery
school books, such as Vänersborgs museum VM21882): each pattern cell is a
graph-paper square filled with watercolour or ink, in any number of colours.

The empty squares of the paper give the local grid (WarpedGrid). Cells far
from any paper square are outside the ruled area (text, margins) and are
left out. Each cell inside the ruled area is given the median colour of its
inner window; a cell is ink when that colour is far from the paper colour
(CIELAB distance). The ink colours are then named per book by clustering
(see PaintedBook), so a chart is written with digits 0 (empty) and 1..9,
one digit per ink of the book's palette.
    python3 painted.py outdir page.webp [page.webp ...]   # one book
"""
import argparse, csv, json
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage
from woodcut import WoodcutPage
from warped import WarpedGrid
from graph import GraphGrid


class PaintedGrid(WarpedGrid):
    light_thr = 0.75     # open paper inside a square
    ink_de = 22.0        # CIELAB distance from paper above which a cell is painted
    close = 5            # cells: gaps bridged when finding the ruled area

    def __init__(self, rgb, light, page_id):
        super().__init__(light, page_id)
        self.lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        self.lab[..., 0] *= 100 / 255; self.lab[..., 1:] -= 128

    def squares(self):
        m = (self.light > self.light_thr).astype(np.uint8)
        n, lab, st, cen = cv2.connectedComponentsWithStats(m)
        a = st[1:, cv2.CC_STAT_AREA]
        w, h = st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]
        med = np.median(a[(a > 12) & (a < 400)])
        ok = (a > 0.4 * med) & (a < 1.8 * med) & (np.abs(w - h) <= 0.35 * np.maximum(w, h))
        self.sq = cen[1:][ok]
        return self.sq

    tile = 160           # px: phase of the ruling is measured per tile

    def phase_field(self, resp, p, axis):
        """Phase of the ruling (lines every p px across `axis`) in each tile,
        unwrapped from tile to tile and smoothed. resp is the line response
        (lines bright)."""
        H, W = resp.shape; t = self.tile
        ny, nx = max(1, H // t), max(1, W // t)
        ph = np.zeros((ny, nx)); wt = np.zeros((ny, nx))
        for i in range(ny):
            for j in range(nx):
                blk = resp[i * t:(i + 1) * t, j * t:(j + 1) * t]
                prof = blk.sum(axis=1 - axis) if axis == 1 else blk.sum(axis=0)
                prof = blk.sum(axis=0) if axis == 1 else blk.sum(axis=1)
                off = (j * t) if axis == 1 else (i * t)
                z = (prof * np.exp(2j * np.pi * (np.arange(len(prof)) + off) / p)).sum()
                ph[i, j] = np.angle(z) / (2 * np.pi) * p; wt[i, j] = abs(z)
        # unwrap: start from the strongest tile and walk outwards
        un = np.full(ph.shape, np.nan); i0, j0 = np.unravel_index(wt.argmax(), wt.shape); un[i0, j0] = ph[i0, j0]
        order = sorted(np.ndindex(ph.shape), key=lambda ij: abs(ij[0] - i0) + abs(ij[1] - j0))
        for (i, j) in order[1:]:
            nb = [un[a, b] for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                  if 0 <= a < ph.shape[0] and 0 <= b < ph.shape[1] and np.isfinite(un[a, b])]
            ref = np.mean(nb) if nb else un[i0, j0]
            un[i, j] = ph[i, j] + p * np.round((ref - ph[i, j]) / p)
        # weak tiles (no ruling: margins, text) take the weighted neighbourhood
        w = wt / (wt.max() + 1e-9); w[w < 0.15] = 0
        sm = ndimage.uniform_filter(un * w, 3, mode="nearest") / (ndimage.uniform_filter(w, 3, mode="nearest") + 1e-9)
        un = np.where(w > 0, 0.5 * un + 0.5 * sm, sm)
        cy = (np.arange(ny) + 0.5) * t; cx = (np.arange(nx) + 0.5) * t
        return cy, cx, un

    def interp(self, cy, cx, f, y, x):
        from scipy.interpolate import RegularGridInterpolator
        if len(cy) < 2 or len(cx) < 2:
            return np.full(np.shape(x), f.mean())
        r = RegularGridInterpolator((cy, cx), f, bounds_error=False, fill_value=None)
        return r(np.c_[np.ravel(y), np.ravel(x)]).reshape(np.shape(x))

    def fit(self, iters=3):
        """Cell centres from the printed ruling: the thin lines show through
        the paint, so their phase, measured tile by tile, places every cell,
        painted or not. The pitch comes from the open squares."""
        c = self.squares()
        if len(c) < 30:
            return None
        p0 = self.pitch(c)
        self.px = self.refine_axis(c[:, 0], c[:, 1], p0); self.py = self.refine_axis(c[:, 1], c[:, 0], p0)
        g = (self.light * 255).astype(np.uint8)
        k = max(3, int(round(0.6 * min(self.px, self.py))) | 1)
        vresp = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, np.ones((1, k), np.uint8)).astype(np.float32)
        hresp = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, np.ones((k, 1), np.uint8)).astype(np.float32)
        H, W = self.light.shape
        vy, vx, vph = self.phase_field(vresp, self.px, 1)    # vertical lines: x = phase + n px
        hy, hx, hph = self.phase_field(hresp, self.py, 0)
        # centres: x = phase(x, y) + (n + 0.5) px, solved by fixed-point steps
        ref_x = self.interp(vy, vx, vph, H / 2, W / 2); ref_y = self.interp(hy, hx, hph, H / 2, W / 2)
        ncol = np.arange(int(np.floor(-ref_x / self.px)) - 1, int(np.ceil((W - ref_x) / self.px)) + 1)
        nrow = np.arange(int(np.floor(-ref_y / self.py)) - 1, int(np.ceil((H - ref_y) / self.py)) + 1)
        gx, gy = np.meshgrid(ref_x + (ncol + 0.5) * self.px, ref_y + (nrow + 0.5) * self.py)
        for _ in range(4):
            gx = self.interp(vy, vx, vph, gy, gx) + (ncol[None, :] + 0.5) * self.px
            gy = self.interp(hy, hx, hph, gy, gx) + (nrow[:, None] + 0.5) * self.py
        keep_c = (gx.mean(0) > 0) & (gx.mean(0) < W); keep_r = (gy.mean(1) > 0) & (gy.mean(1) < H)
        self.gx, self.gy = gx[keep_r][:, keep_c], gy[keep_r][:, keep_c]
        self.p = (self.px + self.py) / 2
        return self.cell_colours()

    def cell_colours(self):
        H, W = self.light.shape
        p = min(self.px, self.py); r = max(1, int(0.3 * p))
        from scipy.spatial import cKDTree
        d, _ = cKDTree(self.sq).query(np.c_[self.gx.ravel(), self.gy.ravel()])
        present = (d < 0.4 * p).reshape(self.gx.shape)
        col = np.zeros(self.gx.shape + (3,), np.float32); inside = np.zeros(self.gx.shape, bool)
        for a, b in np.ndindex(self.gx.shape):
            x, y = int(round(self.gx[a, b])), int(round(self.gy[a, b]))
            if r <= x < W - r and r <= y < H - r:
                col[a, b] = np.median(self.lab[y - r:y + r + 1, x - r:x + r + 1].reshape(-1, 3), axis=0)
                inside[a, b] = True
        paper = np.median(col[present & inside], axis=0) if (present & inside).any() else np.array([90, 0, 10])
        de = np.linalg.norm(col - paper, axis=2)
        painted = inside & (de > self.ink_de)
        # the ruled area: open paper squares and painted cells, joined over
        # small gaps, holes filled; single stray cells (handwriting, stains)
        # are opened away
        region = ndimage.binary_closing(present | painted, np.ones((self.close, self.close)), border_value=0)
        region = ndimage.binary_fill_holes(region) & inside
        region = ndimage.binary_opening(region, np.ones((3, 3)))
        self.region, self.colour_lab, self.paper = region, col, paper
        self.cells = (region & painted).astype(np.uint8)
        self.margin = np.where(region, np.abs(de - self.ink_de) / 100, 1.0)
        self.s = 1 - self.cells
        self.threshold = self.ink_de
        return self

    def bands(self, min_rows=4, gap=2, col_gap=3):
        """Row bands as GraphGrid.bands, each split again at runs of at
        least col_gap empty columns (charts painted side by side)."""
        out = []
        for ra, rb, cl, cr in GraphGrid.bands(self, min_rows, gap):
            used = self.cells[ra:rb, cl:cr].any(axis=0)
            start, run = None, 0
            for c in range(len(used) + 1):
                if c < len(used) and used[c]:
                    start = c if start is None else start; run = 0; last = c
                elif start is not None:
                    run += 1
                    if run >= col_gap or c == len(used):
                        if last + 1 - start >= 4:
                            sub = self.cells[ra:rb, cl + start:cl + last + 1]
                            rows = np.nonzero(sub.any(axis=1))[0]
                            out.append((ra + rows[0], ra + rows[-1] + 1, cl + start, cl + last + 1))
                        start, run = None, 0
        return [b for b in out if b[1] - b[0] >= min_rows]


class PaintedBook:
    """Read every page, cluster the ink colours of the whole book into a
    palette, and write each band as digits (0 empty, k = palette ink k)."""

    def __init__(self, pages, out, k=None, max_k=9):
        self.pages, self.out, self.k, self.max_k = pages, Path(out), k, max_k
        self.out.mkdir(parents=True, exist_ok=True)

    def read(self):
        self.grids = {}
        for p in self.pages:
            page = WoodcutPage(p)
            rgb = cv2.cvtColor(cv2.imread(str(p), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            g = PaintedGrid(rgb, page.light.astype(np.float32), page.path.stem).fit()
            if g is not None:
                self.grids[page.path.stem] = g
        return self

    merge_de = 16.0      # inks closer than this are one ink (shades of one paint)

    def palette(self, k0=12):
        """k-means with generous k, then shades of one paint are merged
        (single link below merge_de) and near-paper clusters (faint wash,
        pencil smudge) are dropped. Digits run dark to light."""
        inks = np.concatenate([g.colour_lab[g.cells == 1] for g in self.grids.values()])
        inks = inks[np.random.default_rng(0).permutation(len(inks))[:80000]]
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.1)
        _, lab, cen = cv2.kmeans(inks, self.k or k0, None, crit, 5, cv2.KMEANS_PP_CENTERS)
        n = np.bincount(lab.ravel(), minlength=len(cen)).astype(float)
        group = list(range(len(cen)))
        for i in range(len(cen)):
            for j in range(i + 1, len(cen)):
                if np.linalg.norm(cen[i] - cen[j]) < self.merge_de:
                    gi, gj = group[i], group[j]
                    group = [gi if g == gj else g for g in group]
        out = []
        for gid in sorted(set(group)):
            m = [i for i in range(len(cen)) if group[i] == gid]
            c = (cen[m] * n[m, None]).sum(0) / n[m].sum()
            chroma = np.hypot(c[1], c[2])
            paper = np.median([g.paper for g in self.grids.values()], axis=0)
            if np.linalg.norm(c - paper) < self.merge_de or (c[0] > 78 and chroma < 15):
                continue                                   # faint: not an ink
            out.append(c)
        self.centres = np.array(sorted(out, key=lambda c: c[0]))[:9]
        self.raw = cen                                     # kept for nearest-ink lookup
        return self

    def digits(self, g):
        """Each painted cell takes the ink of its nearest k-means cluster;
        a cell whose cluster was dropped as faint becomes empty."""
        raw_ink = [np.linalg.norm(self.centres - c, axis=1) for c in self.raw]
        to_ink = [int(np.argmin(d)) + 1 if d.min() < self.merge_de * 1.5 else 0 for d in raw_ink]
        d = np.linalg.norm(g.colour_lab[..., None, :] - self.raw[None, None], axis=3)
        return np.where(g.cells == 1, np.array(to_ink)[d.argmin(axis=2)], 0)

    def rgb_of(self, lab):
        v = np.array([[[lab[0] * 255 / 100, lab[1] + 128, lab[2] + 128]]], np.float32).clip(0, 255).astype(np.uint8)
        return cv2.cvtColor(v, cv2.COLOR_LAB2RGB)[0, 0]

    def write(self):
        meta = {}
        for stem, g in self.grids.items():
            digits = self.digits(g)
            out = []
            for k, (ra, rb, cl, cr) in enumerate(g.bands(), 1):
                name = f"{stem}_b{k}"
                (self.out / f"{name}.txt").write_text("\n".join("".join(map(str, r)) for r in digits[ra:rb, cl:cr]) + "\n")
                out.append(dict(name=name, rows=int(rb - ra), cols=int(cr - cl), pitch_x=round(g.px, 2), pitch_y=round(g.py, 2),
                                threshold=g.ink_de, uncertain=int((g.margin[ra:rb, cl:cr] < 0.05).sum()),
                                fill=round(float(g.cells[ra:rb, cl:cr].mean()), 3),
                                inks=sorted(set(int(v) for v in np.unique(digits[ra:rb, cl:cr])) - {0})))
            (self.out / f"{stem}.json").write_text(json.dumps(out))
            self.check(g, digits, self.out / f"{stem}_check.jpg")
            meta[stem] = out
        with open(self.out / "palette.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["digit", "L", "a", "b", "hex"])
            for i, c in enumerate(self.centres, 1):
                w.writerow([i, *np.round(c, 1), "#%02x%02x%02x" % tuple(int(v) for v in self.rgb_of(c))])
        return meta

    def check(self, g, digits, path):
        """The chart redrawn in the palette colours beside each other cell
        centre, to compare with the page."""
        h, w = digits.shape; z = 6
        img = np.full((h * z, w * z, 3), 255, np.uint8)
        pal = [np.array([255, 255, 255])] + [self.rgb_of(c) for c in self.centres]
        for a, b in zip(*np.nonzero(g.region)):
            img[a * z:(a + 1) * z, b * z:(b + 1) * z] = pal[digits[a, b]] if digits[a, b] else (235, 235, 225)
        cv2.imwrite(str(path), img[..., ::-1])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("outdir"); ap.add_argument("pages", nargs="+")
    ap.add_argument("--k", type=int, help="number of inks (default: chosen from the colours)")
    a = ap.parse_args()
    b = PaintedBook(a.pages, a.outdir, a.k).read().palette()
    b.write()
    print(open(Path(a.outdir) / "palette.csv").read())


if __name__ == "__main__":
    main()
