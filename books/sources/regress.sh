#!/bin/sh
# regress.sh [REV] : read every scan in books/scans with the readers as they
# were at REV (default: de39acd, PR #46) and as they are now, and compare
# every output file byte for byte (<chart>.txt, <page>.json, <page>_check.jpg).
# Needs the scans (books/fetch.py, or a copy in books/scans/<book>/).
set -e
rev=${1:-de39acd}
tmp=${TMPDIR:-/tmp}/sources-regress.$$
mkdir -p "$tmp/old"
git show "$rev:books/digitise.py" > "$tmp/old/digitise.py"
git show "$rev:books/woodcut.py"  > "$tmp/old/woodcut.py"

layout() {   # the layout books.csv gives a book (its "kind")
    python3 -c "import sys; sys.path.insert(0, 'books')
from sources import Provenance, layout_for
print(layout_for(Provenance.lookup('$1')))"
}

run() {   # run <dir with digitise.py and woodcut.py> <out>
    for f in books/scans/*/*.webp; do
        book=$(basename "$(dirname "$f")"); page=$(basename "$f" .webp)
        mkdir -p "$2/$book"
        case $(layout "$book") in
            woodcut) tool=woodcut.py ;;
            *)       tool=digitise.py ;;
        esac
        python3 -W ignore "$1/$tool" "$f" "$2/$book" > "$2/$book/$page.json"
    done
}
run "$tmp/old" "$tmp/a"
run books      "$tmp/b"
n=$(find "$tmp/a" -type f | wc -l)
if diff -r "$tmp/a" "$tmp/b" > "$tmp/diff.txt"; then
    echo "identical: $n files"; rm -rf "$tmp"
else
    echo "DIFFERENT (see $tmp/diff.txt):"; head "$tmp/diff.txt"; exit 1
fi
