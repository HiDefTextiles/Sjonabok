"""Group Sjónabók patterns by what they depict: the computer proposes, a person decides.

Steps (run through the Makefile in this folder, see README.md):

    units    which charts take part, and the picture of each one     -> work/units.csv
    shape    shape distance between every pair, ignoring flips,
             turns and shifts                                         -> work/shape_dist.csv
    (embed.py: image-model distance, optional)                        -> work/embed_dist.csv
    (cluster.R: hierarchical clustering of the distances)             -> work/clusters.csv
    sheets   one contact sheet per cluster and a review form          -> work/sheets/, review.csv
    labels   turn the filled review form into one row per pattern     -> subjects.csv
    suggest  nearest labelled neighbours for charts not yet labelled  -> work/suggestions.csv

Only subjects.csv and review.csv are written by a person and kept in git.
Everything under work/ is rebuilt from the charts.
"""

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "gallery" / "scripts"))
from build_gallery import Pattern  # noqa: E402  (same measures as the gallery)
from pattern_processing.repeat_unit import RepeatUnit  # noqa: E402

WORK = HERE / "work"
SUBJECTS = HERE / "subjects.csv"
REVIEW = HERE / "review.csv"
VOCABULARY = HERE / "vocabulary.csv"

# The pilot covers stand-alone figures; bands join once their repeat units
# are reviewed (patterns/repeat, see gallery About page).
PILOT_KINDS = ("motif", "rosette")
BAND_KINDS = ("border", "edging", "vertical band")


class Unit:
    """One picture to compare: a whole motif, or one repeat of a band."""

    def __init__(self, pattern):
        self.pattern = pattern
        self.id = pattern.id
        self.kind = pattern.kind
        self.cells = self.picture(pattern)

    @staticmethod
    def picture(p):
        if p.kind in BAND_KINDS:
            axis = "y" if p.kind == "vertical band" else "x"
            r = RepeatUnit.from_band(p.trim, axis)
            if r is not None:
                return r.unit if axis == "x" else r.unit.T
        return p.trim

    def variants(self, n=16):
        """The unit as small pictures in all 8 flipped and turned positions."""
        small = Pattern.small(self.cells, n)
        return [np.rot90(b, k) for b in (small, small[:, ::-1]) for k in range(4)]


class Corpus:
    """The charts that take part in this run."""

    def __init__(self, txt_dir, kinds=PILOT_KINDS):
        patterns = [Pattern(p).measure() for p in sorted(Path(txt_dir).glob("*.txt"))]
        self.units = [Unit(p) for p in patterns if p.kind in kinds]

    def write(self, path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "kind", "width", "height", "density"])
            for u in self.units:
                h, wd = u.cells.shape
                w.writerow([u.id, u.kind, wd, h, round(float(u.cells.mean()), 3)])

    @staticmethod
    def read_ids(path):
        with open(path) as f:
            return [r["id"] for r in csv.DictReader(f)]


class ShapeDistance:
    """1 minus the best correlation of two units over the 8 positions of one.

    Each unit is scaled to 16 x 16 cells, so the distance compares the
    arrangement of filled cells, not the size. This is the same comparison
    the gallery uses for "similar patterns".
    """

    def __init__(self, units, n=16):
        v = np.array([[x.ravel() for x in u.variants(n)] for u in units], dtype=float)
        v -= v.mean(axis=2, keepdims=True)
        norm = np.linalg.norm(v, axis=2, keepdims=True)
        self.v = np.divide(v, norm, out=np.zeros_like(v), where=norm > 0)
        self.ids = [u.id for u in units]

    def matrix(self):
        corr = np.max(np.einsum("id,jvd->ijv", self.v[:, 0, :], self.v), axis=2)
        corr = np.maximum(corr, corr.T)
        d = np.clip(1.0 - corr, 0.0, 2.0)
        np.fill_diagonal(d, 0.0)
        return d


def write_matrix(path, ids, d):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id"] + ids)
        for i, row in zip(ids, d):
            w.writerow([i] + [f"{x:.5f}" for x in row])


def read_matrix(path):
    with open(path) as f:
        r = csv.reader(f)
        ids = next(r)[1:]
        d = np.array([[float(x) for x in row[1:]] for row in r])
    return ids, d


def read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class ContactSheet:
    """All units of one cluster on one image, each with its file name."""

    CELL = 120

    def __init__(self, txt_dir):
        self.txt_dir = Path(txt_dir)

    def draw(self, cluster, ids, out, cols=6):
        rows = -(-len(ids) // cols)
        c = self.CELL
        sheet = Image.new("RGB", (cols * c, rows * (c + 16) + 28), "white")
        draw = ImageDraw.Draw(sheet)
        draw.text((6, 6), f"Cluster {cluster}: {len(ids)} charts", fill=(16, 9, 159))
        for k, i in enumerate(ids):
            m = Pattern.trimmed(Pattern.read(self.txt_dir / f"{i}.txt"))
            img = Image.fromarray(np.where(m == 1, 0, 255).astype(np.uint8))
            zoom = max(1, (c - 12) // max(m.shape))
            img = img.resize((m.shape[1] * zoom, m.shape[0] * zoom), Image.NEAREST)
            img.thumbnail((c - 12, c - 12), Image.NEAREST)
            x = (k % cols) * c + (c - img.width) // 2
            y = 28 + (k // cols) * (c + 16) + (c - img.height) // 2
            sheet.paste(img, (x, y))
            draw.text(((k % cols) * c + 4, 28 + (k // cols) * (c + 16) + c), i, fill=(80, 80, 80))
        sheet.save(out, optimize=True)


class Review:
    """The review form (one row per cluster) and the labels it produces.

    review.csv columns:
        cluster     cluster number from this run
        n           charts in the cluster
        ids         the charts, separated by spaces
        subject     the subject for the whole cluster (see vocabulary.csv);
                    several subjects separated by "|"; "mixed" = cut finer
        exceptions  charts that do not fit: id=subject, separated by spaces
        note        free text

    subjects.csv columns: id, subjects ("|" separated), reviewer, date, note.
    A pattern already in subjects.csv is never changed by a later run.
    """

    def __init__(self, vocabulary=VOCABULARY):
        self.words = {r["subject"] for r in read_csv(vocabulary)} | {"mixed"}

    def write_form(self, clusters, path=REVIEW):
        labelled = {r["id"] for r in read_csv(SUBJECTS)}
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["cluster", "n", "ids", "subject", "exceptions", "note"])
            for c, ids in clusters.items():
                todo = [i for i in ids if i not in labelled]
                if todo:
                    w.writerow([c, len(todo), " ".join(todo), "", "", ""])

    def check(self, subject):
        bad = [s for s in subject.split("|") if s and s not in self.words]
        if bad:
            raise SystemExit(f"Unknown subject {bad}; add it to vocabulary.csv first.")
        return subject

    def apply(self, reviewer, path=REVIEW):
        existing = read_csv(SUBJECTS)
        done = {r["id"] for r in existing}
        today = dt.date.today().isoformat()
        new = []
        for row in read_csv(path):
            subject = row["subject"].strip()
            if not subject or subject == "mixed":
                continue
            exceptions = dict(e.split("=", 1) for e in row["exceptions"].split() if "=" in e)
            for i in row["ids"].split():
                s = self.check(exceptions.get(i, subject))
                if i not in done:
                    new.append({"id": i, "subjects": s, "reviewer": reviewer, "date": today,
                                "note": row["note"].strip()})
                    done.add(i)
        rows = sorted(existing + new, key=lambda r: r["id"])
        with open(SUBJECTS, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "subjects", "reviewer", "date", "note"])
            w.writeheader()
            w.writerows(rows)
        print(f"{len(new)} new labels, {len(rows)} in subjects.csv")


class Suggestions:
    """Majority subject of the k nearest labelled charts. Never shown as fact."""

    def __init__(self, dist_path, k=5):
        self.ids, self.d = read_matrix(dist_path)
        self.k = k

    def write(self, path):
        labels = {r["id"]: r["subjects"] for r in read_csv(SUBJECTS)}
        idx = {i: n for n, i in enumerate(self.ids)}
        known = [i for i in self.ids if i in labels]
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "suggested", "agreement", "neighbours"])
            for i in self.ids:
                if i in labels or not known:
                    continue
                near = sorted(known, key=lambda j: self.d[idx[i], idx[j]])[: self.k]
                votes = {}
                for j in near:
                    for s in labels[j].split("|"):
                        votes[s] = votes.get(s, 0) + 1
                best = max(sorted(votes), key=votes.get)
                w.writerow([i, best, f"{votes[best]}/{len(near)}", " ".join(near)])


def read_clusters(path):
    clusters = {}
    for r in read_csv(path):
        clusters.setdefault(int(r["cluster"]), []).append(r["id"])
    return dict(sorted(clusters.items()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=["units", "shape", "sheets", "labels", "suggest"])
    ap.add_argument("--txt", default=str(ROOT / "patterns" / "txt"), help="folder of 0/1 charts")
    ap.add_argument("--kinds", default=",".join(PILOT_KINDS), help="pattern types to include")
    ap.add_argument("--reviewer", default="", help="name written into subjects.csv")
    a = ap.parse_args()
    WORK.mkdir(exist_ok=True)

    if a.step == "units":
        corpus = Corpus(a.txt, tuple(a.kinds.split(",")))
        corpus.write(WORK / "units.csv")
        print(f"{len(corpus.units)} units")
    elif a.step == "shape":
        keep = set(Corpus.read_ids(WORK / "units.csv"))
        corpus = Corpus(a.txt, PILOT_KINDS + BAND_KINDS)
        units = [u for u in corpus.units if u.id in keep]
        sd = ShapeDistance(units)
        write_matrix(WORK / "shape_dist.csv", sd.ids, sd.matrix())
    elif a.step == "sheets":
        clusters = read_clusters(WORK / "clusters.csv")
        out = WORK / "sheets"
        out.mkdir(exist_ok=True)
        sheet = ContactSheet(a.txt)
        for c, ids in clusters.items():
            sheet.draw(c, ids, out / f"cluster_{c:02d}.png")
        Review().write_form(clusters)
        print(f"{len(clusters)} sheets -> {out}")
    elif a.step == "labels":
        if not a.reviewer:
            raise SystemExit("Give --reviewer (or REVIEWER=... to make).")
        Review().apply(a.reviewer)
    elif a.step == "suggest":
        dist = WORK / "dist.csv"
        Suggestions(dist).write(WORK / "suggestions.csv")


if __name__ == "__main__":
    main()
