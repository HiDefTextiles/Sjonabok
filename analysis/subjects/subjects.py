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
    settled  answers of the settle page replace the chart's label in
             subjects.csv and fairtest.csv (git keeps the old ones)   -> subjects.csv, fairtest.csv
    knots    rank every chart by how knot-like it is (thin lines, many
             small enclosed openings, diagonal strokes) and a yes/no
             review page of the most likely ones                      -> work/knots.csv, work/knots/
    knot-answers  Knot / No knot answers (JSON) -> feature_labels.csv, and a
             new page of the unseen charts nearest to the confirmed knots
             (image model over every chart, embed.py --all)           -> work/knots2/
    features distances for every chart, bands by repeat unit: shape,
             symmetry, form, provenance, texture, and texture of the
             repeated chart (+ embed.py --all and --all --tile)       -> work/all/*_dist.csv
    learn    weights for those distances, learnt from the labels
             (main groups and knots); the fair test is held out       -> weights.csv
    groups   final groups for every chart: each cluster of the label-free
             clustering (work/all/clusters.csv, cluster.R with weights.csv)
             takes the main group most of its labelled charts have    -> work/all/groups.csv
    misses   labelled charts whose nearest charts (learnt weights) point
             to another main group, on a page asking what tells them
             apart: the clues become the next features               -> work/misses/
    fair     answers of the fair test (charts labelled one at a time)
             as one row per chart                                     -> fairtest.csv
    evaluate how well each distance finds a fair-test chart's subject
             from its nearest labelled charts                         -> work/evaluation.csv

Only subjects.csv, review.csv, fairtest.csv and feature_labels.csv are written by a person;
weights.csv is learnt from them and kept so the final clustering needs no labels and kept in git.
Everything under work/ is rebuilt from the charts.
"""

import argparse
import csv
import json
import os
import subprocess
import datetime as dt
import sys
from pathlib import Path

import numpy as np
from scipy.stats import rankdata
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
FEATURES = HERE / "features.csv"
FEATURE_LABELS = HERE / "feature_labels.csv"
WEIGHTS = HERE / "weights.csv"
ALL = WORK / "all"

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

    def tiled(self):
        """The unit repeated: 2 x 2 for a motif, 3 repeats along a band. A knot or a
        star can run across the edge of one repeat and only show when repeated."""
        c = self.cells
        return np.tile(c, (1, 3)) if self.kind in BAND_KINDS else np.tile(c, (2, 2))

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

    BLOCKS = ("symmetry", "form", "provenance")   # texture is used by `learn`, not by `meta`

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
                **KnotScore.measures(u.cells),
                **self.upright(u.cells, s),
            })
        self.rows = rows

    @staticmethod
    def upright(cells, s):
        """Which way is up. Charts are drawn upright: a plant stands on a stem or vase, an
        animal has legs below and a back above, an ornament looks the same every way.
            lr, tb        left-right and top-bottom mirror agreement, kept apart (not as
                          larger and smaller), because a plant mirrors left-right only
            top_heavy     filled share of the top half minus the bottom half
            base          width of the filled part in the bottom fifth, relative to the
                          widest row: small for a stem or legs, 1 for a block or a star"""
        m = np.asarray(cells).astype(bool)
        h, w = m.shape
        half = h // 2
        top, bottom = m[:half].sum(), m[h - half:].sum()
        widths = [np.ptp(np.nonzero(r)[0]) + 1 if r.any() else 0 for r in m]
        base_rows = widths[h - max(1, h // 5):]
        return {"lr": s.get("lr", 0), "tb": s.get("tb", 0),
                "top_heavy": float((top - bottom) / max(1, m.sum())),
                "base": float(max(base_rows) / max(1, max(widths)))}

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
        # texture: the knot measures (enclosed openings, diagonal strokes); rank-spread,
        # because a few lacy charts have very many openings
        rk = lambda k: rankdata(col(k), method="average")
        texture = np.mean([self.spread(rk(k)) for k in ("openings", "diagonal")], axis=0)
        upright = np.mean([self.spread(col(k)) for k in ("lr", "tb", "top_heavy", "base")], axis=0)
        return {"symmetry": sym, "form": form, "provenance": prov, "texture": texture, "upright": upright}

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
        vocab = (extra or {}).pop("vocabulary", vocab)
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
    # merge into what is there; a settled answer (see `settled`) is never undone
    rows = {r["id"]: r for r in read_csv(path)}
    n = 0
    for f in sorted(Path(folder).glob("p*.json")):
        d = json.loads(f.read_text())
        d = d.get("data", d)
        subject = review.check("|".join(d.get("subjects", [])))
        i = d["ids"][0]
        if subject and not rows.get(i, {}).get("note", "").startswith("settled:"):
            rows[i] = {"id": i, "subjects": subject, "reviewer": reviewer, "date": today,
                       "note": d.get("note", "").strip()}
            n += 1
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "subjects", "reviewer", "date", "note"])
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["id"]))
    print(f"{n} fair-test labels written, {len(rows)} in {path}")


def settle_answers(folder, reviewer):
    """Answers from the settle page replace both earlier labels of each chart."""
    review = Review()
    today = dt.date.today().isoformat()
    new = {}
    for f in sorted(Path(folder).glob("p*.json")):
        d = json.loads(f.read_text())
        d = d.get("data", d)
        subject = review.check("|".join(d.get("subjects", [])))
        if subject:
            note = ("settled: pile and single answers differed. " + d.get("note", "")).strip()
            new[d["ids"][0]] = {"id": d["ids"][0], "subjects": subject, "reviewer": reviewer, "date": today,
                                "note": note}
    for path in (SUBJECTS, FAIRTEST):
        rows = {r["id"]: r for r in read_csv(path)}
        rows.update({i: r for i, r in new.items() if i in rows or path == SUBJECTS})
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "subjects", "reviewer", "date", "note"])
            w.writeheader()
            w.writerows(sorted(rows.values(), key=lambda r: r["id"]))
    print(f"{len(new)} charts settled")


def feature_answers(folder, feature, reviewer, path=FEATURE_LABELS):
    """Yes/no answers for one feature -> feature_labels.csv (id, feature, value, reviewer, date).
    A later answer for the same chart and feature replaces the earlier one."""
    today = dt.date.today().isoformat()
    rows = {(r["id"], r["feature"]): r for r in read_csv(path)}
    n = 0
    for f in sorted(Path(folder).glob("p*.json")):
        d = json.loads(f.read_text())
        d = d.get("data", d)
        picked = d.get("subjects", [])
        if not picked:
            continue
        i = d["ids"][0]
        if feature in picked and len(picked) > 1:
            print(f"  {i}: both Knot and No knot ticked, skipped")
            continue
        rows[(i, feature)] = {"id": i, "feature": feature, "value": "yes" if feature in picked else "no",
                              "reviewer": reviewer, "date": today, "note": d.get("note", "").strip()}
        n += 1
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "feature", "value", "reviewer", "date", "note"])
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["feature"], r["id"])))
    print(f"{n} answers for {feature} -> {path}")


def nearest_to(seeds, ids, d, exclude, n):
    """Unseen charts nearest to the seeds, taking the nearest to each seed in turn,
    so that one seed (say a band) does not fill the list with look-alikes."""
    idx = {i: k for k, i in enumerate(ids)}
    rest = [i for i in ids if i not in exclude]
    lists = [sorted(rest, key=lambda i: d[idx[i], idx[s]]) for s in seeds if s in idx]
    out = []
    while lists and len(out) < min(n, len(rest)):
        for L in lists:
            x = next((i for i in L if i not in out), None)
            if x and len(out) < n:
                out.append(x)
    return out


def adjusted_rand(a, b):
    """Adjusted Rand index of two labellings (Hubert and Arabie 1985)."""
    from math import comb
    ua, ub = sorted(set(a)), sorted(set(b))
    t = np.zeros((len(ua), len(ub)), dtype=int)
    for x, y in zip(a, b):
        t[ua.index(x), ub.index(y)] += 1
    n = len(a)
    s_ij = sum(comb(int(v), 2) for v in t.ravel())
    s_a = sum(comb(int(v), 2) for v in t.sum(1))
    s_b = sum(comb(int(v), 2) for v in t.sum(0))
    expect = s_a * s_b / comb(n, 2)
    top = (s_a + s_b) / 2
    return (s_ij - expect) / (top - expect) if top != expect else 0.0


class WeightLearner:
    """Learn how much each distance counts, from the people's labels.

    Each distance is rank-scaled to 0..1 (as in cluster.R). Every weighting on
    a grid (steps of `step`, weights summing to 1) is scored by leave-one-out
    k-nearest-neighbour agreement on the labelled charts:

        group   share of charts whose k nearest labelled charts most often
                share its main group (vocabulary.csv), and
        knot    the same for Knot / No knot (feature_labels.csv), when there
                are enough answers

    and the score is their mean. The fair-test charts are left out of the
    learning, so `holdout()` gives an honest score for the chosen weights.
    The result only sets weights; the clustering that uses them sees no labels.
    """

    def __init__(self, distances, k=5, step=0.1, min_knots=10, tie=0.006):
        self.names = list(distances)
        self.ids = distances[self.names[0]][0]
        for n in self.names:
            assert distances[n][0] == self.ids, n
        self.D = np.stack([Evaluation.rank_scale(distances[n][1]) for n in self.names])
        self.k, self.step, self.tie = k, step, tie
        idx = {i: n for n, i in enumerate(self.ids)}
        to = {r["subject"]: r["group"] for r in read_csv(VOCABULARY)}
        groups = {r["id"]: {to.get(x, "") for x in r["subjects"].split("|")} - {""} for r in read_csv(SUBJECTS)}
        fair = {r["id"]: {to.get(x, "") for x in r["subjects"].split("|")} - {""} for r in read_csv(FAIRTEST)}
        self.fair_ids = {i for i in fair if i in idx}
        self.group = {idx[i]: g for i, g in groups.items() if g and i in idx and i not in self.fair_ids}
        self.fair = {idx[i]: g for i, g in fair.items() if g and i in idx}
        knots = {r["id"]: r["value"] == "yes" for r in read_csv(FEATURE_LABELS) if r["feature"] == "knot"}
        self.knot = {idx[i]: {v} for i, v in knots.items() if i in idx and i not in self.fair_ids}
        if len(self.knot) < min_knots:
            self.knot = {}

    def grid(self):
        n, m = len(self.names), round(1 / self.step)
        def parts(left, slots):
            if slots == 1:
                yield (left,)
                return
            for a in range(left + 1):
                for rest in parts(left - a, slots - 1):
                    yield (a,) + rest
        for p in parts(m, n):
            yield np.array(p, dtype=float) / m

    def knn(self, d, test, pool, labels, truth):
        pool = np.array(sorted(pool))
        right = 0
        for i in test:
            cand = pool[pool != i]
            near = cand[np.argsort(d[i, cand], kind="stable")[: self.k]]
            votes = {}
            for rank, j in enumerate(near):
                for s in labels[j]:
                    votes[s] = votes.get(s, 0) + 1 - rank * 1e-3
            right += bool(votes) and max(votes, key=votes.get) in truth[i]
        return right / max(1, len(test))

    def score(self, w):
        d = np.tensordot(w, self.D, axes=1)
        g = self.knn(d, list(self.group), self.group, self.group, self.group)
        if not self.knot:
            return g, None
        kn = self.knn(d, list(self.knot), self.knot, self.knot, self.knot)
        return g, kn

    def split_score(self, w, k=3):
        """ARI of a label-free Ward cut of the labelled motifs (fair test left out) into k
        groups against their main groups: does the top of the tree follow the groups?"""
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import squareform
        idx = [i for i in sorted(self.group) if len(self.group[i]) == 1]
        d = np.tensordot(w, self.D[:, idx][:, :, idx], axes=1)
        cut = fcluster(linkage(squareform(d, checks=False), "ward"), k, "maxclust")
        return adjusted_rand(list(cut), [next(iter(self.group[i])) for i in idx])

    def fit(self):
        """Score = mean of: nearest-neighbour agreement on main groups, on knots (when
        there are enough answers), and how well a cut of the tree into 3 follows the
        main groups (the goal: groups found without labels)."""
        rows = []
        for w in self.grid():
            g, kn = self.score(w)
            parts = [g, self.split_score(w)] + ([] if kn is None else [kn])
            rows.append((float(np.mean(parts)), g, kn, w))
        rows.sort(key=lambda r: -r[0])
        self.results = rows
        # Many weightings tie at the top (one chart more or less right); a single winner
        # would be picked by chance. Take the mean of all weightings within `tie` of the
        # best score, rounded to the grid, so the choice is stable.
        top = [r[3] for r in rows if r[0] >= rows[0][0] - self.tie]
        w = np.mean(top, axis=0)
        self.best = np.round(w / self.step) * self.step
        self.best = self.best / self.best.sum()
        self.n_top = len(top)
        return self.best

    def holdout(self, w):
        """Fair-test charts guessed from their k nearest labelled (non-fair) charts."""
        d = np.tensordot(w, self.D, axes=1)
        return self.knn(d, list(self.fair), self.group, self.group, self.fair), len(self.fair)

    def holdout_detail(self, w, boot=2000, seed=2026):
        """Fair test: share right with a bootstrap 95% interval, and balanced accuracy
        (the mean of the share right within each main group, so the large ornament
        group cannot hide misses among animals)."""
        d = np.tensordot(w, self.D, axes=1)
        pool = np.array(sorted(self.group))
        hits, truth = [], []
        for i in sorted(self.fair):
            cand = pool[pool != i]
            near = cand[np.argsort(d[i, cand], kind="stable")[: self.k]]
            votes = {}
            for rank, j in enumerate(near):
                for g in self.group[j]:
                    votes[g] = votes.get(g, 0) + 1 - rank * 1e-3
            hits.append(bool(votes) and max(votes, key=votes.get) in self.fair[i])
            truth.append(sorted(self.fair[i])[0])
        hits = np.array(hits, dtype=float)
        rng = np.random.default_rng(seed)
        b = hits[rng.integers(0, len(hits), (boot, len(hits)))].mean(axis=1)
        per = {g: hits[[t == g for t in truth]].mean() for g in sorted(set(truth))}
        return hits.mean(), np.percentile(b, [2.5, 97.5]), np.mean(list(per.values())), per

    def top_split(self, w, kinds, k=3):
        """Adjusted Rand index between a label-free Ward cut of the motifs into k groups
        and the people's main groups (charts with one group only). 0 is chance, 1 perfect."""
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import squareform
        d = np.tensordot(w, self.D, axes=1)
        motifs = [n for n, i in enumerate(self.ids) if kinds.get(i) == "0"]
        sub = d[np.ix_(motifs, motifs)]
        cut = fcluster(linkage(squareform(sub, checks=False), "ward"), k, "maxclust")
        lab = {**self.group, **self.fair}
        pairs = [(c, next(iter(lab[m]))) for c, m in zip(cut, motifs) if m in lab and len(lab[m]) == 1]
        return adjusted_rand([p[0] for p in pairs], [p[1] for p in pairs])

    def write(self, path=WEIGHTS):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["distance", "weight"])
            for n, x in zip(self.names, self.best):
                w.writerow([n, f"{x:.2f}"])


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

    def __init__(self, k=5, level="subject"):
        self.k = k
        self.level = level
        # level "group": compare the main groups (vocabulary.csv) instead of the subjects
        to = {r["subject"]: (r["group"] if level == "group" else r["subject"]) for r in read_csv(VOCABULARY)}
        read = lambda path: {r["id"]: {to.get(x, "") for x in r["subjects"].split("|")} - {"", "unknown"}
                             for r in read_csv(path)}
        self.pile = {i: s for i, s in read(SUBJECTS).items() if s}
        self.fair = {i: s for i, s in read(FAIRTEST).items() if s}

    @staticmethod
    def rank_scale(d):
        """Average ranks of the pairs (upper triangle), scaled to 0..1 and mirrored: the
        same as rank_scale in cluster.R, so tied distances get the same value."""
        n = d.shape[0]
        iu = np.triu_indices(n, 1)
        r = np.zeros_like(d, dtype=float)
        if len(iu[0]) > 1:
            r[iu] = (rankdata(d[iu], method="average") - 1) / (len(iu[0]) - 1)
        return r + r.T

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

    def write(self, distances, w):
        ids = next(iter(distances.values()))[0]
        scaled = {n: self.rank_scale(d) for n, (i, d) in distances.items()}
        mixes = {"image 2 : gallery measures 1": {"image": 2, "meta": 1},
                 "image 1 : gallery measures 1": {"image": 1, "meta": 1},
                 "image 2 : symmetry 1": {"image": 2, "symmetry": 1},
                 "image 2 : provenance 1": {"image": 2, "provenance": 1}}
        for name, mix in mixes.items():
            if all(k in scaled for k in mix):
                scaled[name] = sum(v * scaled[k] for k, v in mix.items()) / sum(mix.values())
        print(f"-- {self.level}")
        for name, d in scaled.items():
            for pool, (h, n) in self.score(d, ids).items():
                share = h / n if n else 0.0
                w.writerow([self.level, name, pool, h, n, f"{share:.3f}"])
                print(f"{name:32s} {pool:6s} {h:3d}/{n} {share:.0%}")
        if not self.pile or not self.fair:
            print("no labels to compare with")
            return
        top, (h, n) = self.baseline()
        w.writerow([self.level, f"always {top}", "-", h, n, f"{h / n:.3f}"])
        print(f"{'always ' + top:32s} {'-':6s} {h:3d}/{n} {h / n:.0%}")
        shared, same, n = self.agreement()
        # after `settled` both files hold the same answer for the 20 charts that differed,
        # so this is only informative before settling (it was 25/38 and 20/38 then)
        print(f"pile label vs fair label for the same chart: share a subject {shared}/{n}, identical {same}/{n}"
              " (identical after settling by construction)")


class KnotScore:
    """How much a chart looks like knotwork or interlace, from the 0/1 grid alone.

    openings   enclosed background areas of 2 cells or more, per 100 filled
               cells: interlace leaves many small openings between strands
    diagonal   share of filled cells joined to the rest only at a corner:
               strands in a cross-stitch chart run diagonally

    The score is the sum of the two ranks (0..2). It only orders charts for
    review; a person decides which ones are knots.
    """

    def __init__(self, txt_dir, min_cells=20):
        self.rows = []
        for f in sorted(Path(txt_dir).glob("*.txt")):
            m = Pattern.trimmed(Pattern.read(f)).astype(bool)
            if m.sum() < min_cells:
                continue
            self.rows.append({"id": f.stem, **self.measures(m)})
        rank = lambda k: (rankdata([r[k] for r in self.rows], method="average") - 1) / max(1, len(self.rows) - 1)
        for r, a, b in zip(self.rows, rank("openings"), rank("diagonal")):
            r["score"] = a + b
        self.rows.sort(key=lambda r: -r["score"])

    @staticmethod
    def measures(m):
        from scipy import ndimage
        m = np.asarray(m).astype(bool)
        filled = max(1, int(m.sum()))
        lab, n = ndimage.label(~m)
        edge = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        sizes = ndimage.sum(~m, lab, range(1, n + 1))
        openings = sum(1 for k, size in enumerate(sizes, 1) if k not in edge and size >= 2)
        q = np.pad(m, 1).astype(int)
        orth = q[:-2, 1:-1] + q[2:, 1:-1] + q[1:-1, :-2] + q[1:-1, 2:]
        diag = q[:-2, :-2] + q[:-2, 2:] + q[2:, :-2] + q[2:, 2:]
        return {"openings": 100 * openings / filled,
                "diagonal": float(((orth == 0) & (diag > 0) & m).sum() / filled)}

    def write(self, path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "score", "openings", "diagonal"])
            for r in self.rows:
                w.writerow([r["id"], f"{r['score']:.3f}", f"{r['openings']:.2f}", f"{r['diagonal']:.3f}"])


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
    ap.add_argument("step", choices=["units", "shape", "meta", "sheets", "page", "sample", "answers", "labels", "suggest", "fair", "evaluate", "settle", "settled", "knots", "knot-answers", "features", "learn", "groups", "final", "misses"])
    ap.add_argument("--txt", default=str(ROOT / "patterns" / "txt"), help="folder of 0/1 charts")
    ap.add_argument("--kinds", default=",".join(PILOT_KINDS), help="pattern types to include")
    ap.add_argument("--n", type=int, default=40, help="sample: number of charts")
    ap.add_argument("--seed", type=int, default=2026, help="sample: random seed")
    ap.add_argument("--meta-weights", default="1,1,1", help="meta: symmetry,form,provenance")
    ap.add_argument("--k", type=int, default=50, help="final: number of clusters")
    ap.add_argument("--top", type=int, default=60, help="knots: charts on the review page")
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
    elif a.step == "settled":
        if not a.reviewer:
            raise SystemExit("Give --reviewer (or REVIEWER=... to make).")
        settle_answers(a.src, a.reviewer)
    elif a.step == "knots":
        ks = KnotScore(a.txt)
        ks.write(WORK / "knots.csv")
        top = ks.rows[: a.top]
        knot = next(r for r in read_csv(FEATURES) if r["feature"] == "knot")
        ReviewPage(a.txt).write({k + 1: [r["id"]] for k, r in enumerate(top)}, WORK / "knots", {
            "run": "knots", "single": True, "exclusive": True, "title": "Sjónabók: find the knots",
            "vocabulary": [{"key": "knot", "label": "Knot"}, {"key": "none", "label": "No knot"}],
            "intro": f"The {len(top)} charts the computer finds most knot-like, most likely first "
                     f"({knot['description'].lower()}). Tap Knot or No knot. Your answers teach the next round."})
        j = json.loads((WORK / "knots" / "piles.json").read_text())
        for p, r in zip(j["piles"], top):
            p["hint"] = r["id"]
        (WORK / "knots" / "piles.json").write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")))
        print(f"{len(ks.rows)} charts scored, top {len(top)} -> {WORK / 'knots'}")
    elif a.step == "knot-answers":
        if not a.reviewer:
            raise SystemExit("Give --reviewer (or REVIEWER=... to make).")
        feature_answers(a.src, "knot", a.reviewer)
        seen = {r["id"]: r["value"] for r in read_csv(FEATURE_LABELS) if r["feature"] == "knot"}
        seeds = sorted(i for i, v in seen.items() if v == "yes")
        ids, d = read_matrix(WORK / "embed_all_dist.csv")
        pick = nearest_to(seeds, ids, d, set(seen), a.top)
        ReviewPage(a.txt).write({k + 1: [i] for k, i in enumerate(pick)}, WORK / "knots2", {
            "run": f"knots-{len(seeds)}", "single": True, "exclusive": True, "title": "Sjónabók: more knots",
            "vocabulary": [{"key": "knot", "label": "Knot"}, {"key": "none", "label": "No knot"}],
            "intro": f"The image model's nearest charts to your {len(seeds)} knots, taken from each knot in turn. "
                     "None of these were on the first page. Tap Knot or No knot."})
        j = json.loads((WORK / "knots2" / "piles.json").read_text())
        for p in j["piles"]:
            p["hint"] = p["charts"][0]["id"]
        (WORK / "knots2" / "piles.json").write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")))
        print(f"{len(seeds)} knots, {len(pick)} charts -> {WORK / 'knots2'}")
    elif a.step == "features":
        ALL.mkdir(parents=True, exist_ok=True)
        units = Corpus(a.txt, PILOT_KINDS + BAND_KINDS).units
        sd = ShapeDistance(units)
        write_matrix(ALL / "shape_dist.csv", sd.ids, sd.matrix())
        md = MetaDistance(units)
        for name, d in md.blocks().items():
            np.fill_diagonal(d, 0.0)
            write_matrix(ALL / f"{name}_dist.csv", md.ids, d)
        # the knot measures again on the repeated chart (Unit.tiled)
        tm = [KnotScore.measures(u.tiled()) for u in units]
        rk = lambda k: rankdata([m[k] for m in tm], method="average")
        d = np.mean([MetaDistance.spread(rk(k)) for k in ("openings", "diagonal")], axis=0)
        np.fill_diagonal(d, 0.0)
        write_matrix(ALL / "texture_tiled_dist.csv", md.ids, d)
        with open(ALL / "kinds.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "kind", "band"])
            for u in units:
                w.writerow([u.id, u.kind, int(u.kind in BAND_KINDS)])
        print(f"{len(units)} charts -> {ALL}")
    elif a.step == "learn":
        names = ["image", "image_upright", "image_tiled", "shape", "symmetry", "form", "provenance",
                 "texture", "texture_tiled", "upright"]
        files = {"image": WORK / "embed_all_dist.csv", "image_tiled": WORK / "embed_tiled_dist.csv",
                 "image_upright": WORK / "embed_upright_dist.csv",
                 **{n: ALL / f"{n}_dist.csv" for n in names[3:]}}
        distances = {n: read_matrix(files[n]) for n in names if files[n].exists()}
        # a finer grid for few distances, a coarser one for many (the grid grows fast)
        wl = WeightLearner(distances, step=0.1 if len(distances) <= 8 else 0.2)
        best = wl.fit()
        wl.write()
        print(f"learnt from {len(wl.group)} group labels and {len(wl.knot)} knot answers (objective: group k-NN, "
              f"knot k-NN, 3-way split ARI); fair test held out; "
              f"mean of the {wl.n_top} weightings within {wl.tie} of the best score")
        print("top weightings (score, group, knot, weights " + ",".join(wl.names) + "):")
        for sc, g, kn, w in wl.results[:8]:
            print(f"  {sc:.3f} {g:.3f} {kn if kn is None else round(kn, 3)} {np.round(w, 2)}")
        compare = [("learnt", best), ("equal", np.full(len(wl.names), 1 / len(wl.names)))]
        if "image" in wl.names:
            compare.insert(1, ("image only", np.eye(len(wl.names))[wl.names.index("image")]))
        kinds = {r["id"]: r["band"] for r in read_csv(ALL / "kinds.csv")}
        for label, w in compare:
            g, kn = wl.score(w)
            acc, ci, bal, per = wl.holdout_detail(w)
            print(f"{label:11s} train {g:.0%}  split ARI {wl.split_score(w):.2f}  knot {kn if kn is None else f'{kn:.0%}'}  "
                  f"fair test {acc:.0%} (95% {ci[0]:.0%}-{ci[1]:.0%}), balanced {bal:.0%} "
                  f"[{', '.join(f'{k} {v:.0%}' for k, v in per.items())}]  "
                  f"motifs cut in 3, agreement with groups (ARI) {wl.top_split(w, kinds):.2f}")
    elif a.step == "final":
        # cluster every chart with the learnt weights (no labels), then name the clusters
        files = {"image": "work/embed_all_dist.csv", "image_tiled": "work/embed_tiled_dist.csv",
                 "image_upright": "work/embed_upright_dist.csv"}
        args = [f"{r['weight']}={files.get(r['distance'], 'work/all/' + r['distance'] + '_dist.csv')}"
                for r in read_csv(WEIGHTS) if float(r["weight"]) > 0]
        subprocess.run(["Rscript", "cluster.R", str(a.k), *args], cwd=HERE, check=True,
                       env={**os.environ, "OUT": "work/all"})
        a.step = "groups"
    if a.step == "misses":
        files = {"image": WORK / "embed_all_dist.csv", "image_tiled": WORK / "embed_tiled_dist.csv",
                 "image_upright": WORK / "embed_upright_dist.csv"}
        rows = read_csv(WEIGHTS)
        wl = WeightLearner({r["distance"]: read_matrix(files.get(r["distance"], ALL / f"{r['distance']}_dist.csv"))
                            for r in rows})
        d = np.tensordot(np.array([float(r["weight"]) for r in rows]), wl.D, axes=1)
        labels = {**wl.group, **wl.fair}
        pool = np.array(sorted(labels))
        glabel = {r["group"]: r["label"] for r in read_csv(HERE / "groups.csv")}
        misses = []
        for i in sorted(labels):
            cand = pool[pool != i]
            near = cand[np.argsort(d[i, cand], kind="stable")[:5]]
            votes = {}
            for rank, j in enumerate(near):
                for g in labels[j]:
                    votes[g] = votes.get(g, 0) + 1 - rank * 1e-3
            guess = max(votes, key=votes.get)
            if guess not in labels[i]:
                misses.append((wl.ids[i], guess, labels[i]))
        # animals first: they are missed most
        misses.sort(key=lambda m: ("animals" not in m[2], m[0]))
        # clue words: what a person might use to tell the groups apart
        clues = [("head-legs", "Head and legs"), ("wings-tail", "Wings or tail"), ("stem-leaves", "Stem or leaves"),
                 ("petals", "Petals"), ("outline", "Outline shape"), ("solid-line", "Solid or line drawing"),
                 ("repeat", "Needs repeat"), ("wrong-label", "My label is wrong")]
        ReviewPage(a.txt).write({k + 1: [m[0]] for k, m in enumerate(misses)}, WORK / "misses", {
            "run": "misses", "single": True, "title": "Sjónabók: what the computer misses",
            "label": "What tells you",
            "vocabulary": [{"key": k, "label": v} for k, v in clues],
            "intro": f"The computer puts these {len(misses)} charts with the wrong main group. For each, tap what tells "
                     "you which group it is (several are fine), or write it in the note. Your clues become the next features."})
        j = json.loads((WORK / "misses" / "piles.json").read_text())
        name = lambda gs: " + ".join(glabel.get(g, g) for g in sorted(gs))
        for p, m in zip(j["piles"], misses):
            p["hint"] = f"{m[0]}. You: {name(m[2])}. Computer: {glabel.get(m[1], m[1])}."
        (WORK / "misses" / "piles.json").write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")))
        print(f"{len(misses)} of {len(labels)} labelled charts missed -> {WORK / 'misses'}")
    if a.step == "groups":
        to = {r["subject"]: r["group"] for r in read_csv(VOCABULARY)}
        read = lambda path: {r["id"]: {to.get(x, "") for x in r["subjects"].split("|")} - {""}
                             for r in read_csv(path)}
        fair = {i: g for i, g in read(FAIRTEST).items() if g}
        # clusters are named from the pile labels only; the fair test checks the names
        labels = {i: g for i, g in read(SUBJECTS).items() if g and i not in fair}
        clusters = read_clusters(ALL / "clusters.csv")
        rows, unnamed, right, n, fright, fn = [], [], 0, 0, 0, 0
        for c, ids in clusters.items():
            votes = {}
            for i in ids:
                for g in labels.get(i, ()):
                    votes[g] = votes.get(g, 0) + 1
            group = max(sorted(votes), key=votes.get) if votes else ""
            known = [i for i in ids if i in labels]
            right += sum(group in labels[i] for i in known)
            n += len(known)
            fright += sum(group in fair[i] for i in ids if i in fair)
            fn += sum(i in fair for i in ids)
            if not group:
                unnamed.append(c)
            rows += [{"id": i, "cluster": c, "group": group, "labelled": len(known), "size": len(ids)} for i in ids]
        with open(ALL / "groups.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "cluster", "group", "labelled", "size"])
            w.writeheader()
            w.writerows(rows)
        print(f"{len(clusters)} clusters; pile-labelled charts in their cluster's group (in sample): {right}/{n}; "
              f"fair-test charts (held out): {fright}/{fn}; clusters with no labelled chart: {unnamed}")
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
        with open(WORK / "evaluation.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["level", "distance", "pool", "right", "charts", "share"])
            for level in ("subject", "group"):
                Evaluation(level=level).write(distances, w)


if __name__ == "__main__":
    main()
