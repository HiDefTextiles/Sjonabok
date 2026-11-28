"""Facets: ways to browse the charts, measured from the 0/1 grid alone.

Each facet turns a measure into a few plain words, so it can be a gallery
filter and a way to put like with like (for example as source sets for
pattern synthesis). No labels and no model are used: anyone can recompute
them from the charts, and the thresholds are written here.

    stroke   how thick the drawing is: the median length of the runs of
             filled cells along rows and columns. Thin (under 1.5 cells),
             Double (under 2.5), Bold
    open     how open the figure is: small enclosed openings (2 cells or more)
             per 100 filled cells: under 1 Closed, 5 or more Lacy, otherwise
             Some openings. A chart that runs on across two opposite edges
             (30% or more of both edge rows or columns filled: a tile) or a
             band is counted repeated, 2 x 2 or twice along the
             band, so openings across an edge count; a free-standing figure is
             counted once, because repeating it only adds gaps between copies
    outline  Fills its square (the figure with holes filled covers 82% or
             more of its box), Stands free, or Band
    fit      for knitting on 85 needles: a motif by its width (Up to 20, 21
             to 40, 41 to 60, Over 60 cells), a band by its height across
             (Up to 7, 8 to 12, 13 to 17, Over 17 rows). With a band on both
             edges the motif corridor is 85 minus twice the band height

The thresholds were set by looking at the distribution over all 600 charts
and at examples, then rounded; see the Methods page. Earlier words for line
style (by filled neighbours), outline (round, diamond) and detail were
dropped after a check of random examples showed too many errors. Float
length is not a facet: the gallery already sorts by longest float, and with
a double-bed backing floats do not limit the banner.
"""

import numpy as np

BAND_KINDS = ("border", "edging", "vertical band")

LABELS = {
    "stroke": {"thin": "Thin", "double": "Double", "bold": "Bold"},
    "open": {"closed": "Closed", "some": "Some openings", "lacy": "Lacy"},
    "outline": {"square": "Fills its square", "free": "Stands free", "band": "Band"},
    "fit": {"m20": "Motif up to 20 wide", "m40": "Motif 21–40 wide", "m60": "Motif 41–60 wide",
            "m99": "Motif over 60 wide", "b7": "Band up to 7 rows", "b12": "Band 8–12 rows",
            "b17": "Band 13–17 rows", "b99": "Band over 17 rows"},
}


def components(mask, diagonal=False):
    """Label connected areas of True cells (4- or 8-connected). Returns labels, count."""
    h, w = mask.shape
    lab = np.zeros((h, w), dtype=np.int32)
    steps = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if diagonal:
        steps += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    n = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        stack = [(y0, x0)]
        while stack:
            y, x = stack.pop()
            for dy, dx in steps:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    stack.append((ny, nx))
    return lab, n


class Facets:
    """The measures and words for one trimmed chart."""

    def __init__(self, trim, kind, period=None):
        self.m = np.asarray(trim).astype(bool)
        self.kind = kind
        self.band = kind in BAND_KINDS
        self.period = period

    # ── measures ─────────────────────────────────────────────────────────
    @staticmethod
    def runs(m):
        """Lengths of all runs of True cells along the rows of m."""
        out = []
        for row in m:
            r = np.diff(np.r_[0, row.astype(np.int8), 0])
            out.extend((np.nonzero(r == -1)[0] - np.nonzero(r == 1)[0]).tolist())
        return out

    def stroke(self):
        r = self.runs(self.m) + self.runs(self.m.T)
        return float(np.median(r)) if r else 0.0

    def spans(self, share=0.3):
        """Does the drawing run on across its box, like a tile? (Charts are trimmed, so every
        chart touches its edges; a tile fills a good share of two opposite edges.)"""
        m = self.m
        return bool((m[0].mean() >= share and m[-1].mean() >= share) or
                    (m[:, 0].mean() >= share and m[:, -1].mean() >= share))

    def tiled(self):
        m = self.m
        if self.band:
            return np.tile(m, (2, 1)) if self.kind == "vertical band" else np.tile(m, (1, 2))
        return np.tile(m, (2, 2))

    def open_measure(self):
        return self.openings(self.tiled() if (self.band or self.spans()) else self.m)

    @staticmethod
    def openings(m):
        """Enclosed background areas of 2 cells or more, per 100 filled cells."""
        lab, n = components(~m)
        if n == 0:
            return 0.0
        edge = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        sizes = np.bincount(lab.ravel(), minlength=n + 1)
        count = sum(1 for k in range(1, n + 1) if k not in edge and sizes[k] >= 2)
        return 100.0 * count / max(1, m.sum())

    def silhouette(self):
        """The figure with its holes filled (background not reachable from the edge)."""
        lab, n = components(~self.m)
        edge = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])) - {0}
        outside = np.isin(lab, list(edge))
        return ~outside

    def fill(self):
        return float(self.silhouette().mean())

    # ── words ────────────────────────────────────────────────────────────
    def words(self):
        st = self.stroke()
        stroke = "thin" if st < 1.5 else "double" if st < 2.5 else "bold"
        op = self.open_measure()
        opening = "closed" if op < 1.0 else "lacy" if op >= 5.0 else "some"
        outline = "band" if self.band else "square" if self.fill() >= 0.82 else "free"
        h, w = self.m.shape
        if self.band:
            across = w if self.kind == "vertical band" else h
            fit = "b7" if across <= 7 else "b12" if across <= 12 else "b17" if across <= 17 else "b99"
        else:
            fit = "m20" if w <= 20 else "m40" if w <= 40 else "m60" if w <= 60 else "m99"
        return {"stroke": stroke, "open": opening, "outline": outline, "fit": fit}

    def measures(self):
        """The raw numbers behind the words (for checking thresholds)."""
        return {"stroke": round(self.stroke(), 2), "openings": round(self.open_measure(), 2),
                "fill": round(self.fill(), 3)}
