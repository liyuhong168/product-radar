#!/usr/bin/env python3
"""Amazon UK data fetcher v2 - New Releases + BSR with channel tagging"""
import json, subprocess, re, sys, random
from pathlib import Path

BASE = Path(__file__).parent.parent
CONFIG = json.loads((BASE / "config.json").read_text())

# Amazon UK URLs with channel type
AMAZON_URLS = {
    # === NEW RELEASES ===
    "Kitchen|new_releases": "https://www.amazon.co.uk/gp/new-releases/kitchen/",
    "Garden|new_releases": "https://www.amazon.co.uk/gp/new-releases/garden/",
    "DIY|new_releases": "https://www.amazon.co.uk/gp/new-releases/diy/",
    "Sports|new_releases": "https://www.amazon.co.uk/gp/new-releases/sports/",
    "Bathroom|new_releases": "https://www.amazon.co.uk/gp/new-releases/bathroom/",
    "Cleaning|new_releases": "https://www.amazon.co.uk/gp/new-releases/cleaning/",
    "Office|new_releases": "https://www.amazon.co.uk/gp/new-releases/stationery-office/",
    "Automotive|new_releases": "https://www.amazon.co.uk/gp/new-releases/automotive/",
    "Lighting|new_releases": "https://www.amazon.co.uk/gp/new-releases/lighting/",
    "Storage|new_releases": "https://www.amazon.co.uk/gp/new-releases/kitchen/storage-accessories/",
    "Crafts|new_releases": "https://www.amazon.co.uk/gp/new-releases/diy-craft-tools/",
    "Bedding|new_releases": "https://www.amazon.co.uk/gp/new-releases/bedding/",
    "Pets|new_releases": "https://www.amazon.co.uk/gp/new-releases/pet-supplies/",
    "Home|new_releases": "https://www.amazon.co.uk/gp/new-releases/home/",
    # === BESTSELLERS (BSR) ===
    "Kitchen|bsr": "https://www.amazon.co.uk/gp/bestsellers/kitchen/",
    "Garden|bsr": "https://www.amazon.co.uk/gp/bestsellers/garden/",
    "DIY|bsr": "https://www.amazon.co.uk/gp/bestsellers/diy/",
    "Sports|bsr": "https://www.amazon.co.uk/gp/bestsellers/sports/",
    "Home|bsr": "https://www.amazon.co.uk/gp/bestsellers/home/",
    "Automotive|bsr": "https://www.amazon.co.uk/gp/bestsellers/automotive/",
    "Crafts|bsr": "https://www.amazon.co.uk/gp/bestsellers/diy-craft-tools/",
    "Office|bsr": "https://www.amazon.co.uk/gp/bestsellers/stationery-office/",
    "Bathroom|bsr": "https://www.amazon.co.uk/gp/bestsellers/bathroom/",
    "Cleaning|bsr": "https://www.amazon.co.uk/gp/bestsellers/cleaning/",
    "Lighting|bsr": "https://www.amazon.co.uk/gp/bestsellers/lighting/",
    "Bedding|bsr": "https://www.amazon.co.uk/gp/bestsellers/bedding/",
    "Pets|bsr": "https://www.amazon.co.uk/gp/bestsellers/pet-supplies/",
    # === MOST WISHED FOR (需求信号) ===
    "Kitchen|wished": "https://www.amazon.co.uk/gp/most-wished-for/kitchen/",
    "Garden|wished": "https://www.amazon.co.uk/gp/most-wished-for/garden/",
    "DIY|wished": "https://www.amazon.co.uk/gp/most-wished-for/diy/",
    "Sports|wished": "https://www.amazon.co.uk/gp/most-wished-for/sports/",
    "Home|wished": "https://www.amazon.co.uk/gp/most-wished-for/home/",
    "Automotive|wished": "https://www.amazon.co.uk/gp/most-wished-for/automotive/",
    "Pets|wished": "https://www.amazon.co.uk/gp/most-wished-for/pet-supplies/",
    "Office|wished": "https://www.amazon.co.uk/gp/most-wished-for/stationery-office/",
    # === GIFT IDEAS (送礼需求) ===
    "Kitchen|gifts": "https://www.amazon.co.uk/gp/gifts/kitchen/",
    "Garden|gifts": "https://www.amazon.co.uk/gp/gifts/garden/",
    "DIY|gifts": "https://www.amazon.co.uk/gp/gifts/diy/",
    "Home|gifts": "https://www.amazon.co.uk/gp/gifts/home/",
}

GBP_COOKIES = "lc-main=en_GB; i18n-prefs=GBP"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

CHANNEL_NAMES = {
    "new_releases": "Amazon新品榜",
    "bsr": "Amazon畅销榜",
    "wished": "Amazon心愿榜",
    "gifts": "Amazon送礼榜",
}


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


def _parse_amazon_page(html, category, channel_type):
    """Parse Amazon page HTML for products."""
    products = []
    if not html or len(html) < 1000:
        return products

    import html as htmlmod

    asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
    if not asins:
        asins = list(set(re.findall(r'/dp/([A-Z0-9]{10})', html)))

    titles = re.findall(r'<img[^>]*alt="([^"]{15,300})"', html)
    prices = re.findall(r'£(\d+\.\d{2})', html)
    reviews = re.findall(r'>(\d[\d,]*)</span>\s*</a>', html)
    if not reviews:
        reviews = re.findall(r'(\d[\d,]+)\s*(?:ratings?|reviews?)', html, re.I)
    ratings = re.findall(r'(\d+\.?\d?)\s*out of\s*5', html)

    seen_asins = set()
    for i, asin in enumerate(asins):
        if asin in seen_asins:
            continue
        seen_asins.add(asin)

        title = htmlmod.unescape(titles[i]).strip() if i < len(titles) else ""
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
                "category": category,
                "channel": channel_type,
                "channel_name": CHANNEL_NAMES.get(channel_type, channel_type),
                "review_info": f"{review_count} reviews, {rating}★" if rating else f"{review_count} reviews",
                "amazon_url": f"https://www.amazon.co.uk/dp/{asin}",
            })

    return products


def fetch(max_per_channel_type=8):
    """Fetch Amazon UK data from New Releases and BSR."""
    all_products = []
    seen_asins = set()

    # Category rotation per channel type
    rotation_file = BASE / "data" / "last_categories_v2.json"
    last_cats = {}
    if rotation_file.exists():
        try:
            last_cats = json.loads(rotation_file.read_text())
        except Exception:
            pass

    # Group URLs by channel type
    by_channel = {}
    for key, url in AMAZON_URLS.items():
        cat, ch = key.split("|")
        by_channel.setdefault(ch, []).append((cat, url))

    selected_keys = []
    for channel_type, entries in by_channel.items():
        last = last_cats.get(channel_type, [])
        uncovered = [e for e in entries if e[0] not in last]
        if len(uncovered) >= max_per_channel_type:
            picked = random.sample(uncovered, max_per_channel_type)
        else:
            picked = uncovered[:]
            remaining = [e for e in entries if e[0] not in [p[0] for p in picked]]
            picked.extend(random.sample(remaining, min(max_per_channel_type - len(picked), len(remaining))))

        for cat, url in picked:
            selected_keys.append((cat, channel_type, url))
        last_cats[channel_type] = [p[0] for p in picked]

    # Save rotation
    rotation_file.parent.mkdir(parents=True, exist_ok=True)
    rotation_file.write_text(json.dumps(last_cats))

    # Fetch each URL
    for category, channel_type, url in selected_keys:
        print(f"  Fetching {category} ({CHANNEL_NAMES[channel_type]})...", file=sys.stderr)
        html = _curl_fetch(url)
        if not html:
            print(f"  warn {category}/{channel_type}: empty", file=sys.stderr)
            continue

        products = _parse_amazon_page(html, category, channel_type)
        new_count = 0
        for p in products:
            if p["asin"] not in seen_asins:
                seen_asins.add(p["asin"])
                all_products.append(p)
                new_count += 1

        print(f"  ok {category}/{channel_type}: {new_count} new", file=sys.stderr)

    # Summary by channel
    for ch in CHANNEL_NAMES:
        count = sum(1 for p in all_products if p["channel"] == ch)
        print(f"  {CHANNEL_NAMES[ch]}: {count} products", file=sys.stderr)

    print(f"  Amazon UK total: {len(all_products)} products", file=sys.stderr)
    return all_products
