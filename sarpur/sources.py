#!/usr/bin/env python3
"""One `sources` table with the same metadata for every source we hold or know of.

Each Source subclass reads one committed CSV and maps it to the shared columns
(COLUMNS). build_db.py loads the result into sarpur.sqlite as table `sources`.
"""
import csv
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

COLUMNS = [
    "source_id", "collection", "code", "title", "maker", "holder", "country",
    "date_label", "year_from", "year_to", "place", "lat", "lon", "kind",
    "licence", "limits_extraction", "record_url", "image_url", "n_images",
    "status", "confidence", "note",
]

SARPUR_TERMS = ("Sarpur terms: private non-commercial use and credited social posts; "
                "other use needs permission (ljosmyndasafn@thjodminjasafn.is)")


def read(path):
    with open(ROOT / path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ms_code(label):
    """'Þjms. Th 116' -> 'thjmsth116', 'Þjms. 1105' -> 'thjms1105' (records.csv style)."""
    return re.sub(r"[\s._]", "", label.replace("Þjms", "thjms")).lower()


class Source:
    collection = ""

    def rows(self):
        raise NotImplementedError

    def row(self, **kw):
        r = dict.fromkeys(COLUMNS, "")
        r.update({k: ("" if v is None else str(v)) for k, v in kw.items()})
        r["collection"] = self.collection
        r["source_id"] = f"{self.collection}:{r['code']}"
        return r


class Manuscripts(Source):
    """The ten source manuscripts (gallery/map)."""
    collection = "manuscript"
    NATMUS = {"N.453.a": ("https://samlinger.natmus.dk/dnt/object/269655",
                          "Photos CC BY-SA (Nationalmuseet); manuscript public domain")}

    def rows(self):
        first = {}
        for p in read("gallery/map/places.csv"):
            first.setdefault(p["id"], p)
        imgs = {}
        for r in read("sarpur/records.csv"):
            if r["confidence"] == "core":
                imgs[ms_code(r["manuscript_code"])] = r
        for m in read("gallery/map/manuscripts.csv"):
            p = first.get(m["id"], {})
            rec = imgs.get(ms_code(m["id"]), {})
            url, lic = self.NATMUS.get(m["id"], (rec.get("url") or p.get("url", ""),
                                                 "Manuscript public domain; photos " + SARPUR_TERMS))
            yield self.row(code=m["id"], title=rec.get("title") or "Sjónabók", maker=m["who"],
                           holder=m["repository"], country=m["country"], date_label=m["when_label"],
                           year_from=m["when_start"], year_to=m["when_end"], place=m["where"],
                           lat=p.get("lat"), lon=p.get("lon"), kind="manuscript pattern book (hand-drawn)",
                           licence=lic, limits_extraction="no", record_url=url,
                           n_images=rec.get("n_images"), status="digitised",
                           confidence=m["confidence"], note=m["source"])


class SarpurRecords(Source):
    """Every Sarpur record found in the crawl, core to low confidence."""
    collection = "sarpur"

    def rows(self):
        for r in read("sarpur/records.csv"):
            yield self.row(code=r["oid"], title=r["title"], maker=r["people_on_record"],
                           holder=r["museum"], country="Iceland", date_label=r["dates"],
                           year_from=r["year_from"], year_to=r["year_to"], kind=r["description_kind"] and "museum record",
                           licence=SARPUR_TERMS, limits_extraction="ask", record_url=r["url"],
                           n_images=r["n_images"], status="record", confidence=r["confidence"],
                           note=r["confidence_reason"] + (f" | manuscript {r['manuscript_code']}" if r["manuscript_code"] else ""))


class Books(Source):
    """Printed European pattern books: books.csv where held, survey.csv for the rest."""
    collection = "book"

    def rows(self):
        terms = {t["holder"]: t for t in read("books/library_terms.csv")}
        books = {b["code"]: b for b in read("books/books.csv")}
        for s in read("books/survey.csv"):
            b = books.pop(s["code"], {})
            holder = b.get("holder") or s["scan_holder"]
            t = terms.get(holder, {})
            yield self.row(code=s["code"], title=b.get("title") or s["title"],
                           maker=b.get("author") or s["creator"], holder=holder,
                           country=b.get("country") or s["country"],
                           date_label=b.get("year") or s["first_year"],
                           year_from=b.get("year") or s["first_year"], year_to=b.get("year") or s["first_year"],
                           place=b.get("place") or s["place"], lat=b.get("lat") or s["lat"],
                           lon=b.get("lon") or s["lon"], kind=b.get("kind") or f"{s['kind']} ({s['technique']})",
                           licence=b.get("rights") or t.get("terms"),
                           limits_extraction=t.get("limits_extraction"),
                           record_url=b.get("record_url") or s["scan_url"],
                           n_images=s["pages"], status=s["status"],
                           note=(b.get("notes") or s["notes"])[:300])
        for code, b in books.items():  # in books.csv but not in the survey
            yield self.row(code=code, title=b["title"], maker=b["author"], holder=b["holder"],
                           country=b["country"], date_label=b["year"], year_from=b["year"],
                           year_to=b["year"], place=b["place"], lat=b["lat"], lon=b["lon"],
                           kind=b["kind"], licence=b["rights"], record_url=b["record_url"],
                           status=b["status"], note=b["notes"][:300])


class Europeana(Source):
    """Nordic and Baltic pattern sheets, books and samples found on Europeana."""
    collection = "europeana"

    def rows(self):
        for e in read("sarpur/europeana.csv"):
            yield self.row(code=e["europeana_id"].lstrip("/"), title=e["title"], maker=e["creator"],
                           holder=e["museum"], country=e["country"], date_label=e["date"],
                           year_from=e["year_from"], year_to=e["year_to"], place=e["place"],
                           lat=e["lat"], lon=e["lon"], kind=e["type"], licence=e["licence"],
                           limits_extraction="check" if "Bohus" in e["type"] else "no",
                           record_url=e["record_url"] or e["europeana_url"], image_url=e["image_url"],
                           n_images=e["images"], status="candidate", confidence=f"priority {e['priority']}",
                           note=e["note"])


SOURCES = [Manuscripts(), SarpurRecords(), Books(), Europeana()]


def all_rows():
    for s in SOURCES:
        yield from s.rows()


if __name__ == "__main__":
    import collections
    print(collections.Counter(r["collection"] for r in all_rows()))
