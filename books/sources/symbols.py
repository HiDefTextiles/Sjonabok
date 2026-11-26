"""Multi-symbol plates: a ruled counted grid whose cells carry different
marks (solid square, cross, dot, diagonal, ...) that stand for different
colours or stitches, as in later counted cross-stitch books (Fürst c.1660).

The grid is found exactly as for RuledGridSource. Then every filled cell is
described by a coarse 6x6 picture of its mark, and the filled cells are grouped into
`symbols` kinds by k-means with a fixed seed, so a page reads the same
every time. The 0/1 chart is "any mark"; the kinds are an extra layer
(chart.layers["symbols"]: 0 = empty, 1 = the most frequent mark, 2 = next
most frequent, ...). Rotations and mirrors are canonicalised before grouping.
"""
import cv2
import numpy as np

from .base import otsu
from .ruled import GridRegion, RuledGridSource


def cell_features(cell, size=6):
    """The cell's interior shrunk to size x size (area average): a coarse
    picture of the mark, so solid, cross, dot, diagonal and ring differ.
    Canonicalise its rotations and mirrors so a symmetric symbol does not
    become a new kind solely because it appears in another orientation."""
    if cell.shape[0] < 2 or cell.shape[1] < 2:
        return np.zeros(size * size, np.float32)
    small = cv2.resize(cell.astype(np.float32), (size, size), interpolation=cv2.INTER_AREA)
    small = np.clip(np.rint(small * 255), 0, 255).astype(np.uint8)
    rotations = [np.rot90(small, k) for k in range(4)]
    rotations += [np.fliplr(image) for image in rotations]
    canonical = min(rotations, key=lambda image: image.tobytes())
    return (canonical.astype(np.float32) / 255).ravel()


class SymbolRegion(GridRegion):
    kinds = 3

    def score(self, inner=0.2, q=90):
        """As the ruled reader, but a cell is scored by its darkest part
        (the q-th percentile of its interior), not its mean: with several
        kinds of mark a thin cross has little ink on average yet is as
        much a mark as a solid square. The cut: Otsu would split solid
        marks from light ones, so the scores are grouped into kinds + 1
        levels (1-d k-means, fixed seed) and the cut is halfway between the
        lowest level (empty cells) and the next."""
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        h, w = len(self.ys) - 1, len(self.xs) - 1
        s = np.zeros((h, w))
        for r in range(h):
            a, b = self.ys[r], self.ys[r + 1]
            ma = max(1, int(round((b - a) * inner)))
            for c in range(w):
                l, rr = self.xs[c], self.xs[c + 1]
                mb = max(1, int(round((rr - l) * inner)))
                cell = sub[a + ma:b - ma + 1, l + mb:rr - mb + 1]
                s[r, c] = np.percentile(cell, q) if cell.size else 0.0
        self.scores = s
        self.threshold = otsu(s)
        v = s.astype(np.float32).reshape(-1, 1)
        k = min(self.kinds + 1, len(np.unique(v)))
        if k >= 2:
            cv2.setRNGSeed(1)
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5)
            _, _, c = cv2.kmeans(v, k, None, crit, 8, cv2.KMEANS_PP_CENTERS)
            c = np.sort(c.ravel())
            self.threshold = float((c[0] + c[1]) / 2)
        self.cells = (s > self.threshold).astype(np.uint8)
        self.margin = np.abs(s - self.threshold)
        self.trim_frame()
        return self

    def classify(self, k, inner=0.2):
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        feats, where = [], []
        for r, c in zip(*np.nonzero(self.cells)):
            a, b = self.ys[r], self.ys[r + 1]
            l, rr = self.xs[c], self.xs[c + 1]
            ma, mb = max(1, int(round((b - a) * inner))), max(1, int(round((rr - l) * inner)))
            feats.append(cell_features(sub[a + ma:b - ma + 1, l + mb:rr - mb + 1]))
            where.append((r, c))
        self.symbols = np.zeros_like(self.cells)
        if not feats:
            return self
        X = np.array(feats, np.float32)
        k = min(k, len(X))
        if k <= 1:
            self.symbols[self.cells > 0] = 1
            return self
        cv2.setRNGSeed(1)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-4)
        _, lab, centres = cv2.kmeans(X, k, None, crit, 8, cv2.KMEANS_PP_CENTERS)
        counts = np.bincount(lab.ravel(), minlength=k)
        order = sorted(range(k), key=lambda i: (-counts[i], -centres[i].mean(), i))
        rank = np.empty(k, int); rank[order] = np.arange(1, k + 1)
        for (r, c), l in zip(where, lab.ravel()):
            self.symbols[r, c] = rank[l]
        self.symbol_centres = centres[order]
        return self

    def chart(self):
        ch = super().chart()
        ch.layers["symbols"] = self.symbols
        ch.meta["symbols"] = {str(i + 1): int((self.symbols == i + 1).sum())
                              for i in range(int(self.symbols.max()))}
        return ch


class MultiSymbolPlateSource(RuledGridSource):
    """Ruled grid with several kinds of mark. options: symbols=3 (kinds)."""
    layout = "symbols"
    description = "ruled grid with several mark kinds (colours/stitches), clustered per chart"
    region_class = SymbolRegion
    PALETTE = [(40, 40, 230), (40, 170, 40), (200, 90, 20), (160, 40, 160), (20, 160, 200)]

    def __init__(self, path, provenance=None, symbols=3, **options):
        super().__init__(path, provenance, **options)
        self.k = symbols

    def regions(self):
        regs = super().regions()
        for g in regs:
            g.kinds = self.k
        return regs

    def read(self):
        regs = [g.fit().score() for g in self.regions()]
        self._regions = [g.classify(self.k) for g in regs
                         if g.cells.shape[0] >= 3 and g.cells.shape[1] >= 3]
        return [g.chart() for g in self._regions]

    def check_image(self, path):
        tiles = []
        for g in self._regions:
            img = cv2.cvtColor(g.gray, cv2.COLOR_GRAY2BGR)
            for r, c in zip(*np.nonzero(g.symbols)):
                x0, x1 = g.x0 + g.xs[c], g.x0 + g.xs[c + 1]
                y0, y1 = g.y0 + g.ys[r], g.y0 + g.ys[r + 1]
                col = np.array(self.PALETTE[(g.symbols[r, c] - 1) % len(self.PALETTE)])
                sub = img[y0 + 2:y1 - 1, x0 + 2:x1 - 1]
                sub[:] = (0.45 * sub + 0.55 * col).astype(np.uint8)
            cv2.putText(img, f"{g.name} {g.cells.shape[0]}x{g.cells.shape[1]}", (6, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 80, 0), 2)
            tiles.append(img)
        if tiles:
            w = max(t.shape[1] for t in tiles)
            tiles = [cv2.copyMakeBorder(t, 0, 6, 0, w - t.shape[1], cv2.BORDER_CONSTANT,
                                        value=(255, 255, 255)) for t in tiles]
            cv2.imwrite(str(path), np.vstack(tiles))
