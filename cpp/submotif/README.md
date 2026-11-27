# submotif: whole figures across all charts, in C++

The same rules as `books/travel.py`, so the answers agree exactly, about 100 times faster:

* a **piece** is an 8-connected group of filled cells, at least 10 cells and 2x2, that does not
  touch the edge of its chart; repeat units (`patterns/repeats.csv`, status `unit`) are tiled
  3x3 first and only pieces starting in the middle copy count;
* two pieces **match** when, after one of the 8 turns and mirrors and a shift of up to one
  cell, intersection over union is at least 0.8.

```
make              # bin/submotif and the Python module python/submotif*.so (needs pybind11)
make test         # against books/travel.py: same pieces, same iou, same pairs
make bench        # times both
```

From the repository root, `make similarity` runs the command line on `patterns/min` and
`patterns/books` and writes `books/similarity/pairs.csv` (every pair of matching figures
from different charts: chart, position, cells, iou) and `pieces.csv` (every figure).

Python:

```python
import submotif                     # PYTHONPATH=cpp/submotif/python
ps = submotif.find_pieces(chart.astype("uint8"), "name", tile=False, min_cells=10)
pairs = submotif.Matcher(match=0.8, shift=1).all_pairs(ps)      # [(i, j, iou)]
```

Classes: `Grid` (0/1 matrix with turns and mirror), `Piece` (a figure, its 8 views and a
turn-free key), `Matcher` (bucketed by size, threads). The command line does not try the
negative reading of white-line woodcuts; `travel.py` does that by passing inverted charts.
