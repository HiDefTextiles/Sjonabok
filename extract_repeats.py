"""Write the repeat unit of every border band and a manifest.

    python3 extract_repeats.py patterns/txt patterns     (or: make repeats)

Output (committed, so other projects such as pattern-synthesis can use it):
    patterns/repeat/<name>.txt   one repeat unit, 0/1 rows like patterns/txt
    patterns/repeats.csv         one row per band:
        name      file name without .txt
        kind      border, edging or vertical band
        axis      x = repeats left to right, y = top to bottom
        period    cells per repeat (empty if no repeat was found)
        phase     column (x) or row (y) in the original chart where a clean
                  unit starts, counted from 0
        copies    full repeats in the chart
        status    ok (≤2 % of cells differ from the ideal repeat), check
                  (≤6 %), poor, or none (no repeat found)
        mismatch  share of the chart's cells that differ from the ideal repeat

The unit is a majority vote over every full copy in the chart, so a single
slip in one copy does not end up in the unit.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "gallery" / "scripts"))
from build_gallery import Pattern  # noqa: E402  (shared type classification)
from pattern_processing.repeat_unit import RepeatUnit  # noqa: E402

BANDS = {"border": "x", "edging": "x", "vertical band": "y"}
FIELDS = ["name", "kind", "axis", "period", "phase", "copies", "status", "mismatch"]


class RepeatManifest:
    """All bands in a folder of charts and their repeat units."""

    def __init__(self, txt_dir, out_dir):
        self.txt_dir = Path(txt_dir)
        self.out_dir = Path(out_dir)
        self.rows = []

    def build(self):
        unit_dir = self.out_dir / "repeat"
        unit_dir.mkdir(parents=True, exist_ok=True)
        for old in unit_dir.glob("*.txt"):
            old.unlink()
        for path in sorted(self.txt_dir.glob("*.txt")):
            pattern = Pattern(path).measure()
            axis = BANDS.get(pattern.kind)
            if not axis:
                continue
            ru = RepeatUnit.from_band(pattern.trim, axis)
            row = {"name": pattern.id, "kind": pattern.kind, "axis": axis}
            if ru is None:
                row.update(period="", phase="", copies="", status="none", mismatch="")
            else:
                row.update(period=ru.period, phase=ru.phase + self.trim_offset(pattern.matrix, axis),
                           copies=ru.copies, status=ru.status, mismatch=f"{ru.mismatch:.4f}")
                self.write_unit(unit_dir / f"{pattern.id}.txt", ru.unit)
            self.rows.append(row)
        with open(self.out_dir / "repeats.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(self.rows)
        return self

    @staticmethod
    def trim_offset(m, axis):
        """Empty columns (x) or rows (y) before the first filled cell."""
        ys, xs = np.nonzero(m)
        return int(xs.min() if axis == "x" else ys.min()) if len(xs) else 0

    @staticmethod
    def write_unit(path, unit):
        path.write_text("\n".join("".join(str(c) for c in row) for row in unit) + "\n")

    def report(self):
        counts = {}
        for r in self.rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        print(f"{len(self.rows)} bands -> {self.out_dir}/repeats.csv:",
              ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("txt_dir", nargs="?", default="patterns/txt")
    ap.add_argument("out_dir", nargs="?", default="patterns")
    a = ap.parse_args()
    RepeatManifest(a.txt_dir, a.out_dir).build().report()


if __name__ == "__main__":
    main()
