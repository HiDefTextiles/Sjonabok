"""Regenerate the scan-derived symbol grids and preview for issue #9."""
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "books"))
from sources import MultiSymbolPlateSource  # noqa: E402


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "issue9-example-1.png"
PREVIEW = HERE / "issue9-example-1-preview.png"
CELL = 18
MARGIN = 10
LABEL_HEIGHT = 42
GAP = 14
PALETTE = np.array([
    [255, 255, 255],  # empty
    [150, 30, 105],
    [40, 120, 220],
    [50, 160, 45],
    [20, 150, 220],
], dtype=np.uint8)


def main():
    source = MultiSymbolPlateSource(SOURCE, symbols=4)
    charts = source.charts()
    if len(charts) != 6:
        raise RuntimeError(f"expected six chart bands, found {len(charts)}")

    width = max(chart.cells.shape[1] for chart in charts) * CELL + 2 * MARGIN
    height = sum(chart.cells.shape[0] * CELL + LABEL_HEIGHT + GAP
                 for chart in charts) + MARGIN
    preview = np.full((height, width, 3), 255, np.uint8)
    y = MARGIN
    band_previews = []

    for chart, region in zip(charts, source._regions):
        symbols = chart.layers["symbols"]
        counts = [int((symbols == code).sum()) for code in range(5)]
        # These are long horizontal banners. Compare each cell with cells
        # several columns away to expose the strongest repeated motif spacing
        # as an independent check on the visual symbol assignments.
        repeats = []
        for shift in range(3, symbols.shape[1] // 2 + 1):
            left, right = symbols[:, :-shift], symbols[:, shift:]
            active = (left > 0) | (right > 0)
            coverage = float(active.mean())
            agreement = float(((left == right) & active).sum() / max(1, active.sum()))
            repeats.append((agreement, coverage, shift))
        best = max(repeats, default=(0.0, 0.0, 0))
        label = (f"{chart.name}  {symbols.shape[0]} x {symbols.shape[1]}  "
                 f"(page-global IDs; repeat +{best[2]}: "
                 f"{best[0]:.0%} of marked positions, {best[1]:.0%} coverage)")
        cv2.putText(preview, label, (MARGIN, y + 16), cv2.FONT_HERSHEY_SIMPLEX,
                    0.48, (35, 35, 35), 1, cv2.LINE_AA)
        legend_y = y + 34
        cv2.putText(preview, "0 empty", (MARGIN, legend_y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, (80, 80, 80), 1, cv2.LINE_AA)
        legend_x = MARGIN + 95
        for code in range(1, 5):
            cv2.putText(preview, f"{code}: {counts[code]}", (legend_x, legend_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        tuple(int(v) for v in PALETTE[code]), 1, cv2.LINE_AA)
            legend_x += 95

        sub = region.ink[region.y0:region.y1, region.x0:region.x1]
        for row in range(symbols.shape[0]):
            for col in range(symbols.shape[1]):
                code = int(symbols[row, col])
                if not code:
                    continue
                top, bottom = region.ys[row], region.ys[row + 1]
                left, right = region.xs[col], region.xs[col + 1]
                inset_y = max(1, int(round((bottom - top) * 0.2)))
                inset_x = max(1, int(round((right - left) * 0.2)))
                glyph = sub[top + inset_y:bottom - inset_y + 1,
                            left + inset_x:right - inset_x + 1]
                glyph = cv2.resize(glyph.astype(np.float32), (CELL - 2, CELL - 2),
                                   interpolation=cv2.INTER_AREA)
                tile = np.full((CELL - 2, CELL - 2, 3), 255, np.uint8)
                tile[glyph > 0.35] = PALETTE[code]
                top = y + LABEL_HEIGHT + row * CELL + 1
                left = MARGIN + col * CELL + 1
                preview[top:top + CELL - 2, left:left + CELL - 2] = tile

        grid_top = y + LABEL_HEIGHT
        grid_left = MARGIN
        grid_h, grid_w = symbols.shape[0] * CELL, symbols.shape[1] * CELL
        for row in range(symbols.shape[0] + 1):
            yy = grid_top + row * CELL
            cv2.line(preview, (grid_left, yy), (grid_left + grid_w, yy), (220, 220, 220), 1)
        for col in range(symbols.shape[1] + 1):
            xx = grid_left + col * CELL
            cv2.line(preview, (xx, grid_top), (xx, grid_top + grid_h), (220, 220, 220), 1)

        band = preview[y:grid_top + grid_h, :grid_left + grid_w + MARGIN]
        scale = min(1.0, 1400 / band.shape[1])
        if scale < 1:
            band = cv2.resize(band, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_AREA)
        band_previews.append((HERE / f"{chart.name}-preview.png", band.copy()))

        (HERE / f"{chart.name}.txt").write_text(
            "\n".join("".join(map(str, row)) for row in chart.cells) + "\n",
            encoding="ascii",
        )
        (HERE / f"{chart.name}.symbols.txt").write_text(
            "\n".join("".join(map(str, row)) for row in symbols) + "\n",
            encoding="ascii",
        )
        y += grid_h + LABEL_HEIGHT + GAP

    cv2.imwrite(str(PREVIEW), preview)
    for path, band in band_previews:
        cv2.imwrite(str(path), band, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    print(f"wrote {len(charts)} bands and {PREVIEW}")


if __name__ == "__main__":
    main()
