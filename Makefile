# Define directories and file patterns
EPS_DIR = images/eps
TXT_DIR = images/txt
PNG_DIR = images/png

EPS_FILES = $(wildcard $(EPS_DIR)/*.eps)
TXT_FILES = $(patsubst $(EPS_DIR)/%.eps, $(TXT_DIR)/%.txt, $(EPS_FILES))
PNG_FILES = $(patsubst $(EPS_DIR)/%.eps, $(PNG_DIR)/%.png, $(EPS_FILES))

init:
	mkdir -p $(TXT_DIR)
	mkdir -p $(PNG_DIR)

# Default target
all: $(TXT_FILES) $(PNG_FILES)


# Rule to convert .eps to .txt
convert_to_txt.py: pattern_processing/eps_to_pattern.py
$(TXT_DIR)/%.txt: $(EPS_DIR)/%.eps convert_to_txt.py
	python3 convert_to_txt.py $< $@

# Rule to convert .txt to .png
convert_to_png.py: pattern_processing/pattern_to_png.py
$(PNG_DIR)/%.png: $(TXT_DIR)/%.txt convert_to_png.py
	python3 convert_to_png.py $< $@

# Clean all generated files
clean:
	find $(TXT_DIR) -name '*.txt' -delete
	find $(PNG_DIR) -name '*.png' -delete
