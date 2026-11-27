#!/usr/bin/env python3
"""Build sarpur.sqlite from the sarpur/*.csv files (one table per csv), plus a
shared `sources` table built by sources.py.

The CSVs are the source of truth and are committed; the database is
rebuilt with `make sarpur` and is git-ignored.
"""
import csv
import pathlib
import sqlite3
import sys

from sources import COLUMNS, all_rows


class SarpurDB:
    def __init__(self, folder: pathlib.Path, db: pathlib.Path):
        self.folder, self.db = folder, db

    def tables(self):
        return sorted(self.folder.glob("*.csv"))

    def load(self, con, path):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        head, body = rows[0], rows[1:]
        name = path.stem
        cols = ", ".join(f'"{c}" TEXT' for c in head)
        con.execute(f'DROP TABLE IF EXISTS "{name}"')
        con.execute(f'CREATE TABLE "{name}" ({cols})')
        con.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" * len(head))})', body)
        return name, len(body)

    def build(self):
        self.db.unlink(missing_ok=True)
        with sqlite3.connect(self.db) as con:
            for p in self.tables():
                name, n = self.load(con, p)
                print(f"{name}: {n} rows")
            self.load_sources(con)
            con.execute("CREATE INDEX idx_records_conf ON records(confidence)")
            con.execute("CREATE INDEX idx_images_oid ON images(oid)")
            con.execute("CREATE INDEX idx_sources_coll ON sources(collection)")
            con.execute("CREATE INDEX idx_europeana_prio ON europeana(priority)")

    def load_sources(self, con):
        """Shared metadata table over manuscripts, Sarpur, books and Europeana (sources.py)."""
        rows = list(all_rows())
        cols = ", ".join(f'"{c}" TEXT' for c in COLUMNS)
        con.execute(f"CREATE TABLE sources ({cols})")
        con.executemany(f"INSERT INTO sources VALUES ({','.join('?' * len(COLUMNS))})",
                        [[r[c] for c in COLUMNS] for r in rows])
        print(f"sources: {len(rows)} rows")


if __name__ == "__main__":
    here = pathlib.Path(__file__).parent
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else here / "sarpur.sqlite"
    SarpurDB(here, out).build()
