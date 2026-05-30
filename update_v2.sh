#!/bin/bash
# Product Radar v2 - One-command: scan + generate + push
set -e
cd /home/lee/product-radar

echo "🔍 Starting v2 scan..."
python3 run_scan_v2.py

echo ""
echo "📦 Deploying to GitHub Pages..."
git add data/ output/ -f
git diff --cached --quiet && echo "No changes to commit" && exit 0
git commit -m "v2 scan $(date -u '+%Y-%m-%d %H:%M')"
git pull --rebase 2>/dev/null || true
git push

echo ""
echo "✅ Done! Visit https://liyuhong168.github.io/product-radar/v2.html"
