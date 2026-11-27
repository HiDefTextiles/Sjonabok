#!/usr/bin/env python3
"""Pictures for the gallery page "How we read old pattern books".

Runs the real readers (books/digitise.py, books/woodcut.py) on two Met
Open Access scans (public domain, CC0) and draws each step on a crop of the
scan: the chart found on the page, the grid fitted to it, and the cells read
as filled, then the finished 0/1 chart. The charts it reads are checked
against the committed ones in patterns/books, so the pictures show exactly
what the gallery holds.

    python3 gallery/scripts/reading_examples.py SCANS_DIR OUT_DIR

SCANS_DIR holds the scans by book, e.g. SCANS_DIR/sib1597/DP363485.webp
(books/fetch.py gets them). Writes small WebP files to OUT_DIR.
"""
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "books"))
import digitise   # noqa: E402
import woodcut    # noqa: E402

BLUE = (16, 9, 159)       # HI blue
PINK = (214, 31, 105)     # HI pink
TEAL = (45, 210, 192)     # HI teal
PAPER = (245, 245, 245)
ORANGE = (255, 160, 95)  # HI orange


class Example:
    """One chart on one scanned page. A subclass runs the reader for its
    layout and leaves the same things behind: a straightened grey picture
    of the chart (gray), its column and row lines (xs, ys) and the cells
    read (cells, 1 = filled). Drawing the steps is shared."""

    def __init__(self, scans, book, image, chart):
        self.page_path = Path(scans) / book / f"{image}.webp"
        self.chart = chart
        # the reader's own output: the stored chart with any symmetry edits
        # (books/corrections.csv, books/slips.py) put back to the value read
        stored = (ROOT / "patterns" / "books" / f"{chart}.txt").read_text()
        m = np.array([[int(ch) for ch in line] for line in stored.split()])
        self.slips = []
        path = ROOT / "books" / "corrections.csv"
        if path.exists():
            for r in csv.DictReader(open(path)):
                if r["chart"] == chart and r["status"] == "applied":
                    i, j = int(r["row"]), int(r["col"])
                    m[i, j] = int(r["read"])
                    self.slips.append((i, j, int(r["proposed"])))
        self.stored = stored
        self.expected = "\n".join("".join(map(str, row)) for row in m) + "\n"

    def check(self, cells):
        text = "\n".join("".join(map(str, row)) for row in cells) + "\n"
        if text != self.expected:
            raise SystemExit(f"{self.chart}: reader output differs from patterns/books")

    @staticmethod
    def save(img, path, width=None, lossless=False):
        im = Image.fromarray(img) if isinstance(img, np.ndarray) else img
        if width and im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(path, "WEBP", quality=80, method=6, lossless=lossless)
        print(path, im.size)

    def steps(self, path, rows, cols, scale=3, panels=("scan", "grid", "read")):
        """Panels on the same crop: the scan, the grid fitted, the cells read."""
        xs, ys = self.xs, self.ys
        x0, x1, y0, y1 = xs[cols[0]], xs[cols[1]], ys[rows[0]], ys[rows[1]]
        pad = 4
        img = cv2.copyMakeBorder(self.gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
        base = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)[y0:y1 + 2 * pad, x0:x1 + 2 * pad]
        base = cv2.resize(base, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        def at(x, y):
            return int(round((x - x0 + pad) * scale)), int(round((y - y0 + pad) * scale))

        grid = base.copy()
        for c in range(cols[0], cols[1] + 1):
            cv2.line(grid, at(xs[c], y0), at(xs[c], y1), TEAL, 2)
        for r in range(rows[0], rows[1] + 1):
            cv2.line(grid, at(x0, ys[r]), at(x1, ys[r]), TEAL, 2)
        read = grid.copy()
        for r in range(*rows):
            for c in range(*cols):
                if self.cells[r, c]:
                    p, q = at(xs[c], ys[r]), at(xs[c + 1], ys[r + 1])
                    sub = read[p[1] + 3:q[1] - 2, p[0] + 3:q[0] - 2]
                    sub[:] = (0.35 * sub + 0.65 * np.array(PINK)).astype(np.uint8)
        fixed = read.copy()
        for i, j, v in self.slips:
            if rows[0] <= i < rows[1] and cols[0] <= j < cols[1]:
                p, q = at(xs[j], ys[i]), at(xs[j + 1], ys[i + 1])
                if v:
                    sub = fixed[p[1] + 3:q[1] - 2, p[0] + 3:q[0] - 2]
                    sub[:] = (0.35 * sub + 0.65 * np.array(PINK)).astype(np.uint8)
                else:
                    sub = fixed[p[1] + 3:q[1] - 2, p[0] + 3:q[0] - 2]
                    sub[:] = read[p[1] + 3:q[1] - 2, p[0] + 3:q[0] - 2] * 0 + grid[p[1] + 3:q[1] - 2, p[0] + 3:q[0] - 2]
                cv2.rectangle(fixed, (p[0] + 1, p[1] + 1), (q[0] - 1, q[1] - 1), ORANGE, 4)
        pics = dict(scan=base, grid=grid, read=read, fixed=fixed)
        gap = np.full((base.shape[0], 18, 3), 255, np.uint8)
        row = []
        for name in panels:
            row += [pics[name], gap]
        self.save(np.hstack(row[:-1]), path, 1500)


class GridExample(Example):
    """Ruled grid with a mark in each filled cell (Sibmacher's etchings)."""

    def read(self, index):
        self.page = digitise.Page(self.page_path)
        g = self.page.regions()[index].fit().score()
        self.check(g.cells)
        self.box = g.page_box
        self.gray = g.gray
        self.xs, self.ys = g.x0 + np.asarray(g.xs), g.y0 + np.asarray(g.ys)
        self.cells = g.cells
        return self

    def page_picture(self, path):
        """The whole page with the found chart outlined."""
        rgb = cv2.cvtColor(self.page.gray, cv2.COLOR_GRAY2RGB)
        x0, y0, x1, y1 = self.box
        cv2.rectangle(rgb, (x0, y0), (x1, y1), PINK, 10)
        self.save(rgb, path, 900)


class WoodcutExample(Example):
    """Black block with the empty cells cut out white (Quentel's woodcuts):
    no ruling, so the grid comes from the spacing of the white squares."""

    def read(self, band):
        page = woodcut.WoodcutPage(self.page_path)
        x0, y0, x1, y1 = page.block()
        crop, _ = page.deskew(page.light[y0:y1, x0:x1])
        g = woodcut.WoodcutGrid(crop, page.path.stem).fit()
        ra, rb, cl, cr = g.bands()[band]
        self.check(g.cells[ra:rb, cl:cr])
        self.gray = (crop * 255).astype(np.uint8)
        self.xs, self.ys = np.asarray(g.xs)[cl:], np.asarray(g.ys)[ra:]
        self.cells = g.cells[ra:rb, cl:cr]
        return self


def chart_picture(text, path, cell=6):
    """The finished 0/1 chart, filled cells in HI blue on a light grid."""
    m = np.array([[int(ch) for ch in line] for line in text.split()])
    h, w = m.shape
    im = Image.new("RGB", (w * cell + 1, h * cell + 1), PAPER)
    d = ImageDraw.Draw(im)
    for r in range(h):
        for c in range(w):
            box = (c * cell, r * cell, (c + 1) * cell, (r + 1) * cell)
            d.rectangle(box, fill=BLUE if m[r, c] else (255, 255, 255), outline=(215, 215, 215))
    Example.save(im, path, lossless=True)


def main():
    scans, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    sib = GridExample(scans, "sib1597", "DP363485", "sib1597_12_p1").read(0)
    sib.page_picture(out / "sib1597-page.webp")
    sib.steps(out / "sib1597-steps.webp", rows=(1, 17), cols=(20, 44))
    chart_picture(sib.stored, out / "sib1597-chart.webp")
    sib.steps(out / "sib1597-slips.webp", rows=(28, 45), cols=(0, 26), panels=("read", "fixed"))

    qu = WoodcutExample(scans, "quentel1529", "DP361377", "quentel1529_18_p1").read(0)
    qu.steps(out / "quentel1529-steps.webp", rows=(10, 26), cols=(4, 28))
    chart_picture(qu.stored, out / "quentel1529-chart.webp", cell=4)


if __name__ == "__main__":
    main()
