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

`make sarpur` builds `sarpur/sarpur.sqlite` (one table per CSV, git-ignored).

Confidence: `core` = one of the 9 source manuscripts; `high` = text mentions
sjónabók or its publications; `medium` / `medium-low` = names an owner, place or
manuscript number (National Museum / other museum; many are name collisions,
see `note`); `low` = only a broad term matched.

`description_kind` says whether the text is verbatim from Sarpur or our summary.

Photos belong to the museums. Sarpur's [terms](https://sarpur.is/en/terms) allow
private non-commercial use and social posts with credit and a link; anything else
needs permission (ljosmyndasafn@thjodminjasafn.is). So `images.csv` stores URLs only.
