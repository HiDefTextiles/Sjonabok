#!/usr/bin/env python3
"""Check the C++ matcher against books/travel.py (run from the repo root;
`make -C cpp/submotif test`).

1. pieces: for every chart travel.py reads, the C++ find_pieces gives the
   same figures (same cells, same order) as travel.Chart.pieces().
2. iou: on a sample of piece pairs, C++ iou == travel.Piece.iou exactly.
3. pairs: the European x Icelandic pairs from the C++ Matcher are exactly
   the pairs travel.py finds (as a multiset of chart, chart, cells, iou).
--bench also times the pair search in both.
"""
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "books"))
import numpy as np
import submotif
import travel


def cpp_pieces(chart):
    return submotif.find_pieces(chart.m.astype(np.uint8), chart.name, tile=chart.tile,
                                min_cells=travel.MIN_CELLS)


def py_pairs(ep, ip):
    """travel.Travel.run's pair search, unchanged."""
    from collections import defaultdict
    by_dims = defaultdict(list)
    for p in ip:
        by_dims[p.dims()].append(p)
    pairs = []
    for a in ep:
        h, w = a.dims()
        for dh in (-1, 0, 1):
            for dw in (-1, 0, 1):
                for b in by_dims.get((h + dh, w + dw), []):
                    if abs(a.n - b.n) > (1 - travel.MATCH) * max(a.n, b.n) * 1.2:
                        continue
                    s = 1.0 if a.key == b.key else a.iou(b)
                    if s >= travel.MATCH:
                        pairs.append((a.chart, b.chart, a.n, round(s, 6)))
    return pairs


def main():
    bench = "--bench" in sys.argv
    t = travel.Travel()
    charts = t.eur + t.ice
    bad = 0
    pyp, cpp = {}, {}
    for c in charts:
        a, b = c.pieces(), cpp_pieces(c)
        same = len(a) == len(b) and all(np.array_equal(x.cells, y.cells) for x, y in zip(a, b))
        if not same:
            bad += 1
            print("pieces differ:", c.name, len(a), len(b))
        pyp[id(c)], cpp[id(c)] = a, b
    print(f"1. pieces: {len(charts) - bad}/{len(charts)} charts identical")

    ep = [p for c in t.eur for p in pyp[id(c)]]
    ip = [p for c in t.ice for p in pyp[id(c)]]
    ec = [p for c in t.eur for p in cpp[id(c)]]
    ic = [p for c in t.ice for p in cpp[id(c)]]
    rnd = random.Random(1)
    n_iou, diff = 0, 0
    for _ in range(3000):
        i, j = rnd.randrange(len(ep)), rnd.randrange(len(ip))
        if max(ep[i].cells.shape) > 40 or max(ip[j].cells.shape) > 40:
            continue
        n_iou += 1
        if ep[i].iou(ip[j]) != submotif.iou(ec[i], ic[j], travel.SHIFT):
            diff += 1
    print(f"2. iou: {n_iou - diff}/{n_iou} sampled pairs identical")

    t0 = time.perf_counter()
    m = submotif.Matcher(travel.MATCH, travel.SHIFT).cross_pairs(ec, ic)
    t_cpp = time.perf_counter() - t0
    got = Counter((ec[a].chart, ic[b].chart, ec[a].n, round(s, 6)) for a, b, s in m)
    if bench or not (ROOT / "books/travel/pairs.csv").exists():
        t0 = time.perf_counter()
        want = Counter(py_pairs(ep, ip))
        t_py = time.perf_counter() - t0
    else:
        import csv
        want = Counter((r["book_chart"], r["manuscript_chart"], int(r["cells"]), round(float(r["iou"]), 3))
                       for r in csv.DictReader(open(ROOT / "books/travel/pairs.csv")))
        got = Counter((a, b, n, round(s, 3)) for a, b, n, s in got.elements())
        t_py = None
    ok = got == want
    print(f"3. pairs: C++ {sum(got.values())}, Python {sum(want.values())}, identical: {ok}")
    if t_py is not None:
        print(f"   time: Python {t_py:.2f} s, C++ {t_cpp:.3f} s ({t_py / max(t_cpp, 1e-9):.0f}x)")
    sys.exit(0 if ok and bad == 0 and diff == 0 else 1)


if __name__ == "__main__":
    main()
