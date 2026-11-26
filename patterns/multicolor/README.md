# Multi-symbol chart from issue #9

The scan reader described in [PR #47](https://github.com/HiDefTextiles/Sjonabok/pull/47) and implemented in [PR #49](https://github.com/HiDefTextiles/Sjonabok/pull/49) works from page images, so it does not require an EPS export. `MultiSymbolPlateSource` reads the first image attached to [issue #9](https://github.com/HiDefTextiles/Sjonabok/issues/9) as six ruled chart bands.

The source screenshot and its extracted chart grids are included here. The visible marks are X, diamond, circled cross, and half triangle. The `.symbols.txt` layers use `0` for empty cells and share codes `1`–`4` across all six bands, ordered by each mark's total frequency in the page. Rotated and mirrored instances are grouped as the same shape. The neighbouring `.txt` files retain the reader's binary filled/empty layer.

Page-wide symbol totals are `1: 2,427`, `2: 1,896`, `3: 1,575`, and `4: 829`. `issue9-example-1-preview.png` stacks the six colour-rendered symbol grids, preserving each scanned glyph's orientation while tinting it by its page-wide ID. Regenerate the grids and preview from the scan with `python patterns/multicolor/render_issue9.py`. Hand-drawn pages may need a separate grid or line-drawing strategy.
