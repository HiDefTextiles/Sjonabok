# Group Sjónabók patterns by subject. See README.md and the gallery's
# Methodology page. Run from this folder:
#
#   make            units, shape distance, clusters and review sheets
#   make embed      add the image-model distance (needs PyTorch + network)
#   make review     the phone-friendly review page at http://localhost:8000
#   make labels REVIEWER="Helga Ingimundardóttir"   review.csv -> subjects.csv
#   make suggest    suggestions for charts not yet labelled
#
# Only review.csv and subjects.csv are written by a person and kept in git.

PY      ?= python3
TXT     ?= ../../patterns/txt
KINDS   ?= motif,rosette
K       ?= 50
# Weights of the three distances: cell-by-cell shape, image model (DINOv2),
# gallery measures (symmetry, form, provenance; split by META_WEIGHTS).
W_SHAPE ?= 0
W_EMBED ?= 1
W_META ?= 0
META_WEIGHTS ?= 1,1,1
REVIEWER ?=
DISTS   = work/shape_dist.csv work/meta_dist.csv $(wildcard work/embed_dist.csv)

all: sheets

work/units.csv: subjects.py $(wildcard $(TXT)/*.txt)
	$(PY) subjects.py units --txt $(TXT) --kinds $(KINDS)

work/shape_dist.csv: work/units.csv
	$(PY) subjects.py shape --txt $(TXT)

embed: work/units.csv embed.py
	$(PY) embed.py --txt $(TXT)

work/meta_dist.csv: work/units.csv subjects.py
	$(PY) subjects.py meta --txt $(TXT) --meta-weights $(META_WEIGHTS)

work/clusters.csv: cluster.R $(DISTS) Makefile
	Rscript cluster.R $(K) $(W_SHAPE)=work/shape_dist.csv $(W_EMBED)=work/embed_dist.csv $(W_META)=work/meta_dist.csv

sheets: work/clusters.csv
	$(PY) subjects.py sheets --txt $(TXT)

work/review/index.html: work/clusters.csv review/index.html vocabulary.csv
	$(PY) subjects.py page --txt $(TXT)

review: work/review/index.html
	@echo "Open http://localhost:8000 (Ctrl+C to stop)"
	$(PY) -m http.server 8000 -d work/review

sample: work/units.csv review/index.html vocabulary.csv
	$(PY) subjects.py sample --txt $(TXT) --n 40 --seed 2026
	@echo "Open http://localhost:8001 (Ctrl+C to stop)"
	$(PY) -m http.server 8001 -d work/sample

labels:
	$(PY) subjects.py labels --reviewer "$(REVIEWER)"

suggest: work/clusters.csv subjects.csv
	$(PY) subjects.py suggest

# fair test: score each distance against fairtest.csv
evaluate: work/embed_dist.csv work/meta_dist.csv work/shape_dist.csv subjects.csv fairtest.csv
	$(PY) subjects.py evaluate --txt $(TXT)

# charts whose pile label and fair-test label differ, both answers shown
settle: subjects.csv fairtest.csv review/index.html
	$(PY) subjects.py settle --txt $(TXT)
	@echo "Open http://localhost:8002 (Ctrl+C to stop)"
	$(PY) -m http.server 8002 -d work/settle

# the most knot-like charts, to mark Knot or No knot
knots: review/index.html features.csv
	$(PY) subjects.py knots --txt $(TXT)
	@echo "Open http://localhost:8003 (Ctrl+C to stop)"
	$(PY) -m http.server 8003 -d work/knots

# unlabelled charts nearest to the labelled animals, to mark Animal or No animal
animals: review/index.html work/embed_all_dist.csv work/all/texture_dist.csv
	$(PY) subjects.py animals --txt $(TXT)
	@echo "Open http://localhost:8004 (Ctrl+C to stop)"
	$(PY) -m http.server 8004 -d work/animals

# Final groups: features for every chart, weights learnt from the labels,
# then a clustering that sees no labels, each cluster named by its labelled charts.
CHARTS := $(wildcard $(TXT)/*.txt)

work/embed_all_dist.csv: embed.py $(CHARTS)
	HF_HUB_DISABLE_XET=1 $(PY) embed.py --all --txt $(TXT)

work/embed_tiled_dist.csv: embed.py $(CHARTS)
	HF_HUB_DISABLE_XET=1 $(PY) embed.py --all --tile --txt $(TXT)

work/embed_upright_dist.csv: embed.py $(CHARTS)
	HF_HUB_DISABLE_XET=1 $(PY) embed.py --all --upright --txt $(TXT)

# writes every work/all/*_dist.csv and work/all/kinds.csv
work/all/texture_dist.csv: subjects.py $(CHARTS)
	$(PY) subjects.py features --txt $(TXT)

# image-and-words model (OpenCLIP) against prompts.csv; also writes work/all/clip_text_dist.csv
work/clip_all_dist.csv: clip_features.py prompts.csv $(CHARTS)
	HF_HUB_DISABLE_XET=1 $(PY) clip_features.py --txt $(TXT)

EMBEDS := work/embed_all_dist.csv work/embed_tiled_dist.csv work/embed_upright_dist.csv work/clip_all_dist.csv

weights.csv: $(EMBEDS) work/all/texture_dist.csv subjects.csv fairtest.csv feature_labels.csv
	$(PY) subjects.py learn

final: weights.csv
	$(PY) subjects.py final --k $(K)

# look-alike families for every chart (no labels), kept in git for the gallery
families.csv: weights.csv families.R $(EMBEDS) work/all/texture_dist.csv
	Rscript families.R

families: families.csv

clean:
	rm -rf work

.PHONY: all embed sheets review sample labels suggest evaluate settle knots animals final families clean
