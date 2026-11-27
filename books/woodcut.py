#!/usr/bin/env python3
"""Read a white-line woodcut pattern page (Quentel, Schönsperger, Jobin):
a black block with the empty cells cut out as small white squares.

The reader itself is books/sources/woodcut.py (WhiteLineWoodcutSource);
this file keeps the command line and the outputs of PR #46.

    python3 woodcut.py page.webp outdir [--book CODE] [--sidecars] > outdir/<page>.json

Writes <page>_b<k>.txt (0/1, 1 = filled) and <page>_check.jpg.
"""
import argparse, json

import numpy as np

from sources import WhiteLineWoodcutSource, Provenance
from sources.base import deskew as _deskew, rotate as _rotate
from sources.base import paint_cells
from sources.woodcut import WoodcutGrid       # noqa: F401  (old import path)


class WoodcutPage(WhiteLineWoodcutSource):
    """The PR #46 name, kept for scripts that import it (block, deskew, light)."""

    @staticmethod
    def rotate(img, angle):
        return _rotate(img, angle, border=1.0)

    def deskew(self, crop):
        return _deskew(crop.astype(np.float32), border=1.0)


def check_image(light, grid, bands, path):
    """The PR #46 function (books/fuerst.py uses it): cells painted on the
    deskewed block, bands boxed."""
    import cv2
    img = cv2.cvtColor((light * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    paint_cells(img, grid.cells, grid.margin, grid.xs, grid.ys)
    for i, (a, b, l, r) in enumerate(bands, 1):
        cv2.rectangle(img, (grid.xs[l], grid.ys[a]), (grid.xs[r], grid.ys[b]), (200, 120, 0), 2)
        cv2.putText(img, f"b{i} {b - a}x{r - l}", (grid.xs[l] + 4, grid.ys[a] + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 80, 0), 2)
    cv2.imwrite(str(path), img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page"); ap.add_argument("outdir")
    ap.add_argument("--book", help="books.csv code: attach provenance")
    ap.add_argument("--sidecars", action="store_true", help="also write <chart>.json (meta + provenance)")
    a = ap.parse_args()
    prov = Provenance.lookup(a.book) if a.book else None
    src = WhiteLineWoodcutSource(a.page, provenance=prov)
    print(json.dumps(src.write(a.outdir, sidecars=a.sidecars)))


if __name__ == "__main__":
    main()
