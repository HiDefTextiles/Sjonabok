#!/usr/bin/env python3
"""Read Fürst's Neues Modelbuch pages (archive.org JBIG2 foreground masks).
Ruled grid in black; empty cells are white squares, filled cells are
cross-hatched (only tiny white specks left). Reuses woodcut.WoodcutGrid:
find the white squares, fit the pitch, score each cell's centre lightness.
Splits the chart into panels at rows and columns without any squares.
    python3 fuerst.py page.png outdir  -> outdir/<page>_b<k>.txt + json
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
from woodcut import WoodcutGrid, WoodcutPage, check_image

class FuerstGrid(WoodcutGrid):
    """Cells are not square here: fit the pitch on each axis separately."""
    @staticmethod
    def refine_axis(v, other, p0):
        best = (0, p0)
        for p in np.arange(0.8 * p0, 1.25 * p0, 0.02):
            r = 0
            for lo in np.arange(other.min(), other.max(), 150):
                sel = v[(other >= lo) & (other < lo + 150)]
                if len(sel) > 10:
                    r += abs(np.exp(2j * np.pi * sel / p).sum())
            if r > best[0]:
                best = (r, p)
        return float(best[1])

    def squares(self):
        """Empty cells are the big white blobs; hatching leaves many small
        specks, so take the size from the large end, not the median."""
        m = (self.light > 0.6).astype(np.uint8)
        n, lab, st, cen = cv2.connectedComponentsWithStats(m)
        a = st[1:, cv2.CC_STAT_AREA]; w, h = st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]
        cand = a[(a > 12) & (a < 4000)]
        if len(cand) < 30:
            return cen[1:][:0]
        ref = np.percentile(cand, 90)
        med = np.median(cand[cand > 0.4 * ref])
        ok = (a > 0.5 * med) & (a < 1.8 * med) & (np.abs(w - h) <= 0.4 * np.maximum(w, h))
        return cen[1:][ok]

    def fit(self):
        c = self.squares()
        if len(c) < 30:
            return None
        p0 = self.pitch(c)
        px = self.refine_axis(c[:, 0], c[:, 1], p0)
        py = self.refine_axis(c[:, 1], c[:, 0], p0)
        self.p, self.px, self.py = (px + py) / 2, px, py
        H, W = self.light.shape
        self.xs = self.lines(c[:, 0], px, W)
        self.ys = self.lines(c[:, 1], py, H)
        return self.score()

    def score(self):
        """Empty cell = one big white square; hatched cell = many small
        white specks; solid cell = no white. 1 = filled (solid or hatched);
        self.kind holds 0 empty, 1 solid, 2 hatched."""
        h, w = len(self.ys) - 1, len(self.xs) - 1
        big = np.zeros((h, w)); white = np.zeros((h, w))
        wm = (self.light > 0.5).astype(np.uint8)
        for r in range(h):
            a, b = self.ys[r], self.ys[r + 1]; m = max(1, int(round((b - a) * 0.12)))
            for k in range(w):
                l, rr = self.xs[k], self.xs[k + 1]; mm = max(1, int(round((rr - l) * 0.12)))
                win = wm[a + m:b - m + 1, l + mm:rr - mm + 1]
                if win.size == 0:
                    continue
                n, lab, st, _ = cv2.connectedComponentsWithStats(win, connectivity=4)
                big[r, k] = st[1:, cv2.CC_STAT_AREA].max() / win.size if n > 1 else 0
                white[r, k] = win.mean()
        self.big, self.white = big, white
        self.kind = np.where(big > 0.3, 0, np.where(white > 0.12, 2, 1)).astype(np.uint8)
        self.cells = (self.kind > 0).astype(np.uint8)
        self.threshold = 0.3
        self.margin = np.abs(big - 0.3)
        return self


def diamond(img):
    m = (img > 0.6).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    a = st[1:, cv2.CC_STAT_AREA]; box = st[1:, cv2.CC_STAT_WIDTH] * st[1:, cv2.CC_STAT_HEIGHT]
    med = np.median(a[(a > 12) & (a < 2000)])
    ok = (a > 0.5 * med) & (a < 2 * med)
    return np.median(a[ok] / box[ok]) < 0.68


def turn45(img):
    h, w = img.shape
    d = int(np.ceil(np.hypot(h, w)))
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 45, 1.0)
    M[0, 2] += (d - w) / 2; M[1, 2] += (d - h) / 2
    return cv2.warpAffine(img.astype(np.float32), M, (d, d), flags=cv2.INTER_LINEAR, borderValue=0.0)


def panels_mask(grid, outside):
    """Panels = boxes of the inside area split at empty gutters."""
    from scipy import ndimage
    inside = ~outside
    inside = ndimage.binary_opening(inside, np.ones((3, 3)))
    lab, n = ndimage.label(inside)
    res = []
    for sl in ndimage.find_objects(lab):
        if sl is None: continue
        ys, xs = sl
        if ys.stop - ys.start >= 6 and xs.stop - xs.start >= 6:
            res.append((ys.start, ys.stop, xs.start, xs.stop))
    if not res:
        return panels(grid)
    return res


def panels(grid):
    """Split at runs of >=2 rows / cols that are (almost) all filled."""
    c = grid.cells
    def runs(solid):
        out, s = [], None
        for i in range(len(solid) + 1):
            if i < len(solid) and not solid[i]:
                s = i if s is None else s
            elif s is not None:
                if i - s >= 6: out.append((s, i))
                s = None
        return out
    res = []
    for a, b in runs(c.mean(axis=1) > 0.9):
        for l, r in runs(c[a:b].mean(axis=0) > 0.9):
            sub = c[a:b, l:r]
            # trim solid edge rows/cols again inside the panel
            rows = np.nonzero(sub.mean(axis=1) <= 0.9)[0]; cols = np.nonzero(sub.mean(axis=0) <= 0.9)[0]
            if len(rows) >= 6 and len(cols) >= 6:
                res.append((a + rows[0], a + rows[-1] + 1, l + cols[0], l + cols[-1] + 1))
    return res

def main(page, outdir):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    g = cv2.imread(page, cv2.IMREAD_GRAYSCALE).astype(float) / 255
    stem = Path(page).stem
    grid = FuerstGrid(g, stem)
    c = grid.squares()
    if len(c) < 200:
        print("[]"); return
    # chart box = robust extent of the squares
    x0, x1 = np.percentile(c[:, 0], [0.5, 99.5]); y0, y1 = np.percentile(c[:, 1], [0.5, 99.5])
    p = grid.pitch(c)
    X0, Y0 = int(max(0, x0 - 2 * p)), int(max(0, y0 - 2 * p))
    X1, Y1 = int(min(g.shape[1], x1 + 2 * p)), int(min(g.shape[0], y1 + 2 * p))
    crop = g[Y0:Y1, X0:X1]
    if diamond(crop):                      # net drawn at 45 degrees: turn it square
        crop = turn45(crop)
    best = None
    for a in np.arange(-2.0, 2.01, 0.05):
        r = WoodcutPage.rotate(crop.astype(np.float32), a)
        v = r.mean(axis=1).var() + r.mean(axis=0).var()
        if best is None or v > best[0]:
            best = (v, a)
    crop = WoodcutPage.rotate(crop.astype(np.float32), best[1])
    grid = FuerstGrid(crop, stem).fit()
    if grid is None:
        print("[]"); return
    # padding from the 45-degree turn and the black page around the plate
    # read as solid: clear solid cells joined to the outer edge
    from scipy import ndimage
    solid = grid.kind == 1
    lab, _ = ndimage.label(solid)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    big = [l for l in edge if (lab == l).sum() > 0.02 * lab.size]
    outside = np.isin(lab, big)
    grid.kind[outside] = 0; grid.cells[outside] = 0; grid.margin[outside] = 1
    bands = panels_mask(grid, outside)
    meta = []
    for i, (ra, rb, cl, cr) in enumerate(bands, 1):
        name = f"{stem}_b{i}"
        cells = grid.cells[ra:rb, cl:cr]
        (out / f"{name}.txt").write_text("\n".join("".join(map(str, r)) for r in cells) + "\n")
        kind = grid.kind[ra:rb, cl:cr]
        (out / f"{name}.sym").write_text("\n".join("".join(".#x"[v] for v in r) for r in kind) + "\n")
        meta.append(dict(name=name, box=[X0, Y0, X1, Y1], rows=int(rb - ra), cols=int(cr - cl),
                         pitch_x=round(grid.px, 2), pitch_y=round(grid.py, 2), uncertain=int((grid.margin[ra:rb, cl:cr] < 0.08).sum()), hatched=int((grid.kind[ra:rb, cl:cr] == 2).sum()),
                         fill=round(float(cells.mean()), 3)))
    check_image(crop, grid, bands, out / f"{stem}_check.jpg")
    print(json.dumps(meta))

if __name__ == "__main__":
    main(*sys.argv[1:3])
