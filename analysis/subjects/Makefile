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
W_SHAPE ?= 0          # cell-by-cell shape distance
W_EMBED ?= 1          # image model (DINOv2)
W_META  ?= 0          # gallery measures: symmetry, form, provenance
META_WEIGHTS ?= 1,1,1 # inside W_META: symmetry,form,provenance
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

labels:
	$(PY) subjects.py labels --reviewer "$(REVIEWER)"

suggest: work/clusters.csv subjects.csv
	$(PY) subjects.py suggest

clean:
	rm -rf work

.PHONY: all embed sheets review labels suggest clean
