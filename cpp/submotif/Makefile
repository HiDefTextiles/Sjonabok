# C++ sub-motif matcher
#   make          : bin/submotif (command line) and the Python module submotif*.so
#   make test     : compare with books/travel.py (Python) on the committed charts
#   make bench    : time Python against C++ on the same pairs
#   make clean
CXX      ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -pthread
PYTHON   ?= python3
PYINC    := $(shell $(PYTHON) -m pybind11 --includes)
EXT      := $(shell $(PYTHON) -c "import sysconfig;print(sysconfig.get_config_var('EXT_SUFFIX'))")
ROOT     := ../..

LIB_SRC = src/submotif.cpp
HDR     = include/submotif.hpp
MODULE  = python/submotif$(EXT)

all: bin/submotif $(MODULE)

bin/submotif: src/main.cpp $(LIB_SRC) $(HDR)
	@mkdir -p bin
	$(CXX) $(CXXFLAGS) -Iinclude src/main.cpp $(LIB_SRC) -o $@

$(MODULE): python/bindings.cpp $(LIB_SRC) $(HDR)
	$(CXX) $(CXXFLAGS) -fPIC -shared -Iinclude $(PYINC) python/bindings.cpp $(LIB_SRC) -o $@

test: all
	cd $(ROOT) && PYTHONPATH=cpp/submotif/python $(PYTHON) cpp/submotif/python/check_travel.py

bench: all
	cd $(ROOT) && PYTHONPATH=cpp/submotif/python $(PYTHON) cpp/submotif/python/check_travel.py --bench

clean:
	rm -rf bin python/*.so

.PHONY: all test bench clean
