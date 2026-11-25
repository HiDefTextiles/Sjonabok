"""Colour each chart by the figures found in it, with the whole HÍ palette.

    python recolour.py [--txt ../../patterns/txt] [--sheet OUT.png]

No knitting limits (colours per row, floats): this is to see the figures, not yet to knit.
Reads the places of the recurring sub-motifs (variants.py: places.csv, consensus.csv,
consensus/<id>.txt). In each chart, every kept place gets the exact cells of the consensus
figure (lined up on the place), so a bird joined to a border is coloured on its own and the
border keeps the base colour. A kind of figure (size variants together) gets one colour in
every chart, so the same rosette is the same colour wherever it is. Larger figures are painted
first; a smaller figure lying mostly inside one already painted keeps that colour, so a
rosette stays one rosette rather than a mosaic of its petals.

Writes work/submotifs/colour/<chart>.txt: 0 empty, 1 base (HÍ blue), 2.. the figure colours
in PALETTE order; and, with --sheet, a picture of the charts with the most figures.
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import subjects as S
from submotifs import OUT, SHIFT
from variants import Aligner

# HÍ palette (gallery/styles/hi-site.scss); base first, then the figure colours
BASE = (16, 9, 159)                 # HÍ blue
PALETTE = [(214, 31, 105),          # pink
           (45, 210, 192),          # teal
           (255, 160, 95),          # orange
           (250, 197, 91),          # yellow
           (252, 132, 132),         # red
           (0, 255, 186),           # green
           (38, 38, 38)]            # ink
WHITE = (255, 255, 255)
INK = (38, 38, 38)
COVERED = 0.5   # a smaller figure mostly inside a larger one keeps the larger one's colour


def read_bits(path):
    return np.array([[int(c) for c in line.strip()] for line in open(path) if line.strip()], bool)


class Recolour:
    def __init__(self, txt):
        self.units = {u.id: u for u in S.Corpus(txt, S.PILOT_KINDS + S.BAND_KINDS).units}
        cons = {r["submotif"]: r for r in S.read_csv(OUT / "consensus.csv")}
        self.kind = {m: (r["kind"] or f"s{m}") for m, r in cons.items()}
        self.figure = {m: read_bits(OUT / "consensus" / f"{m}.txt") for m in cons}
        self.places = defaultdict(list)
        for p in S.read_csv(OUT / "places.csv"):
            if p["kept"] == "1":
                self.places[p["chart"]].append(p)
        self.colour_of = self.colours()
        self.key = {}          # chart -> kind -> (sub-motif shown in the key, colour)

    def colours(self):
        """Kinds by how many charts they colour; the commonest get distinct colours first,
        the rest cycle through the palette."""
        n = Counter()
        for chart, pl in self.places.items():
            for k in {self.kind[p["submotif"]] for p in pl}:
                n[k] += 1
        return {k: i % len(PALETTE) for i, (k, _) in enumerate(n.most_common())}

    def mask(self, p):
        """The cells of the consensus figure, lined up on the place, that the chart fills."""
        y, x, h, w = (int(p[k]) for k in ("row", "col", "height", "width"))
        cut = np.asarray(self.units[p["chart"]].cells)[y:y + h, x:x + w].astype(bool)
        fig = Aligner(cut).align(self.figure[p["submotif"]])
        return y, x, cut & fig[SHIFT:SHIFT + h, SHIFT:SHIFT + w]

    def chart(self, cid):
        m = np.asarray(self.units[cid].cells).astype(int)       # 0 empty, 1 base
        used = {}
        self.key[cid] = {}
        for p in sorted(self.places[cid], key=lambda p: -int(p["height"]) * int(p["width"])):
            k = self.kind[p["submotif"]]
            c = self.colour_of[k]
            # two different kinds in one chart get different colours where the palette allows
            while c in used.values() and used.get(k) != c and len(used) < len(PALETTE):
                c = (c + 1) % len(PALETTE)
            used.setdefault(k, c)
            y, x, mk = self.mask(p)
            region = m[y:y + mk.shape[0], x:x + mk.shape[1]]
            if (region[mk] >= 2).mean() > COVERED:      # already part of a larger figure
                continue
            region[mk] = 2 + used[k]
            self.key[cid].setdefault(k, (p["submotif"], used[k]))
        return m

    @staticmethod
    def rgb(m):
        lut = np.array([WHITE, BASE] + PALETTE, np.uint8)
        return lut[m]

    def write(self):
        out = OUT / "colour"
        out.mkdir(exist_ok=True)
        self.done = {}
        for cid in self.units:
            m = self.chart(cid)
            self.done[cid] = m
            np.savetxt(out / f"{cid}.txt", m, fmt="%d", delimiter="")
        coloured = sum(1 for m in self.done.values() if (m >= 2).any())
        print(f"{coloured} of {len(self.done)} charts have coloured figures -> {out}")
        return self

    def sheet(self, path, n=24, cols=4, W=300, H=230):
        """The charts with the most figures, one manuscript after another; under each chart a
        key: every figure coloured in it, drawn on its own in its colour."""
        def score(cid):
            m = self.done[cid]
            return (min(len(self.key[cid]), 4), (m >= 2).mean())
        best = sorted((c for c in self.done if (self.done[c] == 1).any() and self.key[c]),
                      key=score, reverse=True)
        by_src = defaultdict(list)
        for c in best:
            by_src[self.units[c].pattern.source].append(c)
        pick = []
        while len(pick) < n and any(by_src.values()):
            for s in list(by_src):
                if by_src[s] and len(pick) < n:
                    pick.append(by_src[s].pop(0))
        KEY = 54
        rows = (len(pick) + cols - 1) // cols
        img = Image.new("RGB", (cols * W, rows * (H + KEY + 24)), WHITE)
        dr = ImageDraw.Draw(img)
        for i, cid in enumerate(pick):
            m = self.done[cid]
            x0, y0 = (i % cols) * W, (i // cols) * (H + KEY + 24)
            dr.text((x0 + 8, y0 + 6), cid, fill=INK)
            if self.units[cid].kind in S.BAND_KINDS:     # a band is repeated across the tile
                z = max(2, min(8, (H - 10) // m.shape[0]))
                reps = -(-((W - 16) // z) // m.shape[1])
                m = np.tile(m, (1, reps))[:, :(W - 16) // z]
            z = max(1, min((W - 16) // m.shape[1], (H - 10) // m.shape[0], 10))
            I = Image.fromarray(self.rgb(m)).resize((m.shape[1] * z, m.shape[0] * z), Image.NEAREST)
            img.paste(I, (x0 + 8, y0 + 22))
            kx = x0 + 8
            for k, (sm, c) in sorted(self.key[cid].items(), key=lambda kv: kv[1][1]):
                f = self.figure[sm]
                fz = max(1, min(4, (KEY - 8) // max(f.shape)))
                if kx + f.shape[1] * fz > x0 + W - 8:
                    break
                F = Image.fromarray(np.where(f[..., None], PALETTE[c], WHITE).astype(np.uint8))
                img.paste(F.resize((f.shape[1] * fz, f.shape[0] * fz), Image.NEAREST), (kx, y0 + 26 + H))
                kx += f.shape[1] * fz + 10
            dr.line((x0 + 8, y0 + 22 + H, x0 + W - 8, y0 + 22 + H), fill=(220, 220, 220))
        img.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--txt", default="../../patterns/txt")
    ap.add_argument("--sheet")
    a = ap.parse_args()
    r = Recolour(a.txt).write()
    if a.sheet:
        r.sheet(Path(a.sheet))


if __name__ == "__main__":
    main()
