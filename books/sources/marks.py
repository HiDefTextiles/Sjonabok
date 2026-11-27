"""Named kinds of mark in a ruled cell.

Pattern books do not only print filled and empty cells. Sibmacher's plates
mix solid cells, small crosses (+), vertical hatching (|), diagonal strokes
(/ and \\, which together draw a large X over a block of cells), and half
cells cut along a diagonal. Each cell gets one character:

    .  empty                 #  solid
    +  plus (cross on the cell's axes)
    x  diagonal cross (X) or cross-hatching
    |  vertical hatching     -  horizontal hatching
    /  diagonal, bottom-left to top-right
    \\  diagonal, top-left to bottom-right
    < > ^ v  wedge: two diagonals meeting at the middle of one side (an
             "arrow"; the arms of a large X drawn over several cells)
    F 7 L J  half cell: the ink fills the triangle in that corner
             (F top-left, 7 top-right, L bottom-left, J bottom-right)
    ?  marked, but none of the above

The classifier works on the cell's interior (ruling cut off), with ink
0..1, and compares where the ink lies; thresholds are relative to the
cell's own ink so faint and heavy impressions read alike. MARKS maps
every kind to its 0/1 value; FILLED is the default set that counts as 1.
"""
import numpy as np

KINDS = ".#+x|-/\\<>^vF7LJ?"
NAMES = {".": "empty", "#": "solid", "+": "plus", "x": "diagonal cross", "|": "vertical hatching",
         "-": "horizontal hatching", "/": "diagonal /", "\\": "diagonal \\",
         "F": "half cell, top-left", "7": "half cell, top-right", "L": "half cell, bottom-left",
         "J": "half cell, bottom-right", "<": "wedge, point left", ">": "wedge, point right",
         "^": "wedge, point up", "v": "wedge, point down", "?": "other mark"}
FILLED = set(KINDS) - {"."}


class MarkClassifier:
    """classify(cell) -> one character of KINDS for a cell interior (ink 0..1).

    empty: mean ink below `empty`; solid: mean ink above `solid`.
    Otherwise the ink is compared over masks of the unit square
    (u, v in -0.5..0.5, v downwards): the two diagonals, the two axes,
    the four corner triangles, and stripes (column and row profiles).
    """

    def __init__(self, empty=0.06, solid=0.75, band=0.17, contrast=1.35):
        self.empty, self.solid, self.band, self.contrast = empty, solid, band, contrast
        self._masks = {}

    def masks(self, h, w):
        if (h, w) not in self._masks:
            yy, xx = np.mgrid[0:h, 0:w]
            u, v = (xx + 0.5) / w - 0.5, (yy + 0.5) / h - 0.5
            b = self.band
            self._masks[h, w] = dict(
                back=np.abs(u - v) < b,          # "\" top-left to bottom-right
                fwd=np.abs(u + v) < b,           # "/" bottom-left to top-right
                vert=np.abs(u) < b, horz=np.abs(v) < b,
                tl=u + v < -b, br=u + v > b,     # corner triangles beyond the "/" band
                tr=u - v > b, bl=u - v < -b)     # corner triangles beyond the "\" band
            # wedges: both corners of one side joined to the middle of the opposite side
            m = self._masks[h, w]

            def seg(p, q):
                return _segment_distance(u, v, p, q) < b * 0.8
            for k, tip, ends in ((">", (.5, 0), ((-.5, -.5), (-.5, .5))), ("<", (-.5, 0), ((.5, -.5), (.5, .5))),
                                 ("v", (0, .5), ((-.5, -.5), (.5, -.5))), ("^", (0, -.5), ((-.5, .5), (.5, .5)))):
                m[k + "1"], m[k + "2"] = seg(ends[0], tip), seg(ends[1], tip)
                m[k] = m[k + "1"] | m[k + "2"]
        return self._masks[h, w]

    def features(self, cell):
        h, w = cell.shape
        m = self.masks(h, w)
        f = {k: float(cell[v].mean()) if v.any() else 0.0 for k, v in m.items()}
        f.update({"off_" + k: float(cell[~m[k]].mean()) for k in "<>^v"})
        f["mean"] = float(cell.mean())
        core = cell[1:-1, 1:-1] if min(cell.shape) > 4 else cell   # a leftover rule sits on the edge
        f["core"] = float(core.mean())
        f.update(self.arms(cell))
        cols, rows = cell.mean(axis=0), cell.mean(axis=1)
        # stripes: many alternations along one axis, flat along the other
        f["vstripe"] = float(np.abs(np.diff(cols)).sum() / max(len(cols) - 1, 1))
        f["hstripe"] = float(np.abs(np.diff(rows)).sum() / max(len(rows) - 1, 1))
        f["vstrokes"], f["hstrokes"] = self.strokes(cols), self.strokes(rows)
        return f

    @staticmethod
    def strokes(profile, level=0.15):
        """Dark peaks in a profile away from its two ends (a ruling line left
        at the edge of a cut is not a stroke)."""
        p = profile
        return int(sum(1 for i in range(1, len(p) - 1)
                       if p[i] > level and p[i] >= p[i - 1] and p[i] >= p[i + 1]))

    @staticmethod
    def arms(cell, middle=0.6):
        """The darkest column and row within the middle part of the cell, as
        3-px bands: their ink, and the ink of the rest of the cell."""
        h, w = cell.shape

        def band(profile, n):
            lo = int(round(n * (1 - middle) / 2))
            hi = max(lo + 1, n - lo)
            k = lo + int(np.argmax(profile[lo:hi]))
            return max(0, k - 1), min(n, k + 2)
        c0, c1 = band(cell.mean(axis=0), w)
        r0, r1 = band(cell.mean(axis=1), h)
        rest = np.ones_like(cell, bool)
        rest[:, c0:c1] = False
        rest[r0:r1, :] = False
        return dict(arm_v=float(cell[:, c0:c1].mean()), arm_h=float(cell[r0:r1, :].mean()),
                    arm_off=float(cell[rest].mean()) if rest.any() else 0.0)

    def classify(self, cell):
        if cell.size < 9:
            return "?"
        f = self.features(cell)
        if f["core"] < self.empty:
            return "."
        if f["mean"] > self.solid:
            return "#"
        eps = 0.03
        # hatching: many strokes across one axis, flat along the other
        if f["vstripe"] > 2 * f["hstripe"] + eps and f["vstrokes"] >= 2:
            return "|"
        if f["hstripe"] > 2 * f["vstripe"] + eps and f["hstrokes"] >= 2:
            return "-"
        # half cell: one corner triangle inked, the opposite one clean
        tri = {"F": ("tl", "br"), "7": ("tr", "bl"), "L": ("bl", "tr"), "J": ("br", "tl")}
        k = max(tri, key=lambda t: f[tri[t][0]] - f[tri[t][1]])
        if f[tri[k][0]] > 0.5 and f[tri[k][1]] < 0.15:
            return k
        # plus: a dark column and a dark row crossing in the middle part of
        # the cell (found where they are, as the cross is often off centre),
        # both darker than the rest of the cell
        if min(f["arm_v"], f["arm_h"]) > 0.25 and min(f["arm_v"], f["arm_h"]) > self.contrast * (f["arm_off"] + eps):
            return "+"
        # wedges before single diagonals: a wedge's arms are diagonals too
        k = max("<>^v", key=lambda t: f[t] - f["off_" + t])
        if min(f[k + "1"], f[k + "2"]) > 1.8 * self.contrast * (f["off_" + k] + eps):
            return k
        # diagonal strokes: on a diagonal, darker than the corners beside it
        b = f["back"] > self.contrast * (f["tr"] + f["bl"]) / 2 + eps
        w = f["fwd"] > self.contrast * (f["tl"] + f["br"]) / 2 + eps
        if b and w:
            return "x"
        if b:
            return "\\"
        if w:
            return "/"
        return "?"


def _segment_distance(u, v, p, q):
    """Distance of every (u, v) to the segment p-q."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((u - x0) * dx + (v - y0) * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(u - (x0 + t * dx), v - (y0 + t * dy))


def cell_interiors(ink, xs, ys, search=None, gap=2, span=2):
    """Cut each cell out between its own ruling lines.

    The fitted lines xs, ys can be a pixel or two off (paper stretch), and
    a cell cut with ruling inside it looks like a plus or a hatch. So each
    rule is found again near every cell: the darkest column (row) within
    `search` px of the fitted one (default 0.4 pitch: Sibmacher's ruling
    drifts by up to a third of a cell from the fitted comb), measured over a strip `span` cells to
    either side, where the long ruling outweighs any mark. A cell whose
    rules come out more than 2 px off its pitch keeps the fitted ones.
    The interior starts `gap` px inside the rules. Returns {(row, col): interior}."""
    H, W = ink.shape
    nr, nc = len(ys) - 1, len(xs) - 1
    if nr < 1 or nc < 1:
        return {}
    if search is None:
        search = max(3, int(round(0.4 * np.median(np.diff(xs)))))

    def snap(lines, other, k, axis):
        """position of line k near cell `other` along the other axis"""
        o = [lines_o[max(0, other - span)], lines_o[min(len(lines_o) - 1, other + span + 1)]]
        x = lines[k]
        lo, hi = max(0, x - search), min(W if axis == 0 else H, x + search + 1)
        strip = ink[o[0]:o[1], lo:hi] if axis == 0 else ink[lo:hi, o[0]:o[1]].T
        return lo + int(np.argmax(strip.mean(axis=0))) if strip.size else x

    lines_o = ys
    X = [[snap(xs, r, c, 0) for c in range(nc + 1)] for r in range(nr)]
    lines_o = xs
    Y = [[snap(ys, c, r, 1) for r in range(nr + 1)] for c in range(nc)]
    out = {}
    for r in range(nr):
        for c in range(nc):
            l, rr, a, b = X[r][c], X[r][c + 1], Y[c][r], Y[c][r + 1]
            if abs((rr - l) - (xs[c + 1] - xs[c])) > 2:
                l, rr = xs[c], xs[c + 1]
            if abs((b - a) - (ys[r + 1] - ys[r])) > 2:
                a, b = ys[r], ys[r + 1]
            out[r, c] = trim_rules(ink[a + gap:b - gap + 1, l + gap:rr - gap + 1])
    return out


def trim_rules(cell, dark=0.45, most=2):
    """Drop up to `most` edge rows/columns on each side that are a ruling
    line (dark along their whole length), not part of the mark."""
    for _ in range(most):
        if cell.shape[0] > 4 and cell[0].mean() > dark:
            cell = cell[1:]
        if cell.shape[0] > 4 and cell[-1].mean() > dark:
            cell = cell[:-1]
        if cell.shape[1] > 4 and cell[:, 0].mean() > dark:
            cell = cell[:, 1:]
        if cell.shape[1] > 4 and cell[:, -1].mean() > dark:
            cell = cell[:, :-1]
    return cell
