"""Optimise the overview sheets with Gurobi.

Reads the item files written by build_gallery.py and writes layout files
that build_gallery.py then uses instead of its simple packing:

    python gallery/scripts/pack_overview.py bands  gallery/patterns/overview-band-items.csv  gallery/layout/bands.csv
    python gallery/scripts/pack_overview.py motifs gallery/patterns/overview-motif-items.csv gallery/layout/motifs.csv

Only this script needs gurobipy (and a licence); the site build does not.

Bands: every band is repeated to the column width and stacked in one of
K columns, so only heights matter. Assign each band to a column so that,
after each source (in order), the column heights are as equal as possible:
colour changes then run straight across and the columns end level.

Motifs: rectangles (chart + gap) on a strip as wide as the band sheet,
no overlap, no rotation; minimise the height. Colours may mix (--group > 0
adds a weight on each source's vertical span and keeps sources in order).
Non-overlap is added lazily: start with pairs near each other in the
starting layout, solve, add the pairs that clash, repeat.
"""

import argparse
import csv
import itertools
import math

import gurobipy as gp
from gurobipy import GRB


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(fields)
        w.writerows(rows)


class BandPacker:
    """Share each source's bands over the columns (see module docstring)."""

    def __init__(self, items, columns):
        self.items, self.K = items, columns
        self.h = [int(r["h"]) for r in items]
        self.rank = [int(r["rank"]) for r in items]

    def solve(self, time_limit):
        n, K = len(self.items), self.K
        ranks = sorted(set(self.rank))
        m = gp.Model("bands")
        m.Params.TimeLimit = time_limit
        a = m.addVars(n, K, vtype=GRB.BINARY, name="a")
        for i in range(n):
            m.addConstr(a.sum(i, "*") == 1)
        # C[s, c]: height of column c after the sources up to s
        C = m.addVars(ranks, K, lb=0, name="C")
        hi = m.addVars(ranks, lb=0, name="hi")
        lo = m.addVars(ranks, lb=0, name="lo")
        for k, s in enumerate(ranks):
            for c in range(K):
                m.addConstr(C[s, c] == (C[ranks[k - 1], c] if k else 0)
                            + gp.quicksum(self.h[i] * a[i, c] for i in range(n) if self.rank[i] == s))
                m.addConstr(hi[s] >= C[s, c])
                m.addConstr(lo[s] <= C[s, c])
        # straight colour changes: small spread after every source; level
        # bottom: the last spread counts double
        m.setObjective(gp.quicksum(hi[s] - lo[s] for s in ranks) + (hi[ranks[-1]] - lo[ranks[-1]]),
                       GRB.MINIMIZE)
        # column symmetry: the first source fills columns in order of height
        first = [i for i in range(n) if self.rank[i] == ranks[0]]
        for c in range(K - 1):
            m.addConstr(gp.quicksum(self.h[i] * a[i, c] for i in first)
                        >= gp.quicksum(self.h[i] * a[i, c + 1] for i in first))
        m.optimize()
        return [next(c for c in range(K) if a[i, c].X > 0.5) for i in range(n)]

    def run(self, out, time_limit):
        col = self.solve(time_limit)
        write(out, ["id", "column"], [(it["id"], c) for it, c in zip(self.items, col)])


class MotifPacker:
    """Strip packing with source order (see module docstring)."""

    def __init__(self, items, width, group=0.0, near=40):
        self.items, self.width, self.group, self.near = items, width, group, near
        self.w = [int(r["w"]) for r in items]
        self.h = [int(r["h"]) for r in items]
        self.rank = [int(r["rank"]) for r in items]
        self.x0 = [int(r["x"]) for r in items]
        self.y0 = [int(r["y"]) for r in items]

    def overlap(self, i, j, x, y, margin=0):
        return (x[i] < x[j] + self.w[j] + margin and x[j] < x[i] + self.w[i] + margin
                and y[i] < y[j] + self.h[j] + margin and y[j] < y[i] + self.h[i] + margin)

    def solve(self, time_limit, rounds):
        n = len(self.items)
        Hmax = max(y + h for y, h in zip(self.y0, self.h))   # the start is feasible
        m = gp.Model("motifs")
        x = m.addVars(n, lb=0, vtype=GRB.INTEGER, name="x")
        y = m.addVars(n, lb=0, vtype=GRB.INTEGER, name="y")
        H = m.addVar(lb=0, name="H")
        for i in range(n):
            x[i].UB = self.width + 3 - self.w[i]            # w includes the gap on the right
            y[i].UB = Hmax - self.h[i]
            m.addConstr(H >= y[i] + self.h[i])
        ranks = sorted(set(self.rank))
        top = m.addVars(ranks, lb=0, name="top")
        bot = m.addVars(ranks, lb=0, name="bot")
        for i in range(n):
            m.addConstr(top[self.rank[i]] <= y[i])
            m.addConstr(bot[self.rank[i]] >= y[i] + self.h[i])
        if self.group > 0:                  # optional: keep sources in order, compact
            for s, t in zip(ranks, ranks[1:]):
                m.addConstr(top[s] <= top[t])
                m.addConstr(bot[s] <= bot[t])
        m.setObjective(H + self.group * gp.quicksum(bot[s] - top[s] for s in ranks), GRB.MINIMIZE)

        added = set()
        pairs = {}

        def side(i, j, xs, ys):
            """(p, q) of the side that separates i and j in a layout."""
            if xs[i] + self.w[i] <= xs[j]:
                return 0, 0
            if xs[j] + self.w[j] <= xs[i]:
                return 1, 0
            if ys[i] + self.h[i] <= ys[j]:
                return 0, 1
            return 1, 1

        Mx, My = self.width + 3, Hmax

        def separate(i, j):
            # two binaries pick one of four sides: (0,0) i left of j, (1,0) j left
            # of i, (0,1) i above j, (1,1) j above i
            p, q = m.addVar(vtype=GRB.BINARY), m.addVar(vtype=GRB.BINARY)
            pairs[i, j] = (p, q)
            m.addConstr(x[i] + self.w[i] <= x[j] + Mx * (p + q))
            m.addConstr(x[j] + self.w[j] <= x[i] + Mx * (1 - p + q))
            m.addConstr(y[i] + self.h[i] <= y[j] + My * (1 + p - q))
            m.addConstr(y[j] + self.h[j] <= y[i] + My * (2 - p - q))
            added.add((i, j))

        # from the start: pairs close together in the starting layout; the
        # rest only when they clash
        for i, j in itertools.combinations(range(n), 2):
            if self.near < 0 or self.overlap(i, j, self.x0, self.y0, self.near):
                separate(i, j)
        best = (self.x0, self.y0)
        clashes = [(i, j) for i, j in itertools.combinations(range(n), 2) if self.overlap(i, j, *best)]
        if clashes:
            raise SystemExit(f"the starting layout has {len(clashes)} overlaps; rebuild the items file")
        if self.near < 0:
            rounds = 1                      # every pair is in the model: one solve
        for k in range(rounds):
            # a complete start: positions, sides of every pair, height and spans
            bx, by = best
            for i in range(n):
                x[i].Start, y[i].Start = bx[i], by[i]
            for (i, j), (p, q) in pairs.items():
                p.Start, q.Start = side(i, j, bx, by)
            H.Start = max(b + h for b, h in zip(by, self.h))
            for s_ in ranks:
                top[s_].Start = min(b for b, r in zip(by, self.rank) if r == s_)
                bot[s_].Start = max(b + h for b, h, r in zip(by, self.h, self.rank) if r == s_)
            m.Params.TimeLimit = time_limit / rounds
            m.optimize()
            if m.SolCount == 0:
                break
            xs = [round(x[i].X) for i in range(n)]
            ys = [round(y[i].X) for i in range(n)]
            bad = [(i, j) for i, j in itertools.combinations(range(n), 2)
                   if (i, j) not in added and self.overlap(i, j, xs, ys, self.near)]
            clash = sum(self.overlap(i, j, xs, ys) for i, j in bad)
            print(f"round {k + 1}: height {max(a + b for a, b in zip(ys, self.h))}, {clash} overlaps")
            if not clash:
                return xs, ys
            for i, j in bad:
                separate(i, j)
        print("no overlap-free solution better than the start; keeping the start")
        return best

    def run(self, out, time_limit, rounds):
        xs, ys = self.solve(time_limit, rounds)
        write(out, ["id", "x", "y"], [(it["id"], a, b) for it, a, b in zip(self.items, xs, ys)])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sheet", choices=["bands", "motifs"])
    ap.add_argument("items", help="overview-*-items.csv from build_gallery.py")
    ap.add_argument("out", help="layout file to write (gallery/layout/*.csv)")
    ap.add_argument("--time", type=float, default=300, help="seconds for Gurobi")
    ap.add_argument("--columns", type=int, default=8, help="columns on the band sheet")
    ap.add_argument("--width", type=int, default=949, help="motif sheet width in cells (= band sheet)")
    ap.add_argument("--group", type=float, default=0.0, help="weight on each source's vertical span; >0 also keeps sources in order")
    ap.add_argument("--near", type=int, default=-1,
                    help="motifs: separate only pairs this close in the start, more lazily; -1 = all pairs at once")
    ap.add_argument("--rounds", type=int, default=15, help="lazy non-overlap rounds (motifs)")
    args = ap.parse_args()
    items = read(args.items)
    if args.sheet == "bands":
        BandPacker(items, args.columns).run(args.out, args.time)
    else:
        MotifPacker(items, args.width, args.group, args.near).run(args.out, args.time, args.rounds)


if __name__ == "__main__":
    main()
