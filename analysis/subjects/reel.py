"""A short vertical video: one recurring figure as each manuscript draws it, morphing
from book to book in time order, the manuscript named at the bottom.

    python reel.py [--kind 40] [--out work/submotifs/reel.mp4] [--txt ../../patterns/txt]

The figure of each manuscript is the vote of its own charts (variants.Consensus over the
places of the size variant that manuscript uses most), so a book's version is how its
scribe mostly drew it. Between two books, cells that appear or vanish change in a ripple
from the centre outwards; new cells flash HÍ pink, then settle to HÍ blue.
1080 x 1920 (9:16) at 30 frames a second, written with ffmpeg.
"""
import argparse
import csv
import subprocess
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import subjects as S
from submotifs import OUT
from submotifs import SHIFT
from variants import Aligner, Consensus, clean, trim

W, H, FPS = 1080, 1920, 30
HOLD, MORPH, END, CLOSE = 1.7, 1.1, 2.5, 2.5   # under 30 s: Instagram autoplay and stories
BLUE = np.array((16, 9, 159), float)
PINK = np.array((214, 31, 105), float)
PAPER = np.array((255, 255, 255), float)
GRID = np.array((236, 236, 244), float)
INK = (38, 38, 38)
FRAME_BAND = "thjms2008-14_522_p3"   # border band for the frame (patterns/repeat)
OWN_CENTRE = 0   # >0: each book keeps only its centre square of 2*k+1 cells, arms shared (Helga preferred whole figures)
SITE = "hideftextiles.github.io/Sjonabok"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class BookFigures:
    """The figure of one size kind, as each manuscript draws it."""

    def __init__(self, txt, kind):
        self.units = {u.id: u for u in S.Corpus(txt, S.PILOT_KINDS + S.BAND_KINDS).units}
        cons = {r["submotif"]: r for r in S.read_csv(OUT / "consensus.csv")}
        members = {m for m, r in cons.items() if r["kind"] == str(kind)}
        self.dates = {r["source"]: r for r in S.read_csv(S.HERE / "manuscript_dates.csv")}
        by_book = defaultdict(lambda: defaultdict(list))
        for p in S.read_csv(OUT / "places.csv"):
            if p["submotif"] in members and p["kept"] == "1":
                by_book[self.units[p["chart"]].pattern.source][p["submotif"]].append(p)
        # every size variant as each book draws it (the vote of that book's charts)
        self.versions = {}
        for src in sorted(by_book, key=lambda s: int(self.dates[s]["order"])):
            self.versions[src] = [v for pl in by_book[src].values() for v in self.version(pl)]
        # a book may draw the figure more than one way (a star with thin points, a flower with
        # broad petals); show the way closest to what the books draw most, so that the reel
        # compares like with like
        first = {src: max(v, key=lambda t: t[2]) for src, v in self.versions.items()}   # each book's main vote
        n = max(max(t[0].shape) for v in self.versions.values() for t in v) + 2
        self.reference = self.majority([t[0] for t in first.values()], n)
        self.figures, self.charts = [], []
        for src, vs in self.versions.items():
            fig, chart, charts = max(vs, key=lambda t: (self.likeness(t[0], n), t[2]))
            self.figures.append((src, fig, charts))
            self.charts.append(chart)

    def version(self, pl):
        """(figure, marked chart, number of charts) for one book's places of one sub-motif."""
        cuts = [(p["chart"], int(p["row"]), int(p["col"]), self.cut(p)) for p in pl]
        ref = max((c for *_, c in cuts), key=lambda c: c.sum())
        con = Consensus(ref, cuts).settle()
        fig = clean(con.cells)   # stray cells dropped, near symmetry evened out
        best = max(range(len(pl)), key=lambda i: con.fit[i])
        out = [(fig, self.marked(pl[best], fig), len({p["chart"] for p in pl}))]
        # and each single drawing, in case the vote blurred a star into a broad flower
        for p, (*_, c) in zip(pl, cuts):
            f = clean(c)
            out.append((f, self.marked(p, f), 1))
        return out

    @staticmethod
    def on_grid(f, n):
        g = np.zeros((n, n), bool)
        y, x = (n - f.shape[0]) // 2, (n - f.shape[1]) // 2
        g[y:y + f.shape[0], x:x + f.shape[1]] = f[:n, :n]
        return g

    def majority(self, figs, n):
        grids = [self.on_grid(f, n) for f in figs]
        al = [grids[0]] + [Aligner(grids[0]).align(g)[SHIFT:SHIFT + n, SHIFT:SHIFT + n] for g in grids[1:]]
        return np.mean(al, 0) >= 0.5

    def likeness(self, f, n):
        g = Aligner(self.reference).align(self.on_grid(f, n))[SHIFT:SHIFT + n, SHIFT:SHIFT + n]
        return (g & self.reference).sum() / max(1, (g | self.reference).sum())

    def marked(self, p, fig):
        y, x, h, w = (int(p[k]) for k in ("row", "col", "height", "width"))
        m = np.asarray(self.units[p["chart"]].cells).astype(int)
        cut = m[y:y + h, x:x + w].astype(bool)
        mk = cut & Aligner(cut).align(fig)[SHIFT:SHIFT + h, SHIFT:SHIFT + w]
        m[y:y + h, x:x + w][mk] = 2
        if self.units[p["chart"]].kind in S.BAND_KINDS:     # a band: just the stretch around the figure
            a, b = max(0, x - 2 * w), min(m.shape[1], x + 3 * w)
            m = m[:, a:b]
        return p["chart"], m

    def cut(self, p):
        y, x, h, w = (int(p[k]) for k in ("row", "col", "height", "width"))
        return np.asarray(self.units[p["chart"]].cells)[y:y + h, x:x + w].astype(bool)


class MitreFrame:
    """A Sjónabók border band around the picture, mitred at the corners: each cell takes the
    band row of its distance to the nearest edge and the band column of its distance along
    that edge from the nearer corner, so the corners mirror on the diagonal and each side
    mirrors at its middle. The band is a mirror-symmetric repeat unit, turned so that its
    mirror line falls on the corner."""

    def __init__(self, band, cell=8, margin=28, ink=(183, 181, 226), paper=(245, 245, 245)):
        u = band
        for s in range(u.shape[1]):
            r = np.roll(u, s, 1)
            if (r[:, ::-1] == r).all():
                u = r
                break
        self.u, self.cell, self.margin, self.ink, self.paper = u, cell, margin, ink, paper
        self.width = margin + u.shape[0] * cell        # from the edge of the picture to inside the frame

    def background(self, label=None, logo=None):
        b, c, m = self.u.shape[0], self.cell, self.margin
        gh, gw = (H - 2 * m) // c, (W - 2 * m) // c       # frame size in cells
        yy, xx = np.mgrid[:gh, :gw]
        dist = np.minimum.reduce([yy, xx, gh - 1 - yy, gw - 1 - xx])
        on_tb = np.minimum(yy, gh - 1 - yy) <= np.minimum(xx, gw - 1 - xx)
        along = np.where(on_tb, np.minimum(xx, gw - 1 - xx), np.minimum(yy, gh - 1 - yy))
        inside = dist < b
        cells = np.zeros((gh, gw), bool)
        cells[inside] = self.u[dist[inside], along[inside] % self.u.shape[1]].astype(bool)
        rgb = np.full((H, W, 3), 255, np.uint8)
        rgb[:] = self.paper
        y0, x0 = (H - gh * c) // 2, (W - gw * c) // 2
        inner = np.where(cells[..., None], self.ink, (255, 255, 255)).astype(np.uint8)
        inner[~inside] = (255, 255, 255)
        inner[inside & ~cells] = self.paper
        rgb[y0:y0 + gh * c, x0:x0 + gw * c] = np.repeat(np.repeat(inner, c, 0), c, 1)
        img = Image.fromarray(rgb)
        if label:
            self.side_label(img, label, x0, b * c)   # left side: Instagram puts its buttons on the right
        if logo:
            self.bottom_logo(img, logo, y0 + gh * c - b * c, b * c)
        return img

    def bottom_logo(self, img, path, y, width):
        """A logo on a plain strip let into the bottom of the frame, like the side label."""
        lg = Image.open(path).convert("RGBA")
        h = int(width * 0.7)
        lg = lg.resize((round(lg.width * h / lg.height), h), Image.LANCZOS)
        strip = Image.new("RGB", (lg.width + 2 * width, width), self.paper)
        strip.paste(lg, (width, (width - h) // 2), lg)
        img.paste(strip, ((W - strip.width) // 2, y))

    def side_label(self, img, text, x, width):
        """The text on a plain strip let into the left side of the frame, reading upwards."""
        font = ImageFont.truetype(BOLD, int(width * 0.55))
        tw = int(font.getlength(text)) + 2 * width
        strip = Image.new("RGB", (tw, width), self.paper)
        d = ImageDraw.Draw(strip)
        d.text((tw // 2, width // 2), text, font=font, fill=tuple(int(v) for v in BLUE), anchor="mm")
        strip = strip.rotate(90, expand=True)
        img.paste(strip, (x, (H - strip.height) // 2))


class Reel:
    def __init__(self, books, title, subtitle, own_centre=OWN_CENTRE):
        self.books, self.title, self.subtitle = books, title, subtitle
        self.n = max(max(f.shape) for _, f, _ in books.figures) + 2
        self.cell = 640 // self.n
        self.grids = [self.centre(f) for _, f, _ in books.figures]
        for k in range(1, len(self.grids)):        # turn each to the least change from the last
            g = Aligner(self.grids[k - 1]).align(self.grids[k])
            self.grids[k] = g[SHIFT:SHIFT + self.n, SHIFT:SHIFT + self.n]
        if own_centre:
            # the arms are shared: the majority of all books; only the centre is each book's own
            shared = np.mean(self.grids, 0) >= 0.5
            cy = (self.n - 1) / 2
            yy, xx = np.mgrid[:self.n, :self.n]
            centre = np.maximum(abs(yy - cy), abs(xx - cy)) <= own_centre
            self.grids = [np.where(centre, g, shared) for g in self.grids]
        c = (self.n - 1) / 2
        yy, xx = np.mgrid[:self.n, :self.n]
        r = np.hypot(yy - c, xx - c)
        self.delay = r / r.max()                     # ripple from the centre outwards
        band = np.array([[int(c) for c in l.strip()] for l in open(S.HERE / "../../patterns/repeat" / f"{FRAME_BAND}.txt") if l.strip()])
        self.bg = MitreFrame(band).background(SITE, S.HERE / "assets" / "hi_logo_blue.png")
        self.f_title = ImageFont.truetype(BOLD, 58)
        self.f_sub = ImageFont.truetype(FONT, 36)
        self.f_book = ImageFont.truetype(BOLD, 72)
        self.f_when = ImageFont.truetype(FONT, 44)
        self.f_small = ImageFont.truetype(FONT, 28)
        self.footer(self.bg)

    def centre(self, f):
        g = np.zeros((self.n, self.n), bool)
        y, x = (self.n - f.shape[0]) // 2, (self.n - f.shape[1]) // 2
        g[y:y + f.shape[0], x:x + f.shape[1]] = f
        return g

    def label(self, k):
        src = self.books.figures[k][0]
        d = self.books.dates[src]
        when = d["when_label"] if d["when_start"] else "no date on record"
        return d["manuscript"], when

    def frame(self, colours, k, fade=1.0):
        """colours: n x n x 3 cell colours; k: index of the book named at the bottom."""
        img = self.bg.copy()
        dr = ImageDraw.Draw(img)
        dr.text((W // 2, 150), self.title, font=self.f_title, fill=tuple(BLUE.astype(int)), anchor="mm")
        dr.text((W // 2, 225), self.subtitle, font=self.f_sub, fill=INK, anchor="mm")
        size = self.cell * self.n
        x0, y0 = (W - size) // 2, 300
        cells = np.repeat(np.repeat(colours, self.cell, 0), self.cell, 1).astype(np.uint8)
        # thin grid lines, as on a chart
        cells[::self.cell, :] = np.minimum(cells[::self.cell, :], GRID.astype(np.uint8))
        cells[:, ::self.cell] = np.minimum(cells[:, ::self.cell], GRID.astype(np.uint8))
        img.paste(Image.fromarray(cells), (x0, y0))
        self.chart_panel(img, dr, k, fade)
        name, when = self.label(k)
        a = tuple(int(255 - (255 - c) * fade) for c in BLUE)
        b = tuple(int(255 - (255 - c) * fade) for c in INK)
        dr.text((W // 2, 1470), name, font=self.f_book, fill=a, anchor="mm")
        dr.text((W // 2, 1550), when, font=self.f_when, fill=b, anchor="mm")
        # the ten manuscripts as dots in time order, this one filled
        order = [int(self.books.dates[s]["order"]) for s, _, _ in self.books.figures]
        here = order[k]
        for i in range(1, 11):
            cx = W // 2 + (i - 5.5) * 70
            has = i in order
            fill = tuple(BLUE.astype(int)) if i == here else (tuple(GRID.astype(int)) if has else None)
            dr.ellipse((cx - 14, 1660 - 14, cx + 14, 1660 + 14), fill=fill,
                       outline=tuple(BLUE.astype(int)) if has else (200, 200, 200), width=3)
        dr.text((W // 2, 1715), "manuscripts in time order", font=self.f_small, fill=(120, 120, 120), anchor="mm")
        return img

    def footer(self, img):
        """The project name at the foot of every frame (the logo sits in the frame)."""
        ImageDraw.Draw(img).text((W // 2, 1790), "Íslensk sjónabók · HiDef Textiles", font=self.f_small,
                                 fill=(120, 120, 120), anchor="mm")

    def chart_panel(self, img, dr, k, fade):
        """The chart the figure comes from, figure in pink, fading with the name."""
        cid, m = self.books.charts[k]
        lut = np.array([PAPER, BLUE, PINK])
        rgb = PAPER + (lut[m] - PAPER) * fade
        z = max(1, min(520 // m.shape[1], 330 // m.shape[0], 12))
        I = Image.fromarray(rgb.astype(np.uint8)).resize((m.shape[1] * z, m.shape[0] * z), Image.NEAREST)
        cy = 1150
        img.paste(I, ((W - I.width) // 2, cy - I.height // 2))
        grey = tuple(int(255 - (255 - 120) * fade) for _ in range(3))
        dr.text((W // 2, cy + I.height // 2 + 30), f"in chart {cid}", font=self.f_small, fill=grey, anchor="mm")

    def colours(self, g):
        return np.where(g[..., None], BLUE, PAPER)

    def morph(self, a, b, t):
        """Cells changing from grid a to grid b at time t in [0, 1]."""
        out = self.colours(a)
        local = np.clip((t - 0.5 * self.delay) / 0.5, 0, 1)
        local = (local * local * (3 - 2 * local))[..., None]      # ease in and out
        on, off = b & ~a, a & ~b
        flash = np.where(local < 0.5, PAPER + (PINK - PAPER) * (local / 0.5), PINK + (BLUE - PINK) * ((local - 0.5) / 0.5))
        out = np.where(on[..., None], flash, out)
        gone = BLUE + (PAPER - BLUE) * local
        out = np.where(off[..., None], gone, out)
        return out

    def end_card(self):
        """All the books' figures side by side."""
        img = self.bg.copy()
        dr = ImageDraw.Draw(img)
        dr.text((W // 2, 150), self.title, font=self.f_title, fill=tuple(BLUE.astype(int)), anchor="mm")
        dr.text((W // 2, 225), self.subtitle, font=self.f_sub, fill=INK, anchor="mm")
        figs = self.books.figures
        cols = 3
        tile = 320
        for i, (src, f, _) in enumerate(figs):
            g = self.grids[i]
            z = (tile - 40) // self.n
            I = Image.fromarray(self.colours(g).astype(np.uint8)).resize((self.n * z, self.n * z), Image.NEAREST)
            cx = (W - cols * tile) // 2 + (i % cols) * tile
            cy = 330 + (i // cols) * (tile + 60)
            img.paste(I, (cx + (tile - I.width) // 2, cy))
            name, when = self.label(i)
            dr.text((cx + tile // 2, cy + I.height + 26), name, font=self.f_small, fill=INK, anchor="mm")
        return img

    def closing_card(self):
        """Where to see more: the site."""
        img = self.bg.copy()
        dr = ImageDraw.Draw(img)
        g = self.grids[-1]
        z = 360 // self.n
        I = Image.fromarray(self.colours(g).astype(np.uint8)).resize((self.n * z, self.n * z), Image.NEAREST)
        img.paste(I, ((W - I.width) // 2, 420))
        dr.text((W // 2, 1000), "See all 600 patterns", font=self.f_title, fill=tuple(BLUE.astype(int)), anchor="mm")
        dr.text((W // 2, 1090), "from ten Icelandic manuscripts", font=self.f_sub, fill=INK, anchor="mm")
        dr.rounded_rectangle((W // 2 - 400, 1200, W // 2 + 400, 1300), radius=50, fill=tuple(PINK.astype(int)))
        dr.text((W // 2, 1250), SITE, font=self.f_when, fill=(255, 255, 255), anchor="mm")
        return img

    def write(self, path):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-crf", "18", "-movflags", "+faststart", str(path)]
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        put = lambda im: ff.stdin.write(im.tobytes())
        g = self.grids
        for k in range(len(g)):
            hold = self.frame(self.colours(g[k]), k)
            for _ in range(int(HOLD * FPS)):
                put(hold)
            if k + 1 < len(g):
                steps = int(MORPH * FPS)
                for s in range(steps):
                    t = (s + 1) / steps
                    # the name fades out and the next one in, halfway through
                    name_k, fade = (k, 1 - 2 * t) if t < 0.5 else (k + 1, 2 * t - 1)
                    put(self.frame(self.morph(g[k], g[k + 1], t), name_k, max(fade, 0.0)))
        end = self.end_card()
        for _ in range(int(END * FPS)):
            put(end)
        close = self.closing_card()
        for _ in range(int(CLOSE * FPS)):
            put(close)
        ff.stdin.close()
        ff.wait()
        end.save(str(path).replace("_silent", "").replace(".mp4", "_end.png"))
        self.frame(self.colours(g[0]), 0).save(str(path).replace("_silent", "").replace(".mp4", "_cover.png"))


def add_music(video, out):
    """Lay the tvísöngur tune (music.py), cut to the video's length, under the video."""
    from music import Tvisongur
    secs = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", video]))
    tune = out.replace(".mp4", "_tune.wav")
    Tvisongur(secs).write(tune)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", tune, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--txt", default="../../patterns/txt")
    ap.add_argument("--kind", type=int, default=40)
    ap.add_argument("--title", default="The eight-pointed rosette")
    ap.add_argument("--out", default=str(OUT / "reel.mp4"))
    ap.add_argument("--own-centre", type=int, default=OWN_CENTRE,
                    help="half-width of the centre each book keeps; the arms are the books' majority (0: off)")
    a = ap.parse_args()
    books = BookFigures(a.txt, a.kind)
    sub = f"as {len(books.figures)} manuscripts draw it, 1600s–1800s"
    reel = Reel(books, a.title, sub, a.own_centre)
    silent = a.out.replace(".mp4", "_silent.mp4")
    reel.write(silent)
    add_music(silent, a.out)
    for src, f, n in books.figures:
        print(src, f.shape, int(f.sum()), "cells,", n, "charts")


if __name__ == "__main__":
    main()
