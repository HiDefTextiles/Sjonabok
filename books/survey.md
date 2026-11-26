# Survey of known pattern books

`survey.csv` lists every early pattern book we know of, whether or not we can use it.
It starts from Arthur Lotz's *Bibliographie der Modelbücher* (1933, 2nd ed. 1963), as summarised
in the class list by Hastings Sanderson and Helen Hough, and Hough's *Early Modern Embroidery
and Lace Pattern Books: 2017 Index*, which records which titles were online and where. Both are
on the Internet Archive (`emel-pattern-books-cataloged-by-lotz`, `Hough2017EarlyModernCEPR`). We
then checked Hough's Internet Archive collection `early-modern-embroidery-and-lace-pattern-books`
(308 items, Nov 2026) for books that have come online since 2017, and added a few books outside
Lotz (manuscripts, 18th-19th century, Danish holdings).

One row per title (Lotz class), at its first known edition. Columns:

| column | meaning |
|---|---|
| code | our id; same as `books.csv` when the book is in the gallery |
| lotz | Lotz class number (blank for books outside Lotz) |
| first_year, place, country, region, lat, lon | first edition per Lotz; blank place = not known to us |
| kind | printed, manuscript or collection |
| technique | rough guess: charted (counted grid, fits our 0/1 charts), mixed, lace (cut-work, reticella, bobbin lace) or freehand |
| status | `digitised`, `in_progress`, `open_scan` (scan we may use, not digitised), `ask_access` (holder known, we must ask or need a subscription), `out_of_reach` (no scan found; Hough 2017 says "not yet located online") |
| charts | charts in `patterns/books` for digitised books |
| pages | image count of the scan, when the Internet Archive record gives one |
| scan_holder, scan_url | the best copy we found; Internet Archive links mirror the holder's scan |
| contact | who to ask, for `ask_access` rows |

`library_terms.csv` records each holder's terms of use and whether they limit our use. We publish
only extracted 0/1 grids (CC BY 4.0), never the scans, but we flag terms that restrict reuse
(non-commercial, rights reserved, subscription). `verified` says whether the terms were checked
on the holder's site or a Europeana record in this survey, or still need checking.

The map and timeline (`make books-map`) show all rows with a three-way switch: charts we hold,
open scans not yet digitised, and metadata only.
