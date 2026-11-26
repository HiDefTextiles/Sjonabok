"""Ruled plates whose cells carry named kinds of mark (Sibmacher's plates:
plus, vertical hatching, diagonals that draw a star over 2x2 cells, ...).

MultiSymbolPlateSource groups marks into unnamed clusters; this reader
names them instead (books/sources/marks.py: . # + x | - / \\ < > ^ v F 7 L J ?),
so the same mark means the same thing on every page and in every book.

The grid is found as for RuledGridSource. Each cell is cut out between its
own ruling lines (refound locally, so paper stretch does not put a rule
inside a cell) and classified. The any-mark 0/1 reading: a cell is 1 when its kind is in `filled` (default: every mark). The kinds
are kept as chart.layers["marks"] (written as <chart>.marks.txt with
--sidecars), with their counts in meta["marks"]. A 2x2 block of diagonals
drawn as one X (\\ / over / \\) is listed in meta["stars"] by its top-left cell.

Colours: different marks mean different colours (Helga: filled and crossed
cells are two colours), so <chart>.txt holds one digit per colour, 0 = empty,
1, 2, ... (indices into the gallery's COLOR_PALETTE), and the any-mark 0/1
reading is kept as chart.layers["filled"] (<chart>.filled.txt with
--sidecars). Marks with no colour of their own (diagonals, half cells,
unclear) are 0 in the colour chart and stay in <chart>.marks.txt. The mapping mark -> digit is
books/sources/mark_colours.csv: rows for book "*" are the default, rows
for a book code override them; the option colours="#=1,+=1" overrides both.
"""
import csv
from pathlib import Path

import cv2
import numpy as np

from .marks import FILLED, KINDS, MarkClassifier, cell_interiors
from .ruled import GridRegion, RuledGridSource

COLOURS = {"#": (20, 20, 20), "+": (40, 40, 230), "x": (160, 40, 160), "|": (40, 150, 40),
           "-": (40, 150, 150), "/": (220, 90, 20), "\\": (220, 160, 20), "?": (0, 140, 255)}


COLOURS_CSV = Path(__file__).with_name("mark_colours.csv")


def colour_map(book=None, override=None):
    """mark -> digit for a book: defaults, then the book's rows, then the option."""
    m = {}
    with open(COLOURS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for want in ("*", book):
        for r in rows:
            if want and r["book"] == want:
                m[r["mark"]] = int(r["colour"])
    for item in (override or "").split(","):
        if "=" in item:
            k, v = item.rsplit("=", 1)
            m[k.strip()] = int(v)
    return m


class MarkRegion(GridRegion):
    classifier = MarkClassifier()
    filled = FILLED
    colour_map = colour_map()

    def score(self):
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        inner = cell_interiors(sub, self.xs, self.ys)
        h, w = len(self.ys) - 1, len(self.xs) - 1
        self.marks = np.full((h, w), ".", dtype="<U1")
        self.scores = np.zeros((h, w))
        for (r, c), cell in inner.items():
            self.marks[r, c] = self.classifier.classify(cell)
            self.scores[r, c] = float(cell.mean()) if cell.size else 0.0
        self.threshold = self.classifier.empty
        self.cells = np.isin(self.marks, list(self.filled)).astype(np.uint8)
        # uncertain: marks the classifier could not name
        self.margin = np.where(self.marks == "?", 0.0, 1.0)
        self.trim_frame()
        return self

    def trim_frame(self, full=0.9):
        """As the ruled reader, keeping the marks layer in step."""
        h0, w0 = self.cells.shape
        ys0, xs0 = list(self.ys), list(self.xs)
        super().trim_frame(full)
        top = ys0.index(self.ys[0]) if self.ys[0] in ys0 else 0
        left = xs0.index(self.xs[0]) if self.xs[0] in xs0 else 0
        self.marks = self.marks[top:top + self.cells.shape[0], left:left + self.cells.shape[1]]

    def stars(self):
        m = self.marks
        out = []
        for r in range(m.shape[0] - 1):
            for c in range(m.shape[1] - 1):
                if (m[r, c], m[r, c + 1], m[r + 1, c], m[r + 1, c + 1]) == ("\\", "/", "/", "\\"):
                    out.append([r, c])
        return out

    def chart(self):
        ch = super().chart()
        ch.layers["marks"] = self.marks
        kinds, n = np.unique(self.marks, return_counts=True)
        order = {k: i for i, k in enumerate(KINDS)}
        ch.meta["marks"] = {str(k): int(v) for k, v in sorted(zip(kinds, n), key=lambda t: order.get(t[0], 99))}
        ch.meta["stars"] = self.stars()
        cmap = self.colour_map
        colours = np.vectorize(lambda k: cmap.get(k, 0), otypes=[np.uint8])(self.marks) \
            if self.marks.size else np.zeros(self.marks.shape, np.uint8)
        # the chart itself holds the colour digits (Helga: "in txt it is 0 1 2");
        # the any-mark 0/1 reading is kept as a layer
        ch.layers["filled"] = ch.cells
        ch.cells = colours
        ch.meta["colours"] = {k: v for k, v in cmap.items() if k in ch.meta["marks"]}
        return ch


class NamedMarkPlateSource(RuledGridSource):
    """Ruled grid, every cell classified into a named kind of mark.

    options: filled="#+x|-/\\<>^vF7LJ?"  kinds that count as 1 in the 0/1 chart
             (default every mark; e.g. filled="#+" for solid and plus only)
             colours="#=1,+=2"  mark -> colour digit, over mark_colours.csv
    """
    layout = "marks"
    description = "ruled grid, every cell named: empty, solid, plus, hatching, diagonals, half cells"

    def __init__(self, path, provenance=None, filled=None, colours=None, **options):
        super().__init__(path, provenance, **options)
        self.filled = set(filled) if filled else FILLED
        self.colours = colour_map(provenance.book if provenance else None, colours)
        filled_set, cmap = self.filled, self.colours

        class Region(MarkRegion):
            filled = filled_set
            colour_map = cmap
        self.region_class = Region

    def check_image(self, path):
        tiles = []
        for g in self._regions:
            img = cv2.cvtColor(g.gray, cv2.COLOR_GRAY2BGR)
            img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            for r in range(g.marks.shape[0]):
                for c in range(g.marks.shape[1]):
                    k = g.marks[r, c]
                    if k == ".":
                        continue
                    x = 2 * (g.x0 + g.xs[c]) + 4
                    y = 2 * (g.y0 + g.ys[r + 1]) - 5
                    cv2.putText(img, k, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                COLOURS.get(k, (0, 100, 255)), 1, cv2.LINE_AA)
            cv2.putText(img, f"{g.name} {g.cells.shape[0]}x{g.cells.shape[1]}", (6, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 80, 0), 2)
            tiles.append(img)
        if tiles:
            w = max(t.shape[1] for t in tiles)
            tiles = [cv2.copyMakeBorder(t, 0, 6, 0, w - t.shape[1], cv2.BORDER_CONSTANT,
                                        value=(255, 255, 255)) for t in tiles]
            cv2.imwrite(str(path), np.vstack(tiles))
