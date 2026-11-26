#!/usr/bin/env python3
"""Do patterns travel? Sub-motifs shared by the printed European pattern
books and the Icelandic manuscripts.

A piece is a connected group of filled cells (touching at sides or
corners) of at least MIN_CELLS cells that does not touch the edge of its
chart (a cut piece is not a whole figure). Two pieces match when, after
turning or mirroring one of them (8 ways) and shifting it by up to one
cell, they share at least MATCH of their cells (intersection over union).
So a figure drawn with a cell more or less still counts as the same.

    python3 books/travel.py            (from the repository root)

reads patterns/min (Icelandic charts; repeat units are tiled so figures
that cross the cut are whole), patterns/books (European charts),
books/books.csv and gallery/map/manuscripts.csv (dates), and writes
    books/travel/shared.csv   one row per shared sub-motif: size, books,
                              manuscripts, earliest dates on each side
    books/travel/pairs.csv    every matching European/Icelandic piece pair
    books/travel/shared.png   sheet: each shared sub-motif with where it is
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "books" / "travel"
MIN_CELLS = 10
MATCH = 0.8
SHIFT = 1
NAME_RE = re.compile(r"^(?P<source>.+?)_(?P<number>\d+)(?:_p(?P<part>\d+))?$")
EIGHT = np.ones((3, 3), int)
WHITE_LINE = {"quentel1529", "jobin1600", "tagliente1530", "schoensperger1529", "egenolff1535", "gulfferich1553", "quentel1532", "vorsterman1527", "quentel1544"}   # black block, empty cells cut out

# Icelandic museum numbers as gallery file prefixes (as in manuscript_map.R)
def source_of_id(mid):
    if mid == "N.453.a":
        return "natmus453"
    if mid == "Þjms. Th 116":
        return "thjmsth_116"
    return "thjms" + mid.replace("Þjms. ", "")


class Piece:
    def __init__(self, chart, source, cells):
        self.chart, self.source, self.cells = chart, source, cells.astype(bool)
        self.n = int(self.cells.sum())
        self.views = [np.rot90(b, k) for b in (self.cells, self.cells[:, ::-1]) for k in range(4)]
        self.key = min(v.tobytes() + bytes(v.shape) for v in self.views)   # exact shape, any turn

    def dims(self):
        return tuple(sorted(self.cells.shape))

    def iou(self, other):
        a = self.cells
        best = 0.0
        for b in other.views:
            H, W = max(a.shape[0], b.shape[0]) + 2 * SHIFT, max(a.shape[1], b.shape[1]) + 2 * SHIFT
            A = np.zeros((H, W), bool)
            A[SHIFT:SHIFT + a.shape[0], SHIFT:SHIFT + a.shape[1]] = a
            for dy in range(H - b.shape[0] + 1):
                for dx in range(W - b.shape[1] + 1):
                    if abs(dy - SHIFT) > SHIFT + abs(a.shape[0] - b.shape[0]) or \
                       abs(dx - SHIFT) > SHIFT + abs(a.shape[1] - b.shape[1]):
                        continue
                    B = np.zeros((H, W), bool)
                    B[dy:dy + b.shape[0], dx:dx + b.shape[1]] = b
                    inter = (A & B).sum()
                    best = max(best, inter / (self.n + other.n - inter))
        return best


class Chart:
    def __init__(self, path, tile=False):
        self.path = Path(path)
        self.name = self.path.stem
        m = NAME_RE.match(self.name)
        self.source = m["source"] if m else self.name
        rows = [r.strip() for r in self.path.read_text().splitlines() if r.strip()]
        self.m = np.array([[c == "1" for c in r] for r in rows], bool)
        self.tile = tile

    def pieces(self):
        m = self.m
        if self.tile:                          # repeat unit: lay 3 copies, keep the middle
            m = np.tile(m, (3, 3))
        lab, n = ndimage.label(m, EIGHT)
        h, w = m.shape
        out = []
        for i, sl in enumerate(ndimage.find_objects(lab), 1):
            ys, xs = sl
            if ys.start == 0 or xs.start == 0 or ys.stop == h or xs.stop == w:
                continue                       # touches the edge: not a whole figure
            if self.tile:
                uh, uw = self.m.shape          # keep pieces that start in the middle copy
                if not (uh <= ys.start < 2 * uh and uw <= xs.start < 2 * uw):
                    continue
            cells = lab[sl] == i
            if cells.sum() >= MIN_CELLS and cells.shape[0] > 1 and cells.shape[1] > 1:
                out.append(Piece(self.name, self.source, cells))
        # one copy per exact shape per chart
        seen, uniq = set(), []
        for p in out:
            if p.key not in seen:
                seen.add(p.key); uniq.append(p)
        return uniq


class Travel:
    def __init__(self):
        units = self.read_units()
        self.ice = [Chart(p, tile=p.stem in units) for p in sorted((ROOT / "patterns/min").glob("*.txt"))]
        self.books = {r["code"]: r for r in csv.DictReader(open(ROOT / "books/books.csv", encoding="utf-8"))}
        self.eur = []
        for p in sorted((ROOT / "patterns/books").glob("*.txt")):
            c = Chart(p)
            self.eur.append(c)
            if "woodcut" in self.books.get(c.source, {}).get("kind", "") and c.source in WHITE_LINE:
                inv = Chart(p); inv.m = ~inv.m        # cut in negative: try both readings
                self.eur.append(inv)
        self.mss = {}
        for r in csv.DictReader(open(ROOT / "gallery/map/manuscripts.csv", encoding="utf-8")):
            self.mss[source_of_id(r["id"])] = r

    @staticmethod
    def read_units():
        f = ROOT / "patterns/repeats.csv"
        with open(f, newline="") as fh:
            return {r["name"] for r in csv.DictReader(fh) if r["status"] == "unit"}

    def date(self, source):
        if source in self.books:
            return int(self.books[source]["first_edition"] or self.books[source]["year"])
        r = self.mss.get(source)
        return int(r["when_start"]) if r and r["when_start"] else None

    def label(self, source):
        if source in self.books:
            b = self.books[source]
            return f"{b['publisher'] or b['author']}, {b['place']} {b['year']}"
        r = self.mss.get(source)
        return f"{r['id']} ({r['when_label']})" if r else source

    def run(self):
        OUT.mkdir(parents=True, exist_ok=True)
        ep = [p for c in self.eur for p in c.pieces()]
        ip = [p for c in self.ice for p in c.pieces()]
        print(f"{len(ep)} European pieces, {len(ip)} Icelandic pieces")
        by_dims = defaultdict(list)
        for p in ip:
            by_dims[p.dims()].append(p)
        pairs = []
        for a in ep:
            h, w = a.dims()
            for dh in (-1, 0, 1):
                for dw in (-1, 0, 1):
                    for b in by_dims.get((h + dh, w + dw), []):
                        if abs(a.n - b.n) > (1 - MATCH) * max(a.n, b.n) * 1.2:
                            continue
                        s = 1.0 if a.key == b.key else a.iou(b)
                        if s >= MATCH:
                            pairs.append((a, b, s))
        # group: one shared sub-motif per European exact shape, joined when
        # they match the same Icelandic piece
        parent = {}
        def find(x):
            while parent.setdefault(x, x) != x:
                x = parent[x]
            return x
        for a, b, s in pairs:
            parent[find(("e", a.key))] = find(("i", b.key))
        groups = defaultdict(lambda: {"e": {}, "i": {}, "best": 0})
        for a, b, s in pairs:
            g = groups[find(("e", a.key))]
            g["e"].setdefault(a.source, set()).add(a.chart)
            g["i"].setdefault(b.source, set()).add(b.chart)
            g.setdefault("piece", a)
            g["exact"] = g.get("exact", False) or s == 1.0
        rows = []
        for gid, g in groups.items():
            p = g["piece"]
            ed = min(self.date(s) for s in g["e"])
            idates = [d for d in (self.date(s) for s in g["i"]) if d]
            rows.append(dict(
                cells=p.n, size=f"{p.cells.shape[1]}x{p.cells.shape[0]}", exact=g["exact"],
                books=len(g["e"]), manuscripts=len(g["i"]),
                book_sources="; ".join(sorted(g["e"])), manuscript_sources="; ".join(sorted(g["i"])),
                book_charts="; ".join(sorted(c for s in g["e"].values() for c in s)),
                manuscript_charts="; ".join(sorted(c for s in g["i"].values() for c in s)),
                earliest_book=ed, earliest_manuscript=min(idates) if idates else "",
                rows="/".join("".join("1" if v else "0" for v in r) for r in p.cells)))
        # specific figures first: shared by several manuscripts, larger
        rows.sort(key=lambda r: (-(r["manuscripts"] + r["books"]), -r["cells"]))
        with open(OUT / "shared.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        with open(OUT / "pairs.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["book_chart", "manuscript_chart", "cells", "iou"])
            for a, b, s in pairs:
                w.writerow([a.chart, b.chart, a.n, round(s, 3)])
        self.sheet(rows)
        print(f"{len(rows)} shared sub-motifs -> {OUT}")
        return rows

    def sheet(self, rows, top=48, z=7):
        tiles = []
        for r in rows[:top]:
            cells = np.array([[c == "1" for c in line] for line in r["rows"].split("/")])
            img = Image.new("RGB", (220, 30 + max(cells.shape[0] * z, 40) + 34), "white")
            d = ImageDraw.Draw(img)
            for y, x in zip(*np.nonzero(cells)):
                d.rectangle([4 + x * z, 4 + y * z, 4 + x * z + z - 2, 4 + y * z + z - 2], fill=(16, 9, 159))
            ty = 8 + cells.shape[0] * z
            d.text((4, ty), f"{r['cells']} cells, {r['books']} book(s), {r['manuscripts']} ms.", fill=(0, 0, 0))
            d.text((4, ty + 12), f"book {r['earliest_book']}: {r['book_sources'][:30]}", fill=(80, 80, 80))
            d.text((4, ty + 24), f"Iceland {r['earliest_manuscript'] or '?'}: {r['manuscript_sources'][:28]}", fill=(80, 80, 80))
            tiles.append(img)
        if not tiles:
            return
        cols = 6
        W = cols * 224
        rowsh = [max(t.height for t in tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
        sheet = Image.new("RGB", (W, sum(rowsh) + 4 * len(rowsh)), "white")
        y = 0
        for k, i in enumerate(range(0, len(tiles), cols)):
            for j, t in enumerate(tiles[i:i + cols]):
                sheet.paste(t, (j * 224, y))
            y += rowsh[k] + 4
        sheet.save(OUT / "shared.png")


if __name__ == "__main__":
    Travel().run()
