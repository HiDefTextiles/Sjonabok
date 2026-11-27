#!/usr/bin/env python3
"""Digitise counted-thread charts from a page scan (ruled grid).

The reader itself is books/sources/ruled.py (RuledGridSource); this file
keeps the command line and the outputs of PR #46.

usage: digitise.py page.jpg outdir [--woodcut] [--book CODE] [--sidecars]
writes outdir/<page>_r<k>.txt and <page>_check.jpg, prints the json meta.
"""
import argparse, json

from sources import RuledGridSource, Provenance
from sources.base import deskew, rotate
from sources.ruled import GridRegion          # noqa: F401  (old import path)


class Page(RuledGridSource):
    """The PR #46 name, kept for scripts that import it."""

    def __init__(self, path, woodcut=False):
        super().__init__(path, white_line=woodcut)

    rotate = staticmethod(rotate)

    def deskew(self, crop):
        return deskew(crop, border=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page"); ap.add_argument("outdir")
    ap.add_argument("--woodcut", action="store_true",
                    help="white-line woodcut (cells cut out of a black block); woodcut.py reads these better")
    ap.add_argument("--book", help="books.csv code: attach provenance")
    ap.add_argument("--sidecars", action="store_true", help="also write <chart>.json (meta + provenance)")
    a = ap.parse_args()
    prov = Provenance.lookup(a.book) if a.book else None
    src = RuledGridSource(a.page, provenance=prov, white_line=a.woodcut)
    print(json.dumps(src.write(a.outdir, sidecars=a.sidecars)))


if __name__ == "__main__":
    main()
