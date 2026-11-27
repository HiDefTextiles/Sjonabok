"""White-line woodcuts (Quentel, Schönsperger, Jobin): the chart is a black
block with the empty cells cut out as small white squares, so a filled
cell is simply a dark cell. No ruling is printed.

Steps: find the black block, deskew it, find the white squares, take the
pitch from the spacing of neighbouring squares, follow the columns and rows
of squares across the block (line by line, so plate drift is absorbed),
score each cell by the lightness of its centre, and split the block into
bands at rows that are solid black (the printed dividers). This is the
reader that was books/woodcut.py in PR #46.
"""
import cv2
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from .base import (Chart, PatternSource, centre_means, deskew, otsu,
                   paint_cells, paper_level, read_gray)


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

    @staticmethod
    def pitch(c):
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

    @staticmethod
    def lines(coords, p, length):
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

    def fit(self):
        c = self.squares()
        self.n_squares = len(c)
        if len(c) < 30:
            return None
        p = self.refine(c, self.pitch(c))
        self.p = p
        H, W = self.light.shape
        self.xs = self.lines(c[:, 0], p, W)
        self.ys = self.lines(c[:, 1], p, H)
        s = centre_means(self.light, self.xs, self.ys)
        self.threshold = otsu(s)
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


class WhiteLineWoodcutSource(PatternSource):
    """Black block with the empty cells cut out; one block per page, split
    into bands at solid black rows. Charts are named <page>_b<k>."""
    layout = "woodcut"
    description = "white-line woodcut: black block, empty cells cut out as white squares"

    def __init__(self, path, provenance=None, **options):
        super().__init__(path, provenance, **options)
        g = read_gray(self.path)
        bg = paper_level(g, white_line=True)
        self.light = np.clip(g.astype(float) / np.maximum(bg, 1), 0, 1)   # paper = 1
        self.grid = None

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

    def read(self):
        box = self.block()
        if box is None:
            return []
        x0, y0, x1, y1 = box
        self.crop, angle = deskew(self.light[y0:y1, x0:x1].astype(np.float32), border=1.0)
        grid = WoodcutGrid(self.crop, self.page_id).fit()
        if grid is None:
            return []
        self.grid, self.band_spans = grid, grid.bands()
        out = []
        for i, (ra, rb, cl, cr) in enumerate(self.band_spans, 1):
            name = f"{self.page_id}_b{i}"
            cells = grid.cells[ra:rb, cl:cr]
            meta = dict(name=name, box=[int(x0), int(y0), int(x1), int(y1)], angle=angle,
                        rows=int(rb - ra), cols=int(cr - cl), pitch_x=round(grid.p, 2),
                        pitch_y=round(grid.p, 2), threshold=round(grid.threshold, 3),
                        uncertain=int((grid.margin[ra:rb, cl:cr] < 0.05).sum()),
                        fill=round(float(cells.mean()), 3))
            out.append(Chart(name, cells, meta))
        return out

    def check_image(self, path):
        if self.grid is None:
            return
        grid = self.grid
        img = cv2.cvtColor((self.crop * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        paint_cells(img, grid.cells, grid.margin, grid.xs, grid.ys)
        for i, (a, b, l, r) in enumerate(self.band_spans, 1):
            cv2.rectangle(img, (grid.xs[l], grid.ys[a]), (grid.xs[r], grid.ys[b]), (200, 120, 0), 2)
            cv2.putText(img, f"b{i} {b - a}x{r - l}", (grid.xs[l] + 4, grid.ys[a] + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 80, 0), 2)
        cv2.imwrite(str(path), img)
