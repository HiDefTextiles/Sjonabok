# Multi-symbol chart from issue #9

The scan reader described in [PR #47](https://github.com/HiDefTextiles/Sjonabok/pull/47) and implemented in [PR #49](https://github.com/HiDefTextiles/Sjonabok/pull/49) works from page images, so it does not require an EPS export. `MultiSymbolPlateSource` reads the first image attached to [issue #9](https://github.com/HiDefTextiles/Sjonabok/issues/9) as six ruled chart bands.

The source screenshot and its extracted chart grids are included here. The visible marks are X, diamond, circled cross, and half triangle. For each band, the `.symbols.txt` layer uses `0` for an empty cell; codes `1`–`4` identify the mark classes, ordered by frequency within that band. The IDs are local to each chart. Rotated and mirrored instances are grouped as the same shape. The neighbouring `.txt` files retain the reader's binary filled/empty layer.

`issue9-example-1-preview.png` stacks the six colour-rendered symbol grids and displays the representative mark shape in every filled cell. Regenerate the grids and preview from the scan with `python patterns/multicolor/render_issue9.py`. Hand-drawn pages may need a separate grid or line-drawing strategy.
