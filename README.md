# Sjónabok

## Overview

This open-source project digitises historical patterns from *Íslensk sjónabók* and other pattern books into reusable grids for study, comparison and machine knitting. The original digitisation focused on bicolour cross-stitch patterns; the expanded collection includes books with different motifs, symbols and colour schemes.

### About Sjónabók and Heimilisiðnaðarfélagið

The Sjónabók, published by Heimilisiðnaðarfélagið, is a collection of Icelandic medieval patterns that have been meticulously compiled and preserved. Heimilisiðnaðarfélagið, known in English as the Icelandic Home Crafts Association, is dedicated to preserving and promoting traditional Icelandic handcrafts. The book includes an accompanying CD containing .eps figures of these patterns, making them accessible for modern digital projects.

## Project Objectives

1. **Digitize Patterns**: Convert .eps figures from the Sjónabók CD into a simple matrix format.
2. **Open Source Contribution**: Make the digitized patterns available as an open-source resource.
3. **Facilitate Machine Knitting**: Enable the use of these historical patterns in contemporary machine knitting projects by HiDef Textiles.

## Main contributors

- **Snæfríður Ebba Ásgeirsdóttir (@snaefi)** created the original codebase as a **Student Innovation Fund (Nýsköpunarsjóður námsmanna) project**, digitising the bicolour patterns from the EPS files accompanying *Íslensk sjónabók* (2009). The original project and report materials are in the [HiDefTextiles/NSN-2024 repository](https://github.com/HiDefTextiles/NSN-2024).
- **Helga Ingimundardóttir (@tungufoss)** has since developed the codebase into a scalable, reusable project and added new features and pattern-book sources.

The original digitisation focused on bicolour patterns. The expanded collection can represent varied motifs and multi-colour charts with integer-coded grids such as `0`–`4`. [Issue #9](https://github.com/HiDefTextiles/Sjonabok/issues/9) tracks early processing problems with motifs in source EPS files that use different colours.

### Institutional acknowledgements

This project acknowledges the following institutions for their invaluable resources and support:

- **Heimilisiðnaðarfélagið (Icelandic Home Crafts Association)**
- **Listaháskóli Íslands (Iceland University of the Arts)**
- **Þjóðminjasafnið (The National Museum of Iceland)**
## Requirements

The project uses a simple Python program for converting the patterns. The required packages are listed in the `requirements.txt` file.

## File Format
Patterns are stored as text grids. Integer codes such as `0`–`4` distinguish the symbols or colours used in each chart; `0` represents the background. This supports varied motifs and multi-colour patterns instead of assuming every source is a binary cross grid.

## Usage
With the path to the Sjonabok folder the program can be run with the following line:
```
python3 convert_to_txt.py <path_to_eps_file> <path_to_txt_file>
python3 convert_to_png.py <path_to_txt_file> <path_to_png_file>
python3 split_pattern.py --cols_distance <int> --rows_distance <int> <path_to_txt_file> 
```
use `--help` to see the options for each program. To convert all files in a folder:
```
make init
make all 
```
Note, you might need to rename the path of the `EPS_DIR` folder in the Makefile.

## Gallery website
The `gallery/` folder holds a [Quarto](https://quarto.org) website for browsing and inspecting the patterns,
with the same look as the [HiDef textíll site](https://hideftextiles.github.io/). It is published at
<https://hideftextiles.github.io/Sjonabok/> by the GitHub Action in `.github/workflows/gallery.yml`.

```
make gallery-data      # measure each pattern, draw PNGs in the HI palette (gallery/patterns/)
make gallery           # build the site into gallery/_site
make gallery-preview   # live preview while editing
```

`gallery/scripts/build_gallery.py` computes the attributes used by the filters (type, mirror and turn
symmetry, frieze or point group, repeat, size, density, pieces, longest float). Generated files are not
committed. `gallery/scripts/sync-theme.sh` refreshes the shared styles from the main site.

![Gallery](gallery/preview/gallery.webp)

### Charts in the repository

<!-- counts -->
The gallery shows **751** charts from *Íslensk sjónabók*: 600 one-mark charts (`patterns/min/`), 101 multi-mark charts from 43 pages (`patterns/colour/`) and 50 alphabet sheets (`patterns/alphabets/`, 49 of them are fonts). Another 1067 charts from 24 printed European books (`patterns/books/`) are work in progress, hidden unless the *Work in progress* switch is on.
<!-- /counts -->

Only what cannot be rebuilt is committed: `patterns/min/` and `patterns/repeats.csv`, and the
colour charts and alphabet sheets described below (`patterns/colour/`, `patterns/alphabets/`).

- `patterns/min/<name>.txt` has one file per one-mark pattern. A border band whose chart is an exact
  repeat is stored as **one repeat unit**; every other chart (motifs, and bands that do not repeat
  exactly) is stored as drawn.
- `patterns/repeats.csv` lists every band: `name, kind, axis, period, status, mismatch, close`. `axis` is `x`
  for left to right and `y` for top to bottom. `status` is `unit` (the file is one repeat), `near` (it
  repeats, but `mismatch` of the cells differ, so the full chart is kept) or `none` (no repeat found).
  `close` is how many columns of the unit's start to add after whole units so the strip mirrors
  exactly end to end (0 or 1; empty when the band has no mirror), for frame sides that meet the
  corners the same way.
- `patterns/txt/` holds the full charts as digitised from the book. It is git-ignored; `make originals`
  restores it from git history, and `make repeats` rebuilds `patterns/min` and the manifest from it.

A unit is cut so that a border clipped at unit edges ends cleanly: no stray dots (pieces of 4 cells
or fewer) at either end, then ends that mirror each other (see `close`), then as few links between
filled cells cut as possible, then the lightest edge columns. Whole units therefore fit edge to edge, e.g. in a frame. PNGs, thumbnails and the gallery data are generated by `make` or the Action.

### Charts with several kinds of mark (`patterns/colour/`)

43 pages of the book draw their charts with more than one kind of mark: a filled diamond, a
cross, a circled cross, a round dot and a half-filled cell. In the manuscripts these are
different colours or stitches, and the 0/1 reader (`convert_to_txt.py`) merges them into one, so
these pages were left out of `patterns/min` until now. `convert_marks.py` reads them and keeps
the marks apart (`pattern_processing/eps_marks.py`):

```
python3 convert_marks.py images-multi/eps patterns/colour --review marks-review.png
make marks          # the same, with the EPS folder in MARKS_EPS_DIR
```

- `patterns/colour/<name>.txt` holds **one digit per cell**, the colour: `0` empty, `1` diamond,
  `2` cross, `3` circled cross, `4` round dot, `5` half cell. The digits are indices into the HI
  palette the gallery uses (`pattern_processing/pattern_to_png.py`). A chart with one kind of
  mark is plain 0/1, so every 0/1 tool still reads every file that has one colour.
- `patterns/colour/<name>.marks.txt` keeps the kind of every cell as a character (which corner of
  a half cell is inked, ruled lines that are not stitches, `?` for a mark to check by eye).
  `marks.csv` lists the characters and their digits, `pages.csv` what was read from each page.
- Pages that hold several charts are split as `split_patterns.py` does (`_p1`, `_p2`, ...): 101
  charts from 43 pages, 66 of them with two or more colours.
- Four pages print the chart turned 45 degrees (`thjms1105_86`, `thjmsth_116_618`, `_622`, `_642`);
  they are turned back 45 degrees anticlockwise before reading (which way up the chart then
  stands is a guess to check against the book).

Each cell is cut between its own ruling lines and the mark is named from the shape of its ink
(how full its box is, its corners, the middle of its sides, holes), so the reading does not
depend on where a mark sits in its cell. Of 130,557 marks, 96 come out `?` (41 of them on the
turned page 618). The gallery shows these charts in colour and lists, for each, how many
colours fall in one row (the knitting machine takes two).

### Alphabets (`patterns/alphabets/`)

The 50 alphabet sheets of the book are kept as **one motif each**: the whole sheet as drawn,
letters, numbers, frames and small figures together, as 0/1 charts. They are not split into
letters here. The gallery's *Alphabets* page has one tab per region and a rainbow overview
sheet for each. `patterns/alphabets/alphabets.csv` says which sheets have a font: the letters of
49 sheets are TrueType fonts in [Sjónabókarstafróf](https://github.com/HiDefTextiles/Sjonabok-stafrof)
([font gallery](https://hideftextiles.github.io/Sjonabok-stafrof/)); `thjmsth_116_628` is runes
(Futhark) and has no font.

The tabs, and the gallery's Collection filter, come from `gallery/regions.csv`: one row per tab,
in order, with the countries it holds (`*` for every country no other row names). Iceland is one
tab and mainland Europe another; splitting Europe later is a change to that file only.

### Seeds: the smallest piece and a symmetry recipe

`patterns/seeds.csv` goes one step further than the repeat units. For every one-mark chart (`patterns/min/`) it stores
the smallest **seed** and a **recipe** of steps that rebuild the full chart from it, cell for cell,
margins and partial repeats at the band ends included. A square star is one eighth of the star, a
`p2mm` border is a quarter of one repeat, a chart of one motif drawn several times is one motif.

```
make originals     # full charts into patterns/txt (needed only for make seeds)
make seeds         # patterns/seeds.csv and patterns/near.csv
make seeds-check   # rebuild every chart and compare with patterns/min and patterns/txt
make seeds-sheet   # seeds-sheet.png: charts beside their seeds
```

A recipe is read from the seed outwards, e.g. `mirror y 7; mirror x 22; tile x 115 2` (mirror the seed
down, then to the right, then repeat it to 115 cells, starting 2 cells into the repeat). The steps are `diag`,
`antidiag`, `rot4`, `mirror`, `turn`, `glide`, `tile` and `pad`; `pattern_processing/fundamental.py`
explains each one. The `group` column names the exact symmetry: the frieze group of the repeat for
bands (`p1`, `p11g`, `p1m1`, `p2`, `p2mg`, `p11m`, `p2mm`, read left to right as on the
[About page](https://hideftextiles.github.io/Sjonabok/about.html#symmetry)) and the point group for
motifs (`C1` … `D4`). `seen` is the gallery's group, which forgives 2 % of cells.

Hand-drawn charts are not always exact. A symmetry that almost holds is **never forced**: the seed
stays larger and `patterns/near.csv` lists the symmetry, how many cells break it and where (row:col in
the full chart), so the chart can be checked against the book. Every chart whose `group` and `seen`
differ is listed there.

| cells | charts | full charts | `patterns/min` | seeds | full / seed |
|---|---:|---:|---:|---:|---:|
| borders | 326 | 535 562 | 267 650 | 192 599 | 2.8 |
| edgings | 33 | 18 625 | 4 089 | 2 332 | 8.0 |
| vertical bands | 8 | 14 812 | 8 146 | 4 292 | 3.5 |
| rosettes | 100 | 191 632 | 191 632 | 37 047 | 5.2 |
| motifs | 133 | 369 802 | 369 802 | 255 093 | 1.4 |
| all | 600 | 1 130 433 | 841 319 | 491 363 | 2.3 |

`patterns/min` is unchanged; the seeds sit beside it for now.

The patterns are centuries old and in the public domain. Please credit *Íslensk sjónabók*
(Heimilisiðnaðarfélag Íslands, Listaháskóli Íslands, Þjóðminjasafn Íslands, 2009) and HiDef Textiles.

## License
This project is licensed under the [GNU General Public License v3.0](LICENSE), allowing for open collaboration and distribution.
