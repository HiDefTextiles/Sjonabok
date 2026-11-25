#!/usr/bin/env python3
"""Digitise counted-thread charts from a page scan.

A chart is a ruled grid; a filled cell carries a mark (cross, dot or solid
square) in its middle. We find grid regions, fit the line positions, and
score the ink in the middle of every cell.

usage: digitise.py page.jpg outdir [--prefix NAME]
"""
import argparse, json
from pathlib import Path
import numpy as np
import cv2


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
        """Ink in the middle of each cell, relative to the local darkness of
        the ruling (prints are uneven: faint areas have faint marks too)."""
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        h, w = len(self.ys) - 1, len(self.xs) - 1
        s = np.zeros((h, w)); line = np.zeros((h, w))
        for r in range(h):
            a, b = self.ys[r], self.ys[r + 1]
            ma = max(1, int(round((b - a) * 0.25)))
            for c in range(w):
                l, rr = self.xs[c], self.xs[c + 1]
                mb = max(1, int(round((rr - l) * 0.25)))
                s[r, c] = sub[a + ma:b - ma + 1, l + mb:rr - mb + 1].mean()
                # the cell's left and top ruling, centre third only
                line[r, c] = 0.5 * (sub[a + ma:b - ma + 1, max(0, l - 1):l + 2].mean() +
                                    sub[max(0, a - 1):a + 2, l + mb:rr - mb + 1].mean())
        s = np.nan_to_num(s)
        self.scores = s
        t, _ = cv2.threshold((s * 255).astype(np.uint8), 0, 255,
                             cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        self.threshold = t / 255
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

    def text(self):
        return "\n".join("".join(map(str, row)) for row in self.cells) + "\n"


class Page:
    def __init__(self, path, woodcut=False):
        self.path = Path(path)
        g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        self.gray = g
        if woodcut:
            # white-line woodcuts have large solid black fields, so a median
            # would take the ink for paper: use the brightest level nearby
            bg = cv2.blur(cv2.dilate(g, np.ones((151, 151), np.uint8)), (151, 151))
        else:
            bg = cv2.medianBlur(g, 51)                   # paper level
        norm = np.clip(g.astype(float) / np.maximum(bg, 1), 0, 1)
        self.ink = np.clip((1 - norm - 0.04) / 0.55, 0, 1)

    def regions(self, min_side=60):
        """Ruled charts are evenly dense; text and margins are not."""
        d = cv2.blur((self.ink > 0.15).astype(np.float32), (41, 41))
        m = (d > 0.28).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((45, 45), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(m)
        out = []
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if w < min_side or h < min_side:
                continue
            pad = 25
            box = (max(0, x - pad), max(0, y - pad),
                   min(self.ink.shape[1], x + w + pad), min(self.ink.shape[0], y + h + pad))
            out.append(box)
        out.sort(key=lambda bx: (bx[1] // 40, bx[0]))
        regs = []
        for i, (x0, y0, x1, y1) in enumerate(out):
            crop, angle = self.deskew(self.ink[y0:y1, x0:x1])
            g = GridRegion(crop, (0, 0, crop.shape[1], crop.shape[0]), self.path.stem, i + 1)
            g.page_box, g.angle = (x0, y0, x1, y1), angle
            g.gray = 255 - (crop * 255).astype(np.uint8)
            g.tighten()
            regs.append(g)
        return regs

    @staticmethod
    def rotate(img, angle):
        h, w = img.shape
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)

    def deskew(self, crop):
        best = None
        for a in np.arange(-2.5, 2.51, 0.05):
            r = self.rotate(crop, a)
            v = r.mean(axis=1).var() + r.mean(axis=0).var()
            if best is None or v > best[0]:
                best = (v, a)
        return self.rotate(crop, best[1]), float(best[1])


def overlay(page, regions, path):
    """Deskewed crops of every chart with the read cells painted red;
    near-threshold cells outlined orange."""
    tiles = []
    for g in regions:
        img = cv2.cvtColor(g.gray, cv2.COLOR_GRAY2BGR)
        for r in range(g.cells.shape[0]):
            for c in range(g.cells.shape[1]):
                x0, x1 = g.x0 + g.xs[c], g.x0 + g.xs[c + 1]
                y0, y1 = g.y0 + g.ys[r], g.y0 + g.ys[r + 1]
                if g.cells[r, c]:
                    sub = img[y0 + 2:y1 - 1, x0 + 2:x1 - 1]
                    sub[:] = (0.45 * sub + 0.55 * np.array([40, 40, 230])).astype(np.uint8)
                elif g.margin[r, c] < 0.05:
                    cv2.rectangle(img, (x0 + 2, y0 + 2), (x1 - 2, y1 - 2), (0, 160, 255), 1)
        cv2.rectangle(img, (g.x0, g.y0), (g.x1, g.y1), (200, 120, 0), 1)
        cv2.putText(img, f"{g.name} {g.cells.shape[0]}x{g.cells.shape[1]}", (6, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 80, 0), 2)
        tiles.append(img)
    if not tiles:
        return
    w = max(t.shape[1] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, 6, 0, w - t.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
    cv2.imwrite(str(path), np.vstack(tiles))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page"); ap.add_argument("outdir")
    ap.add_argument("--woodcut", action="store_true",
                    help="white-line woodcut (cells cut out of a black block)")
    a = ap.parse_args()
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    page = Page(a.page, a.woodcut)
    regions = [g.fit().score() for g in page.regions()]
    regions = [g for g in regions if g.cells.shape[0] >= 3 and g.cells.shape[1] >= 3]
    for g in regions:
        (out / f"{g.name}.txt").write_text(g.text())
    overlay(page, regions, out / f"{page.path.stem}_check.jpg")
    print(json.dumps([g.meta() for g in regions]))


if __name__ == "__main__":
    main()
