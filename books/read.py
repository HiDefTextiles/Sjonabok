#!/usr/bin/env python3
"""Read one scanned page with the reader for its layout.

usage: read.py page outdir [--book CODE] [--layout ruled|woodcut|symbols|drawing]
               [--option key=value ...] [--sidecars]

Without --layout the layout follows the book's kind in books.csv.
Every layout writes the same thing: <chart>.txt (0/1) and <page>_check.jpg,
with --sidecars also <chart>.json (how it was read + book, date, origin,
holder, scan rights, terms of use, chart licence) and extra layers such as
<chart>.symbols.txt. The json meta list is printed.
    read.py --layouts     lists the layouts
"""
import argparse, json, sys

from sources import LAYOUTS, open_source


def value(v):
    for f in (int, float):
        try:
            return f(v)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(v.lower(), v)


def main():
    if "--layouts" in sys.argv:
        for k, cls in LAYOUTS.items():
            print(f"{k:8s} {cls.__name__:24s} {cls.description}")
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("page"); ap.add_argument("outdir")
    ap.add_argument("--book"); ap.add_argument("--layout", choices=sorted(LAYOUTS))
    ap.add_argument("--option", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--sidecars", action="store_true")
    a = ap.parse_args()
    opts = dict(o.split("=", 1) for o in a.option)
    src = open_source(a.page, book=a.book, layout=a.layout, **{k: value(v) for k, v in opts.items()})
    print(json.dumps(src.write(a.outdir, sidecars=a.sidecars)))


if __name__ == "__main__":
    main()
