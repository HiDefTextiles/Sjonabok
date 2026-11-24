"""Build the data behind the Sjonabok gallery.

Reads every 0/1 matrix in patterns/min, measures it (size, density,
symmetry, repeat, type, pieces, longest float), renders PNG images in the
HI colour palette and writes one JSON index for the gallery page.

    python3 gallery/scripts/build_gallery.py patterns/min gallery/patterns

A band listed in patterns/repeats.csv with status "unit" is stored as one
repeat unit; its type and repeat come from the manifest, and its images
show the unit repeated a few times.

Output (all generated, not committed):
    <out>/patterns.json        one record per pattern, plus summary tables
    <out>/thumb/<id>.png       gallery thumbnail
    <out>/png/<id>.png         full image, 10 px per cell
    <out>/txt/<id>.txt         copy of the matrix (download and zoom view)
    <out>/overview-bands.png   every band on one sheet, coloured by source
    <out>/overview-motifs.png  every motif and rosette on one sheet

The measures are computed automatically; they describe the digitised chart,
not a curator's judgement.
"""

import argparse
import csv
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
from pattern_processing.repeat_unit import RepeatUnit, find_period  # noqa: E402

TOLERANCE = 0.98          # share of cells that must agree for a symmetry
THUMB_PX = 240            # target size of the longest thumbnail side
FULL_ZOOM = 10            # pixels per cell in the full PNG
SHOW_CELLS = 72           # a stored unit is drawn repeated to at least this length

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

# One colour per source on the overview sheets, in SOURCE_LABELS order.
# Checked for colour-blind separation between neighbours in this order;
# the page legend names every colour, so colour is never the only cue.
SOURCE_COLORS = dict(zip(SOURCE_LABELS, [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
    "#008300", "#6250d6", "#e34948", "#2b4ea8", "#a0632d",
]))

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

    def __init__(self, path, unit_row=None):
        self.path = Path(path)
        self.id = self.path.stem
        self.matrix = self.read(self.path)
        self.unit_row = unit_row       # manifest row when the file is one repeat unit
        # a unit keeps its empty edge columns: they belong to the repeat
        self.trim = self.matrix if unit_row else self.trimmed(self.matrix)
        self.display = self.matrix     # what the images show
        m = NAME_RE.match(self.id)
        self.source = m["source"] if m else self.id
        self.number = int(m["number"]) if m else 0
        self.part = int(m["part"]) if m and m["part"] else None
        self.period = None
        self.repeat = None
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
        if self.unit_row:
            return self.measure_unit()
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

    def measure_unit(self):
        """A stored repeat unit: type and period from the manifest, symmetry
        measured on the unit repeated, images of a few repeats."""
        row = self.unit_row
        self.kind, axis = row["kind"], row["axis"]
        unit = self.matrix.T if axis == "y" else self.matrix
        copies = max(3, -(-SHOW_CELLS // unit.shape[1]))
        band = np.tile(unit, (1, copies))
        self.display = band.T if axis == "y" else band
        self.measure_band(band, vertical=axis == "y")
        self.period = int(row["period"])
        self.repeat = RepeatUnit(axis, self.period, 0, self.matrix, 1, 0.0)
        self.pieces = self.count_pieces(self.matrix)
        self.float_fg = self.longest_run(band, 1)
        self.float_bg = self.longest_run(band, 0)
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

    def measure_band(self, t, vertical=False):
        """Symmetry of a frieze, measured on one repeat treated as cyclic."""
        p = find_period(t)
        self.period = p
        self.repeat = RepeatUnit.from_band(t) if p else None   # t is already horizontal
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

    def signature_variants(self, n=16):
        """Small n×n pictures of the pattern for similarity, in every
        position the comparison should ignore.

        Bands are compared on one repeat unit, laid horizontally, in all n
        cyclic shifts and with left–right and top–bottom flips, so a band
        that starts elsewhere in its repeat, runs the other way or is
        mirrored still matches. Motifs use the whole chart in its eight
        turned and mirrored positions. Each picture is centred and scaled
        to length 1, so a dot product is a correlation.
        """
        if self.repeat is not None:
            base = self.small(self.repeat.horizontal(), n)
            flips = [base, base[:, ::-1], base[::-1, :], base[::-1, ::-1]]
            pics = [np.roll(f, k, axis=1) for f in flips for k in range(n)]
        else:
            t = self.trim.T if self.kind == "vertical band" else self.trim
            base = self.small(t, n)
            pics = [np.rot90(b, k) for b in (base, base[:, ::-1]) for k in range(4)]
            pics = pics * (4 * n // len(pics))   # same count as for bands
        v = np.array([p.ravel() for p in pics], dtype=float)
        v -= v.mean(axis=1, keepdims=True)
        norm = np.linalg.norm(v, axis=1, keepdims=True)
        return np.divide(v, norm, out=np.zeros_like(v), where=norm > 0)

    @staticmethod
    def small(a, n):
        return np.asarray(Image.fromarray(a * 255).resize((n, n), Image.BILINEAR), dtype=float)

    def shape_ratio(self):
        """Width to height of what is compared (one repeat for bands)."""
        t = self.repeat.horizontal() if self.repeat is not None else self.trim
        if self.repeat is None and self.kind == "vertical band":
            t = t.T
        return t.shape[1] / t.shape[0]

    # ── images ───────────────────────────────────────────────────────────
    def rgba(self, zoom):
        palette = np.array(COLOR_PALETTE[:2], dtype=np.uint8)
        img = palette[self.display]
        return np.kron(img, np.ones((zoom, zoom, 1), dtype=np.uint8))

    def save_images(self, out):
        h, w = self.display.shape
        thumb_zoom = max(2, THUMB_PX // max(h, w))
        Image.fromarray(self.rgba(thumb_zoom), "RGBA").save(out / "thumb" / f"{self.id}.png", optimize=True)
        Image.fromarray(self.rgba(FULL_ZOOM), "RGBA").save(out / "png" / f"{self.id}.png", optimize=True)
        shutil.copyfile(self.path, out / "txt" / f"{self.id}.txt")

    def band_strip(self):
        """The band laid flat and filled out to BAND_SHOW cells: a stored
        unit or a band that repeats exactly (status ok) is repeated, any other band is drawn as
        in the book."""
        if self.unit_row:
            unit = self.matrix.T if self.unit_row["axis"] == "y" else self.matrix
        elif self.repeat is not None and self.repeat.status == "ok":
            unit = self.repeat.horizontal()
        else:
            return (self.trim.T if self.kind == "vertical band" else self.trim)[:, :BAND_SHOW]
        return RepeatUnit.tile(unit, 0, BAND_SHOW)

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
            "unit": bool(self.unit_row),
            "show": [int(self.display.shape[1]), int(self.display.shape[0])],
            "period": self.period,
            "repeat_status": self.repeat.status if self.repeat else None,
            "repeat_mismatch": self.repeat.mismatch if self.repeat else None,
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
            "color": SOURCE_COLORS.get(self.source),
            "thumb_zoom": max(2, THUMB_PX // max(self.display.shape)),
        }


class Gallery:
    """All patterns, their similarity links and the generated files."""

    def __init__(self, txt_dir, out_dir, manifest=None):
        self.out = Path(out_dir)
        units = self.read_units(Path(manifest) if manifest else Path(txt_dir).parent / "repeats.csv")
        self.patterns = [Pattern(p, units.get(p.stem)) for p in sorted(Path(txt_dir).glob("*.txt"))]

    @staticmethod
    def read_units(path):
        """Manifest rows of the bands stored as one repeat unit."""
        if not path.exists():
            return {}
        with open(path, newline="") as f:
            return {r["name"]: r for r in csv.DictReader(f) if r["status"] == "unit"}

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
        """Nearest neighbours: best correlation over shifts, flips and turns
        (see Pattern.signature_variants), minus small penalties for a
        different shape and density, plus a bonus for the same family."""
        variants = np.stack([p.signature_variants() for p in self.patterns])   # N × V × n²
        canon = variants[:, 0, :]
        corr = np.max(np.einsum("id,jvd->ijv", canon, variants), axis=2)
        corr = np.maximum(corr, corr.T)
        ratio = np.log([p.shape_ratio() for p in self.patterns])
        density = np.array([p.trim.mean() for p in self.patterns])
        family = np.array(["band" if p.kind in ("border", "edging", "vertical band") else p.kind
                           for p in self.patterns])
        score = (corr
                 - 0.3 * np.abs(ratio[:, None] - ratio[None, :])
                 - 1.0 * np.abs(density[:, None] - density[None, :])
                 + 0.1 * (family[:, None] == family[None, :]))
        np.fill_diagonal(score, -np.inf)
        for i, r in enumerate(records):
            r["similar"] = [records[j]["id"] for j in np.argsort(-score[i])[:k]]

    def save_overview(self):
        """Two sheets: all bands (vertical ones laid flat) and all motifs."""
        bands = [p for p in self.patterns if p.kind in ("border", "edging", "vertical band")]
        motifs = [p for p in self.patterns if p.kind in ("motif", "rosette")]
        OverviewSheet(width=8 * (BAND_SHOW + 3), step=BAND_SHOW + 3).add_all(bands, Pattern.band_strip).save(
            self.out / "overview-bands.png")
        OverviewSheet(width=720).add_all(motifs, lambda p: p.trim, tallest_first=True).save(
            self.out / "overview-motifs.png")


BAND_SHOW = 116           # cells of each band shown on the band sheet (widest chart)


class OverviewSheet:
    """Charts packed tightly on one sheet, 1 px per cell, coloured by source.

    Bottom-left skyline packing: each chart drops into the lowest spot it
    fits, so sources stay in rough order from top to bottom with little
    white between them."""

    def __init__(self, width, gap=3, step=1):
        self.width, self.gap, self.step = width, gap, step   # step: allowed x positions
        self.sky = np.zeros(width, dtype=int)   # first free row per column
        self.placed = []                         # (y, x, matrix, colour index)

    def add(self, m, colour):
        h, w = m.shape
        w = min(w, self.width)
        best = None
        for x in range(0, self.width - w + 1, self.step):
            y = int(self.sky[x:x + w].max())
            if best is None or y < best[0]:
                best = (y, x)
        y, x = best
        self.sky[x:x + w + self.gap] = y + h + self.gap
        self.placed.append((y, x, m[:, :w], colour))

    def add_all(self, patterns, chart, tallest_first=False):
        order = list(SOURCE_LABELS)
        def key(p):
            rank = order.index(p.source) if p.source in order else len(order)
            return (rank, -p.trim.shape[0] if tallest_first else 0)
        for p in sorted(patterns, key=key):   # stable: file order within a source
            self.add(chart(p), 1 + (order.index(p.source) if p.source in order else len(order) - 1))
        return self

    def save(self, path):
        height = max(y + m.shape[0] for y, _, m, _ in self.placed)
        canvas = np.zeros((height, self.width), dtype=np.uint8)
        for y, x, m, c in self.placed:
            region = canvas[y:y + m.shape[0], x:x + m.shape[1]]
            region[m == 1] = c
        img = Image.fromarray(canvas, "P")
        palette = [255, 255, 255]
        for hexcol in SOURCE_COLORS.values():
            palette += [int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]
        img.putpalette(palette)
        img.save(path, optimize=True, transparency=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("txt_dir", help="folder with the 0/1 .txt patterns")
    ap.add_argument("out_dir", help="folder for patterns.json and images")
    ap.add_argument("--manifest", help="repeats.csv (default: next to txt_dir)")
    args = ap.parse_args()
    Gallery(args.txt_dir, args.out_dir, args.manifest).build()


if __name__ == "__main__":
    main()
