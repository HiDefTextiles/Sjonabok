# Overview layouts

`bands.csv` (id,row) and `motifs.csv` (id,x,y) place the charts on the two
overview sheets of the Explore page. They are made with Gurobi by
`gallery/scripts/pack_overview.py` from the item files that
`build_gallery.py` writes, and committed because the site build has no
Gurobi. If a file no longer lists exactly the charts on its sheet, the
build falls back to a simple packing.

    make overview-layout     # needs gurobipy and a licence
