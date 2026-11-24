# Define directories and file patterns
PARENT_DIR = patterns
EPS_DIR = $(PARENT_DIR)/eps
TXT_DIR = $(PARENT_DIR)/txt
MIN_DIR = $(PARENT_DIR)/min
PNG_DIR = $(PARENT_DIR)/png

init:
	mkdir -p $(TXT_DIR)
	mkdir -p $(PNG_DIR)

txt: EPS_FILES = $(wildcard $(EPS_DIR)/*.eps)
txt: TXT_FILES = $(patsubst $(EPS_DIR)/%.eps, $(TXT_DIR)/%.txt, $(EPS_FILES))
txt: $(TXT_FILES)
	$(foreach txt_file, $(TXT_FILES), make $(txt_file);)
	@echo "All txt files converted"

png: TXT_FILES = $(wildcard $(TXT_DIR)/*.txt)
png: PNG_FILES = $(patsubst $(TXT_DIR)/%.txt, $(PNG_DIR)/%.png, $(TXT_FILES))
png: $(PNG_FILES)
	$(foreach png_file, $(PNG_FILES), make $(png_file);)
	@echo "All png files converted"

all:
	make txt
	make png
	@echo "All files converted"


alphabet:
	make all PARENT_DIR=alphabet COLS_DISTANCE=1

# Rule to convert .eps to .txt
$(TXT_DIR)/%.txt: $(EPS_DIR)/%.eps convert_to_txt.py pattern_processing/eps_to_pattern.py
	python3 convert_to_txt.py $< $@

$(TXT_DIR)/%_p1.txt: ROWS_DISTANCE=5
$(TXT_DIR)/%_p1.txt: COLS_DISTANCE=5
$(TXT_DIR)/%_p1.txt: $(TXT_DIR)/%.txt $(EPS_DIR)/%.eps split_patterns.py pattern_processing/separate_patterns.py
	python3 split_patterns.py $< --cols_distance $(COLS_DISTANCE) --rows_distance $(ROWS_DISTANCE)

# Rule to convert .txt to .png
$(PNG_DIR)/%.png: ZOOM_FACTOR=10
$(PNG_DIR)/%.png: $(TXT_DIR)/%.txt convert_to_png.py pattern_processing/pattern_to_png.py
	python3 convert_to_png.py $< $@ --zoom_factor $(ZOOM_FACTOR)

# Clean all generated files
clean:
	find $(TXT_DIR) -name '*.txt' -delete
	find $(PNG_DIR) -name '*.png' -delete

# ── Minimal charts (committed) ──────────────────────────────────────────────
# patterns/txt holds the full charts from the book; it is git-ignored.
# make originals : restore patterns/txt from the last commit that had it
# make repeats   : patterns/min/<name>.txt (one repeat unit per exact band,
#                  other charts unchanged) and patterns/repeats.csv
ORIG_REV = $(shell git rev-list -1 HEAD -- $(TXT_DIR)/natmus453_706_p4.txt)^

originals:
	git archive $(ORIG_REV) $(TXT_DIR) | tar -x

repeats: $(PARENT_DIR)/repeats.csv

$(PARENT_DIR)/repeats.csv: $(wildcard $(TXT_DIR)/*.txt) extract_repeats.py pattern_processing/repeat_unit.py gallery/scripts/build_gallery.py
	python3 extract_repeats.py $(TXT_DIR) $(PARENT_DIR)

.PHONY: originals repeats

# ── Gallery website (gallery/, Quarto) ───────────────────────────────────────
# make gallery-data : measure every pattern and draw PNGs in the HI palette
# make gallery      : build the static site into gallery/_site
# make gallery-preview : live preview while editing
GALLERY = gallery
GALLERY_DATA = $(GALLERY)/patterns/patterns.json

$(GALLERY_DATA): $(wildcard $(MIN_DIR)/*.txt) $(PARENT_DIR)/repeats.csv $(GALLERY)/scripts/build_gallery.py pattern_processing/pattern_to_png.py pattern_processing/repeat_unit.py
	python3 $(GALLERY)/scripts/build_gallery.py $(MIN_DIR) $(GALLERY)/patterns

gallery-data: $(GALLERY_DATA)

gallery: $(GALLERY_DATA)
	cd $(GALLERY) && quarto render

gallery-preview: $(GALLERY_DATA)
	cd $(GALLERY) && quarto preview

# make overview-layout : optimise the two overview sheets (bands: Gurobi, needs
#                        gurobipy and a licence; motifs: local search, ~10 min);
#                        commit gallery/layout/*.csv
PACK_TIME = 600
overview-layout: $(GALLERY_DATA)
	python3 $(GALLERY)/scripts/pack_overview.py bands  $(GALLERY)/patterns/overview-band-items.csv  $(GALLERY)/layout/bands.csv  --time $(PACK_TIME)
	python3 $(GALLERY)/scripts/pack_overview.py motifs $(GALLERY)/patterns/overview-motif-items.csv $(GALLERY)/layout/motifs.csv --time $(PACK_TIME)
	python3 $(GALLERY)/scripts/build_gallery.py $(MIN_DIR) $(GALLERY)/patterns

gallery-clean:
	rm -rf $(GALLERY)/_site $(GALLERY)/.quarto $(GALLERY)/patterns

.PHONY: gallery gallery-data gallery-preview gallery-clean overview-layout
