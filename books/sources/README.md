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
│   ├── MultiSymbolPlateSource "symbols" ruled grid, several kinds of mark, unnamed clusters (prototype)
│   └── NamedMarkPlateSource   "marks"   ruled grid, every cell named: . # + | / \ ...  (prototype, Sibmacher)
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

## Named marks (layout "marks")

Sibmacher's cells are not only filled or empty. `NamedMarkPlateSource` gives every cell one
character (`books/sources/marks.py`):

| | kind | | kind |
|---|---|---|---|
| `.` | empty | `#` | solid |
| `+` | plus (cross on the cell's axes) | `x` | diagonal cross |
| `\|` | vertical hatching | `-` | horizontal hatching |
| `/` `\` | one diagonal (four of them, `\ /` over `/ \`, draw the large star) | `< > ^ v` | wedge: two diagonals meeting mid-side |
| `F 7 L J` | half cell, the triangle in that corner is inked | `?` | a mark none of the above fits |

The kinds go to `<chart>.marks.txt` (with `--sidecars`), their counts to the json, and each
2x2 star to `meta["stars"]`. An any-mark 0/1 reading is derived from the kinds: `--option filled=#+`
counts only solid and plus in that 0/1 reading; the default counts every mark.

Different marks mean different colours (filled and crossed cells are two colours), so for this
layout `<chart>.txt` holds one digit per colour, indices into the gallery's palette: 0 empty,
1 solid, 2 plus, 3 hatching, 4 diagonal cross. Diagonals, wedges, half cells and unclear marks
have no colour of their own yet: they are 0 there and stay in `<chart>.marks.txt`. The any-mark
0/1 reading is `<chart>.filled.txt`. The mapping is `books/sources/mark_colours.csv`: rows for
book `*` are the default, rows with a book code override them for that book, and
`--option colours=#=1,+=1` overrides both for one run.

Each cell is cut between its own ruling lines, found again near the cell (Sibmacher's ruling
drifts up to a third of a cell from the fitted comb, and a rule left inside a cell reads as a
plus or a hatch). On plate 12 of Sibmacher 1597 (sib1597_12_p1) about 6 % of cells come out `?`,
mostly a cell whose cut still holds part of a rule. Against the committed 0/1 chart of that
plate: plus cells are 1 (2197 of 2263), hatched cells mostly 1 (496 of 547), the star diagonals
0 (114 of 120), and the `?` cells split about evenly, so they are the cells to check by eye.

## Checks

```
make sources-test    # drawn pages in all four layouts, read back (no scans needed)
make sources-check   # every scan in books/scans, PR #46 readers against these, byte for byte
```

`sources-check` needs the scans in `books/scans/<book>/` (git-ignored; `books/fetch.py`).
On the 129 scans of Sibmacher 1597 and 1604, Quentel 1529 and Jobin 1600 all 596 output files
(charts, check pictures, json) are identical, and all 87 committed charts in `patterns/books`
come out unchanged.

The two new layouts are prototypes, checked only on drawn pages so far:
`MultiSymbolPlateSource` scores a cell by its darkest part and cuts between the empty
level and the lightest mark (Otsu would drop light marks), then groups marks by a coarse
6x6 picture with k-means (fixed seed). `LineDrawingSource` fills closed outlines and fills a
cell when ink covers half of it.
