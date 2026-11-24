"""Write the minimal charts: one repeat unit per exactly repeating band.

    python3 extract_repeats.py patterns/txt patterns     (or: make repeats)

Input: the full charts in patterns/txt (local only, git-ignored; `make
originals` restores them from git history).

Output (committed; pattern-synthesis and the gallery read these):
    patterns/min/<name>.txt   one file per pattern, 0/1 rows. A band whose
                              chart is an exact repeat holds just one repeat
                              unit; every other chart is copied unchanged.
    patterns/repeats.csv      one row per band:
        name      file name without .txt
        kind      border, edging or vertical band
        axis      x = repeats left to right, y = top to bottom
        period    cells per repeat (empty if no repeat was found)
        status    unit  (patterns/min holds one repeat unit),
                  near  (repeats, but some cells differ; full chart kept),
                  none  (no repeat found; full chart kept)
        mismatch  share of the full chart's cells that differ from the
                  ideal repeat (0 for unit)

A unit is cut where the band has a mirror axis in its middle, otherwise
where it is lightest, so motifs are not split.
"""

import argparse
import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gallery" / "scripts"))
from build_gallery import Pattern  # noqa: E402  (shared type classification)
from pattern_processing.repeat_unit import RepeatUnit  # noqa: E402

BANDS = {"border": "x", "edging": "x", "vertical band": "y"}
FIELDS = ["name", "kind", "axis", "period", "status", "mismatch"]


class RepeatManifest:
    """All charts in a folder, with bands reduced to their repeat units."""

    def __init__(self, txt_dir, out_dir):
        self.txt_dir = Path(txt_dir)
        self.out_dir = Path(out_dir)
        self.rows = []

    def build(self):
        min_dir = self.out_dir / "min"
        min_dir.mkdir(parents=True, exist_ok=True)
        for old in min_dir.glob("*.txt"):
            old.unlink()
        for path in sorted(self.txt_dir.glob("*.txt")):
            pattern = Pattern(path).measure()
            row = self.band_row(pattern)
            if row and row["status"] == "unit":
                self.write_unit(min_dir / path.name, row.pop("_unit"))
            else:
                shutil.copyfile(path, min_dir / path.name)
            if row:
                row.pop("_unit", None)
                self.rows.append(row)
        with open(self.out_dir / "repeats.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(self.rows)
        return self

    @staticmethod
    def band_row(pattern):
        axis = BANDS.get(pattern.kind)
        if not axis:
            return None
        row = {"name": pattern.id, "kind": pattern.kind, "axis": axis}
        ru = RepeatUnit.from_band(pattern.trim, axis)
        if ru is None:
            row.update(period="", status="none", mismatch="")
        else:
            row.update(period=ru.period, status="unit" if ru.mismatch == 0 else "near",
                       mismatch=f"{ru.mismatch:.4f}", _unit=ru.unit)
        return row

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
