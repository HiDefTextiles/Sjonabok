#!/usr/bin/env python3
"""Download the museum scans listed in books/images.csv into books/scans/
(git-ignored). The Met serves its public-domain images openly.

usage: fetch.py [--book sib1597] [--scale 0.75]
Scans are stored as greyscale WebP at 0.75 of the original size: the size
the committed charts were read from (digitise.py expects it).
"""
import argparse, csv, io, urllib.request
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book"); ap.add_argument("--scale", type=float, default=0.75)
    a = ap.parse_args()
    with open(HERE / "images.csv", newline="") as f:
        rows = [r for r in csv.DictReader(f) if not a.book or r["book"] == a.book]
    for r in rows:
        out = HERE / "scans" / r["book"] / f"{r['image']}.webp"
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(r["url"], headers={"User-Agent": "sjonabok-books/1.0"})
        im = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=60).read())).convert("L")
        im = im.resize((round(im.width * a.scale), round(im.height * a.scale)), Image.LANCZOS)
        im.save(out, "WEBP", quality=80)
        print(out)


if __name__ == "__main__":
    main()
