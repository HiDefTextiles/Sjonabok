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

    def chart_distance(self):
        ids = [u.id for u in self.units]
        idx = {i: k for k, i in enumerate(ids)}
        motifs = sorted(set(self.motif))
        col = {m: k for k, m in enumerate(motifs)}
        X = np.zeros((len(ids), len(motifs)))
        for p, m in zip(self.pieces, self.motif):
            X[idx[p.chart], col[m]] += 1
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
        charts, sources, size = defaultdict(set), defaultdict(set), defaultdict(list)
        for p, m in zip(self.pieces, self.motif):
            charts[m].add(p.chart)
            sources[m].add(p.source)
            size[m].append(p.n)
        with open(OUT / "motifs.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["submotif", "cells", "charts", "manuscripts", "manuscript_list", "example"])
            for m in sorted(charts, key=lambda m: (-len(charts[m]), m)):
                w.writerow([m, int(np.median(size[m])), len(charts[m]), len(sources[m]),
                            "|".join(sorted(sources[m])), sorted(charts[m])[0]])
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
    a = ap.parse_args()
    sm = SubMotifs(Corpus(a.txt, PILOT_KINDS + BAND_KINDS).units)
    sm.cluster()
    sm.write()


if __name__ == "__main__":
    main()
