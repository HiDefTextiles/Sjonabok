#!/usr/bin/env python3
"""Source-reader checks:  python3 books/sources/test_sources.py

Draws a known chart in each layout (ruled grid with crosses, white-line
woodcut, ruled grid with three kinds of mark, line drawing), reads it back
with the matching PatternSource and checks the 0/1 chart and the interface.
The issue #9 scan fixture also guards against a motif-pulled grid fit.
"""
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sources import LAYOUTS, Chart, Provenance, open_source   # noqa: E402
from sources.symbols import cell_features  # noqa: E402

RNG = np.random.default_rng(7)
P = 14                                   # pitch in pixels (woodcut)
PR = 12                                  # ruled pitch: like the etchings, ruling covers ~30 % of the chart


def known(h=18, w=30, kinds=1):
    m = (RNG.random((h, w)) < 0.35).astype(np.uint8)
    return m * RNG.integers(1, kinds + 1, size=m.shape) if kinds > 1 else m


def ruled_page(sym, path, marks=("cross",), P=PR):
    h, w = sym.shape
    img = np.full((h * P + 200, w * P + 200), 235, np.uint8)
    x0 = y0 = 100
    for r in range(h + 1):
        cv2.line(img, (x0, y0 + r * P), (x0 + w * P, y0 + r * P), 60, 2)
    for c in range(w + 1):
        cv2.line(img, (x0 + c * P, y0), (x0 + c * P, y0 + h * P), 60, 2)
    for r, c in zip(*np.nonzero(sym)):
        kind = marks[sym[r, c] - 1]
        a, b = x0 + c * P, y0 + r * P
        if kind == "cross":
            t = 2
            cv2.line(img, (a + 3, b + 3), (a + P - 3, b + P - 3), 20, t)
            cv2.line(img, (a + P - 3, b + 3), (a + 3, b + P - 3), 20, t)
        elif kind == "solid":
            cv2.rectangle(img, (a + 2, b + 2), (a + P - 2, b + P - 2), 20, -1)
        elif kind == "dot":
            cv2.circle(img, (a + P // 2, b + P // 2), 3, 20, -1)
    img = cv2.GaussianBlur(img, (5, 5), 1.2)         # ink spread of a print
    img = np.clip(img + RNG.normal(0, 6, img.shape), 0, 255).astype(np.uint8)   # paper grain
    cv2.imwrite(str(path), img)


def woodcut_page(m, path):
    h, w = m.shape
    img = np.full((h * P + 300, w * P + 300), 235, np.uint8)
    x0 = y0 = 150
    cv2.rectangle(img, (x0 - 2 * P, y0 - 2 * P), (x0 + (w + 2) * P, y0 + (h + 2) * P), 25, -1)
    for r, c in zip(*np.nonzero(m == 0)):
        a, b = x0 + c * P, y0 + r * P
        cv2.rectangle(img, (a + 3, b + 3), (a + P - 4, b + P - 4), 235, -1)
    cv2.imwrite(str(path), img)


def drawing_page(path):
    img = np.full((500, 500), 235, np.uint8)
    cv2.circle(img, (250, 250), 150, 30, 3)          # outline of a disc, 300 px across
    cv2.imwrite(str(path), img)


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    return ok


def main():
    good = True
    tmp = Path(tempfile.mkdtemp())

    m = known()
    ruled_page(m, tmp / "ruled.png")
    src = open_source(tmp / "ruled.png", layout="ruled")
    ch = src.charts()
    # drawn pages are cleaner than prints: a frame corner can read as filled,
    # so ask for 99 % of the cells (the scans are checked by regress.sh)
    good &= check("ruled: one chart, cells as drawn",
                  len(ch) == 1 and ch[0].cells.shape == m.shape and (ch[0].cells == m).mean() >= 0.99)

    # woodcut: frame rows/cols of solid black are trimmed as band edges, so
    # keep a clear border of empty cells and compare the inner area
    m = known(20, 34); m[[0, -1], :] = 0; m[:, [0, -1]] = 0
    woodcut_page(m, tmp / "wood.png")
    ch = open_source(tmp / "wood.png", layout="woodcut").charts()
    big = max(ch, key=lambda c: c.cells.size) if ch else None
    good &= check("woodcut: cells as cut", big is not None and big.cells.shape == m.shape
                  and (big.cells == m).mean() > 0.99)

    sym = known(16, 26, kinds=3)
    ruled_page(sym, tmp / "plate.png", marks=("solid", "cross", "dot"), P=16)
    ch = open_source(tmp / "plate.png", layout="symbols", symbols=3).charts()
    s = ch[0].layers["symbols"] if ch else None
    same_partition = s is not None and s.shape == sym.shape and all(
        len(set(s[sym == k])) == 1 for k in (1, 2, 3)) and len({s[sym == k][0] for k in (1, 2, 3)}) == 3
    good &= check("symbols: 0/1 chart and three mark kinds kept apart",
                  bool(ch) and (ch[0].cells == (sym > 0)).all() and same_partition)
    frequencies = np.bincount(s.ravel(), minlength=4) if s is not None else np.zeros(4, int)
    good &= check("symbols: kind IDs ranked by frequency",
                  bool(np.all(np.diff(frequencies[1:]) <= 0)))
    sample = np.zeros((6, 6), np.float32)
    sample[[0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5]] = 1
    features = cell_features(sample)
    good &= check("symbols: rotations and mirrors share one feature",
                  all(np.array_equal(features, cell_features(image)) for image in
                      [np.rot90(sample, k) for k in range(4)] +
                      [np.fliplr(np.rot90(sample, k)) for k in range(4)]))

    issue9 = Path(__file__).resolve().parents[2] / "patterns/multicolor/issue9-example-1.png"
    scan = open_source(issue9, layout="symbols", symbols=4)
    scan_charts = scan.charts()
    pitch_error = max((float(np.max(np.abs(np.diff(g.ys) - g.py)))
                       for g in scan._regions if len(g.ys) > 1), default=float("inf"))
    scan_rows = [chart.cells.shape[0] for chart in scan_charts]
    good &= check("symbols: issue #9 scan grids align and trim page margins",
                  len(scan_charts) == 6 and scan_rows == [19, 11, 6, 8, 7, 17]
                  and pitch_error <= 1.25)

    drawing_page(tmp / "draw.png")
    ch = open_source(tmp / "draw.png", layout="drawing", cells=30).charts()
    c = ch[0].cells if ch else np.zeros((1, 1))
    yy, xx = np.mgrid[0:c.shape[0], 0:c.shape[1]]
    disc = (np.hypot(xx + 0.5 - c.shape[1] / 2, yy + 0.5 - c.shape[0] / 2) < c.shape[1] / 2).astype(np.uint8)
    good &= check("drawing: outline filled into a disc, 30 cells across",
                  c.shape[1] == 30 and (c == disc).mean() > 0.95)

    prov = Provenance.lookup("sib1597")
    src = open_source(tmp / "ruled.png", book="sib1597")
    out = src.write(tmp / "out", sidecars=True)
    ch = src.charts()[0]
    good &= check("provenance: book, date, origin, licence, terms attached",
                  ch.provenance == prov and prov.year == "1597" and "Nuremberg" in prov.origin
                  and prov.chart_licence == "CC BY 4.0" and prov.scan_rights and prov.terms_of_use
                  and (tmp / "out" / f"{ch.name}.json").exists() and "layout" not in out[0])
    good &= check("interface: every layout is a PatternSource returning Chart",
                  all(isinstance(c, Chart) for c in src.charts()) and set(LAYOUTS) ==
                  {"ruled", "woodcut", "symbols", "drawing"})
    sys.exit(0 if good else 1)


if __name__ == "__main__":
    main()
