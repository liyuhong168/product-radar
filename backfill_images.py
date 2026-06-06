#!/usr/bin/env python3
"""Backfill image_url for existing products by re-fetching Amazon pages."""
import json, re, sys, glob
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from sources.amazon_uk import _curl_fetch, _parse_amazon_page

def backfill():
    # Collect all ASINs that need images
    data_dir = BASE / "data" / "channels"
    asins_needed = {}  # asin -> list of file paths containing it
    
    for f in sorted(glob.glob(str(data_dir / "*.json"))):
        if "-rejected" in f or "-trends" in f:
            continue
        data = json.load(open(f))
        products = data if isinstance(data, list) else data.get("passed", data.get("products", []))
        for p in products:
            if not p.get("image_url"):
                asins_needed.setdefault(p["asin"], []).append(f)
    
    if not asins_needed:
        print("All products already have image_url!")
        return
    
    print(f"Need images for {len(asins_needed)} ASINs across {len(set(sum(asins_needed.values(), [])))} files")
    
    # Fetch a search page to get image URLs
    # Try multiple search queries to cover all ASINs
    image_map = {}  # asin -> image_url
    
    search_queries = [
        "https://www.amazon.co.uk/s?k=kitchen+accessories&rh=n%3A2908338031",
        "https://www.amazon.co.uk/s?k=car+accessories&rh=n%3A11052591",
        "https://www.amazon.co.uk/s?k=home+decor&rh=n%3A11052591",
        "https://www.amazon.co.uk/s?k=diy+tools&rh=n%3A3026269031",
        "https://www.amazon.co.uk/s?k=garden+accessories",
        "https://www.amazon.co.uk/s?k=pet+supplies",
        "https://www.amazon.co.uk/s?k=phone+accessories",
        "https://www.amazon.co.uk/s?k=travel+accessories",
        "https://www.amazon.co.uk/s?k=party+supplies",
    ]
    
    for url in search_queries:
        if len(image_map) >= len(asins_needed):
            break
        print(f"  Scanning: {url[:60]}...")
        html = _curl_fetch(url)
        if not html:
            continue
        # Extract image URLs from the HTML
        blocks = re.split(r'data-asin="([A-Z0-9]{10})"', html)
        for i in range(1, len(blocks) - 1, 2):
            asin = blocks[i]
            block = blocks[i + 1]
            if asin in asins_needed and asin not in image_map:
                img_match = re.search(r'src="(https?://[^"]*amazon\.com/images/I/[^"]+)"', block)
                if img_match:
                    image_map[asin] = img_match.group(1)
                    print(f"    Found image for {asin}")
    
    # Also try product pages directly for missing ones
    for asin in list(asins_needed.keys()):
        if asin in image_map:
            continue
        print(f"  Fetching product page: {asin}...")
        html = _curl_fetch(f"https://www.amazon.co.uk/dp/{asin}")
        if html:
            m = re.search(r'og:image.*?content="([^"]+)"', html)
            if m:
                image_map[asin] = m.group(1)
                print(f"    Found og:image for {asin}")
            else:
                m2 = re.search(r'<img[^>]*src="(https?://m\.media-amazon\.com/images/[^"]+)"', html)
                if m2:
                    image_map[asin] = m2.group(1)
                    print(f"    Found img for {asin}")
    
    print(f"\nFound images for {len(image_map)}/{len(asins_needed)} ASINs")
    
    # Update all data files
    updated_files = set()
    for asin, files in asins_needed.items():
        if asin not in image_map:
            continue
        for f in files:
            if f in updated_files:
                continue
            data = json.load(open(f))
            products = data if isinstance(data, list) else data.get("passed", data.get("products", []))
            for p in products:
                if p["asin"] == asin:
                    p["image_url"] = image_map[asin]
            with open(f, "w") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            updated_files.add(f)
    
    print(f"Updated {len(updated_files)} files")

if __name__ == "__main__":
    backfill()
