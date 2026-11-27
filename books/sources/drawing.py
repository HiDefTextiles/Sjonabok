"""Line drawings: a design drawn freehand, with no printed grid (outline
patterns in the early Italian books, Vinciolo's figures, sketches to be
counted out by the embroiderer).

There is no grid to find, so the grid is chosen: `cells` cells across the
drawing (or a fixed `pitch` in pixels). The strokes are thresholded,
small gaps closed, and closed outlines filled (fill=True), so a drawn leaf
becomes a solid leaf. Each cell is then filled when ink covers at least
`cover` of it. Uncertain = cells whose cover is within 0.1 of that.
"""
import cv2
import numpy as np
from scipy import ndimage

from .base import Chart, PatternSource, otsu, paint_cells, paper_level, read_gray


class LineDrawingSource(PatternSource):
    layout = "drawing"
    description = "free line drawing, no grid: strokes filled and resampled onto a chosen grid"

    def __init__(self, path, provenance=None, cells=60, pitch=None, fill=True,
                 cover=0.5, close=3, **options):
        super().__init__(path, provenance, **options)
        self.n_across, self.fixed_pitch = cells, pitch
        self.fill, self.cover, self.close = fill, cover, close
        g = read_gray(self.path)
        norm = np.clip(g.astype(float) / np.maximum(paper_level(g), 1), 0, 1)
        self.ink = 1 - norm
        self.result = None

    def shape(self):
        """Binary drawing: strokes, gaps closed, outlines filled."""
        t = otsu(self.ink)
        m = (self.ink > t).astype(np.uint8)
        if self.close:
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((self.close, self.close), np.uint8))
        # drop specks (paper grain, foxing): components under 0.02 % of the page
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= max(8, 0.0002 * m.size)
        m = keep[lab].astype(np.uint8)
        if self.fill:
            m = ndimage.binary_fill_holes(m).astype(np.uint8)
        return m, t

    def read(self):
        m, t = self.shape()
        ys, xs = np.nonzero(m)
        if len(xs) == 0:
            return []
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        p = float(self.fixed_pitch or (x1 - x0) / self.n_across)
        nx, ny = max(1, int(np.ceil((x1 - x0) / p))), max(1, int(np.ceil((y1 - y0) / p)))
        gx = np.round(x0 + p * np.arange(nx + 1)).astype(int)
        gy = np.round(y0 + p * np.arange(ny + 1)).astype(int)
        H, W = m.shape
        pad = np.zeros((max(H, gy[-1]) + 1, max(W, gx[-1]) + 1), np.float32)
        pad[:H, :W] = m
        # cover of each cell = mean of the binary shape inside it
        integ = cv2.integral(pad)
        area = np.outer(np.diff(gy), np.diff(gx)).astype(float)
        cov = (integ[np.ix_(gy[1:], gx[1:])] - integ[np.ix_(gy[:-1], gx[1:])]
               - integ[np.ix_(gy[1:], gx[:-1])] + integ[np.ix_(gy[:-1], gx[:-1])]) / np.maximum(area, 1)
        cells = (cov >= self.cover).astype(np.uint8)
        margin = np.abs(cov - self.cover)
        self.result = (cells, margin, gx, gy, m)
        name = f"{self.page_id}_d1"
        meta = dict(name=name, box=[int(x0), int(y0), int(x1), int(y1)], angle=0.0,
                    rows=int(ny), cols=int(nx), pitch_x=round(p, 2), pitch_y=round(p, 2),
                    threshold=round(float(t), 3), uncertain=int((margin < 0.1).sum()),
                    fill=round(float(cells.mean()), 3))
        return [Chart(name, cells, meta)]

    def check_image(self, path):
        if self.result is None:
            return
        cells, margin, gx, gy, m = self.result
        img = cv2.cvtColor((255 - self.ink * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        paint_cells(img, cells, margin, gx, gy, unsure=0.1)
        for x in gx:
            cv2.line(img, (int(x), int(gy[0])), (int(x), int(gy[-1])), (200, 200, 200), 1)
        for y in gy:
            cv2.line(img, (int(gx[0]), int(y)), (int(gx[-1]), int(y)), (200, 200, 200), 1)
        cv2.imwrite(str(path), img)
