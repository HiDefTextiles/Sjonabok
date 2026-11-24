"""Group Sjónabók patterns by what they depict: the computer proposes, a person decides.

Steps (run through the Makefile in this folder, see README.md):

    units    which charts take part, and the picture of each one     -> work/units.csv
    shape    shape distance between every pair, ignoring flips,
             turns and shifts                                         -> work/shape_dist.csv
    meta     distance from the gallery's own measures: symmetry, form
             (density, width to height, pieces) and provenance
             (manuscript, page)                                       -> work/meta_dist.csv
    (embed.py: image-model distance, optional)                        -> work/embed_dist.csv
    (cluster.R: hierarchical clustering of the distances)             -> work/clusters.csv
    sheets   one contact sheet per cluster and a review form          -> work/sheets/, review.csv
    page     the phone-friendly review page with this run's piles     -> work/review/
    answers  answers saved by the review page on claude.ai (JSON)
             turned into the review form                              -> review.csv
    labels   turn the filled review form into one row per pattern     -> subjects.csv
    suggest  nearest labelled neighbours for charts not yet labelled  -> work/suggestions.csv
    settle   a review page of the charts whose pile label and fair-test
             label disagree, showing both earlier answers             -> work/settle/
    fair     answers of the fair test (charts labelled one at a time)
             as one row per chart                                     -> fairtest.csv
    evaluate how well each distance finds a fair-test chart's subject
             from its nearest labelled charts                         -> work/evaluation.csv

Only subjects.csv, review.csv and fairtest.csv are written by a person and kept in git.
Everything under work/ is rebuilt from the charts.
"""

import argparse
import csv
import json
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
FAIRTEST = HERE / "fairtest.csv"
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


class MetaDistance:
    """Distance from what the gallery already measures about each chart.

    Three equal blocks, each between 0 and 1 (a Gower distance):

    symmetry    how well the chart matches itself mirrored and turned
                (the gallery's agreement scores; left-right and top-bottom
                are taken as the larger and the smaller of the two, so a
                chart turned on its side scores the same), plus whether
                the symmetry group (D4, D1, C1, ...) differs
    form        share of filled cells, width to height, number of pieces
    provenance  a different manuscript counts 1; a different page in the
                same manuscript 0.5; the same page 0. Motifs drawn on one
                page often belong together.
    """

    BLOCKS = ("symmetry", "form", "provenance")

    def __init__(self, units, weights=(1, 1, 1)):
        self.ids = [u.id for u in units]
        self.weights = weights
        rows = []
        for u in units:
            p = u.pattern
            s = p.sym
            h, w = u.cells.shape
            rows.append({
                "mirror_hi": max(s.get("lr", 0), s.get("tb", 0)),
                "mirror_lo": min(s.get("lr", 0), s.get("tb", 0)),
                "rot180": s.get("rot180", 0), "rot90": s.get("rot90", 0), "diag": s.get("diag", 0),
                "group": p.point or p.frieze or "",
                "density": float(u.cells.mean()),
                "aspect": float(np.log(w / h)),
                "pieces": float(np.log1p(p.pieces)),
                "source": p.source, "page": f"{p.source}_{p.number}",
            })
        self.rows = rows

    @staticmethod
    def spread(x):
        x = np.asarray(x, dtype=float)
        r = x.max() - x.min()
        return np.abs(x[:, None] - x[None, :]) / (r if r > 0 else 1.0)

    @staticmethod
    def differs(x):
        x = np.asarray(x)
        return (x[:, None] != x[None, :]).astype(float)

    def blocks(self):
        col = lambda k: [r[k] for r in self.rows]
        sym = np.mean([self.spread(col(k)) for k in ("mirror_hi", "mirror_lo", "rot180", "rot90", "diag")]
                      + [self.differs(col("group"))], axis=0)
        form = np.mean([self.spread(col(k)) for k in ("density", "aspect", "pieces")], axis=0)
        prov = 0.5 * self.differs(col("source")) + 0.5 * self.differs(col("page"))
        return {"symmetry": sym, "form": form, "provenance": prov}

    def matrix(self):
        b = self.blocks()
        w = np.asarray(self.weights, dtype=float)
        d = sum(wi * b[k] for wi, k in zip(w, self.BLOCKS)) / w.sum()
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
        self.order = [r["subject"] for r in read_csv(vocabulary)]
        self.words = set(self.order) | {"mixed"}

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
        # one spelling for each combination: vocabulary order
        return "|".join(sorted(set(filter(None, subject.split("|"))), key=self.order.index))

    def apply(self, reviewer, path=REVIEW):
        existing = read_csv(SUBJECTS)
        done = {r["id"] for r in existing}
        today = dt.date.today().isoformat()
        new = []
        for row in read_csv(path):
            subject = row["subject"].strip()
            if subject == "mixed":
                subject = ""
            exceptions = dict(e.split("=", 1) for e in row["exceptions"].split() if "=" in e)
            for i in row["ids"].split():
                # a mixed or unnamed pile still keeps the charts picked out one by one
                s = self.check(exceptions.get(i, subject))
                if s and i not in done:
                    new.append({"id": i, "subjects": s, "reviewer": reviewer, "date": today,
                                "note": row["note"].strip()})
                    done.add(i)
        rows = sorted(existing + new, key=lambda r: r["id"])
        with open(SUBJECTS, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "subjects", "reviewer", "date", "note"])
            w.writeheader()
            w.writerows(rows)
        print(f"{len(new)} new labels, {len(rows)} in subjects.csv")


class ReviewPage:
    """The review page (review/index.html) with this run's piles beside it.

    Open work/review/index.html through a local web server (make review).
    Answers are kept in the browser and exported as review.csv. The same
    page published on claude.ai keeps answers in its database instead;
    those come back through `subjects.py answers`.
    """

    HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>:root{padding-block:env(safe-area-inset-top,0px) env(safe-area-inset-bottom,0px)}'
            'body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>')

    def __init__(self, txt_dir):
        self.txt_dir = Path(txt_dir)

    def write(self, clusters, out, extra=None):
        out.mkdir(parents=True, exist_ok=True)
        piles = []
        for c, ids in clusters.items():
            charts = []
            for i in ids:
                m = Pattern.trimmed(Pattern.read(self.txt_dir / f"{i}.txt"))
                charts.append({"id": i, "rows": ["".join(map(str, r)) for r in m]})
            piles.append({"pile": c, "charts": charts})
        vocab = [{"key": r["subject"], "label": r["label"]} for r in read_csv(VOCABULARY)]
        run = dt.datetime.fromtimestamp((WORK / "clusters.csv").stat().st_mtime).strftime("%Y-%m-%dT%H%M")
        (out / "piles.json").write_text(json.dumps({"run": run, "piles": piles, "vocabulary": vocab, **(extra or {})},
                                                   ensure_ascii=False, separators=(",", ":")))
        page = (HERE / "review" / "index.html").read_text(encoding="utf-8")
        (out / "index.html").write_text(self.HEAD + page + "</body></html>", encoding="utf-8")


def answers_to_form(folder, path=REVIEW):
    """Answers saved by the claude.ai review page (one JSON file per pile,
    as exported from its database) -> review.csv."""
    rows = []
    for f in sorted(Path(folder).glob("p*.json")):
        d = json.loads(f.read_text())
        d = d.get("data", d)
        ex = " ".join(f"{i}={'|'.join(s)}" for i, s in sorted(d.get("exceptions", {}).items()))
        subject = "mixed" if d.get("mixed") else "|".join(d.get("subjects", []))
        rows.append([d["pile"], len(d["ids"]), " ".join(d["ids"]), subject, ex, d.get("note", "").strip()])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cluster", "n", "ids", "subject", "exceptions", "note"])
        w.writerows(sorted(rows))
    print(f"{len(rows)} piles -> {path}")


def fair_answers(folder, reviewer, path=FAIRTEST):
    """Fair-test answers (one JSON file per chart) -> fairtest.csv."""
    review = Review()
    today = dt.date.today().isoformat()
    rows = []
    for f in sorted(Path(folder).glob("p*.json")):
        d = json.loads(f.read_text())
        d = d.get("data", d)
        subject = review.check("|".join(d.get("subjects", [])))
        if subject:
            rows.append({"id": d["ids"][0], "subjects": subject, "reviewer": reviewer, "date": today,
                         "note": d.get("note", "").strip()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "subjects", "reviewer", "date", "note"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["id"]))
    print(f"{len(rows)} fair-test labels -> {path}")


class Evaluation:
    """Which distance best finds a chart's subject from its k nearest labelled charts?

    The test charts are the fair test: drawn at random and labelled one at a
    time, so their labels do not come from any clustering. A guess is the
    subject most common among the k nearest charts (ties go to the nearer
    chart); it is right if it is one of the chart's own subjects. Two pools of
    neighbours:

    piles   every chart labelled in the pile review, except the test chart
    fair    only the other fair-test charts (cleanest, but a small pool)

    Charts labelled only "unknown" are left out. Distances are rank-scaled
    to 0..1 before they are mixed, as in cluster.R.
    """

    def __init__(self, k=5):
        self.k = k
        self.pile = {r["id"]: set(r["subjects"].split("|")) for r in read_csv(SUBJECTS)}
        self.fair = {r["id"]: set(r["subjects"].split("|")) - {"unknown"} for r in read_csv(FAIRTEST)}
        self.fair = {i: s for i, s in self.fair.items() if s}

    @staticmethod
    def rank_scale(d):
        r = d.ravel().argsort().argsort().reshape(d.shape).astype(float)
        return r / r.max()

    def guess(self, d, idx, i, pool, labels):
        near = sorted((j for j in pool if j != i), key=lambda j: d[idx[i], idx[j]])[: self.k]
        votes = {}
        for rank, j in enumerate(near):
            for s in labels[j]:
                votes[s] = votes.get(s, 0) + 1 - rank * 1e-3
        return max(votes, key=votes.get)

    def score(self, d, ids):
        idx = {i: n for n, i in enumerate(ids)}
        test = [i for i in self.fair if i in idx]
        out = {}
        for name, labels in (("piles", self.pile), ("fair", self.fair)):
            pool = [j for j in labels if j in idx]
            hits = [self.guess(d, idx, i, pool, labels) in self.fair[i] for i in test]
            out[name] = (sum(hits), len(hits))
        return out

    def baseline(self):
        counts = {}
        for s in self.pile.values():
            for x in s:
                counts[x] = counts.get(x, 0) + 1
        top = max(counts, key=counts.get)
        hits = sum(top in s for s in self.fair.values())
        return top, (hits, len(self.fair))

    def agreement(self):
        both = [i for i in self.fair if i in self.pile]
        shared = sum(bool(self.fair[i] & self.pile[i]) for i in both)
        same = sum(self.fair[i] == self.pile[i] for i in both)
        return shared, same, len(both)

    def write(self, distances, path):
        ids = next(iter(distances.values()))[0]
        scaled = {n: self.rank_scale(d) for n, (i, d) in distances.items()}
        mixes = {"image 2 : gallery measures 1": {"image": 2, "meta": 1},
                 "image 1 : gallery measures 1": {"image": 1, "meta": 1},
                 "image 2 : symmetry 1": {"image": 2, "symmetry": 1},
                 "image 2 : provenance 1": {"image": 2, "provenance": 1}}
        for name, w in mixes.items():
            if all(k in scaled for k in w):
                scaled[name] = sum(v * scaled[k] for k, v in w.items()) / sum(w.values())
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["distance", "pool", "right", "charts", "share"])
            for name, d in scaled.items():
                for pool, (h, n) in self.score(d, ids).items():
                    w.writerow([name, pool, h, n, f"{h / n:.3f}"])
                    print(f"{name:32s} {pool:6s} {h:3d}/{n} {h / n:.0%}")
            top, (h, n) = self.baseline()
            w.writerow([f"always {top}", "-", h, n, f"{h / n:.3f}"])
            print(f"{'always ' + top:32s} {'-':6s} {h:3d}/{n} {h / n:.0%}")
        shared, same, n = self.agreement()
        print(f"pile label vs fair label for the same chart: share a subject {shared}/{n}, identical {same}/{n}")


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
    ap.add_argument("step", choices=["units", "shape", "meta", "sheets", "page", "sample", "answers", "labels", "suggest", "fair", "evaluate", "settle"])
    ap.add_argument("--txt", default=str(ROOT / "patterns" / "txt"), help="folder of 0/1 charts")
    ap.add_argument("--kinds", default=",".join(PILOT_KINDS), help="pattern types to include")
    ap.add_argument("--n", type=int, default=40, help="sample: number of charts")
    ap.add_argument("--seed", type=int, default=2026, help="sample: random seed")
    ap.add_argument("--meta-weights", default="1,1,1", help="meta: symmetry,form,provenance")
    ap.add_argument("--reviewer", default="", help="name written into subjects.csv")
    ap.add_argument("--from", dest="src", default="", help="answers: folder of pile JSON files")
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
    elif a.step == "meta":
        keep = set(Corpus.read_ids(WORK / "units.csv"))
        units = [u for u in Corpus(a.txt, PILOT_KINDS + BAND_KINDS).units if u.id in keep]
        md = MetaDistance(units, tuple(float(x) for x in a.meta_weights.split(",")))
        write_matrix(WORK / "meta_dist.csv", md.ids, md.matrix())
    elif a.step == "sheets":
        clusters = read_clusters(WORK / "clusters.csv")
        out = WORK / "sheets"
        out.mkdir(exist_ok=True)
        sheet = ContactSheet(a.txt)
        for c, ids in clusters.items():
            sheet.draw(c, ids, out / f"cluster_{c:02d}.png")
        Review().write_form(clusters)
        print(f"{len(clusters)} sheets -> {out}")
    elif a.step == "page":
        ReviewPage(a.txt).write(read_clusters(WORK / "clusters.csv"), WORK / "review")
        print(f"review page -> {WORK / 'review'}")
    elif a.step == "sample":
        # The fair test: N charts drawn at random (fixed seed), labelled one at a
        # time, so the labels do not depend on any clustering.
        ids = sorted(Corpus.read_ids(WORK / "units.csv"))
        pick = sorted(np.random.default_rng(a.seed).choice(ids, size=min(a.n, len(ids)), replace=False))
        ReviewPage(a.txt).write({k + 1: [str(i)] for k, i in enumerate(pick)}, WORK / "sample", {
            "run": f"sample-{a.seed}-{a.n}", "single": True, "title": "Sjónabók fair test",
            "intro": f"{len(pick)} charts drawn at random. Give each its subject (or several). "
                     "These labels are used to check which features group charts by subject best. "
                     "Answers save as you go."})
        print(f"{len(pick)} charts -> {WORK / 'sample'}")
    elif a.step == "answers":
        answers_to_form(a.src)
    elif a.step == "labels":
        if not a.reviewer:
            raise SystemExit("Give --reviewer (or REVIEWER=... to make).")
        Review().apply(a.reviewer)
    elif a.step == "suggest":
        dist = WORK / "dist.csv"
        Suggestions(dist).write(WORK / "suggestions.csv")
    elif a.step == "fair":
        if not a.reviewer:
            raise SystemExit("Give --reviewer (or REVIEWER=... to make).")
        fair_answers(a.src, a.reviewer)
    elif a.step == "settle":
        label = {r["subject"]: r["label"] for r in read_csv(VOCABULARY)}
        name = lambda x: " + ".join(label.get(s, s) for s in x.split("|")) if x else "nothing"
        pile = {r["id"]: r["subjects"] for r in read_csv(SUBJECTS)}
        fair = {r["id"]: r["subjects"] for r in read_csv(FAIRTEST)}
        todo = [i for i in sorted(fair) if set(pile.get(i, "").split("|")) != set(fair[i].split("|"))]
        page = ReviewPage(a.txt)
        page.write({k + 1: [i] for k, i in enumerate(todo)}, WORK / "settle", {
            "run": "settle", "single": True, "title": "Sjónabók: settle the differences",
            "intro": f"These {len(todo)} charts got one answer in the piles and another when shown on their own. "
                     "Give each the subject you now think is right; your answer replaces both."})
        # show both earlier answers on each card
        j = json.loads((WORK / "settle" / "piles.json").read_text())
        for p in j["piles"]:
            i = p["charts"][0]["id"]
            p["hint"] = f"{i}. In a pile: {name(pile.get(i, ''))}. On its own: {name(fair[i])}."
        (WORK / "settle" / "piles.json").write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")))
        print(f"{len(todo)} charts -> {WORK / 'settle'}")
    elif a.step == "evaluate":
        distances = {}
        for name, f in (("image", "embed_dist.csv"), ("shape", "shape_dist.csv"), ("meta", "meta_dist.csv")):
            if (WORK / f).exists():
                distances[name] = read_matrix(WORK / f)
        ids = next(iter(distances.values()))[0]
        keep = set(ids)
        units = [u for u in Corpus(a.txt, PILOT_KINDS + BAND_KINDS).units if u.id in keep]
        md = MetaDistance(units)
        order = [md.ids.index(i) for i in ids]
        for name, d in md.blocks().items():
            distances[name] = (ids, d[np.ix_(order, order)])
        for name, (i, d) in distances.items():
            assert i == ids, f"{name}: charts in a different order"
        Evaluation().write(distances, WORK / "evaluation.csv")


if __name__ == "__main__":
    main()
