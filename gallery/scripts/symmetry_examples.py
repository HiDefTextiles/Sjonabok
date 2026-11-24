#!/usr/bin/env python3
"""Small pictures of each symmetry group for the About page.

One asymmetric shape (a letter F, which has no symmetry of its own) is
copied with the moves of each group: shift, mirror, turn, glide. Every
picture is checked with the gallery's own classifier, so the code under
each picture is the code the gallery would give it.

    python3 gallery/scripts/symmetry_examples.py gallery/img/symmetry
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_gallery import Pattern  # noqa: E402

BLUE, PINK = "#10099F", "#d61f69"

# the letter F: no mirror, no turn
F = np.array([
    [1, 1, 1, 1],
    [1, 0, 0, 0],
    [1, 1, 1, 0],
    [1, 0, 0, 0],
    [1, 0, 0, 0],
], dtype=np.uint8)

lr = lambda a: a[:, ::-1]           # mirror left to right
tb = lambda a: a[::-1, :]           # mirror top to bottom
half = lambda a: a[::-1, ::-1]      # half-turn


class Example:
    """A 0/1 chart plus the guide lines drawn over it (in cell units)."""

    CELL = 8

    def __init__(self, code, matrix, mirrors=(), centres=(), glide=None):
        self.code, self.m = code, matrix
        self.mirrors = mirrors      # ((x0, y0, x1, y1), ...)
        self.centres = centres      # ((x, y), ...) half-turn or quarter-turn centres
        self.glide = glide          # y of the glide line, if any

    def check(self, kind):
        """Classify with the gallery's own code; the result must match."""
        p = Pattern.__new__(Pattern)
        p.unit_row, p.sym, p.period, p.repeat = None, {}, None, None
        p.frieze = p.point = None
        t = Pattern.trimmed(self.m)
        if kind == "band":
            p.measure_band(t)
            got = p.frieze
        else:
            p.measure_motif(t)
            got = p.point
        assert got == self.code, f"{self.code}: classifier says {got}"
        return self

    def svg(self):
        c = self.CELL
        h, w = self.m.shape
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 {w * c + 8} {h * c + 8}" '
               f'width="{w * c + 8}" height="{h * c + 8}" role="img" aria-label="{self.code}">',
               f'<rect x="0" y="0" width="{w * c}" height="{h * c}" fill="#fff" stroke="#ddd"/>']
        ys, xs = np.nonzero(self.m)
        out += [f'<rect x="{x * c}" y="{y * c}" width="{c}" height="{c}" fill="{BLUE}"/>'
                for y, x in zip(ys, xs)]
        for x0, y0, x1, y1 in self.mirrors:
            out.append(f'<line x1="{x0 * c}" y1="{y0 * c}" x2="{x1 * c}" y2="{y1 * c}" '
                       f'stroke="{PINK}" stroke-width="2" stroke-dasharray="5 3"/>')
        if self.glide is not None:
            out.append(f'<line x1="0" y1="{self.glide * c}" x2="{w * c}" y2="{self.glide * c}" '
                       f'stroke="{PINK}" stroke-width="2" stroke-dasharray="1 4" stroke-linecap="round"/>')
        out += [f'<circle cx="{x * c}" cy="{y * c}" r="3.5" fill="{PINK}" stroke="#fff" stroke-width="1"/>'
                for x, y in self.centres]
        out.append("</svg>")
        return "\n".join(out) + "\n"


class Bands:
    """Frieze examples: 4 cells of F plus 1 empty column per slot, two rows
    of slots (upper rows 0-4, lower rows 6-10) with an empty middle row."""

    H, SLOT, SLOTS = 11, 5, 12

    def build(self, code, upper, lower, mirrors=(), centres=(), glide=None):
        m = np.zeros((self.H, self.SLOT * self.SLOTS), dtype=np.uint8)
        for i in range(self.SLOTS):
            x = i * self.SLOT
            if upper[i % len(upper)] is not None:
                m[0:5, x:x + 4] = upper[i % len(upper)]
            if lower[i % len(lower)] is not None:
                m[6:11, x:x + 4] = lower[i % len(lower)]
        return Example(code, m, mirrors, centres, glide).check("band")

    def examples(self):
        n, s, mid = self.SLOTS, self.SLOT, self.H / 2
        W = n * s
        # mirror lines between neighbouring slots: the gap column is the axis
        vlines = lambda step: tuple((x, 0, x, self.H) for x in np.arange(4.5, W - 1, step))
        along = ((0, mid, W, mid),)
        return [
            self.build("p1", [F], [None]),
            self.build("p11g", [F, None], [None, tb(F)], glide=mid),
            self.build("p1m1", [F, lr(F)], [None], mirrors=vlines(s)),
            self.build("p2", [F, None], [None, half(F)],
                       centres=tuple((x, mid) for x in np.arange(4.5, W - 1, s))),
            self.build("p2mg", [F, lr(F), None, None], [None, None, tb(F), half(F)],
                       mirrors=vlines(2 * s), glide=mid,
                       centres=tuple((x, mid) for x in np.arange(9.5, W - 1, 2 * s))),
            self.build("p11m", [F], [tb(F)], mirrors=along),
            self.build("p2mm", [F, lr(F)], [tb(F), half(F)],
                       mirrors=along + vlines(s)),
        ]


class Motifs:
    """Point-group examples on a 13 × 13 square: copies of a small hook
    turned and mirrored about the centre."""

    N = 13

    def __init__(self):
        hook = np.zeros((self.N, self.N), dtype=np.uint8)
        # a small hook in the top-right part, off every axis
        hook[0, 7:12] = 1
        hook[1, 11] = 1
        hook[2, 9:12] = 1
        hook[1:5, 7] = 1
        self.hook = hook

    def build(self, code, moves, mirrors=(), centre=False):
        m = np.zeros_like(self.hook)
        for f in moves:
            m |= f(self.hook)
        c = self.N / 2
        return Example(code, m, mirrors, ((c, c),) if centre else ()).check("motif")

    def examples(self):
        N, c = self.N, self.N / 2
        r = lambda k: (lambda a: np.rot90(a, k))
        ident = lambda a: a
        vert, horiz = (c, 0, c, N), (0, c, N, c)
        diag = ((0, 0, N, N), (0, N, N, 0))
        return [
            self.build("C1", [ident]),
            self.build("D1", [ident, lr], mirrors=(vert,)),
            self.build("C2", [ident, half], centre=True),
            self.build("D2", [ident, lr, tb, half], mirrors=(vert, horiz), centre=True),
            self.build("C4", [r(k) for k in range(4)], centre=True),
            self.build("D4", [r(k) for k in range(4)] + [lambda a, k=k: np.rot90(lr(a), k) for k in range(4)],
                       mirrors=(vert, horiz) + diag, centre=True),
        ]


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for ex in Bands().examples() + Motifs().examples():
        (out / f"{ex.code}.svg").write_text(ex.svg())
        print(f"{ex.code}: ok")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "gallery/img/symmetry")
