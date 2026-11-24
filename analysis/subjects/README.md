# Sorting Sjónabók patterns by subject

The computer proposes piles of look-alike charts; a person names their
subject. The method, its reasoning and its limits are explained for a
general reader on the gallery's **Methods** page (`gallery/methods.qmd`).

| File | Written by | Kept in git |
|---|---|---|
| `subjects.py` | code: units, shape distance, contact sheets, labels, suggestions | yes |
| `embed.py` | code: DINOv2 image-model distance (optional, needs PyTorch) | yes |
| `cluster.R` | code: rank-scaled distances, Ward clustering into `K` piles | yes |
| `vocabulary.csv` | the fixed list of subject words | yes |
| `review.csv` | the reviewer, one row per pile of the current run | yes |
| `subjects.csv` | `make labels`, from the review: one row per chart, with reviewer and date | yes |
| `work/` | everything else, rebuilt by `make` | no |

```bash
make                                   # units, shape distance, clusters, sheets in work/sheets/
make embed && make -B sheets           # add the image model (PyTorch, downloads ~85 MB once)
make labels REVIEWER="Helga Ingimundardóttir"
make suggest                           # work/suggestions.csv
make KINDS=border,edging,"vertical band"   # later rounds: bands, compared on one repeat
```

Settings: `K` (number of piles, default 50), `KINDS` (pattern types,
default `motif,rosette` for the pilot), `TXT` (chart folder).

A chart already in `subjects.csv` is never changed by `make labels` and is
left out of the next `review.csv`. To correct a label, edit `subjects.csv`
directly; git history shows who changed what.
