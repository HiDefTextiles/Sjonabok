"""Smallest pieces (seeds) that rebuild a chart exactly by symmetry.

Many Sjónabók charts are built from a much smaller piece: a band is one
repeat unit drawn over and over, the unit is often a mirror image of its own
half, and a square star is eight copies of one triangle. This module finds,
for every chart, the smallest seed and the list of steps that turn the seed
back into the chart, cell for cell.

A recipe is read from the seed outwards; every step makes a bigger block
from the current one:

    diag n          the seed is a triangle (row i holds cells i..n-1 of an
                    n × n block); mirror it in the main diagonal
    antidiag n      the same with the other diagonal (row i holds 0..n-1-i)
    rot4 n          four quarter-turned copies make an n × n block
    mirror x n      add the mirror image to the right; n = new width
                    (an odd n means the mirror line runs through the middle column)
    mirror y n      the same downwards
    turn x n        add the block turned half a turn to the right
    turn y n        the same downwards
    glide x n       add the block flipped top to bottom to the right (n = 2 × width)
    glide y n       add the block flipped left to right below it
    tile x n r      repeat the block left to right to width n; the chart
                    starts r columns into the block (a band clipped mid-repeat)
    tile y n r      the same top to bottom
    pad t b l r     add empty rows and columns round the edge

Every step is a plain copy, so the same steps also carry a mask of cells
from the seed to the chart (used to show where a near symmetry breaks).

Near symmetries: a step that almost holds (a few cells differ) is never
forced. It is reported with the cells that break it, and the chart keeps
the larger exact seed.
"""

from dataclasses import dataclass, field

import numpy as np

NEAR_SHARE = 0.02      # a near symmetry: at most this share of the block's cells differ ...
NEAR_INK = 0.10        # ... and at most this share of its filled cells
NEAR_PERIOD = 0.97     # a near repeat: shifted copies agree on this share of cells


# ── steps ────────────────────────────────────────────────────────────────────

class Step:
    """One way of making a block from a smaller one.

    reduce(block) gives the smaller block when the symmetry holds exactly,
    or None. expand(small) builds the block back. near(block) gives a mask
    of the cells that break the symmetry, or None if it holds or the block
    has the wrong shape for it.
    """

    name = ""
    ragged = False          # the seed is a triangle (list of rows), so nothing else can follow

    def args(self):
        return []

    def __str__(self):
        return " ".join([self.name, *map(str, self.args())])

    def reduce(self, b):
        raise NotImplementedError

    def expand(self, s):
        raise NotImplementedError

    def near(self, b):
        return None

    @staticmethod
    def exact(step, b):
        """The reduced block if expanding it gives b back exactly."""
        s = step.cut(b)
        if s is None:
            return None
        e = step.expand(s)
        return s if np.array_equal(e, b) else None


class Mirror(Step):
    """A mirror line across the block (axis x: the right half mirrors the left)."""

    name = "mirror"

    def __init__(self, axis, n, ring=False):
        # ring: the block is one period of a repeat and both of its end lines
        # lie on mirror lines (an even period with mirror lines through cells),
        # so the seed is n/2 + 1 wide and both end lines are shared
        self.axis, self.n, self.ring = axis, n, ring

    def args(self):
        return [self.axis, self.n]

    @property
    def dim(self):
        return 1 if self.axis == "x" else 0

    def cut(self, b):
        n = b.shape[self.dim]
        if n < 2:
            return None
        k = n // 2 + 1 if self.ring else (n + 1) // 2
        return b[:, :k] if self.dim else b[:k, :]

    def flip(self, s):
        return np.flip(s, axis=self.dim)

    def expand(self, s):
        k = s.shape[self.dim]
        shared = 2 * k - self.n          # 0, 1, or 2 (both end lines shared)
        f = self.flip(s)
        keep = slice(1, -1) if shared == 2 else slice(shared, None)
        f = f[:, keep] if self.dim else f[keep, :]
        return np.concatenate([s, f], axis=self.dim)

    def reduce(self, b):
        return self.exact(self, b)

    def near(self, b):
        if b.shape[self.dim] < 2:
            return None
        return b != self.flip(b)


class Turn(Mirror):
    """A half-turn about the block's centre; keeps the first half along axis."""

    name = "turn"

    def flip(self, s):
        return s[::-1, ::-1]


class Glide(Mirror):
    """The second half is the first flipped across the other axis."""

    name = "glide"

    def cut(self, b):
        n = b.shape[self.dim]
        if n < 2 or n % 2:
            return None
        k = n // 2
        return b[:, :k] if self.dim else b[:k, :]

    def flip(self, s):
        return np.flip(s, axis=1 - self.dim)

    def expand(self, s):
        return np.concatenate([s, self.flip(s)], axis=self.dim)

    def near(self, b):
        s = self.cut(b)
        if s is None:
            return None
        other = b[:, s.shape[1]:] if self.dim else b[s.shape[0]:, :]
        half = self.flip(s) != other          # on the second half; its partner is flipped back
        return np.concatenate([self.flip(half), half], axis=self.dim)


class Rot4(Step):
    """Four quarter-turned copies of the top-left quarter (pinwheel)."""

    name = "rot4"

    def __init__(self, n):
        self.n = n

    def args(self):
        return [self.n]

    def cut(self, b):
        n = b.shape[0]
        if n != b.shape[1] or n < 2:
            return None
        c = (n + 1) // 2
        return b[:c, :c]

    def expand(self, s):
        c = s.shape[0]
        b = np.zeros((self.n, self.n), dtype=s.dtype)
        for _ in range(4):
            b[:c, :c] = s
            b = np.rot90(b)
        return b

    def reduce(self, b):
        return self.exact(self, b)

    def near(self, b):
        if b.shape[0] != b.shape[1] or b.shape[0] < 2:
            return None
        return b != np.rot90(b)


class Diag(Step):
    """Mirror in the main diagonal; the seed is the upper triangle."""

    name = "diag"
    ragged = True

    def __init__(self, n):
        self.n = n

    def args(self):
        return [self.n]

    def flip(self, b):
        return b.T

    def cut(self, b):
        n = b.shape[0]
        if n != b.shape[1] or n < 2:
            return None
        return [b[i, i:].copy() for i in range(n)]

    def expand(self, s):
        n = self.n
        b = np.zeros((n, n), dtype=s[0].dtype)
        for i, row in enumerate(s):
            b[i, i:] = row
            b[i:, i] = row
        return b

    def reduce(self, b):
        return self.exact(self, b)

    def near(self, b):
        if b.shape[0] != b.shape[1] or b.shape[0] < 2:
            return None
        return b != self.flip(b)


class AntiDiag(Diag):
    """Mirror in the other diagonal; row i of the seed holds cells 0..n-1-i."""

    name = "antidiag"

    def flip(self, b):
        return b[::-1, ::-1].T

    def cut(self, b):
        n = b.shape[0]
        if n != b.shape[1] or n < 2:
            return None
        return [b[i, :n - i].copy() for i in range(n)]

    def expand(self, s):
        n = self.n
        b = np.zeros((n, n), dtype=s[0].dtype)
        for i, row in enumerate(s):
            b[i, :n - i] = row
        return np.where(np.triu(np.ones((n, n), bool)[:, ::-1]), b, self.flip(b))


class Tile(Step):
    """The block repeated along axis to length n, starting r cells into it."""

    name = "tile"

    def __init__(self, axis, n, r=0):
        self.axis, self.n, self.r = axis, n, r

    def args(self):
        return [self.axis, self.n, self.r]

    @property
    def dim(self):
        return 1 if self.axis == "x" else 0

    def expand(self, s):
        p = s.shape[self.dim]
        idx = (np.arange(self.n) + self.r) % p
        return s[:, idx] if self.dim else s[idx, :]

    @staticmethod
    def periods(b, dim):
        """Exact repeats along dim, smallest first. A chart counts as repeated
        when it holds two full copies, or when the last copy is cut only where
        it is empty (motifs drawn side by side with a gap between them)."""
        h = b if dim else b.T
        n = h.shape[1]
        for p in range(1, n):
            if not np.array_equal(h[:, p:], h[:, :-p]):
                continue
            if 2 * p <= n or not h[:, n - p:p].any():
                yield p

    @staticmethod
    def near_period(b, dim):
        """(period, mask of cells that differ from the majority repeat) for a
        band that almost repeats, or None."""
        h = b if dim else b.T
        n = h.shape[1]
        for p in range(2, n // 2 + 1):
            if np.mean(h[:, p:] == h[:, :-p]) >= NEAR_PERIOD:
                cols = np.arange(n) % p
                unit = np.stack([h[:, cols == k].mean(axis=1) for k in range(p)], axis=1) > 0.5
                mask = unit[:, cols] != h.astype(bool)
                return p, (mask if dim else mask.T)
        return None


class Pad(Step):
    """Empty margins round the block."""

    name = "pad"

    def __init__(self, t, b, l, r):
        self.t, self.b, self.l, self.r = t, b, l, r

    def args(self):
        return [self.t, self.b, self.l, self.r]

    def expand(self, s):
        return np.pad(s, ((self.t, self.b), (self.l, self.r)))

    @classmethod
    def trim(cls, m):
        ys, xs = np.nonzero(m)
        if not len(ys):
            return cls(0, 0, 0, 0), m
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        pad = cls(int(y0), int(m.shape[0] - y1), int(x0), int(m.shape[1] - x1))
        return pad, m[y0:y1, x0:x1]


STEPS = {"mirror": Mirror, "turn": Turn, "glide": Glide, "rot4": Rot4,
         "diag": Diag, "antidiag": AntiDiag, "tile": Tile, "pad": Pad}


def parse_step(text):
    name, *args = text.split()
    args = [a if a in ("x", "y") else int(a) for a in args]
    return STEPS[name](*args)


# ── seeds and recipes ────────────────────────────────────────────────────────

def cells(s):
    return sum(len(r) for r in s) if isinstance(s, list) else int(s.size)


def seed_to_text(s):
    rows = s if isinstance(s, list) else list(s)
    return "/".join("".join(str(int(c)) for c in r) for r in rows)


def seed_from_text(text, ragged):
    rows = [np.array([int(c) for c in r], dtype=np.uint8) for r in text.split("/")]
    return rows if ragged else np.array(rows, dtype=np.uint8)


@dataclass
class Recipe:
    """A seed and the steps (seed outwards) that rebuild the chart."""

    seed: object                       # 2-D array, or a list of rows for a triangle
    steps: list = field(default_factory=list)

    def build(self, upto=None):
        b = self.seed
        for step in self.steps[:upto]:
            b = step.expand(b)
        return b

    def carry(self, mask, level):
        """Carry a mask on the block made after `level` steps out to the chart."""
        m = mask.astype(np.uint8)
        for step in self.steps[level:]:
            m = step.expand(m)
        return m.astype(bool)

    def text(self):
        return "; ".join(map(str, self.steps))

    @classmethod
    def parse(cls, seed_text, recipe_text):
        steps = [parse_step(t) for t in recipe_text.split(";") if t.strip()]
        ragged = bool(steps) and steps[0].ragged
        return cls(seed_from_text(seed_text, ragged), steps)

    @property
    def cells(self):
        return cells(self.seed)


class SeedFinder:
    """Searches the steps for the smallest exact seed of a trimmed block.

    Mirrors, turns and glides each halve the block; a triangle (diagonal
    mirror) ends the search. A repeat cuts the block to one period, and
    because a period is cyclic every starting point of it is tried, so a
    mirror line anywhere in the repeat can be found. Ties go to the shorter
    recipe, then to the order the steps are tried in.
    """

    def __init__(self, tile_axes=("x", "y")):
        self.tile_axes = tile_axes
        self.memo = {}

    def find(self, b, cyclic=(), depth=0):
        """(cells, steps seed-outwards, seed) for block b."""
        key = (b.shape, b.tobytes(), cyclic)
        if key in self.memo:
            return self.memo[key]
        best = (cells(b), [], b)
        for step, s, sub_cyclic in self.candidates(b, cyclic):
            if step.ragged:
                cand = (cells(s), [step], s)
            else:
                c, steps, seed = self.find(s, sub_cyclic, depth + 1)
                cand = (c, steps + [step], seed)
            if (cand[0], len(cand[1])) < (best[0], len(best[1])):
                best = cand
        self.memo[key] = best
        return best

    def candidates(self, b, cyclic):
        h, w = b.shape
        for axis in self.tile_axes:
            dim = 1 if axis == "x" else 0
            if axis in cyclic:
                continue
            for p in Tile.periods(b, dim):
                s = b[:, :p] if dim else b[:p, :]
                for r in range(p):
                    # s rolled so that the chart starts r cells into it
                    sr = np.roll(s, r, axis=dim)
                    step = Tile(axis, b.shape[dim], r)
                    if np.array_equal(step.expand(sr), b):
                        yield step, sr, tuple(sorted(set(cyclic) | {axis}))
                break          # the smallest period is enough
        for cls in (Mirror, Turn, Glide):
            for axis, n in (("x", w), ("y", h)):
                steps = [cls(axis, n)]
                if cls is not Glide and axis in cyclic and n % 2 == 0 and n >= 4:
                    steps.append(cls(axis, n, ring=True))
                for step in steps:
                    s = step.reduce(b)
                    if s is not None:
                        # a halved block is no longer a full period along that axis
                        yield step, s, tuple(a for a in cyclic if a != axis)
        if h == w:
            for cls in (Rot4, Diag, AntiDiag):
                step = cls(h)
                s = step.reduce(b)
                if s is not None:
                    yield step, s, ()

    def recipe(self, chart):
        pad, t = Pad.trim(chart)
        c, steps, seed = self.find(t)
        steps = list(steps)
        if any(pad.args()):
            steps.append(pad)
        return Recipe(seed, steps)


# ── near symmetries ──────────────────────────────────────────────────────────

def _ring(fn, dim):
    """The same check on a cyclic period whose end lines lie on the mirror
    line or turn centre (compare with the flipped block moved one cell)."""
    return lambda b: b != np.roll(fn(b), 1, axis=dim)


def near_checks(shape, cyclic_axis=None):
    """(name, function giving the mask of cells that break it) for a block."""
    h, w = shape
    checks = [("mirror x", lambda b: b != b[:, ::-1]), ("mirror y", lambda b: b != b[::-1, :]),
              ("turn", lambda b: b != b[::-1, ::-1])]
    if w % 2 == 0:
        checks.append(("glide x", Glide("x", w).near))
    if h % 2 == 0:
        checks.append(("glide y", Glide("y", h).near))
    if h == w:
        checks += [("rot4", lambda b: b != np.rot90(b)), ("diag", lambda b: b != b.T),
                   ("antidiag", lambda b: b != b[::-1, ::-1].T)]
    if cyclic_axis:
        dim = 1 if cyclic_axis == "x" else 0
        checks += [(f"mirror {cyclic_axis}", _ring(lambda b: np.flip(b, axis=dim), dim)),
                   ("turn", _ring(lambda b: b[::-1, ::-1], dim))]
    return checks


def is_near(mask, block):
    bad = int(mask.sum())
    ink = int(np.count_nonzero(block))
    return 0 < bad <= NEAR_SHARE * block.size and bad <= NEAR_INK * max(ink, 1)


def near_symmetries(recipe, band_axis=None):
    """Symmetries that almost hold on the blocks of a recipe.

    Every block on the way from the seed to the trimmed chart is checked
    (for a repeating band every starting point of the period, as for exact
    mirrors). A check that holds exactly anywhere is skipped: the recipe
    already uses it or it adds nothing. The same broken cells found by
    several checks or on several blocks are reported once.
    Returns dicts: checks, cells (chart cells that break it), block, mask
    (those chart cells).
    """
    found = {}
    levels = [i for i, s in enumerate(recipe.steps) if not isinstance(s, Pad)]
    tile_levels = [i for i in levels if isinstance(recipe.steps[i], Tile)]
    top = len(levels)
    for level in range(top + 1):
        if level == 0 and isinstance(recipe.seed, list):
            continue                  # a triangle has no further symmetry to test
        b = recipe.build(level)
        cyclic_axis = recipe.steps[level].axis if level in tile_levels else None
        dim = 1 if cyclic_axis == "x" else 0
        rolls = range(b.shape[dim]) if cyclic_axis else [0]
        best, exact = {}, set()
        for r in rolls:
            br = np.roll(b, -r, axis=dim) if r else b
            for name, fn in near_checks(br.shape, cyclic_axis):
                m = fn(br)
                if not m.any():
                    exact.add(name)
                elif is_near(m, br) and (name not in best or m.sum() < best[name][0].sum()):
                    best[name] = (np.roll(m, r, axis=dim) if r else m, b)
        for name, (m, blk) in best.items():
            if name in exact:
                continue
            chart_mask = recipe.carry(m, level)
            key = chart_mask.tobytes()
            if key in found:
                if name not in found[key]["checks"]:
                    found[key]["checks"].append(name)
                continue
            found[key] = {"checks": [name], "cells": int(chart_mask.sum()),
                          "block": f"{blk.shape[0]}x{blk.shape[1]}", "mask": chart_mask}
    if band_axis and not tile_levels:
        pad, t = Pad.trim(recipe.build())
        np_ = Tile.near_period(t, 1 if band_axis == "x" else 0)
        if np_ and is_near(np_[1], t):
            mask = np.pad(np_[1], ((pad.t, pad.b), (pad.l, pad.r)))
            found[mask.tobytes()] = {"checks": [f"repeat {np_[0]}"], "cells": int(np_[1].sum()),
                                     "block": f"{t.shape[0]}x{t.shape[1]}", "mask": mask}
    return list(found.values())


# ── symmetry group names ─────────────────────────────────────────────────────

def frieze_group(unit):
    """Exact frieze group of one cyclic repeat unit, laid horizontally."""
    p = unit.shape[1]
    rolls = [np.roll(unit, s, axis=1) for s in range(p)]
    along = np.array_equal(unit, unit[::-1, :])                 # mirror line along the band
    across = any(np.array_equal(unit, r[:, ::-1]) for r in rolls)   # mirror lines across it
    half = any(np.array_equal(unit, r[::-1, ::-1]) for r in rolls)
    glide = p % 2 == 0 and np.array_equal(unit, np.roll(unit[::-1, :], p // 2, axis=1))
    if along:
        return "p2mm" if across else "p11m"
    if glide:
        return "p2mg" if across else "p11g"
    if across:
        return "p1m1"
    return "p2" if half else "p1"


def point_group(t, cyclic=()):
    """Exact point group of a block (D4, C4, D2, C2, D1, C1).

    cyclic: axes along which the block is one period of a repeat; there a
    symmetry may be centred anywhere (the image is compared under every shift).
    """
    ys = range(t.shape[0]) if "y" in cyclic else [0]
    xs = range(t.shape[1]) if "x" in cyclic else [0]

    def holds(img):
        if img.shape != t.shape:
            return False
        return any(np.array_equal(t, np.roll(img, (y, x), axis=(0, 1))) for y in ys for x in xs)

    lr, tb, rot2 = holds(t[:, ::-1]), holds(t[::-1, :]), holds(t[::-1, ::-1])
    rot4 = holds(np.rot90(t))
    diag = holds(t.T) or holds(t[::-1, ::-1].T)
    if rot4:
        return "D4" if lr or diag else "C4"
    if rot2:
        return "D2" if (lr and tb) or diag else "C2"
    return "D1" if lr or tb or diag else "C1"
