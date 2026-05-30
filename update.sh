#!/bin/bash
# Product Radar - Local scan + deploy
# Run this locally to scan and push results to GitHub Pages
set -e
cd /home/lee/product-radar

echo "[1/3] Running scan..."
python3 run_scan.py > /dev/null 2>&1

echo "[2/3] Generating HTML..."
python3 generate_html.py

echo "[3/3] Pushing to GitHub..."
git add data/ output/ -f
git diff --cached --quiet && echo "No changes" && exit 0
git commit -m "auto-update $(date -u '+%Y-%m-%d %H:%M')"
git push

echo "Done! https://liyuhong168.github.io/product-radar/"
