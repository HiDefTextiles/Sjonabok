# Overview layouts

These two files place the charts on the overview sheets of the Explore page.
They are committed because they take minutes to compute. If a file no
longer lists exactly the charts on its sheet (or, for motifs, has an
overlap), the build falls back to a simple packing.

- `bands.csv` (id,column): which of the 8 columns each band is stacked in.
  Made with Gurobi (needs gurobipy and a licence) so that after every
  manuscript the columns are equally tall.
- `motifs.csv` (id,x,y): motifs, rosettes and short one-off pieces at
  their own size. Each is its stitches plus a one-cell clear ring (the '.'
  of pattern-synthesis clear_space), so outlines interlock; x,y is the
  corner of the ringed mask. Made by a seeded local search (no Gurobi) that
  minimises height with a pull towards rainbow order (--rainbow), then
  spreads the white evenly.

    make overview-layout
