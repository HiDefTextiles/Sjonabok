"""Read Sjónabók EPS charts with several kinds of mark into colour charts.

    python3 convert_marks.py <eps_dir> patterns/colour [--review sheet.png] [--jobs 4]

Writes, for every page, <name>.txt (one colour digit per cell, see
pattern_processing/eps_marks.py) and <name>.marks.txt (the kind of mark in
every cell). A page holding several charts, 5 or more empty rows or
columns apart, is written as <name>_p1, <name>_p2, ... as split_patterns.py
does. patterns/colour/marks.csv lists the kinds; patterns/colour/pages.csv
what was read from each page. --review draws a sheet of 40 marks of every
kind, the cells to check by eye. Pages are read in parallel (--jobs);
rendering an EPS page takes Ghostscript a minute or two. Pages already
rendered at 288 dpi (.png) are read as they are.
"""

import argparse
import csv
import os
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from pattern_processing.eps_marks import INK_MAX, KINDS, MarkClassifier, MarkedEpsChart


def render(path):
    """RGB pixels of one page at 288 dpi (an EPS through Ghostscript)."""
    img = Image.open(path)
    if Path(path).suffix.lower() == ".eps":
        img.load(scale=4)
    return np.asarray(img.convert("RGB"))


def read_page(path, keep=40, seed=1):
    """Read one page; also return a few cells of every kind for the review."""
    rgb = render(path)
    classifier = MarkClassifier()
    chart = MarkedEpsChart.from_image(rgb, Path(path).stem, classifier)
    examples = {}
    if not chart.meta["turned"]:            # the review sheet shows the upright pages
        rng = np.random.default_rng(seed)
        rgb16 = rgb.astype(np.int16)
        rows, cols = MarkedEpsChart.find_grid(rgb16)
        ink = rgb16.sum(axis=2) < INK_MAX
        for row in MarkedEpsChart.cell_windows(ink, rows, cols):
            for w in row:
                k = classifier.kind(w)
                if k == ".":
                    continue
                pool = examples.setdefault(k, [])
                if len(pool) < keep:
                    pool.append(w)
                elif rng.random() < 0.05:
                    pool[rng.integers(keep)] = w
    return chart, examples


class MarkReader:
    """Reads a folder of EPS pages and writes the colour charts."""

    def __init__(self, out_dir, review=None, seed=1):
        self.out = Path(out_dir)
        self.review = review
        self.rng = np.random.default_rng(seed)
        self.examples = {}          # kind -> sampled cell pictures, for the review sheet
        self.rows = []

    def add(self, chart, examples):
        for k, pool in examples.items():
            self.examples.setdefault(k, []).extend(pool)
        parts = chart.parts() or [chart]
        for c in parts:
            c.save(self.out)
        self.rows.append({"page": chart.name, "turned": chart.meta["turned"],
                          "charts": " ".join(c.name for c in parts),
                          **{f"n_{k.char}": chart.meta["counts"].get(k.char, 0) for k in KINDS if k.char != "."}})
        print(chart.name, chart.kinds.shape, chart.meta["counts"], f"{len(parts)} chart(s)", flush=True)

    def save_review(self, path, per_row=40, cell=26):
        kinds = [k.char for k in KINDS if k.char in self.examples]
        sheet = Image.new("RGB", (60 + per_row * (cell + 2), len(kinds) * (cell + 4)), "white")
        draw = ImageDraw.Draw(sheet)
        for r, k in enumerate(kinds):
            y = r * (cell + 4) + 2
            pool = self.examples[k]
            draw.text((4, y + 8), k, fill=(214, 31, 105))
            for i, j in enumerate(self.rng.choice(len(pool), min(per_row, len(pool)), replace=False)):
                pic = Image.fromarray(np.where(pool[j], 0, 255).astype(np.uint8)).resize((cell, cell))
                sheet.paste(pic, (60 + i * (cell + 2), y))
        sheet.save(path)

    def save_tables(self):
        with open(self.out / "marks.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["mark", "digit", "name"])
            for k in KINDS:
                w.writerow([k.char, k.digit, k.name])
        with open(self.out / "pages.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(self.rows[0]))
            w.writeheader()
            w.writerows(self.rows)

    def run(self, pages, jobs=1):
        self.out.mkdir(parents=True, exist_ok=True)
        with Pool(jobs) as pool:
            for chart, examples in pool.imap(read_page, pages):
                self.add(chart, examples)
        self.rows.sort(key=lambda r: r["page"])
        self.save_tables()
        if self.review:
            self.save_review(self.review)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("eps_dir", help="folder of EPS pages (or one .eps file)")
    ap.add_argument("out_dir", help="folder for the colour charts, e.g. patterns/colour")
    ap.add_argument("--review", help="also draw a sheet of example marks of every kind (png)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="pages read at once")
    args = ap.parse_args()
    src = Path(args.eps_dir)
    files = [src] if src.is_file() else sorted(src.glob("*.eps")) or sorted(src.glob("*.png"))
    MarkReader(args.out_dir, args.review).run(files, args.jobs)


if __name__ == "__main__":
    main()
