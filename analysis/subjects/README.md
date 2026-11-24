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
