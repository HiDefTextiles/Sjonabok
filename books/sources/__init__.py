"""Readers for scanned pattern books, one class per scan layout.

    from books.sources import open_source
    src = open_source("books/scans/sib1597/DP363474.webp", book="sib1597")
    for chart in src.charts():
        chart.cells, chart.meta, chart.provenance

Layouts (PatternSource subclasses):
    ruled     RuledGridSource         printed ruled grid, a mark per filled cell
    woodcut   WhiteLineWoodcutSource  black block, empty cells cut out white
    symbols   MultiSymbolPlateSource  ruled grid, several kinds of mark
    drawing   LineDrawingSource       free line drawing, grid chosen by us

With book= and no layout=, the layout comes from the book's "kind" in
books/books.csv (etching/engraving -> ruled, woodcut -> woodcut), unless
the book's code is listed in LAYOUT_BY_BOOK.
"""
from .base import Chart, PatternSource, Provenance, CHART_LICENCE, CREDIT
from .ruled import RuledGridSource
from .woodcut import WhiteLineWoodcutSource
from .symbols import MultiSymbolPlateSource
from .drawing import LineDrawingSource

LAYOUTS = {cls.layout: cls for cls in
           (RuledGridSource, WhiteLineWoodcutSource, MultiSymbolPlateSource, LineDrawingSource)}

# books whose layout the "kind" column does not tell (add as books arrive)
LAYOUT_BY_BOOK = {}


def layout_for(prov: Provenance | None) -> str:
    if prov is None:
        return "ruled"
    if prov.book in LAYOUT_BY_BOOK:
        return LAYOUT_BY_BOOK[prov.book]
    kind = prov.kind.lower()
    if "woodcut" in kind:
        return "woodcut"
    if "cross-stitch" in kind or "symbol" in kind:
        return "symbols"
    if "drawing" in kind:
        return "drawing"
    return "ruled"


def open_source(path, book=None, layout=None, **options) -> PatternSource:
    prov = Provenance.lookup(book) if book else None
    cls = LAYOUTS[layout or layout_for(prov)]
    return cls(path, provenance=prov, **options)


__all__ = ["Chart", "PatternSource", "Provenance", "RuledGridSource", "WhiteLineWoodcutSource",
           "MultiSymbolPlateSource", "LineDrawingSource", "LAYOUTS", "open_source", "layout_for",
           "CHART_LICENCE", "CREDIT"]
