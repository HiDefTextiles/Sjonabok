"""Read Sjónabók EPS charts whose cells carry different kinds of mark.

Most charts in the book have one mark (a filled cell) and are read by
eps_to_pattern.py, which turns every dark pixel into 1. Some 43 charts mix
marks: a filled diamond, a cross, a circled cross, a round dot, a half cell. In the
manuscripts these are different colours (or stitches), so a 0/1 reading
merges them. This module keeps them apart.

    chart = MarkedEpsChart.from_eps("thjmsth_116_612.eps")
    chart.kinds      # one character per cell: . empty, D diamond, x cross, ...
    chart.digits     # one digit per cell, the colour index (see KINDS)

Every cell is cut between its own grid lines (the grey ruling of the book's
chart paper) and named by MarkClassifier from the shape of its ink. Pages
printed turned 45 degrees (the chart drawn on the diagonal) are turned
back first. convert_marks.py runs it over a folder of EPS files.

The output format is the one used for printed books in books/sources
(<chart>.txt holds one digit per colour, indices into the gallery's HI
palette; <chart>.marks.txt keeps the named kind of every cell). A chart
with one kind of mark comes out as plain 0/1, the same as
eps_to_pattern.py.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

GRID_GREY = np.array([128, 130, 133])   # ruling colour in the book's EPS files
INK_MAX = 250                           # R+G+B below this is ink (marks are ~(35,31,32))
SAMPLES = 16                            # a mark is resampled to N x N


class MarkKind:
    """One kind of mark: a one-character name, the colour digit it gets in
    <chart>.txt, and a description."""

    def __init__(self, char, digit, name):
        self.char, self.digit, self.name = char, digit, name

    def __repr__(self):
        return f"MarkKind({self.char!r}, {self.digit}, {self.name!r})"


# Characters follow books/sources/marks.py where the mark is the same.
# Digits are colour indices into the gallery's HI palette, one per kind of
# mark seen in these charts. The four half-cell marks share one colour; which
# corner is inked stays in <chart>.marks.txt.
KINDS = [
    MarkKind(".", 0, "empty"),
    MarkKind("D", 1, "filled diamond"),
    MarkKind("#", 1, "solid square"),
    MarkKind("x", 2, "diagonal cross"),
    MarkKind("O", 3, "circled cross"),
    MarkKind("o", 4, "round dot"),
    MarkKind("F", 5, "half cell, top-left triangle inked"),
    MarkKind("7", 5, "half cell, top-right triangle inked"),
    MarkKind("L", 5, "half cell, bottom-left triangle inked"),
    MarkKind("J", 5, "half cell, bottom-right triangle inked"),
    MarkKind("-", 0, "a ruled line across the cell, not a stitch"),
    MarkKind("|", 0, "a ruled line down the cell, not a stitch"),
    MarkKind("?", 1, "a mark none of the above fits"),
]
KIND_BY_CHAR = {k.char: k for k in KINDS}


class MarkClassifier:
    """Names a mark from a few shape measures.

    The mark is cut to its own ink box and resampled to N x N first, so the
    measures do not depend on where the mark sits in its cell or how big it
    is printed (the book's marks are not always centred). Measured on that
    box, from -1 to 1 each way:

    fill      share of the box inked
    corners   ink in each corner block (tl, tr, bl, br)
    side      ink on the middle of each side, away from the centre
    shoulder  ink just outside the inscribed diamond (a disc has it, a diamond not)
    hole      share of the inner disc left white (a circled cross has holes)

    The book prints every mark from the same vector shape, so the kinds are
    far apart on these measures; the limits were read off a k-means of the
    marked cells of all 43 pages. A mark that fits none is '?', to check by
    eye (make marks-review draws a sheet of every kind)."""

    HALF = {0: "F", 1: "7", 2: "L", 3: "J"}

    def __init__(self, n=SAMPLES):
        self.n = n
        g = (np.arange(n) + 0.5) / n * 2 - 1
        v, u = np.meshgrid(g, g, indexing="ij")              # u right, v down
        r, d = np.hypot(u, v), np.abs(u) + np.abs(v)
        b = max(1, round(n * 0.3))
        self.corner_blocks = [(slice(0, b), slice(0, b)), (slice(0, b), slice(n - b, n)),
                              (slice(n - b, n), slice(0, b)), (slice(n - b, n), slice(n - b, n))]
        self.side = ((np.abs(u) < 0.2) & (np.abs(v) > 0.6)) | ((np.abs(v) < 0.2) & (np.abs(u) > 0.6))
        self.shoulder = (d > 1.0) & (d < 1.4) & (r < 0.97)
        self.inner = r < 0.6

    def normalise(self, ink):
        """The mark cut to its ink box and resampled to n x n (None if empty)."""
        rows, cols = self.main_run(ink.sum(axis=1)), self.main_run(ink.sum(axis=0))
        if rows is None or cols is None:
            return None
        box = ink[rows, cols]
        f = (np.arange(self.n) + 0.5) / self.n
        yi = (f * box.shape[0]).astype(int)
        xi = (f * box.shape[1]).astype(int)
        return box[yi[:, None], xi[None, :]]

    @staticmethod
    def main_run(counts, share=0.15, edge=2):
        """The longest run of rows (or columns) with ink. A sliver of the
        next cell's mark is left out: a run cut off by an empty row, and up
        to edge rows at the window's border holding less than share of the
        fullest row's ink."""
        idx = np.flatnonzero(counts)
        if not len(idx):
            return None
        breaks = np.flatnonzero(np.diff(idx) > 1)
        starts, ends = np.r_[idx[0], idx[breaks + 1]], np.r_[idx[breaks], idx[-1]]
        k = int(np.argmax(ends - starts))
        a, b = int(starts[k]), int(ends[k])
        thin = counts < share * counts.max()
        while a < edge and a < b and thin[a]:
            a += 1
        while b > len(counts) - 1 - edge and b > a and thin[b]:
            b -= 1
        return slice(a, b + 1)

    def measures(self, patch):
        return {"fill": float(patch.mean()),
                "corners": [float(patch[c].mean()) for c in self.corner_blocks],
                "side": float(patch[self.side].mean()),
                "shoulder": float(patch[self.shoulder].mean()),
                "hole": float(1 - patch[self.inner].mean())}

    def kind(self, cell_ink, min_ink=0.04):
        """cell_ink: boolean pixels of one cell, between its ruling lines."""
        if cell_ink.mean() < min_ink:
            return "."
        rows, cols = self.main_run(cell_ink.sum(axis=1)), self.main_run(cell_ink.sum(axis=0))
        h = (rows.stop - rows.start) / cell_ink.shape[0]
        w = (cols.stop - cols.start) / cell_ink.shape[1]
        if h < 0.3 and w > 0.6:
            return "-"
        if w < 0.3 and h > 0.6:
            return "|"
        m = self.measures(self.normalise(cell_ink))
        q = m["corners"]
        if m["fill"] > 0.92:
            return "#"
        e = int(np.argmin(q))                                # half cell: one corner empty,
        if q[e] < 0.15 and q[3 - e] > 0.8 and 0.35 < m["fill"] < 0.75:   # the opposite one full
            return self.HALF[3 - e]
        if m["side"] < 0.3 and min(q) > 0.4:
            return "x"
        if m["hole"] > 0.12 and m["side"] > 0.5:
            return "O"
        if m["hole"] < 0.05:
            if m["shoulder"] < 0.7 and max(q) < 0.45:
                return "D"
            if m["shoulder"] > 0.75 and max(q) < 0.7:
                return "o"
        return "?"


class Grid:
    """Positions of the ruling lines along one axis. Lines are found where
    grey covers much of the page; marks may hide a line over a dense chart,
    so the lines are then fitted to an even comb and missing ones filled."""

    def __init__(self, starts, ends):
        self.starts, self.ends = np.asarray(starts), np.asarray(ends)

    @classmethod
    def find(cls, line_mask, axis, cover=0.3):
        frac = line_mask.mean(axis=axis)
        idx = np.where(frac > cover)[0]
        if len(idx) < 3:
            return None
        br = np.where(np.diff(idx) > 1)[0]
        s, e = np.r_[idx[0], idx[br + 1]], np.r_[idx[br], idx[-1]]
        mid = (s + e) / 2
        steps = np.diff(mid)
        pitch = np.median(steps[(steps > 4)]) if (steps > 4).any() else None
        if not pitch:
            return None
        # number the lines step by step (the pitch is not a whole number of
        # pixels, so numbering from the first line drifts); a run that is
        # not a whole number of steps from the last line is not a ruling line
        k = [0]
        keep = [0]
        for i in range(1, len(mid)):
            n = (mid[i] - mid[keep[-1]]) / pitch
            if round(n) >= 1 and abs(n - round(n)) < 0.3:
                k.append(k[-1] + int(round(n)))
                keep.append(i)
        k = np.array(k)
        s, e, mid = s[keep], e[keep], mid[keep]
        half = np.median(e - s) / 2
        full = np.arange(k[0], k[-1] + 1)
        centre = np.interp(full, k, mid)      # a hidden line sits between its neighbours
        have = dict(zip(k, zip(s, e)))
        starts = [have[j][0] if j in have else c - half for j, c in zip(full, centre)]
        ends = [have[j][1] if j in have else c + half for j, c in zip(full, centre)]
        return cls(starts, ends)


@dataclass
class MarkedEpsChart:
    """A chart read from a Sjónabók EPS page, every cell named."""
    name: str
    kinds: np.ndarray                     # characters, one per cell
    meta: dict = field(default_factory=dict)

    @property
    def digits(self):
        """Colour index per cell. A chart with one colour is plain 0/1."""
        lut = {k.char: k.digit for k in KINDS}
        d = np.vectorize(lambda c: lut[c])(self.kinds).astype(np.uint8)
        used = np.unique(d[d > 0])
        return (d > 0).astype(np.uint8) if len(used) == 1 else d

    @property
    def filled(self):
        return (self.kinds != ".").astype(np.uint8)

    # ── reading ───────────────────────────────────────────────────────────
    @classmethod
    def from_eps(cls, path, dpi=288, classifier=None):
        img = Image.open(path)
        img.load(scale=max(1, round(dpi / 72)))
        return cls.from_image(np.asarray(img.convert("RGB")), Path(path).stem, classifier)

    @classmethod
    def from_image(cls, rgb, name, classifier=None):
        classifier = classifier or MarkClassifier()
        rgb = rgb.astype(np.int16)
        turned = 0
        grids = cls.find_grid(rgb)
        if grids is None:                         # page drawn on the diagonal
            rgb = np.asarray(Image.fromarray(rgb.astype(np.uint8)).rotate(
                45, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))).astype(np.int16)
            turned = 45
            grids = cls.find_grid(rgb, grey_tol=120)
            if grids is None:
                raise ValueError(f"{name}: no grid found")
        rows, cols = grids
        ink = rgb.sum(axis=2) < INK_MAX
        kinds = np.array([[classifier.kind(w) for w in row] for row in cls.cell_windows(ink, rows, cols)])
        ys, xs = np.nonzero(kinds != ".")
        if not len(ys):
            raise ValueError(f"{name}: no marks found")
        box = (ys.min(), ys.max() + 1, xs.min(), xs.max() + 1)
        kinds = kinds[box[0]:box[1], box[2]:box[3]]
        counts = {k.char: int((kinds == k.char).sum()) for k in KINDS if k.char != "."}
        meta = {"turned": turned, "grid": [len(rows.starts) - 1, len(cols.starts) - 1],
                "box": [int(v) for v in box], "counts": {k: v for k, v in counts.items() if v}}
        return cls(name, kinds, meta)

    @staticmethod
    def find_grid(rgb, grey_tol=60):
        grey = np.abs(rgb - GRID_GREY).sum(axis=2) < grey_tol
        cols = Grid.find(grey, axis=0)
        rows = Grid.find(grey, axis=1)
        if cols is None or rows is None or len(cols.starts) < 10 or len(rows.starts) < 10:
            return None
        return rows, cols

    @staticmethod
    def cell_windows(ink, rows, cols, pad=1):
        """The ink of every cell, from just inside one ruling line to just
        inside the next (pad pixels short of the line centre each side)."""
        ys = np.c_[(rows.starts[:-1] + rows.ends[:-1]) / 2, (rows.starts[1:] + rows.ends[1:]) / 2]
        xs = np.c_[(cols.starts[:-1] + cols.ends[:-1]) / 2, (cols.starts[1:] + cols.ends[1:]) / 2]
        grid_w = int(np.ceil(np.median(rows.ends - rows.starts) / 2)) + pad
        for y0, y1 in ys.astype(int):
            yield [ink[y0 + grid_w:y1 - grid_w + 1, x0 + grid_w:x1 - grid_w + 1] for x0, x1 in xs.astype(int)]

    # ── parts and writing ─────────────────────────────────────────────────
    def parts(self, gap=5):
        """Split into separate charts where gap or more empty rows (then
        columns) run between them, as split_patterns.py does for 0/1 charts.
        Returns [] when the page holds one chart."""
        from .separate_patterns import separate_patterns_simple
        filled = self.filled
        tag = np.arange(filled.size).reshape(filled.shape) + 1     # cell id, to carry kinds along
        out = []
        for band in separate_patterns_simple(np.where(filled, tag, 0), axis=0, DISTANCE_BETWEEN_PATTERNS=gap):
            for piece in separate_patterns_simple(band, axis=1, DISTANCE_BETWEEN_PATTERNS=gap):
                ids = piece.astype(int)
                kinds = np.where(ids > 0, self.kinds.ravel()[np.maximum(ids - 1, 0)], ".")
                out.append(kinds)
        if len(out) < 2:
            return []
        return [MarkedEpsChart(f"{self.name}_p{i}", k, {"page": self.name}) for i, k in enumerate(out, 1)]

    def save(self, out_dir, marks=True):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        np.savetxt(out / f"{self.name}.txt", self.digits, fmt="%d", delimiter="")
        if marks:
            (out / f"{self.name}.marks.txt").write_text("\n".join("".join(r) for r in self.kinds) + "\n")
        return out / f"{self.name}.txt"
