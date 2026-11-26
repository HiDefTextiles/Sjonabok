#!/usr/bin/env python3
"""Read a white-line woodcut pattern page (Quentel, Schönsperger style):
the chart is a black block with the empty cells cut out as small white
squares, so a filled cell is simply a dark cell. No ruling is printed.

    python3 woodcut.py page.webp outdir > outdir/<page>.json

Steps: find the black block, deskew it, find the white squares, take the
pitch from the spacing of neighbouring squares, follow the columns and rows
of squares across the block (line by line, so plate drift is absorbed),
score each cell by the lightness of its centre, and split the block into
bands at rows that are solid black (the printed dividers).
Writes <page>_b<k>.txt (0/1, 1 = filled) and <page>_check.jpg.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage


class WoodcutPage:
    def __init__(self, path):
        self.path = Path(path)
        g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        bg = cv2.blur(cv2.dilate(g, np.ones((151, 151), np.uint8)), (151, 151))
        self.light = np.clip(g.astype(float) / np.maximum(bg, 1), 0, 1)   # paper = 1

    def block(self):
        """Bounding box of the largest dark block (white squares closed)."""
        dark = (self.light < 0.6).astype(np.uint8)
        dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
        dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((41, 41), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(dark)
        if n < 2:
            return None
        i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        x, y, w, h, _ = st[i]
        return x, y, x + w, y + h

    def blocks(self, min_frac=0.25):
        """Bounding boxes of all dark blocks at least min_frac of the largest, top to bottom."""
        dark = (self.light < 0.6).astype(np.uint8)
        dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
        dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((41, 41), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(dark)
        if n < 2:
            return []
        H, W = dark.shape
        def edges(r):   # how many page edges a block touches (scanner background, binding)
            x, y, w, h = r[:4]
            return int(x <= 2) + int(y <= 2) + int(x + w >= W - 2) + int(y + h >= H - 2)
        cand = [st[i] for i in range(1, n) if edges(st[i]) < 2]
        if not cand:
            return []
        big = max(r[cv2.CC_STAT_AREA] for r in cand)
        keep = [r for r in cand if r[cv2.CC_STAT_AREA] >= min_frac * big]
        return [(x, y, x + w, y + h) for x, y, w, h, _ in sorted(keep, key=lambda r: (r[1], r[0]))]

    @staticmethod
    def rotate(img, angle):
        h, w = img.shape
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=1.0)

    def deskew(self, crop, span=2.5):
        best = None
        for a in np.arange(-span, span + 0.01, 0.05):
            r = self.rotate(crop.astype(np.float32), a)
            v = r.mean(axis=1).var() + r.mean(axis=0).var()
            if best is None or v > best[0]:
                best = (v, a)
        return self.rotate(crop.astype(np.float32), best[1]), float(best[1])


class WoodcutGrid:
    def __init__(self, light, page_id):
        self.light, self.page_id = light, page_id

    def squares(self):
        m = (self.light > 0.6).astype(np.uint8)
        n, lab, st, cen = cv2.connectedComponentsWithStats(m)
        a = st[1:, cv2.CC_STAT_AREA]
        w, h = st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]
        med = np.median(a[(a > 12) & (a < 2000)])
        ok = (a > 0.35 * med) & (a < 2.2 * med) & (np.abs(w - h) <= 0.5 * np.maximum(w, h))
        return cen[1:][ok]

    def pitch(self, c):
        from scipy.spatial import cKDTree
        d, _ = cKDTree(c).query(c, k=2)
        return float(np.median(d[:, 1]))

    @staticmethod
    def refine(c, p0):
        """The pitch at which the square centres line up best on both axes
        (largest phase coherence), searched around the neighbour spacing.
        Coherence is taken in strips so slow drift does not blur it."""
        best = (0, p0)
        for p in np.arange(0.85 * p0, 1.2 * p0, 0.01):
            r = 0
            for ax in (0, 1):
                v = c[:, ax]
                other = c[:, 1 - ax]
                for lo in np.arange(other.min(), other.max(), 200):
                    sel = v[(other >= lo) & (other < lo + 200)]
                    if len(sel) > 10:
                        r += abs(np.exp(2j * np.pi * sel / p).sum())
            if r > best[0]:
                best = (r, p)
        return float(best[1])

    def lines(self, coords, p, length):
        """Cell borders along one axis: start at the phase of the squares,
        then step one pitch at a time, re-centring on the squares found in
        each strip."""
        phase = (np.angle(np.exp(2j * np.pi * coords / p).mean()) / (2 * np.pi) * p) % p
        centres = []
        x = phase
        while x - p > 0:
            x -= p
        while x < length:
            sel = coords[np.abs(coords - x) < 0.35 * p]
            if len(sel) >= 2:
                x = 0.5 * x + 0.5 * float(np.median(sel))
            centres.append(x)
            x += p
        c = np.array(centres)
        b = np.concatenate([[c[0] - p / 2], (c[1:] + c[:-1]) / 2, [c[-1] + p / 2]])
        return np.clip(np.round(b).astype(int), 0, length - 1)

    @staticmethod
    def refine_axis(v, other, p0):
        """As refine, for one axis only (cells that are not square)."""
        best = (0, p0)
        for p in np.arange(0.85 * p0, 1.2 * p0, 0.01):
            r = 0
            for lo in np.arange(other.min(), other.max(), 200):
                sel = v[(other >= lo) & (other < lo + 200)]
                if len(sel) > 10:
                    r += abs(np.exp(2j * np.pi * sel / p).sum())
            if r > best[0]:
                best = (r, p)
        return float(best[1])

    def fit(self, per_axis=False):
        c = self.squares()
        self.n_squares = len(c)
        if len(c) < 30:
            return None
        p0 = self.pitch(c)
        if per_axis:
            px, py = self.refine_axis(c[:, 0], c[:, 1], p0), self.refine_axis(c[:, 1], c[:, 0], p0)
        else:
            px = py = self.refine(c, p0)
        p = self.p = (px + py) / 2
        self.px, self.py = px, py
        H, W = self.light.shape
        self.xs = self.lines(c[:, 0], px, W)
        self.ys = self.lines(c[:, 1], py, H)
        h, w = len(self.ys) - 1, len(self.xs) - 1
        s = np.zeros((h, w))
        for r in range(h):
            a, b = self.ys[r], self.ys[r + 1]
            m = max(1, int(round((b - a) * 0.25)))
            for k in range(w):
                l, rr = self.xs[k], self.xs[k + 1]
                mm = max(1, int(round((rr - l) * 0.25)))
                s[r, k] = self.light[a + m:b - m + 1, l + mm:rr - mm + 1].mean()
        s = np.nan_to_num(s)
        t, _ = cv2.threshold((s * 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        self.threshold = t / 255
        # prints are unevenly inked: compare each cell with the lightest and
        # darkest cells around it (11x11 cells); where all are alike, fall
        # back to the global threshold
        hi = ndimage.percentile_filter(s, 92, size=11, mode="nearest")
        lo = ndimage.percentile_filter(s, 8, size=11, mode="nearest")
        span = hi - lo
        rel = np.where(span > 0.15, (s - lo) / np.maximum(span, 1e-6), (s > self.threshold).astype(float))
        self.cells = (rel < 0.5).astype(np.uint8)              # dark = filled
        self.margin = np.abs(rel - 0.5) * np.maximum(span, 0.1)
        return self

    def bands(self, min_rows=4):
        """Split at solid rows and trim solid edge columns; every band is
        returned with its row/col span."""
        c = self.cells
        solid_r = c.mean(axis=1) > 0.92
        out, start = [], None
        for r in range(len(c) + 1):
            if r < len(c) and not solid_r[r]:
                start = r if start is None else start
            elif start is not None:
                if r - start >= min_rows:
                    out.append((start, r))
                start = None
        res = []
        for a, b in out:
            sub = c[a:b]
            cols = np.nonzero(sub.mean(axis=0) <= 0.92)[0]
            if len(cols) < 4:
                continue
            l, r = cols[0], cols[-1] + 1
            res.append((a, b, l, r))
        return res


def check_image(light, grid, bands, path):
    img = cv2.cvtColor((light * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    for r in range(grid.cells.shape[0]):
        for k in range(grid.cells.shape[1]):
            x0, x1, y0, y1 = grid.xs[k], grid.xs[k + 1], grid.ys[r], grid.ys[r + 1]
            if grid.cells[r, k]:
                sub = img[y0 + 2:y1 - 1, x0 + 2:x1 - 1]
                sub[:] = (0.45 * sub + 0.55 * np.array([40, 40, 230])).astype(np.uint8)
            elif grid.margin[r, k] < 0.05:
                cv2.rectangle(img, (x0 + 2, y0 + 2), (x1 - 2, y1 - 2), (0, 160, 255), 1)
    for i, (a, b, l, r) in enumerate(bands, 1):
        cv2.rectangle(img, (grid.xs[l], grid.ys[a]), (grid.xs[r], grid.ys[b]), (200, 120, 0), 2)
        cv2.putText(img, f"b{i} {b - a}x{r - l}", (grid.xs[l] + 4, grid.ys[a] + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 80, 0), 2)
    cv2.imwrite(str(path), img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page"); ap.add_argument("outdir")
    ap.add_argument("--per-axis", action="store_true", help="fit the pitch on each axis (cells not square)")
    ap.add_argument("--skew", type=float, default=2.5, help="largest skew to try, degrees")
    a = ap.parse_args()
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    page = WoodcutPage(a.page)
    box = page.block()
    if box is None:
        print("[]"); return
    x0, y0, x1, y1 = box
    crop, angle = page.deskew(page.light[y0:y1, x0:x1], a.skew)
    grid = WoodcutGrid(crop, page.path.stem).fit(a.per_axis)
    if grid is None:
        print("[]"); return
    bands = grid.bands()
    meta = []
    for i, (ra, rb, cl, cr) in enumerate(bands, 1):
        name = f"{page.path.stem}_b{i}"
        cells = grid.cells[ra:rb, cl:cr]
        (out / f"{name}.txt").write_text("\n".join("".join(map(str, r)) for r in cells) + "\n")
        meta.append(dict(name=name, box=[int(x0), int(y0), int(x1), int(y1)], angle=angle,
                         rows=int(rb - ra), cols=int(cr - cl), pitch_x=round(grid.px, 2),
                         pitch_y=round(grid.py, 2), threshold=round(grid.threshold, 3),
                         uncertain=int((grid.margin[ra:rb, cl:cr] < 0.05).sum()),
                         fill=round(float(cells.mean()), 3)))
    check_image(crop, grid, bands, out / f"{page.path.stem}_check.jpg")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
