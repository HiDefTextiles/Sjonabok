"""Optimise the overview sheets with Gurobi.

Reads the item files written by build_gallery.py and writes layout files
that build_gallery.py then uses instead of its simple packing:

    python gallery/scripts/pack_overview.py bands  gallery/patterns/overview-band-items.csv  gallery/layout/bands.csv
    python gallery/scripts/pack_overview.py motifs gallery/patterns/overview-motif-items.csv gallery/layout/motifs.csv

Only this script needs gurobipy (and a licence); the site build does not.

Bands: each band goes into one row. A row is as tall as its tallest band
and its bands share the width, so a band's length is free (it repeats).
Minimise the total height of the rows. Sources keep their order: every row
of source s comes no later than every row of source s+1 (rows may be
shared where one source ends and the next begins).

Motifs: rectangles (chart + gap) on a strip of fixed width, no overlap,
no rotation. Minimise the sheet height plus GROUP times the total vertical
span of each source; sources keep their order top to bottom (first and
last rows of source s are at or above those of s+1). Non-overlap is added
lazily: start with pairs near each other in the starting layout, solve,
add the pairs that overlap, repeat.
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
    """Assign bands to rows (see module docstring)."""

    def __init__(self, items, gap=3):
        self.items, self.gap = items, gap
        self.h = [int(r["h"]) for r in items]
        self.cap = [int(r["max_per_row"]) for r in items]
        self.rank = [int(r["rank"]) for r in items]

    def greedy(self):
        """Starting rows: within each source by height, rows closed when full."""
        order = sorted(range(len(self.items)), key=lambda i: (self.rank[i], self.h[i]))
        row, r, members = [0] * len(order), 0, []
        for i in order:
            if members and len(members) + 1 > min(self.cap[j] for j in members + [i]):
                r, members = r + 1, []
            members.append(i)
            row[i] = r
        return row

    def solve(self, time_limit):
        n, start = len(self.items), self.greedy()
        R = max(start) + 1                         # never need more rows than the start
        m = gp.Model("bands")
        m.Params.TimeLimit = time_limit
        a = m.addVars(n, R, vtype=GRB.BINARY, name="a")
        used = m.addVars(R, vtype=GRB.BINARY, name="used")
        H = m.addVars(R, lb=0, name="H")
        pos = m.addVars(n, lb=0, ub=R - 1, name="row")        # row index of each band
        for i in range(n):
            m.addConstr(a.sum(i, "*") == 1)
            m.addConstr(pos[i] == gp.quicksum(r * a[i, r] for r in range(R)))
            for r in range(R):
                m.addConstr(H[r] >= self.h[i] * a[i, r])
                # a row holds no more bands than any of its members allows
                m.addConstr(a.sum("*", r) <= self.cap[i] + n * (1 - a[i, r]))
        for r in range(R):
            m.addConstr(a.sum("*", r) <= n * used[r])
            if r + 1 < R:
                m.addConstr(used[r] >= used[r + 1])           # rows used from the top
        # sources in order: last row of s <= first row of s+1
        ranks = sorted(set(self.rank))
        last = m.addVars(ranks, lb=0, name="last")
        first = m.addVars(ranks, lb=0, name="first")
        for i in range(n):
            m.addConstr(last[self.rank[i]] >= pos[i])
            m.addConstr(first[self.rank[i]] <= pos[i])
        for s, t in zip(ranks, ranks[1:]):
            m.addConstr(last[s] <= first[t])
        m.setObjective(gp.quicksum(H[r] + self.gap * used[r] for r in range(R)), GRB.MINIMIZE)
        for i in range(n):                                     # warm start
            for r in range(R):
                a[i, r].Start = 1 if start[i] == r else 0
        m.optimize()
        row = [next(r for r in range(R) if a[i, r].X > 0.5) for i in range(n)]
        # renumber the rows that are used, top to bottom
        keep = {r: k for k, r in enumerate(sorted(set(row)))}
        return [keep[r] for r in row]

    def run(self, out, time_limit):
        row = self.solve(time_limit)
        write(out, ["id", "row"], [(it["id"], r) for it, r in zip(self.items, row)])


class MotifPacker:
    """Strip packing with source order (see module docstring)."""

    def __init__(self, items, width, group=0.2, near=40):
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
        for s, t in zip(ranks, ranks[1:]):
            m.addConstr(top[s] <= top[t])
            m.addConstr(bot[s] <= bot[t])
        m.setObjective(H + self.group * gp.quicksum(bot[s] - top[s] for s in ranks), GRB.MINIMIZE)

        added = set()

        Mx, My = self.width + 3, Hmax

        def separate(i, j):
            # two binaries pick one of four sides: (0,0) i left of j, (1,0) j left
            # of i, (0,1) i above j, (1,1) j above i
            p, q = m.addVar(vtype=GRB.BINARY), m.addVar(vtype=GRB.BINARY)
            m.addConstr(x[i] + self.w[i] <= x[j] + Mx * (p + q))
            m.addConstr(x[j] + self.w[j] <= x[i] + Mx * (1 - p + q))
            m.addConstr(y[i] + self.h[i] <= y[j] + My * (1 + p - q))
            m.addConstr(y[j] + self.h[j] <= y[i] + My * (2 - p - q))
            added.add((i, j))

        # from the start: pairs of the same or neighbouring sources, and pairs
        # close together in the starting layout; the rest only when they clash
        for i, j in itertools.combinations(range(n), 2):
            if abs(self.rank[i] - self.rank[j]) <= 1 or self.overlap(i, j, self.x0, self.y0, self.near):
                separate(i, j)
        best = (self.x0, self.y0)
        for k in range(rounds):
            for i in range(n):
                x[i].Start, y[i].Start = best[0][i], best[1][i]
            m.Params.TimeLimit = time_limit / rounds
            m.optimize()
            if m.SolCount == 0:
                break
            xs = [round(x[i].X) for i in range(n)]
            ys = [round(y[i].X) for i in range(n)]
            bad = [(i, j) for i, j in itertools.combinations(range(n), 2)
                   if (i, j) not in added and self.overlap(i, j, xs, ys, self.near // 4)]
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
    ap.add_argument("--width", type=int, default=720, help="motif sheet width in cells")
    ap.add_argument("--group", type=float, default=0.2, help="weight on each source's vertical span")
    ap.add_argument("--rounds", type=int, default=10, help="lazy non-overlap rounds (motifs)")
    args = ap.parse_args()
    items = read(args.items)
    if args.sheet == "bands":
        BandPacker(items).run(args.out, args.time)
    else:
        MotifPacker(items, args.width, args.group).run(args.out, args.time, args.rounds)


if __name__ == "__main__":
    main()
