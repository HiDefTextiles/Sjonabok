// submotif: bulk sub-motif similarity across every chart.
//
//   submotif [--min-cells 10] [--match 0.8] [--shift 1] [--threads N]
//            [--units patterns/repeats.csv] [--pieces pieces.csv] DIR...  > pairs.csv
//
// Reads every DIR/*.txt (0/1 charts), cuts them into whole figures and
// prints every pair of figures from different charts whose iou >= match:
//   chart_a,row_a,col_a,chart_b,row_b,col_b,cells_a,cells_b,iou
// Charts named in --units (status "unit" in repeats.csv) are repeat units
// and are tiled before cutting, as in books/travel.py.
#include "submotif.hpp"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>

namespace fs = std::filesystem;
using namespace submotif;

static std::set<std::string> read_units(const std::string& csv) {
    std::set<std::string> u;
    std::ifstream f(csv);
    std::string line, header;
    std::getline(f, header);
    // columns: find "name" and "status"
    std::vector<std::string> cols;
    { std::stringstream ss(header); std::string c; while (std::getline(ss, c, ',')) cols.push_back(c); }
    int iname = -1, istatus = -1;
    for (int i = 0; i < int(cols.size()); ++i) {
        if (cols[i] == "name") iname = i;
        if (cols[i] == "status") istatus = i;
    }
    while (std::getline(f, line)) {
        std::vector<std::string> v; std::stringstream ss(line); std::string c;
        while (std::getline(ss, c, ',')) v.push_back(c);
        if (iname >= 0 && istatus >= 0 && int(v.size()) > std::max(iname, istatus) && v[istatus] == "unit")
            u.insert(v[iname]);
    }
    return u;
}

int main(int argc, char** argv) {
    int min_cells = 10, shift = 1, threads = 0;
    double match = 0.8;
    std::string units_csv, pieces_csv;
    std::vector<std::string> dirs;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto val = [&]() -> std::string {
            if (i + 1 >= argc) { std::cerr << a << " needs a value\n"; std::exit(2); }
            return argv[++i];
        };
        if (a == "--min-cells") min_cells = std::stoi(val());
        else if (a == "--match") match = std::stod(val());
        else if (a == "--shift") shift = std::stoi(val());
        else if (a == "--threads") threads = std::stoi(val());
        else if (a == "--units") units_csv = val();
        else if (a == "--pieces") pieces_csv = val();
        else if (a == "-h" || a == "--help") {
            std::cerr << "usage: submotif [--min-cells N] [--match X] [--shift N] [--threads N]"
                         " [--units repeats.csv] [--pieces out.csv] DIR...\n";
            return 0;
        } else dirs.push_back(a);
    }
    auto units = units_csv.empty() ? std::set<std::string>{} : read_units(units_csv);
    auto t0 = std::chrono::steady_clock::now();
    std::vector<Piece> pieces;
    int charts = 0;
    for (auto& d : dirs) {
        std::vector<fs::path> files;
        for (auto& e : fs::directory_iterator(d))
            if (e.path().extension() == ".txt") files.push_back(e.path());
        std::sort(files.begin(), files.end());
        for (auto& p : files) {
            std::string name = p.stem().string();
            auto ps = find_pieces(Grid::read_txt(p.string()), name, units.count(name) > 0, min_cells);
            pieces.insert(pieces.end(), ps.begin(), ps.end());
            ++charts;
        }
    }
    auto pairs = Matcher(match, shift, threads).all_pairs(pieces);
    auto t1 = std::chrono::steady_clock::now();
    std::printf("chart_a,row_a,col_a,chart_b,row_b,col_b,cells_a,cells_b,iou\n");
    for (auto& m : pairs) {
        const Piece &a = pieces[m.a], &b = pieces[m.b];
        std::printf("%s,%d,%d,%s,%d,%d,%d,%d,%.3f\n", a.chart().c_str(), a.row(), a.col(),
                    b.chart().c_str(), b.row(), b.col(), a.n(), b.n(), m.iou);
    }
    if (!pieces_csv.empty()) {
        std::ofstream f(pieces_csv);
        f << "chart,row,col,height,width,cells,rows\n";
        for (auto& p : pieces) {
            f << p.chart() << ',' << p.row() << ',' << p.col() << ',' << p.cells().rows() << ','
              << p.cells().cols() << ',' << p.n() << ',';
            for (int r = 0; r < p.cells().rows(); ++r) {
                if (r) f << '/';
                for (int c = 0; c < p.cells().cols(); ++c) f << int(p.cells().at(r, c));
            }
            f << '\n';
        }
    }
    double s = std::chrono::duration<double>(t1 - t0).count();
    std::fprintf(stderr, "%d charts, %zu pieces, %zu pairs, %.2f s\n", charts, pieces.size(), pairs.size(), s);
}
