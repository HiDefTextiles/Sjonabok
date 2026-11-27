"""Condense every chart to its smallest seed plus a symmetry recipe.

    python3 condense.py find  patterns/txt patterns     (make seeds)
    python3 condense.py check patterns                  (make seeds-check)
    python3 condense.py build patterns out_dir          (rebuild every chart)
    python3 condense.py sheet patterns out.png          (before/after picture)

`find` reads the full charts (patterns/txt, restored by `make originals`)
and writes two committed files:

    patterns/seeds.csv  one row per chart
        name        file name without .txt
        kind        border, edging, vertical band, motif or rosette (as in the gallery)
        group       exact symmetry: frieze group of the repeat for bands
                    (p1, p11g, p1m1, p2, p2mg, p11m, p2mm; read left to right),
                    point group for motifs (C1, C2, C4, D1, D2, D4);
                    "tiled <group>" when a motif chart is one motif repeated,
                    empty for a band with no exact repeat
        seen        the gallery's group, which allows 2 % of cells to differ;
                    where it differs from group, see near.csv
        chart       height x width of the full chart
        chart_cells, min_cells, seed_cells
                    cells in the full chart, in patterns/min, in the seed
        shrink      chart_cells / seed_cells
        min_shift   for a band stored in patterns/min as one repeat: roll the
                    repeat built by the recipe by this many cells to get
                    the stored unit (empty for other charts)
        recipe      steps from the seed outwards (see pattern_processing/fundamental.py)
        seed        the seed, rows joined by "/" (a triangle has shorter rows)

    patterns/near.csv   symmetries that almost hold but are not used
        name, block (the block tested, h x w), check (mirror x, turn,
        repeat 18, ...; several when the same cells break each), cells
        (chart cells that break it), where (those cells as row:col, at most 40)

`check` rebuilds every chart from seeds.csv and compares it cell for cell
with patterns/txt (when present) and patterns/min. It needs only the
committed files.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "gallery" / "scripts"))
from build_gallery import Pattern  # noqa: E402  (shared type classification)
from pattern_processing.fundamental import (  # noqa: E402
    Recipe, SeedFinder, Tile, frieze_group, near_symmetries, point_group, seed_to_text)
from pattern_processing.pattern_to_png import COLOR_PALETTE  # noqa: E402

BANDS = {"border": "x", "edging": "x", "vertical band": "y"}
FIELDS = ["name", "kind", "group", "seen", "chart", "chart_cells", "min_cells", "seed_cells",
          "shrink", "min_shift", "recipe", "seed"]
NEAR_FIELDS = ["name", "block", "check", "cells", "where"]


def read_chart(path):
    rows = [r.strip() for r in Path(path).read_text().splitlines() if r.strip()]
    return np.array([[int(c) for c in r] for r in rows], dtype=np.uint8)


class Condensed:
    """One chart, its recipe and what is known about it."""

    def __init__(self, path, min_dir):
        self.path = Path(path)
        self.name = self.path.stem
        self.chart = read_chart(path)
        self.min = read_chart(Path(min_dir) / self.path.name)
        p = Pattern(self.path).measure()
        self.kind = p.kind
        self.seen = p.point if self.kind in ("motif", "rosette") else (p.frieze or "")
        self.axis = BANDS.get(self.kind)
        self.recipe = SeedFinder().recipe(self.chart)
        self.near = []

    def tile_level(self, axis):
        for i, s in enumerate(self.recipe.steps):
            if isinstance(s, Tile) and s.axis == axis:
                return i
        return None

    def group(self):
        if self.axis:
            level = self.tile_level(self.axis)
            if level is None:
                return ""
            unit = self.recipe.build(level)
            return frieze_group(unit.T if self.axis == "y" else unit)
        tiles = [i for i, s in enumerate(self.recipe.steps) if isinstance(s, Tile)]
        if tiles:   # one motif repeated: the symmetry of the repeat, wherever it is centred
            cell = self.recipe.build(min(tiles))
            return "tiled " + point_group(cell, {self.recipe.steps[i].axis for i in tiles})
        pad_free = self.recipe.build(len([s for s in self.recipe.steps if s.name != "pad"]))
        return point_group(pad_free)

    def min_shift(self):
        """Roll that turns the recipe's repeat into the unit in patterns/min."""
        if self.min.shape == self.chart.shape and np.array_equal(self.min, self.chart):
            return ""
        level = self.tile_level(self.axis) if self.axis else None
        if level is None:
            raise ValueError(f"{self.name}: patterns/min differs from the chart but has no repeat")
        unit = self.recipe.build(level)
        dim = 1 if self.axis == "x" else 0
        for k in range(unit.shape[dim]):
            if unit.shape == self.min.shape and np.array_equal(np.roll(unit, k, axis=dim), self.min):
                return k
        raise ValueError(f"{self.name}: no roll of the repeat matches patterns/min")

    def row(self):
        r = self.recipe
        built = r.build()
        if not np.array_equal(built, self.chart):
            raise ValueError(f"{self.name}: recipe does not rebuild the chart")
        h, w = self.chart.shape
        return {
            "name": self.name, "kind": self.kind, "group": self.group(), "seen": self.seen,
            "chart": f"{h}x{w}", "chart_cells": h * w, "min_cells": self.min.size,
            "seed_cells": r.cells, "shrink": f"{h * w / r.cells:.1f}",
            "min_shift": self.min_shift(), "recipe": r.text(), "seed": seed_to_text(r.seed),
        }

    def near_rows(self):
        rows = []
        for n in near_symmetries(self.recipe, self.axis):
            ys, xs = np.nonzero(n["mask"])
            where = " ".join(f"{y}:{x}" for y, x in list(zip(ys, xs))[:40])
            rows.append({"name": self.name, "block": n["block"], "check": ", ".join(n["checks"]),
                         "cells": n["cells"], "where": where})
            self.near.append(n)
        return rows


class SeedTable:
    """seeds.csv: read, rebuild and check."""

    def __init__(self, out_dir):
        self.out_dir = Path(out_dir)
        self.csv = self.out_dir / "seeds.csv"

    def find(self, txt_dir):
        rows, near = [], []
        for path in sorted(Path(txt_dir).glob("*.txt")):
            c = Condensed(path, self.out_dir / "min")
            rows.append(c.row())
            near.extend(c.near_rows())
        self.write(self.csv, FIELDS, rows)
        self.write(self.out_dir / "near.csv", NEAR_FIELDS, near)
        self.summary(rows, near)

    @staticmethod
    def write(path, fields, rows):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    def rows(self):
        with open(self.csv, newline="") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def rebuild(row):
        return Recipe.parse(row["seed"], row["recipe"]).build()

    @staticmethod
    def rebuild_min(row):
        r = Recipe.parse(row["seed"], row["recipe"])
        if row["min_shift"] == "":
            return r.build()
        axis = BANDS[row["kind"]]
        level = next(i for i, s in enumerate(r.steps) if isinstance(s, Tile) and s.axis == axis)
        dim = 1 if axis == "x" else 0
        return np.roll(r.build(level), int(row["min_shift"]), axis=dim)

    def check(self):
        txt_dir, min_dir = self.out_dir / "txt", self.out_dir / "min"
        bad, n_txt = [], 0
        rows = self.rows()
        for row in rows:
            name = row["name"] + ".txt"
            if not np.array_equal(self.rebuild_min(row), read_chart(min_dir / name)):
                bad.append(f"{row['name']} (min)")
            if (txt_dir / name).exists():
                n_txt += 1
                if not np.array_equal(self.rebuild(row), read_chart(txt_dir / name)):
                    bad.append(f"{row['name']} (txt)")
        listed = {r["name"] for r in rows}
        missing = [p.stem for p in min_dir.glob("*.txt") if p.stem not in listed]
        print(f"{len(rows)} seeds rebuilt: {len(rows)} checked against patterns/min, "
              f"{n_txt} against patterns/txt; {len(bad)} differ; {len(missing)} charts without a seed")
        for b in bad + missing:
            print("  ", b)
        return not bad and not missing

    def build(self, out):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        for row in self.rows():
            m = self.rebuild(row)
            (out / f"{row['name']}.txt").write_text(
                "\n".join("".join(str(c) for c in r) for r in m) + "\n")

    @staticmethod
    def summary(rows, near):
        tot = lambda k: sum(int(r[k]) for r in rows)
        print(f"{len(rows)} charts: {tot('chart_cells')} cells in full charts, "
              f"{tot('min_cells')} in patterns/min, {tot('seed_cells')} in seeds "
              f"({tot('chart_cells') / tot('seed_cells'):.1f}x and "
              f"{tot('min_cells') / tot('seed_cells'):.1f}x smaller)")
        names = {n["name"] for n in near}
        print(f"{len(near)} near symmetries on {len(names)} charts -> near.csv")


class Sheet:
    """Before/after picture: each chart beside its seed, cells that break a
    near symmetry in red."""

    ZOOM, GAP = 4, 8

    def __init__(self, table, names=None, kinds=None, limit=24):
        rows = table.rows()
        near = {}
        with open(table.out_dir / "near.csv", newline="") as f:
            for r in csv.DictReader(f):
                near.setdefault(r["name"], []).append(r)
        if names:
            rows = [r for r in rows if r["name"] in names]
        else:
            rows = sorted(rows, key=lambda r: -float(r["shrink"]))[:limit]
        self.rows, self.near = rows, near

    def seed_image(self, row):
        r = Recipe.parse(row["seed"], row["recipe"])
        s = r.seed
        if isinstance(s, list):          # triangle: draw in place, unused cells pale
            n = len(s)
            img = np.full((n, n), 2, np.uint8)
            diag = r.steps[0].name == "diag"
            for i, cells in enumerate(s):
                if diag:
                    img[i, i:] = cells
                else:
                    img[i, :n - i] = cells
            return img
        return s.astype(np.uint8)

    def chart_image(self, row):
        chart = SeedTable.rebuild(row).astype(np.uint8)
        m = chart.copy()
        for n in self.near.get(row["name"], []):
            for yx in n["where"].split():
                y, x = map(int, yx.split(":"))
                m[y, x] = 3 + chart[y, x]
        return m

    def save(self, out):
        pal = np.array([(255, 255, 255), COLOR_PALETTE[1][:3], (225, 225, 225),
                        (255, 170, 170), (200, 0, 0)], np.uint8)
        z, g = self.ZOOM, self.GAP
        pairs = [(self.chart_image(r), self.seed_image(r)) for r in self.rows]
        width = max(a.shape[1] + b.shape[1] for a, b in pairs) * z + 3 * g
        height = sum(max(a.shape[0], b.shape[0]) * z + g for a, b in pairs) + g
        canvas = np.full((height, width, 3), 246, np.uint8)
        y = g
        for a, b in pairs:
            for img, x in ((a, g), (b, 2 * g + a.shape[1] * z)):
                px = np.kron(pal[img], np.ones((z, z, 1), np.uint8))
                canvas[y:y + px.shape[0], x:x + px.shape[1]] = px
            y += max(a.shape[0], b.shape[0]) * z + g
        Image.fromarray(canvas).save(out, optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("txt_dir", nargs="?", default="patterns/txt")
    f.add_argument("out_dir", nargs="?", default="patterns")
    c = sub.add_parser("check")
    c.add_argument("out_dir", nargs="?", default="patterns")
    b = sub.add_parser("build")
    b.add_argument("out_dir", nargs="?", default="patterns")
    b.add_argument("dest")
    s = sub.add_parser("sheet")
    s.add_argument("out_dir", nargs="?", default="patterns")
    s.add_argument("png")
    s.add_argument("--names", nargs="*")
    s.add_argument("--limit", type=int, default=24)
    a = ap.parse_args()
    table = SeedTable(a.out_dir)
    if a.cmd == "find":
        table.find(a.txt_dir)
    elif a.cmd == "check":
        sys.exit(0 if table.check() else 1)
    elif a.cmd == "build":
        table.build(a.dest)
    else:
        Sheet(table, a.names, limit=a.limit).save(a.png)


if __name__ == "__main__":
    main()
