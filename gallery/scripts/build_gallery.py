"""Build the data behind the Sjonabok gallery.

Reads every 0/1 matrix in patterns/txt, measures it (size, density,
symmetry, repeat, type, pieces, longest float), renders PNG images in the
HI colour palette and writes one JSON index for the gallery page.

    python3 gallery/scripts/build_gallery.py patterns/txt gallery/patterns

Output (all generated, not committed):
    <out>/patterns.json        one record per pattern, plus summary tables
    <out>/thumb/<id>.png       gallery thumbnail
    <out>/png/<id>.png         full image, 10 px per cell
    <out>/txt/<id>.txt         copy of the matrix (download and zoom view)
    <out>/overview.png         every pattern on one sheet

The measures are computed automatically; they describe the digitised chart,
not a curator's judgement.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Reuse the palette of the existing converter so there is one source of truth.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pattern_processing.pattern_to_png import COLOR_PALETTE  # noqa: E402

TOLERANCE = 0.98          # share of cells that must agree for a symmetry
PERIOD_TOLERANCE = 0.97   # share of cells that must agree for a repeat
THUMB_PX = 240            # target size of the longest thumbnail side
FULL_ZOOM = 10            # pixels per cell in the full PNG

# Readable names for the source codes in the file names. Þjms. is the
# accession prefix of Þjóðminjasafn Íslands (National Museum of Iceland).
SOURCE_LABELS = {
    "natmus453": "Natmus 453",
    "thjms1105": "Þjms. 1105",
    "thjms1960-60": "Þjms. 1960-60",
    "thjms1985-235": "Þjms. 1985-235",
    "thjms1997-123": "Þjms. 1997-123",
    "thjms2007-45": "Þjms. 2007-45",
    "thjms2008-14": "Þjms. 2008-14",
    "thjms5898": "Þjms. 5898",
    "thjms6950": "Þjms. 6950",
    "thjmsth_116": "Þjms. Th 116",
}

FRIEZE_NAMES = {
    "p1": "translation only",
    "p11g": "glide reflection",
    "p1m1": "vertical mirrors",
    "p2": "half-turns",
    "p2mg": "vertical mirrors and glide",
    "p11m": "horizontal mirror",
    "p2mm": "horizontal and vertical mirrors",
}

POINT_NAMES = {
    "D4": "fourfold, mirrored (square star)",
    "C4": "fourfold turn, no mirror",
    "D2": "two mirrors",
    "C2": "half-turn only",
    "D1": "one mirror",
    "C1": "no symmetry",
}

NAME_RE = re.compile(r"^(?P<source>.+?)_(?P<number>\d+)(?:_p(?P<part>\d+))?$")


def agreement(a, b):
    """Share of equal cells in two arrays of the same shape."""
    return float(np.mean(a == b)) if a.size else 0.0


class Pattern:
    """One digitised chart and everything the gallery shows about it."""

    def __init__(self, path):
        self.path = Path(path)
        self.id = self.path.stem
        self.matrix = self.read(self.path)
        self.trim = self.trimmed(self.matrix)
        m = NAME_RE.match(self.id)
        self.source = m["source"] if m else self.id
        self.number = int(m["number"]) if m else 0
        self.part = int(m["part"]) if m and m["part"] else None
        self.period = None
        self.frieze = None
        self.point = None
        self.sym = {}

    # ── reading ──────────────────────────────────────────────────────────
    @staticmethod
    def read(path):
        rows = [r.strip() for r in path.read_text().splitlines() if r.strip()]
        return np.array([[int(c) for c in r] for r in rows], dtype=np.uint8)

    @staticmethod
    def trimmed(m):
        """Cut the empty margin (rows and columns with no 1)."""
        ys, xs = np.nonzero(m)
        if not len(ys):
            return m
        return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    # ── measures ─────────────────────────────────────────────────────────
    def measure(self):
        t = self.trim
        h, w = t.shape
        self.kind = self.classify_shape(h, w)
        if self.kind in ("border", "edging"):
            self.measure_band(t)
        elif self.kind == "vertical band":
            self.measure_band(t.T, vertical=True)
        else:
            self.measure_motif(t)
        if self.kind == "motif" and self.point == "D4" and 0.8 <= w / h <= 1.25:
            self.kind = "rosette"
        self.pieces = self.count_pieces(t)
        self.float_fg = self.longest_run(t, 1)
        self.float_bg = self.longest_run(t, 0)
        return self

    @staticmethod
    def classify_shape(h, w):
        if h <= 5 and w >= 15:
            return "edging"
        if w / h >= 2.0:
            return "border"
        if h / w >= 2.0:
            return "vertical band"
        return "motif"

    def measure_motif(self, t):
        s = {
            "lr": agreement(t, t[:, ::-1]),
            "tb": agreement(t, t[::-1, :]),
            "rot180": agreement(t, t[::-1, ::-1]),
        }
        square = t.shape[0] == t.shape[1]
        s["rot90"] = agreement(t, np.rot90(t)) if square else 0.0
        s["diag"] = max(agreement(t, t.T), agreement(t, np.rot90(t, 2).T)) if square else 0.0
        self.sym = s
        ok = {k: v >= TOLERANCE for k, v in s.items()}
        if ok["rot90"] and (ok["lr"] or ok["diag"]):
            self.point = "D4"
        elif ok["rot90"]:
            self.point = "C4"
        elif ok["rot180"] and (ok["lr"] and ok["tb"] or ok["diag"]):
            self.point = "D2"
        elif ok["rot180"]:
            self.point = "C2"
        elif ok["lr"] or ok["tb"] or ok["diag"]:
            self.point = "D1"
        else:
            self.point = "C1"

    def find_period(self, t):
        """Smallest horizontal repeat that occurs at least twice."""
        w = t.shape[1]
        for p in range(2, w // 2 + 1):
            if agreement(t[:, :-p], t[:, p:]) >= PERIOD_TOLERANCE:
                return p
        return None

    def measure_band(self, t, vertical=False):
        """Symmetry of a frieze, measured on one repeat treated as cyclic."""
        p = self.find_period(t)
        self.period = p
        tile = t[:, :p] if p else t
        n = tile.shape[1]
        flip = tile[::-1, :]

        def best_mirror(a):
            # a vertical mirror axis may sit anywhere in a cyclic tile
            if not p:
                return agreement(tile, a[:, ::-1])
            return max(agreement(tile, np.roll(a[:, ::-1], s, axis=1)) for s in range(n))

        s = {
            "tb": agreement(tile, flip),
            "lr": best_mirror(tile),
            "rot180": best_mirror(flip),
            "glide": agreement(tile, np.roll(flip, n // 2, axis=1)) if p and n % 2 == 0 else 0.0,
            "rot90": 0.0,
            "diag": 0.0,
        }
        if vertical:  # report mirrors in the orientation the viewer sees
            s["lr"], s["tb"] = s["tb"], s["lr"]
        self.sym = s
        ok = {k: v >= TOLERANCE for k, v in s.items()}
        across, along = (ok["lr"], ok["tb"]) if vertical else (ok["tb"], ok["lr"])
        if not p:
            self.frieze = None
        elif across:
            self.frieze = "p2mm" if along else "p11m"
        elif ok["glide"]:
            self.frieze = "p2mg" if along else "p11g"
        elif along:
            self.frieze = "p1m1"
        elif ok["rot180"]:
            self.frieze = "p2"
        else:
            self.frieze = "p1"

    @staticmethod
    def count_pieces(t):
        """Number of separate shapes of 1s (touching corners count as joined)."""
        seen = np.zeros_like(t, dtype=bool)
        h, w = t.shape
        pieces = 0
        for y0, x0 in zip(*np.nonzero(t)):
            if seen[y0, x0]:
                continue
            pieces += 1
            stack = [(y0, x0)]
            seen[y0, x0] = True
            while stack:
                y, x = stack.pop()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and t[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
        return pieces

    @staticmethod
    def longest_run(t, value):
        """Longest run of one colour along a row (a float in knitting)."""
        best = 0
        for row in t:
            run = 0
            for c in row:
                run = run + 1 if c == value else 0
                best = max(best, run)
        return best

    def signature(self, n=16):
        """Small fixed-size picture of the trimmed chart, for similarity."""
        img = Image.fromarray(self.trim * 255).resize((n, n), Image.BILINEAR)
        v = np.asarray(img, dtype=float).ravel()
        v -= v.mean()
        norm = np.linalg.norm(v)
        return v / norm if norm else v

    # ── images ───────────────────────────────────────────────────────────
    def rgba(self, zoom):
        palette = np.array(COLOR_PALETTE[:2], dtype=np.uint8)
        img = palette[self.matrix]
        return np.kron(img, np.ones((zoom, zoom, 1), dtype=np.uint8))

    def save_images(self, out):
        h, w = self.matrix.shape
        thumb_zoom = max(2, THUMB_PX // max(h, w))
        Image.fromarray(self.rgba(thumb_zoom), "RGBA").save(out / "thumb" / f"{self.id}.png", optimize=True)
        Image.fromarray(self.rgba(FULL_ZOOM), "RGBA").save(out / "png" / f"{self.id}.png", optimize=True)
        shutil.copyfile(self.path, out / "txt" / f"{self.id}.txt")

    # ── record ───────────────────────────────────────────────────────────
    def record(self):
        h, w = self.matrix.shape
        th, tw = self.trim.shape
        ones = int(self.trim.sum())
        ok = {k: bool(v >= TOLERANCE) for k, v in self.sym.items()}
        return {
            "id": self.id,
            "source": self.source,
            "source_label": SOURCE_LABELS.get(self.source, self.source),
            "number": self.number,
            "part": self.part,
            "width": int(w), "height": int(h),
            "trim_width": int(tw), "trim_height": int(th),
            "cells": int(tw * th),
            "ones": ones,
            "density": round(ones / (tw * th), 3),
            "kind": self.kind,
            "period": self.period,
            "frieze": self.frieze,
            "frieze_name": FRIEZE_NAMES.get(self.frieze),
            "point": self.point,
            "point_name": POINT_NAMES.get(self.point),
            "sym": {k: round(v, 3) for k, v in self.sym.items()},
            "mirror_lr": ok.get("lr", False),
            "mirror_tb": ok.get("tb", False),
            "turn180": ok.get("rot180", False),
            "turn90": ok.get("rot90", False),
            "diagonal": ok.get("diag", False),
            "glide": ok.get("glide", False),
            "pieces": self.pieces,
            "float_fg": self.float_fg,
            "float_bg": self.float_bg,
            "thumb_zoom": max(2, THUMB_PX // max(h, w)),
        }


class Gallery:
    """All patterns, their similarity links and the generated files."""

    def __init__(self, txt_dir, out_dir):
        self.out = Path(out_dir)
        self.patterns = [Pattern(p) for p in sorted(Path(txt_dir).glob("*.txt"))]

    def build(self):
        for sub in ("thumb", "png", "txt"):
            (self.out / sub).mkdir(parents=True, exist_ok=True)
        for p in self.patterns:
            p.measure().save_images(self.out)
        records = [p.record() for p in self.patterns]
        self.add_similar(records)
        self.save_overview()
        index = {
            "count": len(records),
            "tolerance": TOLERANCE,
            "sources": self.summary(records, "source_label"),
            "kinds": self.summary(records, "kind"),
            "patterns": records,
        }
        (self.out / "patterns.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))
        print(f"{len(records)} patterns -> {self.out}")

    @staticmethod
    def summary(records, key):
        counts = {}
        for r in records:
            counts[r[key]] = counts.get(r[key], 0) + 1
        return dict(sorted(counts.items()))

    def add_similar(self, records, k=8):
        """Nearest neighbours by shape signature, aspect ratio, density and type."""
        sig = np.array([p.signature() for p in self.patterns])
        aspect = np.log([p.trim.shape[1] / p.trim.shape[0] for p in self.patterns])
        density = np.array([p.trim.mean() for p in self.patterns])
        kind = np.array([p.kind for p in self.patterns])
        score = (sig @ sig.T
                 - 0.5 * np.abs(aspect[:, None] - aspect[None, :])
                 - 1.0 * np.abs(density[:, None] - density[None, :])
                 + 0.2 * (kind[:, None] == kind[None, :]))
        np.fill_diagonal(score, -np.inf)
        for i, r in enumerate(records):
            r["similar"] = [records[j]["id"] for j in np.argsort(-score[i])[:k]]

    def save_overview(self, cell=48, cols=30):
        """Contact sheet of every pattern, in file order."""
        rows = -(-len(self.patterns) // cols)
        sheet = Image.new("RGBA", (cols * cell, rows * cell), (255, 255, 255, 0))
        for i, p in enumerate(self.patterns):
            img = Image.fromarray(p.rgba(1), "RGBA")
            img.thumbnail((cell - 6, cell - 6), Image.NEAREST)
            x = (i % cols) * cell + (cell - img.width) // 2
            y = (i // cols) * cell + (cell - img.height) // 2
            sheet.paste(img, (x, y), img)
        sheet.save(self.out / "overview.png", optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("txt_dir", help="folder with the 0/1 .txt patterns")
    ap.add_argument("out_dir", help="folder for patterns.json and images")
    args = ap.parse_args()
    Gallery(args.txt_dir, args.out_dir).build()


if __name__ == "__main__":
    main()
