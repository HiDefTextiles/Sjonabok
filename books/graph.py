#!/usr/bin/env python3
"""Hand-drawn charts on printed graph paper (manuscript pattern books):
filled cells are inked dots or squares, empty cells are paper inside thin
grey ruling. The empty cells are the light squares, so the WarpedGrid local
grid applies once the square threshold sits above the ruling. The whole
page is one block; bands are split at rows that are entirely empty, and
empty edge rows/columns are trimmed.
    python3 graph.py page.webp outdir > outdir/page.json
"""
import argparse, json
from pathlib import Path
import cv2, numpy as np
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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("page"); ap.add_argument("outdir")
    ap.add_argument("--thr", type=float, default=0.85, help="lightness above which a pixel is open paper")
    ap.add_argument("--margin", type=float, default=0.06, help="fraction of each side cropped (page edge, gutter)")
    a = ap.parse_args(); out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    page = WoodcutPage(a.page)
    H, W = page.light.shape
    x0, y0 = int(a.margin * W), int(a.margin * H); x1, y1 = W - x0, H - y0
    crop = page.light[y0:y1, x0:x1].astype(np.float32)
    GraphGrid.light_thr = a.thr
    g = GraphGrid(crop, page.path.stem).fit()
    meta = []
    if g is not None:
        bands = g.bands()
        for k, (ra, rb, cl, cr) in enumerate(bands, 1):
            name = f"{page.path.stem}_b{k}"; cells = g.cells[ra:rb, cl:cr]
            (out / f"{name}.txt").write_text("\n".join("".join(map(str, r)) for r in cells) + "\n")
            meta.append(dict(name=name, box=[x0, y0, x1, y1], angle=0.0, rows=int(rb - ra), cols=int(cr - cl),
                             pitch_x=round(g.px, 2), pitch_y=round(g.py, 2), threshold=round(g.threshold, 3),
                             uncertain=int((g.margin[ra:rb, cl:cr] < 0.05).sum()), fill=round(float(cells.mean()), 3)))
        check_local(crop, g, bands, out / f"{page.path.stem}_check.jpg")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
