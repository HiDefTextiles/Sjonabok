"""The PatternSource interface: one scanned page in, 0/1 charts out.

Every scan layout (ruled counted grid, white-line woodcut, multi-symbol
plate, line drawing) is a subclass of PatternSource. Whatever the layout,
a source returns Chart objects with the same three parts:

    cells       0/1 matrix, 1 = filled (stitched) cell
    meta        how it was read: box on the page, angle, pitch, threshold,
                uncertain cells, fill (the json digitise.py always printed)
    provenance  where it comes from: book, date, origin, holder, licence of
                the scan, terms of use, licence of the chart we publish

Subclasses implement read() (find the charts) and may override
check_image() (the picture for checking a page by eye). The shared
steps (page normalisation, deskew, Otsu, cell-centre scores, the red
overlay) live here so all layouts measure cells the same way.
"""
from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np

BOOKS_CSV = Path(__file__).resolve().parents[1] / "books.csv"

CHART_LICENCE = "CC BY 4.0"
CREDIT = "Helga Ingimundardóttir, Háskóli Íslands (HiDef Textiles)"


# ── provenance ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Provenance:
    """Who printed the book, where, when, who holds the copy we read, and
    on what terms. Read from one row of books/books.csv."""
    book: str
    title: str = ""
    author: str = ""
    publisher: str = ""
    place: str = ""
    country: str = ""
    year: str = ""
    first_edition: str = ""
    kind: str = ""
    holder: str = ""
    holder_place: str = ""
    accession: str = ""
    record_url: str = ""
    scan_rights: str = ""          # books.csv "rights"
    terms_of_use: str = ""         # books.csv "rights_source" (or "terms" if added)
    chart_licence: str = CHART_LICENCE
    credit: str = CREDIT

    @property
    def date(self):
        return self.year

    @property
    def origin(self):
        return ", ".join(v for v in (self.place, self.country) if v)

    @classmethod
    def from_row(cls, r: dict) -> "Provenance":
        return cls(book=r["code"], title=r.get("title", ""), author=r.get("author", ""),
                   publisher=r.get("publisher", ""), place=r.get("place", ""),
                   country=r.get("country", ""), year=r.get("year", ""),
                   first_edition=r.get("first_edition", ""), kind=r.get("kind", ""),
                   holder=r.get("holder", ""), holder_place=r.get("holder_place", ""),
                   accession=r.get("accession", ""), record_url=r.get("record_url", ""),
                   scan_rights=r.get("rights", ""),
                   terms_of_use=r.get("terms") or r.get("rights_source", ""))

    @classmethod
    def lookup(cls, code: str, books_csv: Path = BOOKS_CSV) -> "Provenance":
        with open(books_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["code"] == code:
                    return cls.from_row(r)
        raise KeyError(f"{code} is not in {books_csv}")

    def as_dict(self):
        d = asdict(self)
        d["origin"] = self.origin
        return d


# ── a chart ─────────────────────────────────────────────────────────────────

@dataclass
class Chart:
    name: str
    cells: np.ndarray                    # uint8, 1 = filled
    meta: dict
    provenance: Provenance | None = None
    layers: dict = field(default_factory=dict)   # extra matrices, e.g. "symbols"

    def text(self) -> str:
        return "\n".join("".join(map(str, row)) for row in self.cells) + "\n"

    def record(self) -> dict:
        """Everything about the chart except the cells, for a sidecar file."""
        d = dict(self.meta)
        if self.provenance is not None:
            d["provenance"] = self.provenance.as_dict()
        return d


# ── shared image steps ──────────────────────────────────────────────────────

def read_gray(path) -> np.ndarray:
    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if g is None:
        raise FileNotFoundError(path)
    return g


def paper_level(g, white_line=False):
    """Local paper brightness. Ruled prints: a median. White-line woodcuts
    have large solid black fields, so a median would take the ink for
    paper: use the brightest level nearby instead."""
    if white_line:
        return cv2.blur(cv2.dilate(g, np.ones((151, 151), np.uint8)), (151, 151))
    return cv2.medianBlur(g, 51)


def rotate(img, angle, border=0):
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=border)


def deskew(crop, border=0, span=2.5, step=0.05):
    """Turn that makes the row and column profiles sharpest."""
    best = None
    for a in np.arange(-span, span + 0.01, step):
        r = rotate(crop, a, border)
        v = r.mean(axis=1).var() + r.mean(axis=0).var()
        if best is None or v > best[0]:
            best = (v, a)
    return rotate(crop, best[1], border), float(best[1])


def centre_means(img, xs, ys):
    """Mean of the middle half of every cell bounded by lines xs, ys."""
    h, w = len(ys) - 1, len(xs) - 1
    s = np.zeros((h, w))
    for r in range(h):
        a, b = ys[r], ys[r + 1]
        ma = max(1, int(round((b - a) * 0.25)))
        for c in range(w):
            l, rr = xs[c], xs[c + 1]
            mb = max(1, int(round((rr - l) * 0.25)))
            s[r, c] = img[a + ma:b - ma + 1, l + mb:rr - mb + 1].mean()
    return np.nan_to_num(s)


def otsu(scores):
    t, _ = cv2.threshold((scores * 255).astype(np.uint8), 0, 255,
                         cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return t / 255


def paint_cells(img, cells, margin, xs, ys, x0=0, y0=0, unsure=0.05):
    """Filled cells tinted red, near-threshold empty cells outlined orange."""
    for r in range(cells.shape[0]):
        for c in range(cells.shape[1]):
            a, b = x0 + xs[c], x0 + xs[c + 1]
            t, u = y0 + ys[r], y0 + ys[r + 1]
            if cells[r, c]:
                sub = img[t + 2:u - 1, a + 2:b - 1]
                sub[:] = (0.45 * sub + 0.55 * np.array([40, 40, 230])).astype(np.uint8)
            elif margin[r, c] < unsure:
                cv2.rectangle(img, (a + 2, t + 2), (b - 2, u - 2), (0, 160, 255), 1)
    return img


# ── the interface ───────────────────────────────────────────────────────────

class PatternSource(ABC):
    """One scanned page of one layout.

    usage:  src = RuledGridSource("DP363474.webp", provenance=Provenance.lookup("sib1597"))
            charts = src.charts()
            src.write("read/sib1597")          # <name>.txt, <page>_check.jpg
    """
    layout = "abstract"                 # registry key, set by subclasses
    description = ""

    def __init__(self, path, provenance: Provenance | None = None, **options):
        self.path = Path(path)
        self.provenance = provenance
        self.options = options
        self._charts = None

    @property
    def page_id(self):
        return self.path.stem

    @abstractmethod
    def read(self) -> list[Chart]:
        """Find and read every chart on the page."""

    def check_image(self, path):
        """Write a picture of the page with the read cells marked (optional)."""

    def charts(self) -> list[Chart]:
        if self._charts is None:
            self._charts = self.read()
            for c in self._charts:
                c.provenance = c.provenance or self.provenance
                c.meta.setdefault("layout", self.layout)
        return self._charts

    def write(self, outdir, sidecars=False):
        """Write <name>.txt for every chart and <page>_check.jpg; with
        sidecars also <name>.json (meta + provenance) and any extra layers
        as <name>.<layer>.txt. Returns the meta list (printed as json by
        the command line tools)."""
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        charts = self.charts()
        for c in charts:
            (out / f"{c.name}.txt").write_text(c.text())
            if sidecars:
                (out / f"{c.name}.json").write_text(
                    json.dumps(c.record(), ensure_ascii=False, indent=1) + "\n")
                for k, m in c.layers.items():
                    (out / f"{c.name}.{k}.txt").write_text(
                        "\n".join("".join(map(str, row)) for row in m) + "\n")
        self.check_image(out / f"{self.page_id}_check.jpg")
        return [self.public_meta(c) for c in charts]

    @staticmethod
    def public_meta(chart):
        """The per-chart json the old tools printed (no layout key)."""
        return {k: v for k, v in chart.meta.items() if k != "layout"}
