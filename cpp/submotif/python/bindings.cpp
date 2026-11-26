// Python module `submotif` (pybind11): the C++ matcher on numpy charts.
//
//   import submotif
//   ps = submotif.find_pieces(chart_bool_array, "name", tile=False, min_cells=10)
//   submotif.iou(ps[0], ps[1], shift=1)
//   pairs = submotif.Matcher(match=0.8, shift=1).all_pairs(pieces)   # [(i, j, iou)]
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "submotif.hpp"

namespace py = pybind11;
using namespace submotif;

static Grid to_grid(py::array_t<uint8_t, py::array::c_style | py::array::forcecast> a) {
    if (a.ndim() != 2) throw std::invalid_argument("chart must be a 2-d array");
    std::vector<uint8_t> v(a.data(), a.data() + a.size());
    for (auto& x : v) x = x != 0;
    return Grid(int(a.shape(0)), int(a.shape(1)), std::move(v));
}

static py::array_t<uint8_t> to_array(const Grid& g) {
    py::array_t<uint8_t> a({g.rows(), g.cols()});
    std::copy(g.data().begin(), g.data().end(), a.mutable_data());
    return a;
}

static py::list matches(const std::vector<Match>& ms) {
    py::list out;
    for (auto& m : ms) out.append(py::make_tuple(m.a, m.b, m.iou));
    return out;
}

PYBIND11_MODULE(submotif, m) {
    m.doc() = "Whole figures in 0/1 charts and their similarity (C++, same rules as books/travel.py)";
    py::class_<Piece>(m, "Piece")
        .def(py::init([](std::string chart, py::array_t<uint8_t, py::array::c_style | py::array::forcecast> a,
                         int row, int col) { return Piece(chart, to_grid(a), row, col); }),
             py::arg("chart"), py::arg("cells"), py::arg("row") = 0, py::arg("col") = 0)
        .def_property_readonly("chart", &Piece::chart)
        .def_property_readonly("n", &Piece::n)
        .def_property_readonly("row", &Piece::row)
        .def_property_readonly("col", &Piece::col)
        .def_property_readonly("key", [](const Piece& p) { return py::bytes(p.key()); })
        .def_property_readonly("cells", [](const Piece& p) { return to_array(p.cells()); })
        .def("__repr__", [](const Piece& p) {
            return "<Piece " + p.chart() + " " + std::to_string(p.cells().rows()) + "x" +
                   std::to_string(p.cells().cols()) + " n=" + std::to_string(p.n()) + ">";
        });
    m.def("find_pieces",
          [](py::array_t<uint8_t, py::array::c_style | py::array::forcecast> a, std::string chart, bool tile,
             int min_cells, bool unique) { return find_pieces(to_grid(a), chart, tile, min_cells, unique); },
          py::arg("chart"), py::arg("name") = "", py::arg("tile") = false, py::arg("min_cells") = 10,
          py::arg("unique") = true);
    m.def("iou", &iou, py::arg("a"), py::arg("b"), py::arg("shift") = 1);
    py::class_<Matcher>(m, "Matcher")
        .def(py::init<double, int, int>(), py::arg("match") = 0.8, py::arg("shift") = 1, py::arg("threads") = 0)
        .def("all_pairs", [](const Matcher& M, const std::vector<Piece>& ps) {
            std::vector<Match> r; { py::gil_scoped_release g; r = M.all_pairs(ps); } return matches(r); })
        .def("cross_pairs", [](const Matcher& M, const std::vector<Piece>& a, const std::vector<Piece>& b) {
            std::vector<Match> r; { py::gil_scoped_release g; r = M.cross_pairs(a, b); } return matches(r); })
        .def("candidate", &Matcher::candidate);
}
