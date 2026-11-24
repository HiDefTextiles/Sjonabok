# Group Sjónabók patterns by subject. See README.md and the gallery's
# Methodology page. Run from this folder:
#
#   make            units, shape distance, clusters and review sheets
#   make embed      add the image-model distance (needs PyTorch + network)
#   make labels REVIEWER="Helga Ingimundardóttir"   review.csv -> subjects.csv
#   make suggest    suggestions for charts not yet labelled
#
# Only review.csv and subjects.csv are written by a person and kept in git.

PY      ?= python3
TXT     ?= ../../patterns/txt
KINDS   ?= motif,rosette
K       ?= 50
REVIEWER ?=
DISTS   = work/shape_dist.csv $(wildcard work/embed_dist.csv)

all: sheets

work/units.csv: subjects.py $(wildcard $(TXT)/*.txt)
	$(PY) subjects.py units --txt $(TXT) --kinds $(KINDS)

work/shape_dist.csv: work/units.csv
	$(PY) subjects.py shape --txt $(TXT)

embed: work/units.csv embed.py
	$(PY) embed.py --txt $(TXT)

work/clusters.csv: cluster.R $(DISTS)
	Rscript cluster.R $(K) $(DISTS)

sheets: work/clusters.csv
	$(PY) subjects.py sheets --txt $(TXT)

labels:
	$(PY) subjects.py labels --reviewer "$(REVIEWER)"

suggest: work/clusters.csv subjects.csv
	$(PY) subjects.py suggest

clean:
	rm -rf work

.PHONY: all embed sheets labels suggest clean
