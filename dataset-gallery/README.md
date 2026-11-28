# Dataset gallery template

Each dataset repository pins Sjonabok as a Git submodule at `sjonabok`.
Its static gallery lives in `docs/`, served by GitHub Pages from `main`.
The build reads the dataset’s own `books/books.csv`, `books/charts.csv`, and
`patterns/books/*.txt` and uses Sjonabok’s PNG renderer.

From the dataset checkout, update the submodule and regenerate the gallery:

```sh
git submodule update --init
python -m pip install Pillow numpy
python sjonabok/dataset-gallery/build.py . docs --repository https://github.com/HiDefTextiles/REPOSITORY
```

Commit the regenerated `docs/` alongside changes to grids or source metadata.
To update the shared design, advance the pinned Sjonabok revision and rebuild.
