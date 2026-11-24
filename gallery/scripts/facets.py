"""Facets: ways to browse the charts, measured from the 0/1 grid alone.

Each facet turns a measure into a few plain words, so it can be a gallery
filter and a way to put like with like (for example as training sets for
pattern synthesis). No labels and no model are used: anyone can recompute
them from the charts, and the thresholds are written here.

    line     how the figure is drawn: Line drawing (under 5% of filled
             cells have all four neighbours filled), Solid (20% or more), Mixed
    open     how open the figure is when repeated: Closed, Some openings, Lacy
             (small enclosed openings per 100 filled cells, chart repeated
             2 x 2, a band twice along its length, so openings across an
             edge count): under 1 Closed, 5 or more Lacy
    outline  the silhouette of a motif (holes filled): Square (fills 82% or
             more of its box), Diamond or eight-point star (corners nearly
             empty, edges touched only near the middle), Rounded or octagon
             (fills 60% or more), otherwise Free shape (animals, flowers,
             trees); bands get Band
    size     a motif by its longer side: Small (up to 15 cells), Medium (up
             to 40), Large; a band by its width across: Small (up to 7 rows),
             Medium (up to 15), Large

The thresholds were set by looking at the distribution over all 600 charts
so that each word holds a useful share, then rounded; see the Methods page.
"""

import numpy as np

BAND_KINDS = ("border", "edging", "vertical band")

LABELS = {
    "line": {"line": "Line drawing", "mixed": "Mixed", "solid": "Solid"},
    "open": {"closed": "Closed", "some": "Some openings", "lacy": "Lacy"},
    "outline": {"square": "Square", "round": "Rounded or octagon", "diamond": "Diamond or eight-point star",
                "free": "Free shape", "band": "Band"},
    "size": {"small": "Small", "medium": "Medium", "large": "Large"},
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
    def interior(self):
        p = np.pad(self.m, 1)
        inner = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        return float(inner.sum() / max(1, self.m.sum()))

    def tiled(self):
        m = self.m
        if self.band:
            if self.kind == "vertical band":
                return np.tile(m, (2, 1))
            return np.tile(m, (1, 2))
        return np.tile(m, (2, 2))

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

    def outline_measures(self):
        s = self.silhouette()
        h, w = s.shape
        fill = float(s.mean())
        # corners: the four quarter-size corner squares; a diamond leaves them nearly empty
        ch, cw = max(1, h // 4), max(1, w // 4)
        corners = np.concatenate([s[:ch, :cw].ravel(), s[:ch, -cw:].ravel(),
                                  s[-ch:, :cw].ravel(), s[-ch:, -cw:].ravel()]).mean()
        # middle of each edge (the centre half of the outer rows and columns)
        y0, y1, x0, x1 = h // 4, h - h // 4, w // 4, w - w // 4
        mids = np.concatenate([s[0, x0:x1], s[-1, x0:x1], s[y0:y1, 0], s[y0:y1, -1]]).mean()
        return fill, float(corners), float(mids)

    # ── words ────────────────────────────────────────────────────────────
    def words(self):
        inner = self.interior()
        line = "line" if inner < 0.05 else "solid" if inner >= 0.2 else "mixed"
        op = self.openings(self.tiled())
        opening = "closed" if op < 1.0 else "lacy" if op >= 5.0 else "some"
        if self.band:
            outline = "band"
        else:
            fill, corners, mids = self.outline_measures()
            if fill >= 0.82:
                outline = "square"
            elif corners < 0.12 and mids < 0.45 and fill < 0.62:
                outline = "diamond"
            elif fill >= 0.6:
                outline = "round"
            else:
                outline = "free"
        if self.band:
            # a band by its width across (rows of a border, columns of a vertical band)
            side = min(self.m.shape)
            size = "small" if side <= 7 else "medium" if side <= 15 else "large"
        else:
            side = max(self.m.shape)
            size = "small" if side <= 15 else "medium" if side <= 40 else "large"
        return {"line": line, "open": opening, "outline": outline, "size": size}

    def measures(self):
        """The raw numbers behind the words (for checking thresholds)."""
        out = {"interior": round(self.interior(), 3), "openings": round(self.openings(self.tiled()), 2)}
        if not self.band:
            fill, corners, mids = self.outline_measures()
            out.update(fill=round(fill, 3), corners=round(corners, 3), mids=round(mids, 3))
        return out
