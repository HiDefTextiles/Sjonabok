# Sorting Sjónabók patterns by subject

The computer proposes piles of look-alike charts; a person names their
subject. The method, its reasoning and its limits are explained for a
general reader on the gallery's **Methods** page (`gallery/methods.qmd`).

| File | Written by | Kept in git |
|---|---|---|
| `subjects.py` | code: units, shape distance, contact sheets, labels, suggestions | yes |
| `embed.py` | code: DINOv2 image-model distance (optional, needs PyTorch and timm) | yes |
| `cluster.R` | code: rank-scaled distances, Ward clustering into `K` piles | yes |
| `review/index.html` | the phone-friendly review page (tap a subject per pile, set odd charts apart) | yes |
| `vocabulary.csv` | the fixed list of subject words | yes |
| `review.csv` | the reviewer, one row per pile of the current run | yes |
| `subjects.csv` | `make labels`, from the review: one row per chart, with reviewer and date | yes |
| `work/` | everything else, rebuilt by `make` | no |

```bash
make embed                             # image model (pip install torch timm; ~85 MB from huggingface.co once)
make                                   # units, distances, clusters, sheets in work/sheets/
# HF_HUB_DISABLE_XET=1 avoids Hugging Face's xet download server if a firewall blocks it
#          # add the image model (pip install torch timm; downloads ~85 MB from huggingface.co once)
make review                            # review page at http://localhost:8000, exports review.csv
make labels REVIEWER="Helga Ingimundardóttir"
make suggest                           # work/suggestions.csv
make KINDS=border,edging,"vertical band"   # later rounds: bands, compared on one repeat
```

Settings: `K` (number of piles, default 50), `WEIGHTS` (shape and
image-model weights, default `0 1`; without `make embed` the shape distance is used alone), `KINDS` (pattern types,
default `motif,rosette` for the pilot), `TXT` (chart folder).

A chart already in `subjects.csv` is never changed by `make labels` and is
left out of the next `review.csv`. To correct a label, edit `subjects.csv`
directly; git history shows who changed what.

## The review page

`make review` builds `work/review/` (the page plus `piles.json` for the
current run) and serves it at http://localhost:8000. It works on a phone on
the same network too. Answers are kept in the browser; **Export review.csv**
writes the form that `make labels` reads.

The same page can be published on claude.ai, where answers are kept in the
page's own database. Export the pile documents as JSON files (one per pile)
and run `python3 subjects.py answers --from <folder>` to write `review.csv`.

## The fair test

`make sample` draws 40 charts at random (seed 2026) and serves them as a
review page with one chart per card. Labels made this way do not depend on
any clustering, so they can compare the distances (shape, image model,
gallery measures) without favouring the one that made the piles.

## Main groups, features and knots

- `vocabulary.csv` gives each subject a main group (`groups.csv`: animals, plants, ornament, letters).
  The gallery's *Main group* filter comes from it. Reviewers disagree far less on groups than
  on subjects (see the Methods page).
- `features.csv` lists features any chart can have (knot, small flowers, frame), kept apart
  from subjects.
- `make knots` ranks every chart by how knot-like it is (enclosed openings, diagonal strokes)
  and serves a Knot / No knot page of the top 60.
- `misses_clues.csv` holds what the reviewer said tells the group for charts the computer
  missed; `MetaDistance.clues` turns the clues into measures (facing, tips, thin, solidity,
  roughness) and `features` writes `work/all/clues_dist.csv`.
- `clip_features.py` (`make work/clip_all_dist.csv`) scores every chart with OpenCLIP against the
  phrases in `prompts.csv` (no labels): an image distance and a word-score distance for `learn`.
- `make animals` serves an Animal / No animal page of the 60 unlabelled charts nearest to the
  labelled animals (image model 0.7, clue measures 0.3).
- `make evaluate` scores each distance against `fairtest.csv`; `make settle` serves a page of
  the charts whose two labels differ, and `subjects.py settled --from <dir>` writes the answers.

## Ways to browse (no labels)

- `gallery/scripts/facets.py`: fit on 85 needles, outline, stroke and openness words from each
  0/1 chart, computed when the gallery is built (NumPy only).
- `subjects.py features`, `make weights.csv`: distances for all 600 charts and the weights learnt
  from the labels (`weights.csv`, kept in git).
- `make families` (Rscript families.R): look-alike families, as many as stay stable under
  resampling (fpc::clusterboot, mean Jaccard 0.7; now M1..M4 motifs, B1..B3 bands), 24 close
  families per part, the look-alike order and a t-SNE map -> `families.csv`, kept in git so the
  gallery and pattern synthesis can use it without the image model. Needs the R packages Rtsne
  and fpc.
- `subjects.py learn` reports the fair test with a bootstrap 95% interval, balanced accuracy
  and the agreement (ARI) of a 3-way cut of the motifs with the main groups.
- `subjects.py misses`: a review page of the charts the computer places in the wrong main
  group, asking what tells them apart (the next features).
