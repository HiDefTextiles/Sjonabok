"""Build a static documentation gallery for one Sjonabok data repository."""

import argparse
import csv
import shutil
import sys
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import quote

TEMPLATE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEMPLATE_DIR.parent))

from pattern_processing.pattern_to_png import convert_txt_to_png


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build(dataset, output, repository):
    books = read_csv(dataset / "books/books.csv")
    if len(books) != 1:
        raise ValueError("Expected exactly one source record in books/books.csv")
    book = books[0]
    charts = {row["name"]: row for row in read_csv(dataset / "books/charts.csv")}
    patterns = sorted((dataset / "patterns/books").glob("*.txt"))
    if not patterns:
        raise ValueError("No text grids found under patterns/books")

    previews = output / "previews"
    previews.mkdir(parents=True, exist_ok=True)
    for stale in previews.glob("*.png"):
        stale.unlink()

    cards = []
    for grid in patterns:
        filename = f"{grid.stem}.png"
        convert_txt_to_png(grid, previews / filename, None, None)
        chart = charts.get(grid.stem, {})
        plate = f"Plate {chart['plate']}" if chart.get("plate") else ""
        status = chart.get("status", "")
        detail = escape(" · ".join(part for part in (plate, status) if part))
        raw_url = f"{repository}/blob/main/patterns/books/{quote(grid.name)}"
        preview_url = f"previews/{quote(filename)}"
        name = escape(grid.stem)
        cards.append(f"""<article class="card">
  <a class="preview" href="{preview_url}" aria-label="View {name} preview">
    <img src="{preview_url}" alt="Grid for {name}" loading="lazy">
  </a>
  <div class="caption">
    <a href="{escape(raw_url, quote=True)}">{name}</a>
    <p>{detail}</p>
  </div>
</article>""")

    fields = (
        ("Author", book["author"]),
        ("Edition", ", ".join(value for value in (book["place"], book["year"]) if value)),
        ("Collection", book["holder"]),
        ("Accession", book["accession"]),
        ("Rights", book["rights"]),
        ("Coverage", book["status"]),
    )
    metadata = "\n".join(
        f"<div><dt>{label}</dt><dd>{escape(value)}</dd></div>"
        for label, value in fields if value
    )
    document = Template((TEMPLATE_DIR / "index.html").read_text(encoding="utf-8"))
    (output / "index.html").write_text(document.substitute(
        title=escape(book["title"]),
        count=len(patterns),
        metadata=metadata,
        source=escape(book["record_url"], quote=True),
        repository=escape(repository, quote=True),
        cards="\n".join(cards),
    ), encoding="utf-8")
    shutil.copyfile(TEMPLATE_DIR / "style.css", output / "style.css")
    (output / ".nojekyll").touch()
    return len(patterns)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    print(f"Built {build(args.dataset, args.output, args.repository)} previews")
