"""Recurring sub-motifs: the pieces charts are built from, matched across charts.

A piece is a connected group of filled cells (touching at sides or corners)
in a chart's repeat unit, of at least MIN_CELLS cells. Two pieces match when,
after turning or mirroring one of them (8 ways) and shifting it by up to SHIFT
cells, they share at least MATCH of their filled cells (intersection over
union). Matching pieces are joined into one sub-motif (average linkage on
1 - IoU, cut at 1 - MATCH), so a bird drawn with one cell more or less in
another manuscript still counts as the same bird.

Each chart then has a list of the sub-motifs it contains, and two charts are
close when they share sub-motifs, weighted by how rare each sub-motif is
(tf-idf, cosine). Nothing here uses labels.

    python3 submotifs.py --txt ../../patterns/txt

writes
    work/submotifs/pieces.csv      every piece: chart, sub-motif, size, position
    work/submotifs/motifs.csv      every sub-motif: size, charts, manuscripts
    work/all/submotif_dist.csv     chart distance from shared sub-motifs
"""

import argparse
import csv
from collections import defaultdict

import numpy as np
from scipy import ndimage
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from scipy import fft as sfft

from subjects import ALL, BAND_KINDS, PILOT_KINDS, WORK, Corpus, write_matrix

MIN_CELLS = 8
SHIFT = 2
MATCH = 0.7
OUT = WORK / "submotifs"


class Piece:
    def __init__(self, chart, source, cells, y, x):
        self.chart, self.source, self.cells, self.y, self.x = chart, source, cells, y, x
        self.n = int(cells.sum())
        # the 8 turned and mirrored versions, each padded by SHIFT for shifting
        self.views = [np.pad(np.rot90(b, k), SHIFT) for b in (cells, cells[:, ::-1]) for k in range(4)]

    @staticmethod
    def overlap(a, b):
        """Best intersection over union of b on a, b shifted by up to SHIFT cells."""
        H, W = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
        A = np.zeros((H, W), bool)
        A[(H - a.shape[0]) // 2:(H - a.shape[0]) // 2 + a.shape[0], (W - a.shape[1]) // 2:(W - a.shape[1]) // 2 + a.shape[1]] = a
        B = np.zeros((H, W), bool)
        B[(H - b.shape[0]) // 2:(H - b.shape[0]) // 2 + b.shape[0], (W - b.shape[1]) // 2:(W - b.shape[1]) // 2 + b.shape[1]] = b
        best = 0.0
        na, nb = A.sum(), B.sum()
        for dy in range(-SHIFT, SHIFT + 1):
            for dx in range(-SHIFT, SHIFT + 1):
                inter = (A & np.roll(np.roll(B, dy, 0), dx, 1)).sum()
                best = max(best, inter / (na + nb - inter))
        return best

    def iou(self, other):
        a = np.pad(self.cells, SHIFT).astype(bool)
        return max(self.overlap(a, v.astype(bool)) for v in other.views)


class FigureFinder:
    """Find each sub-motif also where it is joined to something else (a bird on a branch,
    a star on a border line), which the cut into pieces misses.

    All charts are laid side by side on one large sheet with empty gaps, and each sub-motif
    (in its 8 turns and mirrors) is slid over the sheet by Fourier correlation. A hit is a place
    where at least COVER of the sub-motif's filled cells are filled, where the chart adds at
    most EXTRA times as many filled cells again inside the sub-motif's outline, and where at
    most AROUND of the empty cells around it (inside its bounding box) are filled: a figure
    with a stem joined on still counts, a solid block or dense lace does not."""

    COVER = 0.85
    EXTRA = 0.35
    AROUND = 0.25
    GAP = 4

    def __init__(self, units, width=2400):
        self.units = units
        x = y = row_h = 0
        self.place = []
        for u in units:
            h, w = np.asarray(u.cells).shape
            if x + w > width:
                x, y, row_h = 0, y + row_h + self.GAP, 0
            self.place.append((y, x, h, w))
            x += w + self.GAP
            row_h = max(row_h, h)
        H = y + row_h + self.GAP
        self.sheet = np.zeros((H, width + self.GAP), np.float32)
        for u, (y, x, h, w) in zip(units, self.place):
            self.sheet[y:y + h, x:x + w] = np.asarray(u.cells)
        self.owner = -np.ones(self.sheet.shape, int)
        for k, (y, x, h, w) in enumerate(self.place):
            self.owner[y:y + h, x:x + w] = k
        self.shape = [sfft.next_fast_len(n) for n in self.sheet.shape]
        self.F = sfft.rfft2(self.sheet, self.shape)

    def correlate(self, t):
        """Sum of sheet cells under t at every top-left position."""
        T = sfft.rfft2(t[::-1, ::-1].astype(np.float32), self.shape)
        c = sfft.irfft2(self.F * T, self.shape)
        th, tw = t.shape
        return c[th - 1:th - 1 + self.sheet.shape[0], tw - 1:tw - 1 + self.sheet.shape[1]]

    def find(self, cells, where=False):
        """Charts (indices) in which the figure occurs, joined or not; with where=True,
        (chart, row, col, height, width) of every hit."""
        hits = set()
        spots = []
        seen = set()
        for b in (cells, cells[:, ::-1]):
            for k in range(4):
                t = np.rot90(b, k).astype(bool)
                key = (t.shape, t.tobytes())
                if key in seen:
                    continue
                seen.add(key)
                n = t.sum()
                filled = np.asarray(ndimage.binary_fill_holes(t), bool)
                cover = self.correlate(t) / n
                inside = self.correlate(filled)
                around = ~filled
                ok = (cover >= self.COVER - 1e-4) & (inside - cover * n <= self.EXTRA * n + 1e-4)
                if around.any():
                    ok &= self.correlate(around) <= self.AROUND * around.sum() + 1e-4
                for yy, xx in zip(*np.nonzero(ok)):
                    o = self.owner[yy, xx]
                    if o >= 0 and self.owner[min(yy + t.shape[0] - 1, self.owner.shape[0] - 1),
                                             min(xx + t.shape[1] - 1, self.owner.shape[1] - 1)] == o:
                        hits.add(o)
                        y0, x0 = self.place[o][:2]
                        spots.append((o, yy - y0, xx - x0, *t.shape))
        return spots if where else hits


class SubMotifs:
    def __init__(self, units):
        self.units = units
        self.pieces = []
        for u in units:
            m = np.asarray(u.cells).astype(bool)
            lab, k = ndimage.label(m, np.ones((3, 3)))
            for sl, j in zip(ndimage.find_objects(lab), range(1, k + 1)):
                p = lab[sl] == j
                if p.sum() >= MIN_CELLS:
                    self.pieces.append(Piece(u.id, u.pattern.source, p.astype(np.uint8), sl[0].start, sl[1].start))

    def comparable(self, a, b):
        """Only pieces of similar size can reach MATCH: IoU <= smaller / larger."""
        if min(a.n, b.n) / max(a.n, b.n) < MATCH:
            return False
        da = sorted(a.cells.shape)
        db = sorted(b.cells.shape)
        return abs(da[0] - db[0]) <= 2 * SHIFT and abs(da[1] - db[1]) <= 2 * SHIFT

    def distances(self):
        n = len(self.pieces)
        d = np.ones((n, n))
        np.fill_diagonal(d, 0.0)
        order = sorted(range(n), key=lambda i: self.pieces[i].n)
        for ii, i in enumerate(order):
            a = self.pieces[i]
            for j in order[ii + 1:]:
                b = self.pieces[j]
                if b.n * MATCH > a.n:
                    break
                if self.comparable(a, b):
                    d[i, j] = d[j, i] = 1.0 - a.iou(b)
        return d

    def cluster(self):
        d = self.distances()
        z = linkage(squareform(d, checks=False), "average")
        self.motif = fcluster(z, t=1.0 - MATCH, criterion="distance")
        return self.motif

    def find_joined(self, min_cells=20):
        """Add the charts where a sub-motif of at least min_cells cells occurs joined to
        something else (FigureFinder). Every distinct piece of the sub-motif is searched."""
        ff = FigureFinder(self.units)
        self.joined = defaultdict(set)
        done = {}
        for p, m in zip(self.pieces, self.motif):
            if p.n < min_cells:
                continue
            key = min((v.shape, v.tobytes()) for v in p.views)
            if key not in done:
                done[key] = {self.units[k].id for k in ff.find(p.cells)}
            self.joined[m] |= done[key]
        return self.joined

    def occurrences(self):
        """sub-motif -> charts, from pieces and (if searched) joined figures."""
        occ = defaultdict(set)
        for p, m in zip(self.pieces, self.motif):
            occ[m].add(p.chart)
        for m, charts in getattr(self, "joined", {}).items():
            occ[m] |= charts
        return occ

    def chart_distance(self):
        ids = [u.id for u in self.units]
        idx = {i: k for k, i in enumerate(ids)}
        motifs = sorted(set(self.motif))
        col = {m: k for k, m in enumerate(motifs)}
        X = np.zeros((len(ids), len(motifs)))
        for m, charts in self.occurrences().items():
            for c in charts:
                X[idx[c], col[m]] = 1
        df = (X > 0).sum(0)
        X = (X > 0) * np.log(len(ids) / df)          # tf-idf: presence, weighted by rarity
        X[:, df < 2] = 0                             # a sub-motif in one chart only says nothing
        norm = np.linalg.norm(X, axis=1, keepdims=True)
        Xn = np.divide(X, norm, out=np.zeros_like(X), where=norm > 0)
        d = 1.0 - Xn @ Xn.T
        d[norm[:, 0] == 0, :] = 1.0
        d[:, norm[:, 0] == 0] = 1.0
        np.fill_diagonal(d, 0.0)
        return ids, np.clip(d, 0, 1)

    def write(self):
        OUT.mkdir(parents=True, exist_ok=True)
        with open(OUT / "pieces.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["chart", "submotif", "cells", "height", "width", "row", "col"])
            for p, m in zip(self.pieces, self.motif):
                w.writerow([p.chart, m, p.n, *p.cells.shape, p.y, p.x])
        source = {u.id: u.pattern.source for u in self.units}
        charts, sources, size = self.occurrences(), defaultdict(set), defaultdict(list)
        for p, m in zip(self.pieces, self.motif):
            size[m].append(p.n)
        for m, cs in charts.items():
            sources[m] = {source[c] for c in cs}
        example = {}
        for p, m in zip(self.pieces, self.motif):
            example.setdefault(m, p.chart)
        with open(OUT / "occurrences.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["submotif", "chart", "manuscript", "as_piece"])
            pieceset = {(m, p.chart) for p, m in zip(self.pieces, self.motif)}
            for m in sorted(charts):
                for c in sorted(charts[m]):
                    w.writerow([m, c, source[c], int((m, c) in pieceset)])
        with open(OUT / "motifs.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["submotif", "cells", "charts", "manuscripts", "manuscript_list", "example"])
            for m in sorted(charts, key=lambda m: (-len(charts[m]), m)):
                w.writerow([m, int(np.median(size[m])), len(charts[m]), len(sources[m]),
                            "|".join(sorted(sources[m])), example[m]])
        # a small picture of each recurring sub-motif (its first piece), for timeline.R
        from PIL import Image
        (OUT / "png").mkdir(exist_ok=True)
        drawn = set()
        for p, m in zip(self.pieces, self.motif):
            if m in drawn or len(charts[m]) < 2:
                continue
            drawn.add(m)
            Image.fromarray(np.where(p.cells == 1, 0, 255).astype(np.uint8)).save(OUT / "png" / f"{m}.png")
        ids, d = self.chart_distance()
        ALL.mkdir(parents=True, exist_ok=True)
        write_matrix(ALL / "submotif_dist.csv", ids, d)
        rec = sum(1 for m in charts if len(charts[m]) >= 2)
        multi = sum(1 for m in charts if len(sources[m]) >= 2)
        print(f"{len(self.pieces)} pieces -> {len(charts)} sub-motifs; {rec} recur in 2+ charts, "
              f"{multi} in 2+ manuscripts -> {OUT}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--txt", default="../../patterns/txt")
    ap.add_argument("--pieces-only", action="store_true", help="skip the search for joined figures")
    a = ap.parse_args()
    sm = SubMotifs(Corpus(a.txt, PILOT_KINDS + BAND_KINDS).units)
    sm.cluster()
    if not a.pieces_only:
        sm.find_joined()
    sm.write()


if __name__ == "__main__":
    main()
