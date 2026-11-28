# Dataset gallery template

Each dataset repository pins Sjonabok as a Git submodule at `sjonabok`.
GitHub Pages serves the generated gallery from the root of the dataset repository’s
`docs` branch. The builder reads the dataset’s source record and text grids, and
uses Sjonabok’s PNG renderer for previews. Each download is the original TXT grid.

From the dataset’s `main` checkout, update the submodule and build into a separate
checkout of the `docs` branch:

```sh
git submodule update --init --remote sjonabok
git worktree add ../dataset-docs docs
python -m pip install Pillow numpy
python sjonabok/dataset-gallery/build.py . ../dataset-docs --repository https://github.com/HiDefTextiles/REPOSITORY
```

Commit the submodule pin on `main` and the generated site on `docs`. A gallery
update does not require a dataset release.
