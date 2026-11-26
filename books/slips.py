#!/usr/bin/env python3
"""Find reading slips in charts read from printed books, using symmetry.

A printed band is (nearly always) drawn with exact symmetry: it repeats along
its length and is usually mirrored left/right and top/bottom. A reader that
makes a mistake breaks that symmetry in one cell. So for every chart we find
the symmetries that almost hold, gather each cell with all the cells the
symmetries map it to (its orbit), and where a clear majority of the orbit
disagrees with the cell, the cell is a likely reading slip and the majority
value is the proposed edit. This is a reading correction, not a design
choice: the original is kept in books/corrections.csv (column `read`).

    python3 books/slips.py find   [charts...]   # -> books/corrections.csv
    python3 books/slips.py apply                # edit patterns/books
    python3 books/slips.py revert               # put the read values back

`make slips` runs find + apply. Charts with no clear symmetry are skipped.
"""
import csv
import sys
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "patterns" / "books"
CSV = ROOT / "books" / "corrections.csv"
FIELDS = ["chart", "row", "col", "read", "proposed", "orbit", "agree", "symmetries", "status"]


class Symmetry:
    """A map from cell (r, c) to cell (r', c'), and how well it holds."""

    def __init__(self, name, fn, mismatch):
        self.name, self.fn, self.mismatch = name, fn, mismatch

    def __call__(self, r, c):
        return self.fn(r, c)

    def __repr__(self):
        return f"{self.name} ({100 * self.mismatch:.1f}% off)"


class SlipFinder:
    """Symmetries that almost hold in one chart, and the cells that break them."""

    MAX_MISMATCH = 0.05      # a symmetry must hold in at least 95% of cells
    MAX_SLIPS = 0.015        # more slips than this share of cells: flag for review, don't edit
    MIN_ORBIT = 3            # cell plus at least two images
    MAJORITY = 0.75          # share of the other cells in the orbit that must disagree

    def __init__(self, name, m):
        self.name, self.m = name, m
        self.h, self.w = m.shape
        self.symmetries = []

    @staticmethod
    def load(path):
        return np.array([[int(ch) for ch in line] for line in Path(path).read_text().split()])

    def inside(self, r, c):
        return 0 <= r < self.h and 0 <= c < self.w

    def _shift_mismatch(self, p):
        """Repeat by p columns: compare the overlap."""
        a, b = self.m[:, :self.w - p], self.m[:, p:]
        return (a != b).mean(), a.size

    def _mirror_mismatch(self, a2, axis):
        """Mirror about index a2/2 along axis 1 (left/right) or 0 (top/bottom)."""
        m = self.m if axis == 1 else self.m.T
        n = m.shape[1]
        lo, hi = max(0, a2 - (n - 1)), min(n - 1, a2)
        if hi - lo < 1:
            return 1.0, 0
        left = m[:, lo:hi + 1]
        right = m[:, lo:hi + 1][:, ::-1]           # column c pairs with a2 - c
        return (left != right).mean(), left.size

    def find_symmetries(self):
        h, w = self.h, self.w
        area = h * w
        cands = []
        # repeat along the band (shortest period that holds)
        for p in range(4, w - max(8, w // 4)):
            mm, n = self._shift_mismatch(p)
            if n >= area // 3 and mm <= self.MAX_MISMATCH:
                cands.append(Symmetry(f"repeat {p}", (lambda p: lambda r, c: (r, c + p))(p), mm))
                break
        # mirror left/right and top/bottom: best axis whose overlap covers a third of the chart
        for name, axis, size, make in (("left/right", 1, w, lambda a: lambda r, c: (r, a - c)),
                                       ("top/bottom", 0, h, lambda a: lambda r, c: (a - r, c))):
            best = None
            for a2 in range(1, 2 * size - 2):            # a2 = 2 * axis position
                mm, n = self._mirror_mismatch(a2, axis)
                if n >= area // 3 and (best is None or mm < best[0]):
                    best = (mm, a2)
            if best and best[0] <= self.MAX_MISMATCH:
                cands.append(Symmetry(f"mirror {name} at {best[1] / 2:g}", make(best[1]), best[0]))
        self.symmetries = cands
        return cands

    def orbit(self, r, c):
        seen, todo = {(r, c)}, deque([(r, c)])
        while todo:
            cell = todo.popleft()
            for s in self.symmetries:
                nxt = s(*cell)
                if self.inside(*nxt) and nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return seen

    def slips(self):
        if not self.symmetries:
            return []
        out = []
        for r in range(self.h):
            for c in range(self.w):
                orb = self.orbit(r, c) - {(r, c)}
                if len(orb) + 1 < self.MIN_ORBIT:
                    continue
                vals = [self.m[x] for x in orb]
                other = 1 - self.m[r, c]
                agree = sum(v == other for v in vals)
                if agree / len(vals) >= self.MAJORITY:
                    out.append(dict(chart=self.name, row=r, col=c, read=int(self.m[r, c]),
                                    proposed=int(other), orbit=len(orb) + 1, agree=agree,
                                    symmetries="; ".join(map(repr, self.symmetries)),
                                    status="applied"))
        if len(out) > self.MAX_SLIPS * self.m.size:
            for row in out:
                row["status"] = "review"
        return out


class Corrections:
    """books/corrections.csv: one row per edited cell, original value kept."""

    def __init__(self, path=CSV):
        self.path = path
        self.rows = list(csv.DictReader(open(path))) if path.exists() else []

    def replace(self, charts, rows):
        self.rows = [r for r in self.rows if r["chart"] not in charts] + rows
        with open(self.path, "w", newline="") as f:
            wr = csv.DictWriter(f, FIELDS, lineterminator="\n")
            wr.writeheader()
            wr.writerows(self.rows)

    def edit(self, column):
        by_chart = {}
        for r in self.rows:
            if r["status"] == "applied":
                by_chart.setdefault(r["chart"], []).append(r)
        for chart, rows in by_chart.items():
            p = CHARTS / f"{chart}.txt"
            m = SlipFinder.load(p)
            other = "read" if column == "proposed" else "proposed"
            for r in rows:
                i, j = int(r["row"]), int(r["col"])
                # skip edits that no longer fit (chart re-read since `find`)
                if i < m.shape[0] and j < m.shape[1] and m[i, j] in (int(r[other]), int(r[column])):
                    m[i, j] = int(r[column])
                else:
                    print(f"{chart}: cell {i},{j} changed since the check, run `find` again")
            p.write_text("\n".join("".join(map(str, row)) for row in m) + "\n")
        return len(by_chart)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "find"
    corr = Corrections()
    if cmd == "find":
        names = sys.argv[2:] or sorted(p.stem for p in CHARTS.glob("*.txt"))
        # never look for slips in a chart that already has edits applied
        corr.edit("read")
        found = []
        for name in names:
            f = SlipFinder(name, SlipFinder.load(CHARTS / f"{name}.txt"))
            f.find_symmetries()
            s = f.slips()
            found += s
            if s:
                print(f"{name}: {len(s)} {s[0]['status']}; {f.symmetries}")
        corr.replace(set(names), found)
        ok = [r for r in found if r["status"] == "applied"]
        print(f"{len(ok)} slips to edit in {len({r['chart'] for r in ok})} charts, "
              f"{len(found) - len(ok)} cells in {len({r['chart'] for r in found}) - len({r['chart'] for r in ok})} charts to review"
              f" -> {CSV.relative_to(ROOT)}")
    elif cmd == "apply":
        print(f"edited {corr.edit('proposed')} charts")
    elif cmd == "revert":
        print(f"restored {corr.edit('read')} charts")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
