# Sarpur records for the Sjónabók manuscripts

Everything [Sarpur](https://sarpur.is) (the Icelandic museums' shared catalogue)
holds that touches the Sjónabók manuscripts, collected 2026-11-25.
Low-confidence hits are kept on purpose, with a `confidence` column.

| File | One row per |
| --- | --- |
| `records.csv` | Sarpur record (407): confidence, reason, text, people, matched terms |
| `provenance.csv` | ownership step per manuscript, with `read_or_inferred` |
| `people.csv` | person record linked from a relevant item |
| `leads.csv` | relative or archive worth following up |
| `images.csv` | photo on Sarpur (193), with page/pattern match when known |
| `searches.csv` | query run against Sarpur's search index |
| `europeana.csv` | open-licence pattern sheet, book or sample on Europeana (1282 groups, Nordic and Baltic museums, collected 2026-11-27) |

`make sarpur` builds `sarpur/sarpur.sqlite` (one table per CSV, git-ignored),
plus a `sources` table made by `sources.py`.

## The `sources` table

One row per source with the same metadata, whatever it came from:
`collection` (manuscript, sarpur, book, europeana), `code`, `title`, `maker`,
`holder`, `country`, `date_label`, `year_from`, `year_to`, `place`, `lat`,
`lon`, `kind`, `licence`, `limits_extraction`, `record_url`, `image_url`,
`n_images`, `status`, `confidence`, `note`. It is built from
`gallery/map/manuscripts.csv` + `places.csv`, `sarpur/records.csv`,
`books/survey.csv` + `books.csv` + `library_terms.csv` and `sarpur/europeana.csv`,
so fix a value in those files, not in the database.

```r
library(DBI); library(dplyr)
con <- dbConnect(RSQLite::SQLite(), "sarpur/sarpur.sqlite")
tbl(con, "sources") |> count(collection, status)
```

## Europeana

Found through the Europeana API (`reusability=open&media=true`) with the terms
mönsterbok, mönsterblad, broderimönster, stickmönster, korsstygnsmönster, märkbok,
mønsterark, kirjontamalli and others. Records with the same object number and a
page suffix are one row (`images` = pages). Full metadata (date, maker, place,
description, medium, size) comes from each record; `year_from`/`year_to` are read
from the record date, or from the description when there is none (`year_how`).

`priority`: 1 = hand-drawn counted chart, digitise first; 2 = hand-drawn or
stitched, worth checking; 3 = printed 20th-century chart or not yet looked at;
4 = not a counted chart. Notes to keep in mind:

- Göteborgs stadsmuseum `stickmönster` are Bohus Stickning charts (1939-1969) by
  named designers; the photos are CC BY but the designs may still be in copyright
  (`limits_extraction` = check).
- Craft Museum of Finland `kirjontamalli` are dated 1965-1969 on the record:
  modern model cloths, possibly of older patterns.
- Lithuanian and Latvian hits for "raštų knyga"/"rakstu grāmata" and Finnish
  "mallikirja" were archive registers and furniture drawings, and are left out.

Confidence: `core` = one of the 9 source manuscripts; `high` = text mentions
sjónabók or its publications; `medium` / `medium-low` = names an owner, place or
manuscript number (National Museum / other museum; many are name collisions,
see `note`); `low` = only a broad term matched.

`description_kind` says whether the text is verbatim from Sarpur or our summary.

Photos belong to the museums. Sarpur's [terms](https://sarpur.is/en/terms) allow
private non-commercial use and social posts with credit and a link; anything else
needs permission (ljosmyndasafn@thjodminjasafn.is). So `images.csv` stores URLs only.
