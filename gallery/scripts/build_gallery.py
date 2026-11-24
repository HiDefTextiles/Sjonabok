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
from facets import Facets, LABELS as FACET_LABELS  # noqa: E402
from pattern_processing.pattern_to_png import COLOR_PALETTE  # noqa: E402
from pattern_processing.repeat_unit import RepeatUnit, find_period  # noqa: E402

TOLERANCE = 0.98          # share of cells that must agree for a symmetry
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

# Subjects (bird, flower, ...) reviewed by a person; see analysis/subjects
# and the gallery's Methods page. Charts not reviewed yet get no subject.
SUBJECTS_CSV = Path(__file__).resolve().parents[2] / "analysis" / "subjects" / "subjects.csv"
VOCABULARY_CSV = SUBJECTS_CSV.with_name("vocabulary.csv")
GROUPS_CSV = SUBJECTS_CSV.with_name("groups.csv")
FAMILIES_CSV = SUBJECTS_CSV.with_name("families.csv")


def read_rows(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


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
        subjects, themes = self.add_subjects(records)
        facets = self.add_facets(records)
        families = self.add_families(records)
        self.save_overview()
        index = {
            "count": len(records),
            "tolerance": TOLERANCE,
            "sources": self.summary(records, "source_label"),
            "kinds": self.summary(records, "kind"),
            "subjects": subjects,
            "themes": themes,
            "facets": facets,
            "families": families,
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

    @staticmethod
    def add_subjects(records):
        """Reviewed subjects per pattern, and the labels of those in use."""
        labels = {r["id"]: r["subjects"].split("|") for r in read_rows(SUBJECTS_CSV) if r["subjects"]}
        vocab = read_rows(VOCABULARY_CSV)
        to_group = {v["subject"]: v.get("group", "") for v in vocab}
        for r in records:
            r["subjects"] = labels.get(r["id"], [])
            # main groups (groups.csv): the safer filter, see the Methods page
            r["themes"] = sorted({to_group.get(s, "") for s in r["subjects"]} - {""})
        used = {s for v in labels.values() for s in v}
        used_groups = {to_group.get(s, "") for s in used}
        subjects = {v["subject"]: v["label"] for v in vocab if v["subject"] in used}
        themes = {g["group"]: g["label"] for g in read_rows(GROUPS_CSV) if g["group"] in used_groups}
        return subjects, themes

    def add_facets(self, records):
        """Line, openness, outline and size words for every chart (facets.py)."""
        by_id = {p.id: p for p in self.patterns}
        for r in records:
            p = by_id[r["id"]]
            r["facets"] = Facets(p.trim, p.kind, p.period).words()
        return {k: {v: lab for v, lab in FACET_LABELS[k].items() if any(r["facets"][k] == v for r in records)}
                for k in FACET_LABELS}

    @staticmethod
    def add_families(records):
        """Look-alike families from analysis/subjects/families.csv (families.R), if present.
        Each family gets a short description from the facet words most of its charts share."""
        rows = {r["id"]: r for r in read_rows(FAMILIES_CSV)} if FAMILIES_CSV.exists() else {}
        families = {}
        for r in records:
            f = rows.get(r["id"])
            if not f:
                continue
            r["family"], r["close"], r["order"] = f["family"], f["close"], int(f["order"])
            r["map"] = [float(f["x"]), float(f["y"])]
            fam = families.setdefault(f["family"], {"n": 0, "example": None, "words": {}})
            fam["n"] += 1
            if f.get("family_example", f["example"]) == "TRUE":
                fam["example"] = r["id"]
            if "stability" in f:
                fam["stability"] = float(f["stability"])
            for k in ("outline", "stroke", "open"):
                w = fam["words"].setdefault(k, {})
                w[r["facets"][k]] = w.get(r["facets"][k], 0) + 1
        for key, fam in families.items():
            top = {k: max(c, key=c.get) for k, c in fam.pop("words").items()}
            band = key.startswith("B")
            first = "Bands" if band else FACET_LABELS["outline"][top["outline"]]
            stable = f", stability {fam['stability']:.2f}" if "stability" in fam else ""
            fam["label"] = f"{key}: {fam['n']} charts{stable}; mostly {first.lower()}, {FACET_LABELS['stroke'][top['stroke']].lower()} stroke, {FACET_LABELS['open'][top['open']].lower()}"
        return dict(sorted(families.items(), key=lambda kv: (kv[0][0] != "M", int(kv[0][1:]))))

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
