"""Repeat units of border bands.

A border in Sjónabók is usually one unit drawn over and over, but the chart
may start part-way into a unit and end with a partial one, and hand copying
leaves small slips. RepeatUnit finds the period, picks a clean place to cut
the unit (the phase: no stray dots at a clipped end, few links cut), takes the unit as a majority vote over every full copy
in the chart and reports how well the chart agrees with that unit.

All work is done on a horizontal band; a vertical band is transposed in and
out (axis "y").
"""

from dataclasses import dataclass

import numpy as np

PERIOD_TOLERANCE = 0.97   # share of cells that must agree for a repeat
MIRROR_TOLERANCE = 0.98   # share of cells that must agree for a mirror
STATUS_LIMITS = (("ok", 0.02), ("check", 0.06))   # mismatch up to … -> status
TINY_FRAGMENT = 4         # cells; a smaller piece at a clipped end looks like a stray dot


def agreement(a, b):
    """Share of equal cells in two arrays of the same shape."""
    return float(np.mean(a == b)) if a.size else 0.0


def find_period(t, tolerance=PERIOD_TOLERANCE):
    """Smallest horizontal repeat that occurs at least twice, or None."""
    w = t.shape[1]
    for p in range(2, w // 2 + 1):
        if agreement(t[:, :-p], t[:, p:]) >= tolerance:
            return p
    return None


def cut_links(u):
    """Pairs of filled cells (touching at a side or corner) that the cut
    between the unit's last and first column separates."""
    a, b = u[:, -1].astype(bool), u[:, 0].astype(bool)
    links = int((a & b).sum())
    links += int((a[1:] & b[:-1]).sum()) + int((a[:-1] & b[1:]).sum())
    return links


def mirror_close(u):
    """Columns to add after whole units so the strip is its own mirror image:
    0 when the unit is symmetric, 1 when the unit plus its first column is
    (the mirror axis runs through the cut column), None when neither."""
    if np.array_equal(u, u[:, ::-1]):
        return 0
    c = np.concatenate([u, u[:, :1]], axis=1)
    return 1 if np.array_equal(c, c[:, ::-1]) else None


def edge_fragments(u, tiny=TINY_FRAGMENT):
    """Shapes of at most `tiny` cells touching the ends of two copies of the
    unit side by side: what is left of a motif when a border is clipped."""
    strip = np.concatenate([u, u], axis=1).astype(bool)
    h, w = strip.shape
    seen = np.zeros_like(strip)
    count = 0
    for y0, x0 in zip(*np.nonzero(strip[:, [0, w - 1]])):
        x0 = 0 if x0 == 0 else w - 1
        if seen[y0, x0]:
            continue
        stack, size, seen[y0, x0] = [(y0, x0)], 0, True
        while stack:
            y, x = stack.pop()
            size += 1
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= ny < h and 0 <= nx < w and strip[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        count += size <= tiny
    return count


@dataclass
class RepeatUnit:
    """One repeat of a band, cut at a clean phase."""

    axis: str            # "x" (horizontal band) or "y" (vertical band)
    period: int          # cells per repeat along the band
    phase: int           # where the unit starts, counted in the trimmed chart
    unit: np.ndarray     # the unit in the chart's own orientation
    copies: int          # full repeats in the chart
    mismatch: float      # share of cells that differ from the ideal repeat

    @property
    def status(self):
        for name, limit in STATUS_LIMITS:
            if self.mismatch <= limit:
                return name
        return "poor"

    @classmethod
    def from_band(cls, t, axis="x"):
        """Repeat unit of a trimmed band, or None if it does not repeat."""
        h_band = t.T if axis == "y" else t
        p = find_period(h_band)
        if not p:
            return None
        copies = h_band.shape[1] // p
        stack = np.stack([h_band[:, k * p:(k + 1) * p] for k in range(copies)])
        votes = stack.mean(axis=0)                 # majority vote; a tie keeps the first copy
        unit = np.where(votes > 0.5, 1, np.where(votes < 0.5, 0, stack[0])).astype(np.uint8)
        phase = cls.clean_phase(unit)              # rotate the unit to a clean cut
        unit = np.roll(unit, -phase, axis=1)
        copies = (h_band.shape[1] - phase) // p
        ideal = cls.tile(unit, phase, h_band.shape[1])
        mismatch = float(np.mean(ideal != h_band))
        return cls(axis, p, phase, unit.T if axis == "y" else unit, copies, round(mismatch, 4))

    @staticmethod
    def clean_phase(unit):
        """Where to cut a cyclic unit so that a band clipped at unit edges ends
        cleanly. In order of priority:
          1. no tiny fragment (a few cells cut off a motif) at either end,
          2. ends that mirror each other exactly, so a frame side closes
             symmetrically (see mirror_close),
          3. as few connections between filled cells cut as possible,
          4. as little ink in the edge columns as possible."""
        best, best_score = 0, None
        for s in range(unit.shape[1]):
            u = np.roll(unit, -s, axis=1)
            cut_ink = int(u[:, 0].sum()) + int(u[:, -1].sum())
            score = (edge_fragments(u), mirror_close(u) is None, cut_links(u), cut_ink, s)   # lower is better
            if best_score is None or score < best_score:
                best, best_score = s, score
        return best

    @staticmethod
    def tile(unit, phase, width):
        """The ideal band: the unit repeated so that it starts at phase."""
        p = unit.shape[1]
        cols = (np.arange(width) - phase) % p
        return unit[:, cols]

    def horizontal(self):
        """The unit laid horizontally (rows across the band)."""
        return self.unit.T if self.axis == "y" else self.unit
