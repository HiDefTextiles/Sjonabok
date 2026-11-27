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

# Without patterns/txt (git-ignored; restore with `make originals`) the
# committed units are kept, so editing a script does not wipe patterns/min.
$(PARENT_DIR)/repeats.csv: $(wildcard $(TXT_DIR)/*.txt) extract_repeats.py pattern_processing/repeat_unit.py gallery/scripts/build_gallery.py
	$(if $(wildcard $(TXT_DIR)/*.txt),python3 extract_repeats.py $(TXT_DIR) $(PARENT_DIR),@echo "$(TXT_DIR) is empty: keeping the committed repeat units")

.PHONY: originals repeats

# ── Charts with several kinds of mark (committed) ───────────────────────────
# make marks : read the EPS pages whose charts mix marks (diamond, cross,
#              circled cross, dot, half cell) into colour-digit charts in
#              patterns/colour, and draw a review sheet of every kind of mark
MARKS_EPS_DIR = images-multi/eps
COLOUR_DIR = $(PARENT_DIR)/colour

marks:
	python3 convert_marks.py $(MARKS_EPS_DIR) $(COLOUR_DIR) --review marks-review.png

.PHONY: marks

# ── Gallery website (gallery/, Quarto) ───────────────────────────────────────
# make gallery-data : measure every pattern and draw PNGs in the HI palette
# make gallery      : build the static site into gallery/_site
# make gallery-preview : live preview while editing
# make symmetry-examples : redraw the symmetry pictures on the About page
#                  (small SVGs in gallery/img/symmetry, committed)
GALLERY = gallery
GALLERY_DATA = $(GALLERY)/patterns/patterns.json
SYMMETRY_SVG = $(GALLERY)/img/symmetry/p1.svg

BOOKS_DIR = $(PARENT_DIR)/books
ALPHABET_DIR = $(PARENT_DIR)/alphabets
$(GALLERY_DATA): $(wildcard $(MIN_DIR)/*.txt) $(wildcard $(BOOKS_DIR)/*.txt) $(wildcard $(COLOUR_DIR)/*.txt) $(wildcard $(ALPHABET_DIR)/*.txt) $(ALPHABET_DIR)/alphabets.csv $(GALLERY)/regions.csv books/books.csv $(PARENT_DIR)/repeats.csv $(GALLERY)/scripts/build_gallery.py pattern_processing/pattern_to_png.py pattern_processing/repeat_unit.py
	python3 $(GALLERY)/scripts/build_gallery.py $(MIN_DIR) $(GALLERY)/patterns --extra $(BOOKS_DIR) --extra $(COLOUR_DIR) --alphabets $(ALPHABET_DIR)

gallery-data: $(GALLERY_DATA)

# Chart counts for the pages (gallery/_counts.yml) and the README, from the chart files
COUNTS = $(GALLERY)/_counts.yml
$(COUNTS): $(wildcard $(MIN_DIR)/*.txt) $(wildcard $(BOOKS_DIR)/*.txt) $(wildcard $(COLOUR_DIR)/*.txt) $(wildcard $(ALPHABET_DIR)/*.txt) $(ALPHABET_DIR)/alphabets.csv $(GALLERY)/scripts/counts.py
	python3 $(GALLERY)/scripts/counts.py --yaml $@ --readme README.md

counts: $(COUNTS)

$(SYMMETRY_SVG): $(GALLERY)/scripts/symmetry_examples.py $(GALLERY)/scripts/build_gallery.py
	python3 $(GALLERY)/scripts/symmetry_examples.py $(GALLERY)/img/symmetry

symmetry-examples: $(SYMMETRY_SVG)

# make reading-examples SCANS=dir : redraw the pictures on the "How we read
#                  old pattern books" page from Met scans (SCANS/<book>/<image>.webp,
#                  books/fetch.py gets them). Small WebP files in gallery/img/reading,
#                  committed; the script stops if a reading differs from patterns/books.
SCANS ?= books/scans
reading-examples:
	python3 $(GALLERY)/scripts/reading_examples.py $(SCANS) $(GALLERY)/img/reading

gallery: $(GALLERY_DATA) $(SYMMETRY_SVG) $(COUNTS)
	cd $(GALLERY) && quarto render

gallery-preview: $(GALLERY_DATA) $(SYMMETRY_SVG) $(COUNTS)
	cd $(GALLERY) && quarto preview

# make overview-layout : optimise the two overview sheets (bands: Gurobi, needs
#                        gurobipy and a licence; motifs: local search, --time as long as you like);
#                        commit gallery/layout/*.csv
PACK_TIME = 600
overview-layout: $(GALLERY_DATA)
	python3 $(GALLERY)/scripts/pack_overview.py bands  $(GALLERY)/patterns/overview-band-items.csv  $(GALLERY)/layout/bands.csv  --time $(PACK_TIME)
	python3 $(GALLERY)/scripts/pack_overview.py motifs $(GALLERY)/patterns/overview-motif-items.csv $(GALLERY)/layout/motifs.csv --time $(PACK_TIME) --rainbow 1
	python3 $(GALLERY)/scripts/build_gallery.py $(MIN_DIR) $(GALLERY)/patterns --extra $(BOOKS_DIR) --extra $(COLOUR_DIR) --alphabets $(ALPHABET_DIR)

gallery-clean:
	rm -rf $(GALLERY)/_site $(GALLERY)/.quarto $(GALLERY)/patterns $(COUNTS)

.PHONY: counts gallery gallery-data gallery-preview gallery-clean symmetry-examples reading-examples overview-layout

# ── Manuscript map (gallery/map/, R) ─────────────────────────────────────────
# make motifs : pick a signature motif per manuscript from patterns/min
#               -> gallery/map/signatures.csv (+ candidates.png review sheet)
# make map    : leaflet map with those motifs as markers -> gallery/map/web/
# Needs R with readr, dplyr, purrr, stringr, tibble, leaflet, htmlwidgets.
# The built map is committed, so the gallery Action does not need R.
MAP = $(GALLERY)/map

$(MAP)/signatures.csv: $(wildcard $(MIN_DIR)/*.txt) $(PARENT_DIR)/repeats.csv $(MAP)/signature_motifs.R $(wildcard $(MAP)/picks.csv)
	LC_ALL=C.UTF-8 Rscript $(MAP)/signature_motifs.R

$(MAP)/web/index.html: $(MAP)/signatures.csv $(MAP)/manuscripts.csv $(MAP)/places.csv $(MAP)/manuscript_map.R
	cd $(MAP) && LC_ALL=C.UTF-8 Rscript manuscript_map.R

motifs: $(MAP)/signatures.csv
map: $(MAP)/web/index.html

# ── Printed European pattern books (books/) ──────────────────────────────────
# make travel    : sub-motifs shared by the books and the manuscripts
#                  -> books/travel/shared.csv, pairs.csv, shared.png
# make books-map : map + timeline of books and manuscripts -> gallery/map/web/europe.html
# Charts read from the scans are committed in patterns/books; the scans are
# not (books/fetch.py gets them, books/digitise.py and books/woodcut.py read them).
books/travel/shared.csv: $(wildcard $(MIN_DIR)/*.txt) $(wildcard $(BOOKS_DIR)/*.txt) books/books.csv books/travel.py
	python3 books/travel.py

$(MAP)/web/europe.html: books/travel/shared.csv books/books.csv $(MAP)/manuscripts.csv $(MAP)/places.csv $(MAP)/books_map.R
	cd $(MAP) && LC_ALL=C.UTF-8 Rscript books_map.R

# make slips : find squares that break a band's symmetry (reading slips) and
#              edit them in patterns/books; each edit, with the value read, is
#              kept in books/corrections.csv (python3 books/slips.py revert undoes them)
slips:
	python3 books/slips.py find
	python3 books/slips.py apply

travel: books/travel/shared.csv
books-map: $(MAP)/web/europe.html

.PHONY: motifs map travel books-map slips

# ── Seeds: smallest piece + symmetry recipe per chart ───────────────────────
# make seeds       : patterns/seeds.csv (seed, recipe, frieze/point group,
#                    sizes) and patterns/near.csv (symmetries that almost hold)
#                    from the full charts in patterns/txt (make originals)
# make seeds-check : rebuild every chart from seeds.csv and compare it cell for
#                    cell with patterns/min (and patterns/txt when present)
# make seeds-sheet : before/after picture, chart beside its seed
SEEDS = $(PARENT_DIR)/seeds.csv

seeds: $(SEEDS)

$(SEEDS): $(wildcard $(TXT_DIR)/*.txt) $(wildcard $(MIN_DIR)/*.txt) condense.py pattern_processing/fundamental.py
	$(if $(wildcard $(TXT_DIR)/*.txt),python3 condense.py find $(TXT_DIR) $(PARENT_DIR),@echo "$(TXT_DIR) is empty: run make originals first")

seeds-check:
	python3 condense.py check $(PARENT_DIR)

seeds-sheet: $(SEEDS)
	python3 condense.py sheet $(PARENT_DIR) seeds-sheet.png

.PHONY: seeds seeds-check seeds-sheet

# ── Scan readers (books/sources/) and the C++ sub-motif matcher (cpp/) ──────
# make sources-test    : read drawn test pages in every layout (no scans needed)
# make sources-check   : re-read every scan in books/scans with the PR #46
#                        readers and the current ones; outputs must be identical
# make submotif        : build cpp/submotif (command line + Python module)
# make submotif-test   : C++ against books/travel.py (pieces, iou, pairs)
# make similarity      : every pair of similar whole figures across all charts
#                        -> books/similarity/pairs.csv, pieces.csv
SUBMOTIF = cpp/submotif

sources-test:
	python3 -W ignore books/sources/test_sources.py

sources-check:
	books/sources/regress.sh

submotif:
	$(MAKE) -C $(SUBMOTIF)

submotif-test:
	$(MAKE) -C $(SUBMOTIF) test

books/similarity/pairs.csv: $(wildcard $(MIN_DIR)/*.txt) $(wildcard $(BOOKS_DIR)/*.txt) $(PARENT_DIR)/repeats.csv | submotif
	@mkdir -p books/similarity
	$(SUBMOTIF)/bin/submotif --units $(PARENT_DIR)/repeats.csv --pieces books/similarity/pieces.csv $(MIN_DIR) $(BOOKS_DIR) > $@

similarity: books/similarity/pairs.csv

.PHONY: sources-test sources-check submotif submotif-test similarity

# ── Sarpur records (sarpur.is) ──────────────────────────────────────────────
# sarpur/*.csv are committed; make sarpur rebuilds sarpur/sarpur.sqlite, which
# also holds europeana.csv and a shared `sources` table (sarpur/sources.py) with
# the same metadata for every source: manuscripts, Sarpur, books, Europeana
SOURCE_CSVS = books/books.csv books/survey.csv books/library_terms.csv $(MAP)/manuscripts.csv $(MAP)/places.csv
sarpur: sarpur/sarpur.sqlite
sarpur/sarpur.sqlite: sarpur/build_db.py sarpur/sources.py $(wildcard sarpur/*.csv) $(SOURCE_CSVS)
	python3 sarpur/build_db.py $@
.PHONY: sarpur
