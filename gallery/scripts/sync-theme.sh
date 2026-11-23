#!/bin/sh
# Copy the HÍ look from the main HiDef textíll site so both sites match.
# Usage: sh gallery/scripts/sync-theme.sh   (run from the repository root)
set -eu
base=https://raw.githubusercontent.com/HiDefTextiles/hidefTextiles.github.io/main
dir=gallery
for f in styles/hi-site.scss styles/hidef.scss styles/hi-watermark.css \
         img/hi/favicon.svg img/hi/hi_logo.svg img/hi/hi_named_logo-en.svg; do
  curl -fsSL "$base/$f" -o "$dir/$f"
  echo "updated $dir/$f"
done
