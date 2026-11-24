"""Repeat units of border bands.

A border in Sjónabók is usually one unit drawn over and over, but the chart
may start part-way into a unit and end with a partial one, and hand copying
leaves small slips. RepeatUnit finds the period, picks a clean place to cut
the unit (the phase), takes the unit as a majority vote over every full copy
in the chart and reports how well the chart agrees with that unit.

All work is done on a horizontal band; a vertical band is transposed in and
out (axis "y").
"""

from dataclasses import dataclass

import numpy as np

PERIOD_TOLERANCE = 0.97   # share of cells that must agree for a repeat
MIRROR_TOLERANCE = 0.98   # share of cells that must agree for a mirror
STATUS_LIMITS = (("ok", 0.02), ("check", 0.06))   # mismatch up to … -> status


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
        phase = cls.clean_phase(h_band, p)
        copies = (h_band.shape[1] - phase) // p
        stack = np.stack([h_band[:, phase + k * p: phase + (k + 1) * p] for k in range(copies)])
        votes = stack.mean(axis=0)                 # majority vote; a tie keeps the first copy
        unit = np.where(votes > 0.5, 1, np.where(votes < 0.5, 0, stack[0])).astype(np.uint8)
        ideal = cls.tile(unit, phase, h_band.shape[1])
        mismatch = float(np.mean(ideal != h_band))
        return cls(axis, p, phase, unit.T if axis == "y" else unit, copies, round(mismatch, 4))

    @staticmethod
    def clean_phase(t, p):
        """Start of the unit: centred on a mirror axis when there is one,
        and cut where the band is lightest so motifs are not split."""
        w = t.shape[1]
        most = (w // p) - (1 if w // p > 2 else 0)   # keep enough copies to vote
        best, best_score = 0, None
        for s in range(min(p, w - p + 1)):
            if (w - s) // p < most:
                break
            u = t[:, s:s + p]
            mirrored = agreement(u, u[:, ::-1]) >= MIRROR_TOLERANCE
            cut_ink = int(t[:, s].sum()) + int(t[:, s + p - 1].sum())
            score = (not mirrored, cut_ink, s)     # lower is better
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
