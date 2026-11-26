#!/usr/bin/env python3
"""White-line woodcut pages photographed with a warped page (Gülfferich,
Egenolff): the cell grid bends, so one set of column and row borders does
not fit the whole block. Same steps as woodcut.py, but every cell centre is
re-centred on the white squares near it (a local grid), then smoothed.
    python3 warped.py page.webp outdir
"""
import argparse, json
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from woodcut import WoodcutPage, WoodcutGrid, check_image


class WarpedGrid(WoodcutGrid):
    def fit(self, iters=3):
        c = self.squares()
        if len(c) < 30:
            return None
        p0 = self.pitch(c)
        px, py = self.refine_axis(c[:, 0], c[:, 1], p0), self.refine_axis(c[:, 1], c[:, 0], p0)
        self.p, self.px, self.py = (px + py) / 2, px, py
        H, W = self.light.shape
        xs = self.lines(c[:, 0], px, W); ys = self.lines(c[:, 1], py, H)
        cx = (xs[:-1] + xs[1:]) / 2; cy = (ys[:-1] + ys[1:]) / 2
        gx, gy = np.meshgrid(cx, cy)                     # cell centres, rows x cols
        tree = cKDTree(c)
        for _ in range(iters):                           # pull each centre to the square near it
            d, i = tree.query(np.c_[gx.ravel(), gy.ravel()], distance_upper_bound=0.4 * min(px, py))
            ok = np.isfinite(d)
            dx = np.zeros(gx.size); dy = np.zeros(gx.size); w = ok.astype(float)
            dx[ok] = c[i[ok], 0] - gx.ravel()[ok]; dy[ok] = c[i[ok], 1] - gy.ravel()[ok]
            # smooth the shift field over 7x7 cells (filled cells have no square)
            k = np.ones((7, 7))
            ws = ndimage.convolve(w.reshape(gx.shape), k, mode="nearest") + 1e-6
            sx = ndimage.convolve((dx * w).reshape(gx.shape), k, mode="nearest") / ws
            sy = ndimage.convolve((dy * w).reshape(gx.shape), k, mode="nearest") / ws
            gx = gx + sx; gy = gy + sy
        self.gx, self.gy = gx, gy
        h, w = gx.shape
        s = np.zeros((h, w)); r = 0.25 * min(px, py)
        for a in range(h):
            for b in range(w):
                x, y = gx[a, b], gy[a, b]
                y0, y1, x0, x1 = int(y - r), int(y + r) + 1, int(x - r), int(x + r) + 1
                if y0 < 0 or x0 < 0 or y1 > H or x1 > W:
                    s[a, b] = 0; continue
                s[a, b] = self.light[y0:y1, x0:x1].mean()
        t, _ = cv2.threshold((s * 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        self.threshold = t / 255
        hi = ndimage.percentile_filter(s, 92, size=11, mode="nearest")
        lo = ndimage.percentile_filter(s, 8, size=11, mode="nearest")
        span = hi - lo
        rel = np.where(span > 0.15, (s - lo) / np.maximum(span, 1e-6), (s > self.threshold).astype(float))
        self.cells = (rel < 0.5).astype(np.uint8)
        self.margin = np.abs(rel - 0.5) * np.maximum(span, 0.1)
        # borders for the check image: mean positions
        self.xs = np.clip(np.r_[gx[:, 0].mean() - px / 2, (gx.mean(0)[1:] + gx.mean(0)[:-1]) / 2, gx[:, -1].mean() + px / 2], 0, W - 1).astype(int)
        self.ys = np.clip(np.r_[gy[0].mean() - py / 2, (gy.mean(1)[1:] + gy.mean(1)[:-1]) / 2, gy[-1].mean() + py / 2], 0, H - 1).astype(int)
        return self


def check_local(light, g, bands, path):
    img = cv2.cvtColor((light * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    r = int(0.35 * min(g.px, g.py))
    for a in range(g.cells.shape[0]):
        for b in range(g.cells.shape[1]):
            x, y = int(g.gx[a, b]), int(g.gy[a, b])
            if g.cells[a, b]:
                cv2.rectangle(img, (x - r, y - r), (x + r, y + r), (40, 40, 230), -1)
            else:
                cv2.circle(img, (x, y), 1, (0, 200, 0), -1)
    cv2.imwrite(str(path), img)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("page"); ap.add_argument("outdir")
    ap.add_argument("--all-blocks", action="store_true", help="read every large dark block, not only the largest")
    a = ap.parse_args(); out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    page = WoodcutPage(a.page)
    boxes = page.blocks() if a.all_blocks else [b for b in [page.block()] if b is not None]
    meta = []; k = 0
    for j, (x0, y0, x1, y1) in enumerate(boxes):
        crop = page.light[y0:y1, x0:x1].astype(np.float32)
        g = WarpedGrid(crop, page.path.stem).fit()
        if g is None:
            continue
        bands = g.bands()
        for ra, rb, cl, cr in bands:
            k += 1; name = f"{page.path.stem}_b{k}"; cells = g.cells[ra:rb, cl:cr]
            (out / f"{name}.txt").write_text("\n".join("".join(map(str, r)) for r in cells) + "\n")
            meta.append(dict(name=name, box=[int(x0), int(y0), int(x1), int(y1)], angle=0.0, rows=int(rb - ra), cols=int(cr - cl),
                             pitch_x=round(g.px, 2), pitch_y=round(g.py, 2), threshold=round(g.threshold, 3),
                             uncertain=int((g.margin[ra:rb, cl:cr] < 0.05).sum()), fill=round(float(cells.mean()), 3)))
        suffix = "" if j == 0 else f"_{j + 1}"
        check_local(crop, g, bands, out / f"{page.path.stem}_check{suffix}.jpg")
    print(json.dumps(meta))

if __name__ == "__main__":
    main()
