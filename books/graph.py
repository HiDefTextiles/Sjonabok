#!/usr/bin/env python3
"""Hand-drawn charts on printed graph paper (manuscript pattern books):
filled cells are inked dots or squares, empty cells are paper inside thin
grey ruling. The empty cells are the light squares, so the WarpedGrid local
grid applies once the square threshold sits above the ruling. The whole
page is one block; bands are split at rows that are entirely empty, and
empty edge rows/columns are trimmed.
    python3 graph.py page.webp outdir > outdir/page.json
    python3 graph.py page.webp outdir --colour page_colour.webp   # 0/1/2 inks
The grid and the filled/empty call always come from the grey page, so a
colour run gives the same bands as a grey run, with 2 where the ink is red.
    python3 graph.py page.webp outdir --colour page_colour.webp --red-is grid
is for black ink on point paper ruled in red (Frölich 1759, Arnold 1825):
the grid is fitted to the squares between the red lines in the colour page
and a cell is filled when it holds black ink (RulingGrid).
"""
import argparse, json, warnings
from collections import deque
from pathlib import Path
import cv2, numpy as np
from scipy.spatial import cKDTree
from woodcut import WoodcutPage
from warped import WarpedGrid, check_local


class GraphGrid(WarpedGrid):
    light_thr = 0.85

    def squares(self):
        m = (self.light > self.light_thr).astype(np.uint8)
        n, lab, st, cen = cv2.connectedComponentsWithStats(m)
        a = st[1:, cv2.CC_STAT_AREA]
        w, h = st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]
        med = np.median(a[(a > 12) & (a < 2000)])
        ok = (a > 0.4 * med) & (a < 1.8 * med) & (np.abs(w - h) <= 0.4 * np.maximum(w, h))
        return cen[1:][ok]

    def fit(self, iters=3):
        """Ink and paper are well separated on graph paper, while a page
        often holds two inks of different darkness, so the cell call uses
        the global Otsu threshold rather than the local contrast."""
        if super().fit(iters) is None:
            return None
        # hand-drawn dots sit off centre: score a cell by the darker quarter
        # of its inner window instead of the mean of a small centre patch
        H, W = self.light.shape; r = 0.35 * min(self.px, self.py)
        s = np.ones(self.gx.shape)
        for a in range(s.shape[0]):
            for b in range(s.shape[1]):
                x, y = self.gx[a, b], self.gy[a, b]
                y0, y1, x0, x1 = int(y - r), int(y + r) + 1, int(x - r), int(x + r) + 1
                if y0 >= 0 and x0 >= 0 and y1 <= H and x1 <= W:
                    s[a, b] = np.percentile(self.light[y0:y1, x0:x1], 25)
        self.s = s
        t, _ = cv2.threshold((s * 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        self.threshold = t / 255
        self.cells = (self.s < self.threshold).astype(np.uint8)
        self.margin = np.abs(self.s - self.threshold)
        return self

    def bands(self, min_rows=4, gap=2):
        """Split at runs of >= gap empty rows; trim empty edge columns."""
        c = self.cells
        empty = c.sum(axis=1) == 0
        out, start, run = [], None, 0
        for r in range(len(c) + 1):
            e = r == len(c) or empty[r]
            if not e:
                start = r if start is None else start
                run = 0; last = r
            elif start is not None:
                run += 1
                if run >= gap or r == len(c):
                    if last + 1 - start >= min_rows:
                        out.append((start, last + 1))
                    start, run = None, 0
        res = []
        for a, b in out:
            cols = np.nonzero(c[a:b].sum(axis=0))[0]
            if len(cols) >= 4:
                res.append((a, b, cols[0], cols[-1] + 1))
        return res

    def inks(self, rgb, red_thr, red_is="ink"):
        """Score each filled cell by the redness R - (G+B)/2 of the darkest
        30 % of its inner window in the colour page (cropped like the grey
        one). Above red_thr the cell holds red, not black: with red_is="ink"
        it becomes 2 (red ink); with red_is="grid" it is cleared to 0, for
        point paper printed in red where the ruling, not ink, made the cell
        dark."""
        H, W = self.light.shape; r = 0.35 * min(self.px, self.py)
        rgb = rgb.astype(np.float32) / 255
        red = rgb[..., 0] - 0.5 * (rgb[..., 1] + rgb[..., 2])
        self.redness = np.zeros(self.cells.shape)
        out = self.cells.copy()
        for a, b in zip(*np.nonzero(self.cells)):
            x, y = self.gx[a, b], self.gy[a, b]
            y0, y1, x0, x1 = int(y - r), int(y + r) + 1, int(x - r), int(x + r) + 1
            if y0 < 0 or x0 < 0 or y1 > H or x1 > W:
                continue
            w = self.light[y0:y1, x0:x1]
            self.redness[a, b] = red[y0:y1, x0:x1][w <= np.percentile(w, 30)].mean()
            if self.redness[a, b] > red_thr:
                out[a, b] = 2 if red_is == "ink" else 0
        self.colours = out
        if red_is == "grid":
            self.cells = (out > 0).astype(np.uint8)
        return self


class RulingGrid(GraphGrid):
    """Point paper whose ruling is printed in red and whose pattern is drawn
    in black (Frölich 1759, Arnold 1825). In colour the ruling separates
    cleanly, so every cell, filled or not, is a square between red lines:
    the local grid then has a centre for every cell and follows the page
    curvature closely. A cell is filled when it holds enough black ink."""
    light_thr = 0.5
    line_red = 0.2      # R-(G+B)/2 above which a pixel is ruling (set per page by Otsu)
    ink_r = 0.48        # ink (black or faded brown): red channel below this;
                        # the ruling is as dark in grey but its red channel is high
    fill_frac = 0.06    # share of the inner window that must be ink

    def __init__(self, rgb, light, page_id):
        rgb = rgb.astype(np.float32) / 255
        red = rgb[..., 0] - 0.5 * (rgb[..., 1] + rgb[..., 2])
        self.ink = (rgb[..., 0] < self.ink_r).astype(np.float32)
        # ruling ink differs between pages and papers: Otsu on the redness
        t, _ = cv2.threshold((np.clip(red, 0, 1) * 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        self.line_red = float(np.clip(t / 255, 0.1, 0.25))
        super().__init__((red < self.line_red).astype(np.float32), page_id)
        self.grey = light

    def fit(self, iters=None):
        """Index the squares by walking from square to neighbouring square
        (the step is re-measured at every square, so curvature and drift
        never move a centre onto a line), fill the few missing squares from
        their neighbours, then score each cell by its share of black ink."""
        c = self.squares()
        if len(c) < 30:
            return None
        tree = cKDTree(c)
        d, _ = tree.query(c, k=2)
        p = float(np.median(d[:, 1]))
        idx = {}; at = {}                                  # square -> (row, col); (row, col) -> square
        seed = int(np.argmin(((c - np.median(c, 0)) ** 2).sum(1)))
        idx[seed] = (0, 0); at[(0, 0)] = seed
        steps = {seed: (np.array([p, 0.0]), np.array([0.0, p]))}
        queue = deque([seed])
        while queue:
            i = queue.popleft(); r, k = idx[i]; sx, sy = steps[i]
            for dr, dk, v in ((0, 1, sx), (0, -1, -sx), (1, 0, sy), (-1, 0, -sy)):
                for m in (1, 2, 3):                        # jump ruled lines and blots
                    dist, j = tree.query(c[i] + m * v, distance_upper_bound=0.35 * p)
                    if np.isfinite(dist):
                        break
                tgt = (r + m * dr, k + m * dk)
                if not np.isfinite(dist) or j in idx or tgt in at:
                    continue
                idx[j] = tgt; at[tgt] = j
                step = (c[j] - c[i]) / m * (1 if dr + dk > 0 else -1)
                steps[j] = (step, sy) if dk else (sx, step)
                queue.append(j)
        rk = np.array(list(at)); r0, k0 = rk.min(0); h, w = rk.max(0) - rk.min(0) + 1
        gx = np.full((h, w), np.nan); gy = np.full((h, w), np.nan)
        for (r, k), j in at.items():
            gx[r - r0, k - k0], gy[r - r0, k - k0] = c[j]
        self.px = float(np.nanmedian(np.diff(gx, axis=1))); self.py = float(np.nanmedian(np.diff(gy, axis=0)))
        self.p = (self.px + self.py) / 2
        for _ in range(max(h, w)):                         # fill holes from neighbours
            miss = np.isnan(gx)
            if not miss.any():
                break
            ex = []; ey = []
            for sh, ox, oy in (((0, 1), -self.px, 0), ((0, -1), self.px, 0), ((1, 0), 0, -self.py), ((-1, 0), 0, self.py)):
                ex.append(np.roll(gx, sh, (0, 1)) - ox); ey.append(np.roll(gy, sh, (0, 1)) - oy)
            # np.roll wraps: drop wrapped edges
            ex[0][:, 0] = ex[1][:, -1] = ex[2][0, :] = ex[3][-1, :] = np.nan
            ey[0][:, 0] = ey[1][:, -1] = ey[2][0, :] = ey[3][-1, :] = np.nan
            with np.errstate(all="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fx = np.nanmean(ex, 0); fy = np.nanmean(ey, 0)
            gx[miss] = fx[miss]; gy[miss] = fy[miss]
        gx = np.nan_to_num(gx, nan=-1e6); gy = np.nan_to_num(gy, nan=-1e6)
        self.gx, self.gy = gx, gy
        H, W = self.ink.shape; r = 0.35 * min(self.px, self.py)
        f = np.zeros(gx.shape)
        for a in range(h):
            for b in range(w):
                x, y = gx[a, b], gy[a, b]
                y0, y1, x0, x1 = int(y - r), int(y + r) + 1, int(x - r), int(x + r) + 1
                if y0 >= 0 and x0 >= 0 and y1 <= H and x1 <= W:
                    f[a, b] = self.ink[y0:y1, x0:x1].mean()
        self.s = 1 - f
        self.threshold = 1 - self.fill_frac
        self.cells = (f >= self.fill_frac).astype(np.uint8)
        self.margin = np.abs(f - self.fill_frac)
        # ruled ink lines between bands (and the frame) fill whole rows or
        # columns of cells: clear them so the bands split there
        self.cells[self.cells.mean(1) > 0.9, :] = 0
        self.cells[:, self.cells.mean(0) > 0.9] = 0
        # an ink rule drawn on a grid line between two cell rows also parts bands
        self.rules = []
        for a in range(h - 1):
            ys = ((gy[a] + gy[a + 1]) / 2).astype(int); xs = gx[a].astype(int)
            ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
            if ok.mean() > 0.5 and self.ink[ys[ok], xs[ok]].mean() > 0.6:
                self.rules.append(a + 1)
        self.colours = self.cells
        self.found = len(at) / gx.size                     # share of cells seen as squares
        return self


    def bands(self, min_rows=4, gap=2):
        """As GraphGrid.bands, but also split at ink rules between rows."""
        cuts = [0] + self.rules + [len(self.cells)]
        full, out = self.cells, []
        for a, b in zip(cuts[:-1], cuts[1:]):
            self.cells = full[a:b]
            out += [(ra + a, rb + a, cl, cr) for ra, rb, cl, cr in GraphGrid.bands(self, min_rows, gap)]
        self.cells = full
        return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("page"); ap.add_argument("outdir")
    ap.add_argument("--thr", type=float, default=0.85, help="lightness above which a pixel is open paper")
    ap.add_argument("--margin", type=float, default=0.06, help="fraction of each side cropped (page edge, gutter)")
    ap.add_argument("--colour", help="the same page in colour (same size): write 0/1/2 = empty/black/red ink")
    ap.add_argument("--red", type=float, default=0.22, help="redness R-(G+B)/2 of the darkest 30 %% of a cell above which it is red")
    ap.add_argument("--red-is", choices=["ink", "grid"], default="ink", help="red cells are red ink (2) or red ruling (cleared)")
    a = ap.parse_args(); out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    page = WoodcutPage(a.page)
    H, W = page.light.shape
    x0, y0 = int(a.margin * W), int(a.margin * H); x1, y1 = W - x0, H - y0
    crop = page.light[y0:y1, x0:x1].astype(np.float32)
    GraphGrid.light_thr = a.thr
    g = None
    meta = []
    if a.colour and a.red_is == "grid":
        rgb = cv2.cvtColor(cv2.imread(a.colour, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        assert rgb.shape[:2] == (H, W), "colour page must match the grey page"
        g = RulingGrid(rgb[y0:y1, x0:x1], crop, page.path.stem).fit()
    else:
        g = GraphGrid(crop, page.path.stem).fit()
    if g is not None:
        if a.colour and a.red_is == "ink":
            rgb = cv2.cvtColor(cv2.imread(a.colour, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            assert rgb.shape[:2] == (H, W), "colour page must match the grey page"
            g.inks(rgb[y0:y1, x0:x1], a.red, a.red_is)
        cols = g.colours if a.colour and a.red_is == "ink" else g.cells
        bands = g.bands()
        for k, (ra, rb, cl, cr) in enumerate(bands, 1):
            name = f"{page.path.stem}_b{k}"; cells = g.cells[ra:rb, cl:cr]
            ink = cols[ra:rb, cl:cr]
            (out / f"{name}.txt").write_text("\n".join("".join(map(str, r)) for r in ink) + "\n")
            meta.append(dict(name=name, box=[x0, y0, x1, y1], angle=0.0, rows=int(rb - ra), cols=int(cr - cl),
                             pitch_x=round(g.px, 2), pitch_y=round(g.py, 2), threshold=round(g.threshold, 3),
                             uncertain=int((g.margin[ra:rb, cl:cr] < 0.05).sum()), fill=round(float(cells.mean()), 3),
                             **({"red": round(float((ink == 2).sum() / max(1, cells.sum())), 3)} if a.colour and a.red_is == "ink" else {})))
        check_local(crop, g, bands, out / f"{page.path.stem}_check.jpg")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
