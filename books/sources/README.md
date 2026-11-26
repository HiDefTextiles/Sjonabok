# books/sources: one reader per scan layout

Every scanned page is read by a `PatternSource`. The subclass depends on how the book
prints its charts. Every subclass returns the same thing, a list of `Chart` objects:

| part | what it is |
|---|---|
| `cells` | 0/1 matrix, 1 = filled cell, written as `<chart>.txt` (the format of `patterns/`) |
| `meta` | how it was read: box on the page, angle, pitch, threshold, uncertain cells, fill |
| `provenance` | book, date, origin (place, country), holder and accession, record URL, scan rights, terms of use, chart licence (CC BY 4.0) and credit, all from `books/books.csv` |
| `layers` | extra matrices for some layouts, e.g. `symbols` (which kind of mark each cell has) |

```
PatternSource (abstract: read(), check_image())
├── RuledGridSource          "ruled"    ruled counted grid, one mark per filled cell   (Sibmacher)
│   └── MultiSymbolPlateSource "symbols" ruled grid, several kinds of mark            (prototype, Fürst-type plates)
├── WhiteLineWoodcutSource   "woodcut"  black block, empty cells cut out white         (Quentel, Jobin, Schönsperger)
└── LineDrawingSource        "drawing"  free drawing, no grid: filled, put on a chosen grid (prototype)
```

The steps every layout shares are in `base.py`: paper level, deskew, the mean of the middle
half of each cell, Otsu, and the red check overlay. `ruled.py` and `woodcut.py` are the
readers from PR #46, moved here without changing anything they compute.

## Use

```
python3 books/read.py page.webp outdir --book sib1597             # layout from books.csv "kind"
python3 books/read.py page.webp outdir --layout symbols --option symbols=3 --sidecars
python3 books/read.py --layouts
python3 books/digitise.py page.webp outdir                         # same as before PR (ruled)
python3 books/woodcut.py  page.webp outdir                         # same as before PR (woodcut)
```

`--sidecars` also writes `<chart>.json` (meta + provenance) and `<chart>.<layer>.txt`.
Without it the outputs are exactly the PR #46 outputs: `<chart>.txt`, `<page>_check.jpg`,
and the json list on stdout.

From Python:

```python
import sys; sys.path.insert(0, "books")
from sources import open_source
src = open_source("books/scans/sib1597/DP363474.webp", book="sib1597")
for ch in src.charts():
    print(ch.name, ch.cells.shape, ch.provenance.origin, ch.provenance.chart_licence)
```

A new book with a layout `kind` does not name goes in `LAYOUT_BY_BOOK` in `__init__.py`.
A new layout is a new subclass with a `layout` key, added to `LAYOUTS`.

## Checks

```
make sources-test    # drawn pages in all four layouts, read back (no scans needed)
make sources-check   # every scan in books/scans, PR #46 readers against these, byte for byte
```

`sources-check` needs the scans in `books/scans/<book>/` (git-ignored; `books/fetch.py`).
On the 129 scans of Sibmacher 1597 and 1604, Quentel 1529 and Jobin 1600 all 596 output files
(charts, check pictures, json) are identical, and all 87 committed charts in `patterns/books`
come out unchanged.

`MultiSymbolPlateSource` remains a prototype; it is tested on the drawn plate and on the
issue #9 page capture. It uses a low-quantile grid profile so dense marks do not pull the
fit away from faint ruling. The followed lines are then replaced by one evenly spaced
lattice per axis (a robust fit, so a heavy major line that pulled the follower a few pixels
off for a stretch no longer cuts glyphs in half), nudged by at most 1.5 px so its lines run
through the white gaps between glyphs. Chart bands on one unrotated page share a single
column lattice, pooled from all bands, so every banner gets the same width. It trims padded
page rows and columns using the darker motif area (columns page-wide), scores
a cell by its darkest part and cuts between the empty level and the lightest mark (Otsu
would drop light marks), then groups marks by a coarse 6x6 picture with k-means (fixed
seed). It treats rotations and mirrors of a mark as the same shape, shares IDs across
all chart bands on the page, and ranks them by total frequency, leaving `0` for empty
cells.
`LineDrawingSource` is still a prototype checked only on drawn pages. It fills closed
outlines and fills a cell when ink covers half of it.
