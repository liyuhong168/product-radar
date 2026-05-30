#!/usr/bin/env python3
"""Amazon UK data fetcher - uses curl with GBP cookie to get real BSR data"""
import json, subprocess, re, sys, os
from pathlib import Path

BASE = Path(__file__).parent.parent
CONFIG = json.loads((BASE / "config.json").read_text())

# Amazon UK BSR category URLs
AMAZON_URLS = {
    "Kitchen BSR": "https://www.amazon.co.uk/gp/bestsellers/kitchen/",
    "Garden BSR": "https://www.amazon.co.uk/gp/bestsellers/garden/",
    "DIY & Tools BSR": "https://www.amazon.co.uk/gp/bestsellers/diy/",
    "Bathroom BSR": "https://www.amazon.co.uk/gp/bestsellers/bathroom/",
    "Cleaning BSR": "https://www.amazon.co.uk/gp/bestsellers/cleaning/",
    "Office BSR": "https://www.amazon.co.uk/gp/bestsellers/stationery-office/",
    "Pet Supplies BSR": "https://www.amazon.co.uk/gp/bestsellers/pet-supplies/",
    "Sports BSR": "https://www.amazon.co.uk/gp/bestsellers/sports/",
    "Automotive BSR": "https://www.amazon.co.uk/gp/bestsellers/automotive/",
    "Storage BSR": "https://www.amazon.co.uk/gp/bestsellers/kitchen/storage-accessories/",
    "Home & Living BSR": "https://www.amazon.co.uk/gp/bestsellers/home/",
    "Crafts BSR": "https://www.amazon.co.uk/gp/bestsellers/diy-craft-tools/",
    "Lighting BSR": "https://www.amazon.co.uk/gp/bestsellers/lighting/",
    "Bedding BSR": "https://www.amazon.co.uk/gp/bestsellers/bedding/",
    "Kitchen New": "https://www.amazon.co.uk/gp/new-releases/kitchen/",
    "Garden New": "https://www.amazon.co.uk/gp/new-releases/garden/",
    "Sports New": "https://www.amazon.co.uk/gp/new-releases/sports/",
    "DIY New": "https://www.amazon.co.uk/gp/new-releases/diy/",
}

# GBP cookie forces Amazon to show GBP prices
GBP_COOKIES = "lc-main=en_GB; i18n-prefs=GBP"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _curl_fetch(url):
    """Fetch a page with curl, forcing GBP."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--compressed",
             "--connect-timeout", "10", "--max-time", "30",
             "-H", f"User-Agent: {USER_AGENT}",
             "-H", "Accept-Language: en-GB,en;q=0.9",
             "-b", GBP_COOKIES,
             url],
            capture_output=True, text=True, timeout=45
        )
        return result.stdout
    except Exception as e:
        print(f"  curl error: {e}", file=sys.stderr)
    return ""


def _parse_amazon_bsr(html, source_name):
    """Parse Amazon BSR page HTML for products."""
    products = []
    if not html or len(html) < 1000:
        return products

    import html as htmlmod

    # Extract ASINs
    asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
    if not asins:
        asins = list(set(re.findall(r'/dp/([A-Z0-9]{10})', html)))

    # Extract titles (img alt text)
    titles = re.findall(r'<img[^>]*alt="([^"]{15,300})"', html)

    # Extract GBP prices
    prices = re.findall(r'£(\d+\.\d{2})', html)

    # Extract review counts
    reviews = re.findall(r'>(\d[\d,]*)</span>\s*</a>', html)
    if not reviews:
        reviews = re.findall(r'(\d[\d,]+)\s*(?:ratings?|reviews?)', html, re.I)

    # Extract star ratings
    ratings = re.findall(r'(\d+\.?\d?)\s*out of\s*5', html)

    # Match them up
    seen_asins = set()
    for i, asin in enumerate(asins):
        if asin in seen_asins:
            continue
        seen_asins.add(asin)

        title = htmlmod.unescape(titles[i]).strip() if i < len(titles) else ""
        # Clean title
        title = re.sub(r'\s+', ' ', title).strip()

        price_str = prices[i] if i < len(prices) else ""
        price = float(price_str) if price_str else 0

        review_str = reviews[i].replace(",", "") if i < len(reviews) else "0"
        try:
            review_count = int(review_str)
        except ValueError:
            review_count = 0

        rating = float(ratings[i]) if i < len(ratings) else 0

        if title and price > 0:
            products.append({
                "asin": asin,
                "name": title[:120],
                "price": price,
                "reviews": review_count,
                "rating": rating,
                "rank": i + 1,
                "sources": [source_name],
                "review_info": f"{review_count} reviews, {rating}★" if rating else f"{review_count} reviews",
                "signal": f"{source_name} BSR #{i+1}"
            })

    return products


def fetch():
    """Fetch Amazon UK BSR data from multiple categories."""
    all_products = []
    seen_asins = set()

    # Rotate categories each run
    import random
    url_keys = list(AMAZON_URLS.keys())
    selected = random.sample(url_keys, min(8, len(url_keys)))

    for source_name in selected:
        url = AMAZON_URLS[source_name]
        print(f"  Fetching {source_name}...", file=sys.stderr)

        html = _curl_fetch(url)
        if not html:
            print(f"  warn {source_name}: empty response", file=sys.stderr)
            continue

        products = _parse_amazon_bsr(html, source_name)
        new_count = 0
        for p in products:
            if p["asin"] not in seen_asins:
                seen_asins.add(p["asin"])
                all_products.append(p)
                new_count += 1

        print(f"  ok {source_name}: {new_count} products ({len(products)} total)", file=sys.stderr)

    print(f"  Amazon UK total: {len(all_products)} products", file=sys.stderr)
    return all_products
