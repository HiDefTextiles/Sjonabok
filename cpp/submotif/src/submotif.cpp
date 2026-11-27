#include "submotif.hpp"

#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>
#include <thread>

namespace submotif {

// ── Grid ────────────────────────────────────────────────────────────────────

int Grid::count() const {
    int n = 0;
    for (auto x : v_) n += x != 0;
    return n;
}

Grid Grid::rot90() const {
    Grid g(cols_, rows_);
    for (int i = 0; i < cols_; ++i)
        for (int j = 0; j < rows_; ++j) g.at(i, j) = at(j, cols_ - 1 - i);
    return g;
}

Grid Grid::mirror() const {
    Grid g(rows_, cols_);
    for (int r = 0; r < rows_; ++r)
        for (int c = 0; c < cols_; ++c) g.at(r, c) = at(r, cols_ - 1 - c);
    return g;
}

Grid Grid::tile(int ny, int nx) const {
    Grid g(rows_ * ny, cols_ * nx);
    for (int r = 0; r < g.rows(); ++r)
        for (int c = 0; c < g.cols(); ++c) g.at(r, c) = at(r % rows_, c % cols_);
    return g;
}

std::vector<Grid> Grid::views() const {
    std::vector<Grid> out;
    out.reserve(8);
    for (const Grid& b : {*this, mirror()}) {
        Grid v = b;
        for (int k = 0; k < 4; ++k) {
            out.push_back(v);
            v = v.rot90();
        }
    }
    return out;
}

std::string Grid::bytes_key() const {
    std::string s(v_.begin(), v_.end());
    s.push_back(char(rows_ & 0xff)); s.push_back(char(rows_ >> 8));
    s.push_back(char(cols_ & 0xff)); s.push_back(char(cols_ >> 8));
    return s;
}

Grid Grid::read_txt(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("cannot read " + path);
    std::vector<std::string> rows;
    std::string line;
    while (std::getline(f, line)) {
        std::string t;
        for (char ch : line)
            if (ch == '0' || ch == '1') t.push_back(ch);
        if (!t.empty()) rows.push_back(t);
    }
    if (rows.empty()) return Grid();
    size_t w = 0;
    for (auto& r : rows) w = std::max(w, r.size());
    Grid g(int(rows.size()), int(w));
    for (size_t r = 0; r < rows.size(); ++r)
        for (size_t c = 0; c < rows[r].size(); ++c) g.at(int(r), int(c)) = rows[r][c] == '1';
    return g;
}

// ── Piece ───────────────────────────────────────────────────────────────────

Piece::Piece(std::string chart, Grid cells, int row, int col)
    : chart_(std::move(chart)), cells_(std::move(cells)), n_(cells_.count()), row_(row), col_(col) {
    views_ = cells_.views();
    key_ = views_[0].bytes_key();
    for (auto& v : views_) key_ = std::min(key_, v.bytes_key());
}

// 8-connected components, labelled in raster order of their first cell
// (the order scipy.ndimage.label gives), so the same piece is kept when
// several copies of one shape are in a chart.
std::vector<Piece> find_pieces(const Grid& unit, const std::string& chart, bool tile,
                               int min_cells, bool unique) {
    const Grid m = tile ? unit.tile(3, 3) : unit;
    const int H = m.rows(), W = m.cols();
    std::vector<int> lab(size_t(H) * W, 0);
    std::vector<Piece> out;
    std::set<std::string> seen;
    std::vector<int> stack, members;
    int next = 0;
    for (int r0 = 0; r0 < H; ++r0)
        for (int c0 = 0; c0 < W; ++c0) {
            if (!m.at(r0, c0) || lab[size_t(r0) * W + c0]) continue;
            ++next;
            members.clear();
            stack.assign(1, r0 * W + c0);
            lab[size_t(r0) * W + c0] = next;
            int top = H, left = W, bottom = -1, right = -1;
            while (!stack.empty()) {
                int p = stack.back(); stack.pop_back();
                members.push_back(p);
                int r = p / W, c = p % W;
                top = std::min(top, r); bottom = std::max(bottom, r);
                left = std::min(left, c); right = std::max(right, c);
                for (int dr = -1; dr <= 1; ++dr)
                    for (int dc = -1; dc <= 1; ++dc) {
                        int rr = r + dr, cc = c + dc;
                        if (rr < 0 || cc < 0 || rr >= H || cc >= W) continue;
                        size_t q = size_t(rr) * W + cc;
                        if (m.at(rr, cc) && !lab[q]) { lab[q] = next; stack.push_back(int(q)); }
                    }
            }
            if (top == 0 || left == 0 || bottom == H - 1 || right == W - 1) continue;
            if (tile) {
                int uh = unit.rows(), uw = unit.cols();
                if (!(uh <= top && top < 2 * uh && uw <= left && left < 2 * uw)) continue;
            }
            int h = bottom - top + 1, w = right - left + 1;
            if (int(members.size()) < min_cells || h < 2 || w < 2) continue;
            Grid cells(h, w);
            for (int p : members) cells.at(p / W - top, p % W - left) = 1;
            Piece pc(chart, std::move(cells), top, left);
            if (unique && !seen.insert(pc.key()).second) continue;
            out.push_back(std::move(pc));
        }
    return out;
}

// ── similarity ──────────────────────────────────────────────────────────────

double iou(const Piece& pa, const Piece& pb, int S) {
    const Grid& a = pa.cells();
    const int ha = a.rows(), wa = a.cols();
    double best = 0.0;
    for (const Grid& b : pb.views()) {
        const int hb = b.rows(), wb = b.cols();
        const int H = std::max(ha, hb) + 2 * S, W = std::max(wa, wb) + 2 * S;
        for (int dy = 0; dy <= H - hb; ++dy) {
            if (std::abs(dy - S) > S + std::abs(ha - hb)) continue;
            for (int dx = 0; dx <= W - wb; ++dx) {
                if (std::abs(dx - S) > S + std::abs(wa - wb)) continue;
                // a sits at (S, S); b at (dy, dx)
                int inter = 0;
                const int r0 = std::max(S, dy), r1 = std::min(S + ha, dy + hb);
                const int c0 = std::max(S, dx), c1 = std::min(S + wa, dx + wb);
                for (int r = r0; r < r1; ++r)
                    for (int c = c0; c < c1; ++c) inter += a.at(r - S, c - S) & b.at(r - dy, c - dx);
                double v = double(inter) / double(pa.n() + pb.n() - inter);
                best = std::max(best, v);
            }
        }
    }
    return best;
}

bool Matcher::candidate(const Piece& a, const Piece& b) const {
    if (std::abs(a.short_side() - b.short_side()) > 1 || std::abs(a.long_side() - b.long_side()) > 1)
        return false;
    return !(std::abs(a.n() - b.n()) > (1 - match_) * std::max(a.n(), b.n()) * 1.2);
}

namespace {
template <class Fn>
void parallel_for(int n, int threads, Fn fn) {
    int t = threads > 0 ? threads : int(std::max(1u, std::thread::hardware_concurrency()));
    std::atomic<int> next{0};
    std::vector<std::thread> pool;
    for (int k = 0; k < t; ++k)
        pool.emplace_back([&, k] {
            for (int i; (i = next.fetch_add(1)) < n;) fn(i, k);
        });
    for (auto& th : pool) th.join();
}

// pieces bucketed by (short side, long side)
std::map<std::pair<int, int>, std::vector<int>> by_dims(const std::vector<Piece>& ps) {
    std::map<std::pair<int, int>, std::vector<int>> m;
    for (int i = 0; i < int(ps.size()); ++i) m[{ps[i].short_side(), ps[i].long_side()}].push_back(i);
    return m;
}

std::vector<Match> run(const std::vector<Piece>& L, const std::vector<Piece>& R, bool same,
                       const Matcher& M, double match, int shift, int threads) {
    auto buckets = by_dims(R);
    int t = threads > 0 ? threads : int(std::max(1u, std::thread::hardware_concurrency()));
    std::vector<std::vector<Match>> part(t);
    parallel_for(int(L.size()), t, [&](int i, int k) {
        const Piece& a = L[i];
        for (int dh = -1; dh <= 1; ++dh)
            for (int dw = -1; dw <= 1; ++dw) {
                auto it = buckets.find({a.short_side() + dh, a.long_side() + dw});
                if (it == buckets.end()) continue;
                for (int j : it->second) {
                    const Piece& b = R[j];
                    if (same && (j <= i || a.chart() == b.chart())) continue;
                    if (!M.candidate(a, b)) continue;
                    double s = a.key() == b.key() ? 1.0 : iou(a, b, shift);
                    if (s >= match) part[k].push_back({i, j, s});
                }
            }
    });
    std::vector<Match> out;
    for (auto& p : part) out.insert(out.end(), p.begin(), p.end());
    std::sort(out.begin(), out.end(), [](const Match& x, const Match& y) {
        return x.a != y.a ? x.a < y.a : x.b < y.b;
    });
    return out;
}
}  // namespace

std::vector<Match> Matcher::all_pairs(const std::vector<Piece>& ps) const {
    return run(ps, ps, true, *this, match_, shift_, threads_);
}

std::vector<Match> Matcher::cross_pairs(const std::vector<Piece>& L, const std::vector<Piece>& R) const {
    return run(L, R, false, *this, match_, shift_, threads_);
}

}  // namespace submotif
