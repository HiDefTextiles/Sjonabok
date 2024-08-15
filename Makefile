# Define directories and file patterns
PARENT_DIR = images
EPS_DIR = $(PARENT_DIR)/eps
TXT_DIR = $(PARENT_DIR)/txt
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

%_p1.txt: ROWS_DISTANCE=5
%_p1.txt: COLS_DISTANCE=5
%_p1.txt: %.txt split_patterns.py pattern_processing/separate_patterns.py
	python3 split_patterns.py $< --cols_distance $(COLS_DISTANCE) --rows_distance $(ROWS_DISTANCE)

# Rule to convert .txt to .png
$(PNG_DIR)/%.png: $(TXT_DIR)/%.txt convert_to_png.py pattern_processing/pattern_to_png.py
	python3 convert_to_png.py $< $@

# Clean all generated files
clean:
	find $(TXT_DIR) -name '*.txt' -delete
	find $(PNG_DIR) -name '*.png' -delete
