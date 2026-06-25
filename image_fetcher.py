#!/usr/bin/env python3
"""
Image Fetcher — Fetch product images from Amazon UK for radar products.

For each ASIN:
- Try ScraperAPI to scrape the product page and extract the main image
- Fallback: construct image URL from ASIN pattern
- Update radar JSON files with discovered image URLs

Usage:
    python3 image_fetcher.py --backfill
    python3 image_fetcher.py --asin B0ABC12345 B0DEF67890
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
SCRAPERAPI_KEY_FILE = Path.home() / ".hermes" / "scraperapi_key.txt"
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")


def _get_scraperapi_key():
    """Read ScraperAPI key if available."""
    if SCRAPERAPI_KEY_FILE.exists():
        key = SCRAPERAPI_KEY_FILE.read_text().strip()
        if key:
            return key
    return None


def _fetch_page_via_scraperapi(url, api_key):
    """Fetch a page via ScraperAPI. Returns HTML or empty string."""
    api_url = (f"http://api.scraperapi.com?api_key={api_key}"
               f"&url={urllib.parse.quote(url)}&country_code=gb")
    try:
        req = urllib.request.Request(api_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    ScraperAPI error: {e}", file=sys.stderr)
        return ""


def _extract_image_from_html(html):
    """Extract the main product image URL from Amazon product page HTML."""
    # Method 1: landingImage src or data-old-hires
    m = re.search(r'id="landingImage"[^>]*data-old-hires="([^"]+)"', html)
    if m:
        return m.group(1)

    m = re.search(r'id="landingImage"[^>]*src="([^"]+)"', html)
    if m:
        return m.group(1)

    # Method 2: data-old-hires anywhere
    m = re.search(r'data-old-hires="(https://[^"]+images[^"]+)"', html)
    if m:
        return m.group(1)

    # Method 3: imgTagWrapperId
    m = re.search(r'id="imgTagWrapperId"[^>]*>.*?<img[^>]*src="([^"]+)"', html, re.DOTALL)
    if m:
        return m.group(1)

    # Method 4: main image in the standard block
    m = re.search(r'"hiRes":"(https://[^"]+images[^"]+)"', html)
    if m:
        return m.group(1)

    # Method 5: Look for large product images
    m = re.search(r'"large":"(https://[^"]+images[^"]+)"', html)
    if m:
        return m.group(1)

    # Method 6: Any amazon image in the main image area
    m = re.search(r'(https://m\.media-amazon\.com/images/I/[^"]+\._AC_SL\d+_[^"]+)', html)
    if m:
        return m.group(1)

    return None


def _construct_image_url_from_asin(asin):
    """Construct a best-guess image URL from ASIN.
    This doesn't always work but is a reasonable fallback."""
    return f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg"


def _fetch_image_via_anysearch(asin):
    """Try to find image URL via AnySearch."""
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search",
             f"Amazon UK {asin} product image",
             "--domain", "ecommerce", "--max_results", "3", "--zone", "intl"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            text = result.stdout.strip()
            # Look for amazon image URLs in results
            m = re.search(r'(https://m\.media-amazon\.com/images/I/[^"\s]+\._AC_[^"\s]+)', text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def fetch_product_images(asin_list):
    """Fetch product images for a list of ASINs.

    Args:
        asin_list: list of ASIN strings

    Returns:
        dict mapping asin -> image_url (None if not found)
    """
    api_key = _get_scraperapi_key()
    results = {}

    for asin in asin_list:
        asin = asin.strip().upper()
        if not asin:
            continue

        image_url = None

        # Strategy 1: ScraperAPI
        if api_key:
            print(f"  [{asin}] Fetching via ScraperAPI...", file=sys.stderr)
            url = f"https://www.amazon.co.uk/dp/{asin}"
            html = _fetch_page_via_scraperapi(url, api_key)
            if html:
                image_url = _extract_image_from_html(html)
                if image_url:
                    print(f"  [{asin}] ✓ Found image via ScraperAPI", file=sys.stderr)
                else:
                    print(f"  [{asin}] No image in page HTML", file=sys.stderr)
            time.sleep(1)  # Rate limit

        # Strategy 2: AnySearch
        if not image_url:
            print(f"  [{asin}] Trying AnySearch...", file=sys.stderr)
            image_url = _fetch_image_via_anysearch(asin)
            if image_url:
                print(f"  [{asin}] ✓ Found image via AnySearch", file=sys.stderr)

        # Strategy 3: Construct URL from ASIN
        if not image_url:
            image_url = _construct_image_url_from_asin(asin)
            print(f"  [{asin}] Using constructed URL (may not work)", file=sys.stderr)

        results[asin] = image_url

    return results


def _find_latest_radar_file():
    """Find the latest radar scan JSON file."""
    channels_dir = BASE / "data" / "channels"
    if not channels_dir.exists():
        return None
    files = sorted(channels_dir.glob("*.json"), reverse=True)
    for f in files:
        if "rejected" in f.name or "trends" in f.name:
            continue
        try:
            data = json.loads(f.read_text())
            if "products" in data:
                return f
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def _find_all_radar_files():
    """Find all radar scan JSON files."""
    channels_dir = BASE / "data" / "channels"
    if not channels_dir.exists():
        return []
    files = []
    for f in sorted(channels_dir.glob("*.json"), reverse=True):
        if "rejected" in f.name or "trends" in f.name:
            continue
        try:
            data = json.loads(f.read_text())
            if "products" in data:
                files.append(f)
        except (json.JSONDecodeError, KeyError):
            continue
    return files


def backfill_radar_images():
    """Read radar scan JSON, find products without image_url, fetch images, update JSON.

    Returns:
        dict with stats: total, updated, failed
    """
    radar_files = _find_all_radar_files()
    if not radar_files:
        print("No radar scan files found.", file=sys.stderr)
        return {"total": 0, "updated": 0, "failed": 0}

    total_missing = 0
    total_updated = 0
    total_failed = 0

    for radar_file in radar_files:
        data = json.loads(radar_file.read_text())
        products = data.get("products", [])

        # Find products without image_url
        missing = []
        for p in products:
            img = p.get("image_url", "")
            if not img or img.strip() == "":
                if p.get("asin"):
                    missing.append(p["asin"])

        if not missing:
            print(f"  {radar_file.name}: all products have images", file=sys.stderr)
            continue

        total_missing += len(missing)
        print(f"  {radar_file.name}: {len(missing)} products missing images", file=sys.stderr)

        # Fetch images
        image_map = fetch_product_images(missing)

        # Update products
        updated = 0
        for p in products:
            asin = p.get("asin", "")
            if asin in image_map and image_map[asin]:
                p["image_url"] = image_map[asin]
                updated += 1

        # Save back
        if updated > 0:
            data["image_backfill_ts"] = datetime.now().isoformat(timespec="seconds")
            radar_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"  {radar_file.name}: updated {updated} products", file=sys.stderr)

        total_updated += updated
        total_failed += len(missing) - updated

    return {
        "total_missing": total_missing,
        "updated": total_updated,
        "failed": total_failed,
        "files_processed": len(radar_files),
    }


def _print_asin_results(asin_list, results):
    """Print results for direct ASIN fetch."""
    print(f"\n{'='*60}")
    print(f"  IMAGE FETCH RESULTS")
    print(f"{'='*60}")
    for asin in asin_list:
        url = results.get(asin.upper(), results.get(asin, None))
        if url:
            print(f"  ✅ {asin}: {url[:80]}")
        else:
            print(f"  ❌ {asin}: not found")
    print()


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        print("=== Backfilling radar images ===", file=sys.stderr)
        stats = backfill_radar_images()
        print(f"\nBackfill complete:", file=sys.stderr)
        print(f"  Missing: {stats['total_missing']}", file=sys.stderr)
        print(f"  Updated: {stats['updated']}", file=sys.stderr)
        print(f"  Failed:  {stats['failed']}", file=sys.stderr)
        print(f"  Files:   {stats['files_processed']}", file=sys.stderr)
        print(json.dumps(stats, indent=2))

    elif "--asin" in sys.argv:
        idx = sys.argv.index("--asin")
        asins = sys.argv[idx + 1:]
        if not asins:
            print("Usage: python3 image_fetcher.py --asin B0ABC12345 B0DEF67890", file=sys.stderr)
            sys.exit(1)
        results = fetch_product_images(asins)
        _print_asin_results(asins, results)
        print(json.dumps(results, indent=2))

    else:
        print("Usage:")
        print("  python3 image_fetcher.py --backfill")
        print("  python3 image_fetcher.py --asin B0ABC12345 B0DEF67890")
        sys.exit(1)
