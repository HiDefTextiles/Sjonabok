#!/usr/bin/env python3
"""Copy the charts accepted in books/charts.csv (status good or fair) from
the digitiser's output folder into patterns/books/<name>.txt.

usage: select_charts.py <digitised dir> <patterns/books>
digitise.py names each chart <image>_<region>.txt; charts.csv maps that
region to its plate and band.
"""
import csv, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.mkdir(parents=True, exist_ok=True)
n = 0
with open(HERE / "charts.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["status"] not in ("good", "fair"):
            continue
        t = src / r["book"] / f"{r['image']}_{r['region']}.txt"
        (dst / f"{r['name']}.txt").write_text(t.read_text())
        n += 1
print(f"{n} charts -> {dst}")
