"""Multi-symbol plates: a ruled counted grid whose cells carry different
marks (solid square, cross, dot, diagonal, ...) that stand for different
colours or stitches, as in later counted cross-stitch books (Fürst c.1660).

The grid is found exactly as for RuledGridSource. Then every filled cell is
described by a coarse 6x6 picture of its mark, and the filled cells are grouped into
`symbols` kinds by k-means with a fixed seed, so a page reads the same
every time. The 0/1 chart is "any mark"; the kinds are an extra layer
(chart.layers["symbols"]: 0 = empty, 1 = the most frequent mark, 2 = next
most frequent, ...). Rotations and mirrors are canonicalised before grouping.
"""
import cv2
import numpy as np

from .base import otsu
from .ruled import GridRegion, RuledGridSource


def cell_features(cell, size=6):
    """The cell's interior shrunk to size x size (area average): a coarse
    picture of the mark, so solid, cross, dot, diagonal and ring differ.
    Canonicalise its rotations and mirrors so a symmetric symbol does not
    become a new kind solely because it appears in another orientation."""
    if cell.shape[0] < 2 or cell.shape[1] < 2:
        return np.zeros(size * size, np.float32)
    small = cv2.resize(cell.astype(np.float32), (size, size), interpolation=cv2.INTER_AREA)
    small = np.clip(np.rint(small * 255), 0, 255).astype(np.uint8)
    rotations = [np.rot90(small, k) for k in range(4)]
    rotations += [np.fliplr(image) for image in rotations]
    canonical = min(rotations, key=lambda image: image.tobytes())
    return (canonical.astype(np.float32) / 255).ravel()


def cluster_page_features(feature_groups, kinds):
    """Cluster glyphs from all chart bands and rank IDs by page frequency."""
    lengths = [len(group) for group in feature_groups]
    total = sum(lengths)
    if not total:
        return ([np.zeros(0, np.int32) for _ in feature_groups],
                np.zeros((0, 36), np.float32), np.zeros(0, np.int64))
    X = np.concatenate(feature_groups).astype(np.float32, copy=False)
    k = min(kinds, len(X))
    if k == 1:
        labels, centres = np.zeros(len(X), np.int32), X[:1]
    else:
        cv2.setRNGSeed(1)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-4)
        _, labels, centres = cv2.kmeans(X, k, None, crit, 8, cv2.KMEANS_PP_CENTERS)
        labels = labels.ravel()
    counts = np.bincount(labels, minlength=k)
    order = sorted(range(k), key=lambda i: (-counts[i], -centres[i].mean(), i))
    rank = np.empty(k, dtype=np.int32)
    rank[order] = np.arange(1, k + 1)
    groups = np.split(rank[labels], np.cumsum(lengths)[:-1])
    return groups, centres[order], counts[order]


def mark_profile(ink, axis, q=10):
    """How much mark ink lies on each line across `axis`.

    A ruling line (and the soft edge of a blurred one) is equally dark
    along its whole length, so the low quantile of each line is
    subtracted: what is left is the marks only, and the narrow white gaps
    between neighbouring glyphs show up as minima."""
    return np.clip(ink.mean(axis=axis) - np.percentile(ink, q, axis=axis), 0, None)


def fit_lattice(lines, tol=1.5):
    """Fit x = phase + i * pitch to the line follower's snapped lines.

    The follower snaps each line within +-3 px, which absorbs paper
    stretch, but on a clean capture a heavy major line (every tenth) can
    pull it a few pixels off for a stretch. Lines more than `tol` px off
    the fit are dropped and the fit repeated. Returns (pitch, phase), or
    None for fewer than four lines."""
    lines = np.asarray(lines, float)
    if len(lines) < 4:
        return None
    i = np.arange(len(lines))
    keep = np.ones(len(lines), bool)
    for _ in range(5):
        pitch, phase = np.polyfit(i[keep], lines[keep], 1)
        new = np.abs(lines - (phase + pitch * i)) <= tol
        if new.sum() < 4 or (new == keep).all():
            break
        keep = new
    return float(pitch), float(phase)


def gap_lattice(profile, pitch, phase0, lo, hi, span=0.03, shift=1.5, fixed_pitch=False):
    """Refine a ruling lattice so its lines run through the glyph gaps.

    Start from the fitted ruling (pitch, phase0) and search pitch within
    +-span and phase within +-shift px for the evenly spaced
    boundaries with the least mark ink between `lo` and `hi`. A screen
    capture rendered at a fractional pitch then stays within half a pixel
    of the glyphs across the whole page; on a blurred print, where marks
    have no clear gaps, the profile is flat and the ruling wins.
    Returns (pitch, phase)."""
    pitches = [pitch] if fixed_pitch else np.arange(pitch - span, pitch + span, 0.002)
    x = np.arange(len(profile))
    best = (np.inf, pitch, 0.0)
    # The same boundaries (counted from the left end of the motif) are
    # compared for every candidate, so a smaller pitch cannot win by
    # squeezing in an extra boundary over empty paper.
    k = np.arange(0, int(round((hi - lo) / pitch)) + 2)
    for p in pitches:
        # phase0 moved to the left end of the motif, +- `shift` px
        base = phase0 + p * np.floor((lo - p - phase0) / p)
        phases = base + np.arange(-shift, shift + 1e-9, 0.1)
        pos = phases[:, None] + p * k[None, :]
        cost = np.interp(pos, x, profile).mean(axis=1)
        i = int(np.argmin(cost))
        if cost[i] < best[0] - 1e-9:
            best = (float(cost[i]), float(p), float(phases[i] % p))
    return best[1], best[2]


def lattice_lines(pitch, phase, size):
    """Every lattice line phase + k * pitch inside [0, size)."""
    first = int(np.ceil(-phase / pitch))
    last = int(np.floor((size - 1 - phase) / pitch))
    return np.rint(phase + pitch * np.arange(first, last + 1)).astype(int)


def mark_bounds(mask, axis):
    """First and last index of the dark motif area along one axis.

    Pale graph paper around and between charts is ruled like the chart
    itself, so the chart's extent comes from the darker mark ink instead:
    the span from the first to the last substantial run of marked lines."""
    profile = mask.mean(axis=axis)
    smooth = np.convolve(profile, np.ones(9, np.float32) / 9, mode="same")
    low, high = np.percentile(smooth, [20, 90])
    cut = low + 0.2 * (high - low)
    active = np.flatnonzero(smooth > cut)
    runs = np.split(active, np.flatnonzero(np.diff(active) > 1) + 1) if len(active) else []
    substantial = [run for run in runs if len(run) >= 12]
    return (int(substantial[0][0]), int(substantial[-1][-1])) if substantial else None


class SymbolRegion(GridRegion):
    kinds = 3

    def tighten(self):
        """Remember the high-contrast motif area inside the ruled-page crop.

        Some scans show the pale cell grid in the margins between charts. The
        base reader treats that ruling as chart content, so keep a separate
        extent based on the darker motif ink for trimming padded rows and
        columns later (crop coordinates).
        """
        mask = (self.ink > 0.5).astype(np.float32)
        self.mark_y_bounds = mark_bounds(mask, axis=1)
        self.mark_x_bounds = mark_bounds(mask, axis=0)
        super().tighten()

    def trim_mark_margins(self):
        """Drop padded rows whose cell centres lie outside the printed motifs."""
        if self.mark_y_bounds is None or not len(self.ys):
            return
        centres = self.y0 + (self.ys[:-1] + self.ys[1:]) / 2
        keep = np.flatnonzero((centres >= self.mark_y_bounds[0]) &
                              (centres <= self.mark_y_bounds[1]))
        if not len(keep):
            return
        first, last = int(keep[0]), int(keep[-1])
        if first == 0 and last == len(self.cells) - 1:
            return
        self.cells = self.cells[first:last + 1]
        self.scores = self.scores[first:last + 1]
        self.margin = self.margin[first:last + 1]
        self.ys = self.ys[first:last + 2]

    def fit(self):
        """Track the pale ruling beneath dense marks, then cut between glyphs.

        The general ruled reader uses the 30th percentile so dark marks do not
        pull the line fit. Multi-symbol plates can fill nearly every cell, so
        that profile often follows the motifs instead of the faint grid. A
        lower quantile keeps the regular ruling visible in those scans; it
        gives the pitch. The cell lattice itself is then placed in the gaps
        between the glyphs (gap_lattice), one evenly spaced lattice per axis.
        Padding rows and columns are trimmed later by the motif extent.
        """
        super().fit(profile_quantile=10)
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        ylo, yhi = self.motif_span(self.mark_y_bounds, self.y0, sub.shape[0])
        xlo, xhi = self.motif_span(self.mark_x_bounds, self.x0, sub.shape[1])
        band = sub[ylo:yhi + 1]
        self.col_profile = mark_profile(band, axis=0)
        px, phx = fit_lattice(self.xs) or (self.px, float(self.xs[0]))
        self.px, phx = gap_lattice(self.col_profile, px, phx, xlo, xhi)
        self.py = self.px
        self.x_phase = phx
        _, phy = gap_lattice(mark_profile(sub[:, xlo:xhi + 1], axis=1), self.py,
                             float(self.ys[0]), ylo, yhi, fixed_pitch=True)
        # stay within the ruled area the line follower found
        self.ruled_x = (int(self.xs[0]), int(self.xs[-1]))
        self.xs = self.within(lattice_lines(self.px, phx, sub.shape[1]), self.ruled_x, self.px)
        self.ys = self.within(lattice_lines(self.py, phy, sub.shape[0]),
                              (int(self.ys[0]), int(self.ys[-1])), self.py)
        return self

    @staticmethod
    def within(lines, span, pitch):
        """Lattice lines inside the ruled span, allowing a half-cell shift."""
        ok = (lines >= span[0] - pitch / 2) & (lines <= span[1] + pitch / 2)
        return lines[ok] if ok.sum() >= 2 else lines

    @staticmethod
    def motif_span(bounds, offset, size):
        """Motif extent in crop-box coordinates (whole box if unknown)."""
        if bounds is None:
            return 0, size - 1
        return max(0, bounds[0] - offset), min(size - 1, bounds[1] - offset)

    @property
    def page_x(self):
        """Offset from crop columns to page columns."""
        return self.page_box[0] + self.x0

    def set_columns(self, pitch, page_phase):
        """Use a page-wide column lattice (given in page pixels)."""
        sub_w = self.x1 - self.x0
        self.xs = self.within(lattice_lines(pitch, page_phase - self.page_x, sub_w),
                              self.ruled_x, pitch)

    def column_centres(self):
        """Column centres in page pixels."""
        return self.page_x + (self.xs[:-1] + self.xs[1:]) / 2

    def keep_columns(self, keep):
        """Keep columns [first, last] (inclusive), lines and layers in step."""
        first, last = keep
        self.cells = self.cells[:, first:last + 1]
        self.scores = self.scores[:, first:last + 1]
        self.margin = self.margin[:, first:last + 1]
        self.xs = self.xs[first:last + 2]

    def score(self, inner=0.2, q=90):
        """As the ruled reader, but a cell is scored by its darkest part
        (the q-th percentile of its interior), not its mean: with several
        kinds of mark a thin cross has little ink on average yet is as
        much a mark as a solid square. The cut: Otsu would split solid
        marks from light ones, so the scores are grouped into kinds + 1
        levels (1-d k-means, fixed seed) and the cut is halfway between the
        lowest level (empty cells) and the next."""
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        h, w = len(self.ys) - 1, len(self.xs) - 1
        s = np.zeros((h, w))
        for r in range(h):
            a, b = self.ys[r], self.ys[r + 1]
            ma = max(1, int(round((b - a) * inner)))
            for c in range(w):
                l, rr = self.xs[c], self.xs[c + 1]
                mb = max(1, int(round((rr - l) * inner)))
                cell = sub[a + ma:b - ma + 1, l + mb:rr - mb + 1]
                s[r, c] = np.percentile(cell, q) if cell.size else 0.0
        self.scores = s
        self.threshold = otsu(s)
        v = s.astype(np.float32).reshape(-1, 1)
        k = min(self.kinds + 1, len(np.unique(v)))
        if k >= 2:
            cv2.setRNGSeed(1)
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5)
            _, _, c = cv2.kmeans(v, k, None, crit, 8, cv2.KMEANS_PP_CENTERS)
            c = np.sort(c.ravel())
            self.threshold = float((c[0] + c[1]) / 2)
        self.cells = (s > self.threshold).astype(np.uint8)
        self.margin = np.abs(s - self.threshold)
        # A dense symbol chart can have a legitimate fully marked edge row;
        # trim the padded scan margin by its motif bounds below instead.
        self.trim_mark_margins()
        return self

    def mark_features(self, inner=0.2):
        sub = self.ink[self.y0:self.y1, self.x0:self.x1]
        feats, where = [], []
        for r, c in zip(*np.nonzero(self.cells)):
            a, b = self.ys[r], self.ys[r + 1]
            l, rr = self.xs[c], self.xs[c + 1]
            ma, mb = max(1, int(round((b - a) * inner))), max(1, int(round((rr - l) * inner)))
            feats.append(cell_features(sub[a + ma:b - ma + 1, l + mb:rr - mb + 1]))
            where.append((r, c))
        return (np.asarray(feats, np.float32).reshape(-1, 36), where)

    def set_symbols(self, where, labels, centres):
        self.symbols = np.zeros_like(self.cells)
        for (r, c), code in zip(where, labels):
            self.symbols[r, c] = code
        self.symbol_centres = centres

    def classify(self, k, inner=0.2):
        X, where = self.mark_features(inner)
        labels, centres, _ = cluster_page_features([X], k)
        self.set_symbols(where, labels[0], centres)
        return self

    def chart(self):
        ch = super().chart()
        ch.layers["symbols"] = self.symbols
        ch.meta["symbols"] = {str(i + 1): int((self.symbols == i + 1).sum())
                              for i in range(int(self.symbols.max()))}
        return ch


class MultiSymbolPlateSource(RuledGridSource):
    """Ruled grid with several kinds of mark. options: symbols=3 (kinds)."""
    layout = "symbols"
    description = "ruled grid with several mark kinds, IDs shared and ranked page-wide"
    region_class = SymbolRegion
    PALETTE = [(40, 40, 230), (40, 170, 40), (200, 90, 20), (160, 40, 160), (20, 160, 200)]

    def __init__(self, path, provenance=None, symbols=3, **options):
        super().__init__(path, provenance, **options)
        self.k = symbols

    def regions(self):
        regs = super().regions()
        for g in regs:
            g.kinds = self.k
        return regs

    def read(self):
        regs = [g.fit() for g in self.regions()]
        self.share_columns(regs)
        regs = [g.score() for g in regs]
        self._regions = [g for g in regs
                         if g.cells.shape[0] >= 3 and g.cells.shape[1] >= 3]
        self.trim_page_columns()
        feature_groups, locations = [], []
        for g in self._regions:
            current, where = g.mark_features()
            feature_groups.append(current)
            locations.append(where)
        labels, centres, counts = cluster_page_features(feature_groups, self.k)
        self._symbol_counts = np.zeros(self.k + 1, dtype=int)
        self._symbol_counts[1:len(counts) + 1] = counts
        for g, where, codes in zip(self._regions, locations, labels):
            g.set_symbols(where, codes, centres)
        return [g.chart() for g in self._regions]

    def share_columns(self, regs):
        """Give every chart band on the page one column lattice.

        Banners laid out on one sheet share their columns. Pooling the mark
        profiles of all bands fixes pitch and phase better than any single
        sparse band can. Skipped when a band had to be deskewed, since its
        columns are then not the page's."""
        if len(regs) < 2 or any(abs(g.angle) > 0.2 for g in regs):
            return
        width = max(g.page_x + len(g.col_profile) for g in regs)
        pooled = np.zeros(width)
        spans = []
        for g in regs:
            pooled[g.page_x:g.page_x + len(g.col_profile)] += g.col_profile
            lo, hi = g.motif_span(g.mark_x_bounds, g.x0, len(g.col_profile))
            spans.append((g.page_x + lo, g.page_x + hi))
        lo, hi = min(sp[0] for sp in spans), max(sp[1] for sp in spans)
        pitch = float(np.median([g.px for g in regs]))
        # the bands' own phases on the page, folded onto one cell
        folded = np.array([(g.page_x + g.x_phase) % pitch for g in regs])
        angles = folded / pitch * 2 * np.pi
        phase0 = (np.angle(np.exp(1j * angles).mean()) / (2 * np.pi) * pitch) % pitch
        pitch, phase = gap_lattice(pooled, pitch, phase0, lo, hi)
        for g in regs:
            g.px = g.py = pitch
            g.set_columns(pitch, phase)

    def trim_page_columns(self):
        """Drop grid-only margin columns, page-wide.

        Banners on one sheet share their columns, and a sparse band can
        legitimately start or end with empty columns, so the margin is set
        by the dark motif extent of the whole page, not band by band. With
        the shared column lattice every band then has the same width."""
        bounds = [(g.page_x - g.x0 + b[0], g.page_x - g.x0 + b[1])
                  for g in self._regions if (b := g.mark_x_bounds)]
        if len(self._regions) < 2 or not bounds:
            return
        lo, hi = min(b[0] for b in bounds), max(b[1] for b in bounds)
        for g in self._regions:
            centres = g.column_centres()
            keep = np.flatnonzero((centres >= lo) & (centres <= hi))
            if len(keep):
                g.keep_columns((int(keep[0]), int(keep[-1])))

    def check_image(self, path):
        tiles = []
        for g in self._regions:
            img = cv2.cvtColor(g.gray, cv2.COLOR_GRAY2BGR)
            for r, c in zip(*np.nonzero(g.symbols)):
                x0, x1 = g.x0 + g.xs[c], g.x0 + g.xs[c + 1]
                y0, y1 = g.y0 + g.ys[r], g.y0 + g.ys[r + 1]
                col = np.array(self.PALETTE[(g.symbols[r, c] - 1) % len(self.PALETTE)])
                sub = img[y0 + 2:y1 - 1, x0 + 2:x1 - 1]
                sub[:] = (0.45 * sub + 0.55 * col).astype(np.uint8)
            cv2.putText(img, f"{g.name} {g.cells.shape[0]}x{g.cells.shape[1]}", (6, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 80, 0), 2)
            tiles.append(img)
        if tiles:
            w = max(t.shape[1] for t in tiles)
            tiles = [cv2.copyMakeBorder(t, 0, 6, 0, w - t.shape[1], cv2.BORDER_CONSTANT,
                                        value=(255, 255, 255)) for t in tiles]
            cv2.imwrite(str(path), np.vstack(tiles))
