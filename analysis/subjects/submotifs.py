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
INNER_CELLS = 20     # smallest figure looked for as a repeat inside one chart
JOINED_CELLS = 30    # smallest sub-motif searched for where joined to other figures
GENERIC = 0.15       # a sub-motif in more than this share of charts is too common to tell charts apart
OUT = WORK / "submotifs"


class Piece:
    def __init__(self, chart, source, cells, y, x, how="piece"):
        self.chart, self.source, self.cells, self.y, self.x, self.how = chart, source, cells, y, x, how
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


class InnerRepeats:
    """Figures repeated inside one chart, also where they are joined to the rest.

    The chart is laid over itself turned, mirrored and shifted (Fourier correlation); at
    the best few places where the copies overlap only in part (between LO and HI of the
    filled cells, so not the chart's own overall symmetry, which the seeds in
    patterns/seeds.csv describe), the cells that coincide are a figure that occurs at least
    twice. Such a figure is kept only if it is clean: it holds at least CLEAN of the chart's
    filled cells inside its own bounding box, so it is a whole figure and not a fragment
    of a larger one."""

    LO, HI, CLEAN, PEAKS = 0.08, 0.75, 0.85, 6

    @staticmethod
    def find(m, min_cells):
        from scipy.signal import fftconvolve
        m = m.astype(bool)
        n, (H, W) = m.sum(), m.shape
        out = []
        for f in (0, 1):
            for k in range(4):
                t = np.rot90(m[:, ::-1] if f else m, k)
                th, tw = t.shape
                c = np.rint(fftconvolve(m.astype(float), t[::-1, ::-1].astype(float))).astype(int)
                peak = (c == ndimage.maximum_filter(c, size=7)) & (c >= max(min_cells, InnerRepeats.LO * n))
                for i, j in sorted(np.argwhere(peak), key=lambda ij: -c[ij[0], ij[1]])[:InnerRepeats.PEAKS]:
                    dy, dx = i - th + 1, j - tw + 1
                    if (f, k, dy, dx) == (0, 0, 0, 0) or c[i, j] > InnerRepeats.HI * n:
                        continue
                    sh = np.zeros_like(m)
                    ys, ye, xs, xe = max(0, dy), min(H, dy + th), max(0, dx), min(W, dx + tw)
                    sh[ys:ye, xs:xe] = t[ys - dy:ye - dy, xs - dx:xe - dx]
                    lab, q = ndimage.label(m & sh, np.ones((3, 3)))
                    for sl, r in zip(ndimage.find_objects(lab), range(1, q + 1)):
                        piece = lab[sl] == r
                        if piece.sum() >= min_cells and piece.sum() >= InnerRepeats.CLEAN * m[sl].sum():
                            out.append((sl[0].start, sl[1].start, piece))
        return out


class SubMotifs:
    def __init__(self, units, inner=True):
        self.units = units
        self.pieces = []
        seen = set()
        for u in units:
            m = np.asarray(u.cells).astype(bool)
            lab, k = ndimage.label(m, np.ones((3, 3)))
            found = [(sl[0].start, sl[1].start, lab[sl] == j, "piece")
                     for sl, j in zip(ndimage.find_objects(lab), range(1, k + 1))]
            if inner:
                found += [(y, x, p, "inner") for y, x, p in InnerRepeats.find(m, INNER_CELLS)]
            for y, x, p, how in found:
                if p.sum() < MIN_CELLS or min(p.shape) < 3:     # too small, or a plain line
                    continue
                if how == "inner" and not self.telling(p):
                    continue
                key = (u.id, min((np.rot90(b, r).shape, np.rot90(b, r).tobytes())
                                 for b in (p, p[:, ::-1]) for r in range(4)))
                if key in seen:       # the same figure found twice in one chart
                    continue
                seen.add(key)
                self.pieces.append(Piece(u.id, u.pattern.source, p.astype(np.uint8), y, x, how))

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

    @staticmethod
    def telling(cells):
        """A shape worth searching for: not a strip (sides at most 3 : 1) and not a near-solid
        block (at most 70% of its bounding box filled), which match almost anything dense."""
        h, w = cells.shape
        return max(h, w) <= 3 * min(h, w) and cells.mean() <= 0.7

    def find_joined(self, min_cells=JOINED_CELLS):
        """Add the charts where a sub-motif of at least min_cells cells occurs joined to
        something else (FigureFinder). Every distinct telling piece of the sub-motif is searched."""
        ff = FigureFinder(self.units)
        self.joined = defaultdict(set)
        done = {}
        for p, m in zip(self.pieces, self.motif):
            if p.n < min_cells or not self.telling(p.cells):
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
        X[:, df > GENERIC * len(ids)] = 0            # nor does one found almost everywhere
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
            w.writerow(["chart", "submotif", "cells", "height", "width", "row", "col", "how"])
            for p, m in zip(self.pieces, self.motif):
                w.writerow([p.chart, m, p.n, *p.cells.shape, p.y, p.x, p.how])
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
            w.writerow(["submotif", "cells", "charts", "manuscripts", "manuscript_list", "example", "generic"])
            for m in sorted(charts, key=lambda m: (-len(charts[m]), m)):
                w.writerow([m, int(np.median(size[m])), len(charts[m]), len(sources[m]),
                            "|".join(sorted(sources[m])), example[m],
                            int(len(charts[m]) > GENERIC * len(self.units))])
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
    ap.add_argument("--pieces-only", action="store_true",
                    help="only separate pieces: no repeats inside charts, no search for joined figures")
    a = ap.parse_args()
    sm = SubMotifs(Corpus(a.txt, PILOT_KINDS + BAND_KINDS).units, inner=not a.pieces_only)
    sm.cluster()
    if not a.pieces_only:
        sm.find_joined()
    sm.write()


if __name__ == "__main__":
    main()
