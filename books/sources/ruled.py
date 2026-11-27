"""Counted charts on a printed ruled grid (Sibmacher's etchings).

A chart is a ruled grid; a filled cell carries a mark (cross, dot or solid
square) in its middle. We find grid regions, fit the line positions, and
score the ink in the middle of every cell. This is the reader that was
books/digitise.py in PR #46, moved here unchanged in what it computes.
"""
import cv2
import numpy as np

from .base import (Chart, PatternSource, centre_means, deskew, otsu,
                   paint_cells, paper_level, read_gray)


class GridRegion:
    """One ruled chart on the page: its line positions and cell values."""

    def __init__(self, ink, box, page_id, index):
        self.ink = ink                      # 0..1 float, ink = 1
        self.x0, self.y0, self.x1, self.y1 = box
        self.page_id, self.index = page_id, index
        self.xs = self.ys = None
        self.scores = self.cells = None

    def tighten(self):
        """Shrink the box to the rows/columns that are ruled."""
        r = (self.ink > 0.15).astype(np.float32)
        rows = np.convolve(r.mean(axis=1), np.ones(9) / 9, mode="same")
        cols = np.convolve(r.mean(axis=0), np.ones(9) / 9, mode="same")
        ys = np.nonzero(rows > 0.5 * np.median(rows[rows > 0.1]))[0]
        xs = np.nonzero(cols > 0.5 * np.median(cols[cols > 0.1]))[0]
        self.x0, self.x1 = max(0, xs[0] - 3), min(r.shape[1], xs[-1] + 4)
        self.y0, self.y1 = max(0, ys[0] - 3), min(r.shape[0], ys[-1] + 4)

    @staticmethod
    def autocorr(profile):
        p = profile - np.convolve(profile, np.ones(15) / 15, mode="same")
        p = np.clip(p, 0, None)
        a = np.correlate(p - p.mean(), p - p.mean(), mode="full")[len(p) - 1:]
        return a / (a[0] + 1e-9)

    @staticmethod
    def clean(profile):
        p = profile - np.convolve(profile, np.ones(15) / 15, mode="same")
        return np.clip(p, 0, None)

    @staticmethod
    def phase_score(p, pitch):
        """Best mean profile value on a comb of this pitch, and its phase."""
        best = (-1, 0)
        for phase in np.arange(0, pitch, 0.25):
            idx = np.round(np.arange(phase, len(p) - 1, pitch)).astype(int)
            v = p[idx].mean()
            if v > best[0]:
                best = (v, phase)
        return best

    @staticmethod
    def comb(p, pitch, phase):
        """Follow the ruling line by line: predict the next line one pitch
        on, then snap to the darkest column within ±3 px (absorbs paper
        stretch and plate drift)."""
        lines, x = [], phase
        while x < len(p) - 1:
            i = int(round(x))
            lo, hi = max(0, i - 3), min(len(p), i + 4)
            j = lo + int(np.argmax(p[lo:hi]))
            # take the snap only if it is a real peak; else keep the prediction
            if p[j] > 0.3 * np.median(p[p > 0]) if (p > 0).any() else False:
                x = j
            else:
                x = i
            lines.append(int(x))
            x += pitch
        return np.array(lines)

    def fit(self):
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        # A ruling line is inked along (nearly) its whole length; the
        # marks inside filled cells are not. A low percentile across the
        # chart keeps the lines and drops the marks.
        colp = np.percentile(sub, 30, axis=0)
        rowp = np.percentile(sub, 30, axis=1)
        n = min(len(colp), len(rowp), 60)
        a = self.autocorr(colp)[:n] + self.autocorr(rowp)[:n]
        lo = 7
        lag = lo + int(np.argmax(a[lo:n]))
        # cells are square: one pitch for both axes, chosen jointly
        cx, cy = self.clean(colp), self.clean(rowp)
        best = None
        for pitch in np.arange(lag - 0.7, lag + 0.7, 0.02):
            sx, phx = self.phase_score(cx, pitch)
            sy, phy = self.phase_score(cy, pitch)
            if best is None or sx + sy > best[0]:
                best = (sx + sy, pitch, phx, phy)
        _, pitch, phx, phy = best
        self.px = self.py = pitch
        self.xs, self.ys = self.comb(cx, pitch, phx), self.comb(cy, pitch, phy)
        self.colp, self.rowp = colp, rowp

        # keep only lines inside the ruled area: a line must be dark along
        # most of its length
        def keep(lines, axis):
            prof = self.colp if axis == 0 else self.rowp
            thr = 0.3 * np.median(prof[lines])
            ok = np.nonzero(prof[lines] > thr)[0]
            return lines[ok[0]:ok[-1] + 1] if len(ok) else lines
        self.xs, self.ys = keep(self.xs, 0), keep(self.ys, 1)
        return self

    def score(self):
        """Ink in the middle of each cell, one Otsu threshold per chart."""
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        s = centre_means(sub, self.xs, self.ys)
        self.scores = s
        self.threshold = otsu(s)
        # cells near the threshold are uncertain
        self.cells = (s > self.threshold).astype(np.uint8)
        self.margin = np.abs(s - self.threshold)
        self.trim_frame()
        return self

    def trim_frame(self, full=0.9):
        """Drop edge rows/columns that are the printed frame (almost all
        'filled' because of the heavy rule), keeping line lists in step."""
        while self.cells.shape[0] > 2 and self.cells[0].mean() > full:
            self.cells, self.scores, self.margin = self.cells[1:], self.scores[1:], self.margin[1:]
            self.ys = self.ys[1:]
        while self.cells.shape[0] > 2 and self.cells[-1].mean() > full:
            self.cells, self.scores, self.margin = self.cells[:-1], self.scores[:-1], self.margin[:-1]
            self.ys = self.ys[:-1]
        while self.cells.shape[1] > 2 and self.cells[:, 0].mean() > full:
            self.cells, self.scores, self.margin = self.cells[:, 1:], self.scores[:, 1:], self.margin[:, 1:]
            self.xs = self.xs[1:]
        while self.cells.shape[1] > 2 and self.cells[:, -1].mean() > full:
            self.cells, self.scores, self.margin = self.cells[:, :-1], self.scores[:, :-1], self.margin[:, :-1]
            self.xs = self.xs[:-1]

    @property
    def name(self):
        return f"{self.page_id}_r{self.index}"

    def meta(self):
        return dict(name=self.name, box=[int(v) for v in self.page_box], angle=round(self.angle, 2),
                    rows=int(self.cells.shape[0]), cols=int(self.cells.shape[1]),
                    pitch_x=round(float(self.px), 2), pitch_y=round(float(self.py), 2),
                    threshold=round(float(self.threshold), 3),
                    uncertain=int((self.margin < 0.05).sum()),
                    fill=round(float(self.cells.mean()), 3))

    def chart(self):
        return Chart(self.name, self.cells, self.meta())


class RuledGridSource(PatternSource):
    """Printed counted grid: ruling lines plus a mark in each filled cell.

    options: white_line=False  paper level from dilation (the old
             --woodcut flag of digitise.py; WhiteLineWoodcutSource is the
             reader that works for woodcuts)
             min_side=60       smallest chart region, pixels
    """
    layout = "ruled"
    description = "ruled counted grid, one mark per filled cell (etching, engraving)"
    region_class = GridRegion

    def __init__(self, path, provenance=None, white_line=False, min_side=60, **options):
        super().__init__(path, provenance, **options)
        self.white_line, self.min_side = white_line, min_side
        g = read_gray(self.path)
        self.gray = g
        bg = paper_level(g, white_line)
        norm = np.clip(g.astype(float) / np.maximum(bg, 1), 0, 1)
        self.ink = np.clip((1 - norm - 0.04) / 0.55, 0, 1)

    def region_boxes(self):
        """Ruled charts are evenly dense; text and margins are not."""
        d = cv2.blur((self.ink > 0.15).astype(np.float32), (41, 41))
        m = (d > 0.28).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((45, 45), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(m)
        out = []
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if w < self.min_side or h < self.min_side:
                continue
            pad = 25
            out.append((max(0, x - pad), max(0, y - pad),
                        min(self.ink.shape[1], x + w + pad), min(self.ink.shape[0], y + h + pad)))
        out.sort(key=lambda bx: (bx[1] // 40, bx[0]))
        return out

    def regions(self):
        regs = []
        for i, (x0, y0, x1, y1) in enumerate(self.region_boxes()):
            crop, angle = deskew(self.ink[y0:y1, x0:x1], border=0)
            g = self.region_class(crop, (0, 0, crop.shape[1], crop.shape[0]), self.page_id, i + 1)
            g.page_box, g.angle = (x0, y0, x1, y1), angle
            g.gray = 255 - (crop * 255).astype(np.uint8)
            g.tighten()
            regs.append(g)
        return regs

    def read(self):
        regs = [g.fit().score() for g in self.regions()]
        self._regions = [g for g in regs if g.cells.shape[0] >= 3 and g.cells.shape[1] >= 3]
        return [g.chart() for g in self._regions]

    def check_image(self, path):
        """Deskewed crops of every chart with the read cells painted red;
        near-threshold cells outlined orange."""
        tiles = []
        for g in self._regions:
            img = cv2.cvtColor(g.gray, cv2.COLOR_GRAY2BGR)
            paint_cells(img, g.cells, g.margin, g.xs, g.ys, g.x0, g.y0)
            cv2.rectangle(img, (g.x0, g.y0), (g.x1, g.y1), (200, 120, 0), 1)
            cv2.putText(img, f"{g.name} {g.cells.shape[0]}x{g.cells.shape[1]}", (6, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 80, 0), 2)
            tiles.append(img)
        if not tiles:
            return
        w = max(t.shape[1] for t in tiles)
        tiles = [cv2.copyMakeBorder(t, 0, 6, 0, w - t.shape[1], cv2.BORDER_CONSTANT,
                                    value=(255, 255, 255)) for t in tiles]
        cv2.imwrite(str(path), np.vstack(tiles))
