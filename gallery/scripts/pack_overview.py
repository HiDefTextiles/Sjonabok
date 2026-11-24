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

Motifs (default, no Gurobi needed): skyline packing improved by a seeded
local search over the order (MotifSearch), minimising the height; the
result is then spread so the white is even through the sheet. Long runs
write the best layout every --checkpoint seconds. With --mip:
rectangles (chart + gap) on a strip as wide as the band sheet,
no overlap, no rotation; minimise the height. Colours may mix (--group > 0
adds a weight on each source's vertical span and keeps sources in order).
Non-overlap is added lazily: start with pairs near each other in the
starting layout, solve, add the pairs that clash, repeat.
"""

import argparse
import csv
import itertools
import math

import random
import time

try:                       # only the Gurobi models need it
    import gurobipy as gp
    from gurobipy import GRB
except ImportError:
    gp = GRB = None


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


class MotifSearch:
    """Motif sheet without Gurobi: bottom-left skyline packing of an order
    of the charts, improved by a seeded local search that swaps nearby
    charts in the order and keeps any swap that is no taller. On this sheet
    it beats the MIP, whose bound stays far from any packing."""

    def __init__(self, items, width, gap=3, seed=1):
        self.items, self.W = items, width + gap         # w and h include the gap
        self.w = [int(r["w"]) for r in items]
        self.h = [int(r["h"]) for r in items]
        self.rng = random.Random(seed)

    def place(self, order):
        """Positions and height of a bottom-left skyline packing of order."""
        sky = [0] * self.W
        pos, height = [None] * len(order), 0
        for i in order:
            w, h = self.w[i], self.h[i]
            steps = [0] + [x for x in range(1, self.W) if sky[x] != sky[x - 1]] + [self.W - w]
            y, x = min((max(sky[x:x + w]), x) for x in steps if x + w <= self.W)
            sky[x:x + w] = [y + h] * w
            pos[i], height = (x, y), max(height, y + h)
        return pos, height

    def spread(self, pos, height):
        """Even out the empty space: every chart also gets its lowest
        position (the same packing dropped to the bottom edge, keeping x),
        and goes halfway between the two. Charts that share columns keep
        their order in both, so the halfway layout cannot overlap; the
        white left at the ragged bottom is spread through the sheet."""
        floor = [height] * self.W
        down = [None] * len(pos)
        for i in sorted(range(len(pos)), key=lambda i: -pos[i][1]):
            x, w, h = pos[i][0], self.w[i], self.h[i]
            y = min(floor[x:x + w]) - h
            floor[x:x + w] = [y] * w
            down[i] = y
        return [(x, (y + d) // 2) for (x, y), d in zip(pos, down)]

    def save(self, out, order):
        pos, height = self.place(order)
        pos = self.spread(pos, height)
        write(out, ["id", "x", "y"], [(it["id"], *p) for it, p in zip(self.items, pos)])
        return height

    def run(self, out, seconds, checkpoint=3600):
        n = len(self.items)
        starts = {
            "area": sorted(range(n), key=lambda i: -self.w[i] * self.h[i]),
            "height": sorted(range(n), key=lambda i: (-self.h[i], -self.w[i])),
            "longest side": sorted(range(n), key=lambda i: -max(self.w[i], self.h[i])),
        }
        best = min(((self.place(o)[1], name, o) for name, o in starts.items()), key=lambda t: t[0])
        print(f"start ({best[1]} first): height {best[0] - 3}", flush=True)
        height, order = best[0], best[2]
        bound = sum(a * b for a, b in zip(self.w, self.h)) / self.W
        self.save(out, order)
        t0 = time.time()
        end, next_save, saved = t0 + seconds, t0 + checkpoint, height
        while time.time() < end:
            trial = list(order)
            if self.rng.random() < 0.5:                 # swap a few nearby charts
                for _ in range(self.rng.randint(1, 3)):
                    i = self.rng.randrange(n)
                    j = min(n - 1, i + self.rng.randrange(1, 8))
                    trial[i], trial[j] = trial[j], trial[i]
            else:                                       # move one chart elsewhere in the order
                trial.insert(self.rng.randrange(n), trial.pop(self.rng.randrange(n)))
            h = self.place(trial)[1]
            if h <= height:
                if h < height:
                    print(f"{(time.time() - t0) / 60:6.1f} min: height {h - 3}", flush=True)
                height, order = h, trial
            if time.time() >= next_save:
                if height < saved:
                    self.save(out, order)
                    saved = height
                    print(f"checkpoint: wrote {out} (height {height - 3})", flush=True)
                next_save += checkpoint
        self.save(out, order)
        print(f"final height {height - 3} cells (lower bound from area {bound - 3:.0f})", flush=True)


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
    ap.add_argument("--mip", action="store_true", help="motifs: use the Gurobi MIP instead of the local search")
    ap.add_argument("--checkpoint", type=float, default=3600, help="motifs: write the best layout so far every this many seconds")
    ap.add_argument("--seed", type=int, default=1, help="motifs: seed of the local search")
    ap.add_argument("--rounds", type=int, default=15, help="lazy non-overlap rounds (motifs)")
    args = ap.parse_args()
    items = read(args.items)
    if args.sheet == "bands":
        BandPacker(items, args.columns).run(args.out, args.time)
    elif args.mip:
        MotifPacker(items, args.width, args.group, args.near).run(args.out, args.time, args.rounds)
    else:
        MotifSearch(items, args.width, seed=args.seed).run(args.out, args.time, args.checkpoint)


if __name__ == "__main__":
    main()
