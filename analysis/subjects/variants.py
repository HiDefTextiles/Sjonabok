"""Better pictures of the recurring sub-motifs, and size variants of the same figure.

    python variants.py [--txt ../../patterns/txt] [--min-charts 2]

Reads work/submotifs/pieces.csv and motifs.csv (submotifs.py). For each recurring
sub-motif:

1. Every place it occurs (as a separate piece, or found joined to something by
   FigureFinder) is cut out of its chart, turned and shifted to line up with the others.
2. The consensus figure keeps the cells filled in at least half of the places (each chart
   counts once, however often it repeats the figure). This is the figure as the scribes
   mostly drew it, not the first copy the computer happened to find.
3. Each place gets a fit: its overlap (intersection over union) with the consensus. Places
   below STRETCH are a stretch and are dropped; a sub-motif whose places mostly fit badly
   is marked as doubtful.

Then the consensus figures are compared regardless of size (each scaled to the same
square), so that a rosette with longer arms, or a bird a row taller, falls into the same
kind as the smaller one.

Writes work/submotifs/consensus.csv (sub-motif, cells, places, charts, fit, doubtful, kind),
places.csv (sub-motif, chart, row, col, height, width, fit, kept), kinds.csv and
consensus/<id>.png pictures (cells shaded by how many places agree).
"""
import argparse
import csv
from collections import defaultdict

import numpy as np
from scipy import ndimage
from PIL import Image
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial import ConvexHull
from scipy.spatial.distance import squareform

import subjects as S
from submotifs import OUT, SHIFT, FigureFinder, SubMotifs, HI_BLUE, WHITE

STRETCH = 0.7      # a place overlapping the consensus less than this is a stretch
DOUBTFUL = 0.65    # median fit below this: the sub-motif itself is doubtful
VOTE = 0.5         # share of charts that must fill a cell for the consensus to keep it
PALE = (205, 204, 236)   # HÍ blue at a fifth
KIND_SIDE = 24     # side of the square every figure is scaled to before comparing sizes
KIND_MATCH = 0.6   # scaled overlap needed to call two figures the same kind
KIND_RATIO = 3.0   # at most this many times as many cells as the other
KIND_SOLID = 0.7    # only figures with arms, holes or branches (see solidity)
KIND_CELLS = 20    # smaller figures are too plain to compare across sizes


def views(m):
    """The 8 turned and mirrored versions."""
    return [np.rot90(b, k) for b in (m, m[:, ::-1]) for k in range(4)]


class Aligner:
    """Lines a cut-out up with a reference figure: best turn, mirror and shift (up to
    SHIFT cells) by overlap, on a canvas the size of the reference padded by SHIFT."""

    def __init__(self, ref):
        self.ref = ref.astype(bool)
        self.H, self.W = ref.shape[0] + 2 * SHIFT, ref.shape[1] + 2 * SHIFT
        self.R = np.pad(self.ref, SHIFT)

    def place(self, m):
        """m on the canvas, centred."""
        c = np.zeros((self.H, self.W), bool)
        h, w = min(m.shape[0], self.H), min(m.shape[1], self.W)
        m = m[(m.shape[0] - h) // 2:(m.shape[0] - h) // 2 + h, (m.shape[1] - w) // 2:(m.shape[1] - w) // 2 + w]
        y, x = (self.H - h) // 2, (self.W - w) // 2
        c[y:y + h, x:x + w] = m
        return c

    def align(self, m):
        best, out = -1.0, None
        for v in views(m.astype(bool)):
            c = self.place(v)
            for dy in range(-SHIFT, SHIFT + 1):
                for dx in range(-SHIFT, SHIFT + 1):
                    s = np.roll(np.roll(c, dy, 0), dx, 1)
                    inter = (s & self.R).sum()
                    iou = inter / max(1, (s | self.R).sum())
                    if iou > best:
                        best, out = iou, s
        return out


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def solidity(m):
    """Filled share of the convex hull: near 1 for solid triangles and corners, which scale
    into each other whatever they are; about 0.5 for a rosette or a tree."""
    ys, xs = np.nonzero(m)
    pts = np.array([(y + dy, x + dx) for y, x in zip(ys, xs) for dy in (0, 1) for dx in (0, 1)])
    return m.sum() / ConvexHull(pts).volume


def trim(m):
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        return m
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def clean(m, agree=0.85, strict=False):
    """Tidy a figure: even out the symmetry it nearly has, and drop stray cells.

    Each of the 8 turns and mirrors (with a shift of up to one cell, for figures whose centre
    falls between cells) that matches the figure on at least `agree` of its cells counts as one
    of its symmetries; every cell then takes the majority over those symmetric copies, so a
    cell a scribe added or left out on one arm only is settled by the other arms. Finally a
    cell touching no other filled cell (a stray pixel) is dropped, and so is anything not
    joined to the figure's largest piece (bits of the neighbouring pattern). With agree=0 and
    strict=True every turn and mirror counts and a tie drops the cell: full eightfold symmetry."""
    m = trim(m.astype(bool))
    s = max(m.shape) + 2
    sq = np.zeros((s, s), bool)
    y, x = (s - m.shape[0]) // 2, (s - m.shape[1]) // 2
    sq[y:y + m.shape[0], x:x + m.shape[1]] = m
    copies = []
    for v in views(sq):
        best, bv = 0, None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                w = np.roll(np.roll(v, dy, 0), dx, 1)
                o = iou(w, sq)
                if o > best:
                    best, bv = o, w
        if best >= agree:
            copies.append(bv)
    vote = np.mean(copies, 0)
    # strict: a tie drops the cell (for a figure known to be fully symmetric, like a rosette)
    out = (vote > 0.5) | ((vote == 0.5) & sq & (not strict))
    nb = ndimage.convolve(out.astype(int), np.ones((3, 3), int), mode="constant") - out
    out &= nb > 0
    # only the figure itself: the largest joined piece (cells touching at a corner count)
    lab, k = ndimage.label(out, np.ones((3, 3)))
    if k > 1:
        sizes = ndimage.sum(out, lab, range(1, k + 1))
        out = lab == 1 + int(np.argmax(sizes))
    return trim(out)


class Consensus:
    """All places of one sub-motif, lined up, voted into one figure."""

    def __init__(self, ref, places):
        self.al = Aligner(ref)
        self.places = places                     # (chart, row, col, cut-out)
        self.stack = [self.al.align(c) for _, _, _, c in places]
        self.vote()

    def vote(self, keep=None):
        keep = keep if keep is not None else [True] * len(self.places)
        per_chart = defaultdict(list)
        for (chart, *_), s, k in zip(self.places, self.stack, keep):
            if k:
                per_chart[chart].append(s)
        # each chart counts once: its share of filled copies per cell
        self.share = np.mean([np.mean(v, 0) for v in per_chart.values()], 0)
        self.charts = len(per_chart)
        self.cells = self.share >= VOTE
        self.fit = [iou(s, self.cells) for s in self.stack]
        return self

    def settle(self):
        """Vote, drop the stretches, vote again with the places that fit."""
        keep = [f >= STRETCH for f in self.fit]
        if sum(keep) >= 2:
            self.vote(keep)
        self.keep = [f >= STRETCH for f in self.fit]
        return self

    def picture(self):
        """The consensus in HÍ blue; cells that only some charts fill (a quarter or more) in a
        pale tint of it, so the usual variations show without blurring the figure."""
        sh = self.share
        ys, xs = np.nonzero(sh >= 0.25)
        sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
        rgb = np.full(sh[sl].shape + (3,), 255, np.uint8)
        rgb[sh[sl] >= 0.25] = PALE
        rgb[self.cells[sl]] = HI_BLUE
        return rgb


class SizeKinds:
    """Consensus figures compared regardless of size: each is scaled (keeping its
    proportions) onto a KIND_SIDE square, and two figures overlap if their scaled grey
    pictures do (sum of minima over sum of maxima, best turn and mirror)."""

    @staticmethod
    def scaled(m):
        m = trim(m).astype(float)
        s = max(m.shape)
        sq = np.zeros((s, s))
        y, x = (s - m.shape[0]) // 2, (s - m.shape[1]) // 2
        sq[y:y + m.shape[0], x:x + m.shape[1]] = m
        img = Image.fromarray((sq * 255).astype(np.uint8)).resize((KIND_SIDE, KIND_SIDE), Image.BOX)
        return np.asarray(img, float) / 255

    def __init__(self, figures):
        self.ids = list(figures)
        self.n = {k: int(figures[k].sum()) for k in self.ids}
        self.pics = {k: views(self.scaled(figures[k])) for k in self.ids}

    def overlap(self, a, b):
        A = self.pics[a][0]
        return max(np.minimum(A, B).sum() / np.maximum(A, B).sum() for B in self.pics[b])

    def cluster(self):
        n = len(self.ids)
        d = np.ones((n, n))
        np.fill_diagonal(d, 0)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = self.ids[i], self.ids[j]
                if max(self.n[a], self.n[b]) <= KIND_RATIO * min(self.n[a], self.n[b]):
                    d[i, j] = d[j, i] = 1 - self.overlap(a, b)
        z = linkage(squareform(d, checks=False), "average")
        lab = fcluster(z, t=1 - KIND_MATCH, criterion="distance")
        return dict(zip(self.ids, lab))


class Variants:
    def __init__(self, txt, min_charts=2):
        self.units = S.Corpus(txt, S.PILOT_KINDS + S.BAND_KINDS).units
        self.byid = {u.id: u for u in self.units}
        self.motifs = {m["submotif"]: m for m in S.read_csv(OUT / "motifs.csv")}
        self.pieces = defaultdict(list)
        for p in S.read_csv(OUT / "pieces.csv"):
            self.pieces[p["submotif"]].append(p)
        self.keep = [m for m, r in self.motifs.items()
                     if int(r["charts"]) >= min_charts and r["generic"] == "0"]

    def cut(self, chart, y, x, h, w):
        return np.asarray(self.byid[chart].cells)[y:y + h, x:x + w].astype(bool)

    def places(self, m, ff):
        """Every place of sub-motif m: its pieces, and the joined hits of its first telling piece."""
        out, seen = [], set()
        ref = None
        for p in self.pieces[m]:
            y, x, h, w = (int(p[k]) for k in ("row", "col", "height", "width"))
            c = self.cut(p["chart"], y, x, h, w)
            if ref is None or (SubMotifs.telling(c) and not SubMotifs.telling(ref)):
                ref = c
            seen.add((p["chart"], y, x))
            out.append((p["chart"], y, x, c))
        if int(self.motifs[m]["cells"]) >= 30 and SubMotifs.telling(ref):
            for o, y, x, h, w in ff.find(ref, where=True):
                chart = self.units[o].id
                if not any(c == chart and abs(y - yy) <= SHIFT and abs(x - xx) <= SHIFT for c, yy, xx in seen):
                    seen.add((chart, y, x))
                    out.append((chart, y, x, self.cut(chart, y, x, h, w)))
        return ref, out

    def run(self):
        ff = FigureFinder(self.units)
        self.result = {}
        for k, m in enumerate(self.keep):
            ref, pl = self.places(m, ff)
            self.result[m] = Consensus(ref, pl).settle()
            if k % 50 == 0:
                print(f"{k}/{len(self.keep)}", flush=True)
        figs = {m: c.cells for m, c in self.result.items()
                if c.cells.sum() >= KIND_CELLS and SubMotifs.telling(trim(c.cells))
                and solidity(c.cells) <= KIND_SOLID}
        self.kind = SizeKinds(figs).cluster()
        return self

    def write(self):
        (OUT / "consensus").mkdir(exist_ok=True)
        with open(OUT / "consensus.csv", "w", newline="") as f, open(OUT / "places.csv", "w", newline="") as g:
            w = csv.writer(f)
            w.writerow(["submotif", "cells", "places", "charts", "fit", "doubtful", "kind"])
            v = csv.writer(g)
            v.writerow(["submotif", "chart", "row", "col", "height", "width", "fit", "kept"])
            for m, c in self.result.items():
                fit = float(np.median([f for f, k in zip(c.fit, c.keep) if k] or c.fit))
                w.writerow([m, int(c.cells.sum()), sum(c.keep), c.charts, f"{fit:.2f}",
                            int(fit < DOUBTFUL), self.kind.get(m, "")])
                for (chart, y, x, cut), fi, k in zip(c.places, c.fit, c.keep):
                    v.writerow([m, chart, y, x, *cut.shape, f"{fi:.2f}", int(k)])
                Image.fromarray(c.picture()).save(OUT / "consensus" / f"{m}.png")
                np.savetxt(OUT / "consensus" / f"{m}.txt", trim(c.cells).astype(int), fmt="%d", delimiter="")
        sizes = defaultdict(list)
        for m, k in self.kind.items():
            sizes[k].append(m)
        with open(OUT / "kinds.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["kind", "submotifs", "smallest", "largest", "charts"])
            for k, ms in sorted(sizes.items()):
                cells = [int(self.result[m].cells.sum()) for m in ms]
                charts = len({p for m in ms for p, *_ in
                              (pl for pl, kk in zip(self.result[m].places, self.result[m].keep) if kk)})
                w.writerow([k, "|".join(ms), min(cells), max(cells), charts])
        multi = sum(1 for ms in sizes.values() if len(ms) > 1)
        print(f"{len(self.result)} sub-motifs; {sum(1 for c in self.result.values() if np.median(c.fit) < DOUBTFUL)} doubtful; "
              f"{len(sizes)} kinds, {multi} with more than one size -> {OUT}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--txt", default="../../patterns/txt")
    ap.add_argument("--min-charts", type=int, default=2)
    a = ap.parse_args()
    Variants(a.txt, a.min_charts).run().write()


if __name__ == "__main__":
    main()
