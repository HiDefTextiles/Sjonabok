// submotif: whole figures (connected pieces) in 0/1 charts and their
// similarity under the 8 turns/mirrors and a small shift.
//
// The same definitions as books/travel.py, so results agree cell for cell:
//   piece  = 8-connected group of filled cells, >= min_cells cells, at least
//            2x2, not touching the chart edge. A repeat unit is tiled 3x3
//            and only pieces whose box starts in the middle copy are kept.
//   iou    = best intersection over union of piece a against the 8 views
//            of piece b, b shifted by up to `shift` cells (plus the size
//            difference) around the centred placement.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace submotif {

// A small dense 0/1 matrix, row major.
class Grid {
public:
    Grid() = default;
    Grid(int rows, int cols) : rows_(rows), cols_(cols), v_(size_t(rows) * cols, 0) {}
    Grid(int rows, int cols, std::vector<uint8_t> v) : rows_(rows), cols_(cols), v_(std::move(v)) {}

    int rows() const { return rows_; }
    int cols() const { return cols_; }
    uint8_t at(int r, int c) const { return v_[size_t(r) * cols_ + c]; }
    uint8_t& at(int r, int c) { return v_[size_t(r) * cols_ + c]; }
    const std::vector<uint8_t>& data() const { return v_; }
    int count() const;

    Grid rot90() const;        // numpy np.rot90(m, 1): anticlockwise
    Grid mirror() const;       // m[:, ::-1]
    Grid tile(int ny, int nx) const;
    std::vector<Grid> views() const;     // [rot90^k(m), rot90^k(mirror m)], k = 0..3
    // bytes + shape, as travel.py's key (min over views gives the canonical key)
    std::string bytes_key() const;

    static Grid read_txt(const std::string& path);

private:
    int rows_ = 0, cols_ = 0;
    std::vector<uint8_t> v_;
};

class Piece {
public:
    Piece(std::string chart, Grid cells, int row = 0, int col = 0);
    const std::string& chart() const { return chart_; }
    const Grid& cells() const { return cells_; }
    int n() const { return n_; }
    int row() const { return row_; }          // box origin in the chart
    int col() const { return col_; }
    const std::string& key() const { return key_; }   // same shape in any turn <=> same key
    const std::vector<Grid>& views() const { return views_; }
    int short_side() const { return std::min(cells_.rows(), cells_.cols()); }
    int long_side() const { return std::max(cells_.rows(), cells_.cols()); }

private:
    std::string chart_;
    Grid cells_;
    int n_, row_, col_;
    std::vector<Grid> views_;
    std::string key_;
};

// Pieces of one chart. tile: the chart is a repeat unit.
std::vector<Piece> find_pieces(const Grid& m, const std::string& chart, bool tile = false,
                               int min_cells = 10, bool unique = true);

double iou(const Piece& a, const Piece& b, int shift = 1);

struct Match {
    int a, b;          // indices into the piece list
    double iou;
};

class Matcher {
public:
    explicit Matcher(double match = 0.8, int shift = 1, int threads = 0)
        : match_(match), shift_(shift), threads_(threads) {}

    // every pair (i < j) of pieces from different charts with iou >= match
    std::vector<Match> all_pairs(const std::vector<Piece>& pieces) const;
    // every pair (a from left, b from right) with iou >= match
    std::vector<Match> cross_pairs(const std::vector<Piece>& left,
                                   const std::vector<Piece>& right) const;
    bool candidate(const Piece& a, const Piece& b) const;   // the cheap size filter

private:
    double match_;
    int shift_, threads_;
};

}  // namespace submotif
