#!/usr/bin/env python3
"""Amazon UK search-based fetcher - targets specific price range via search URL"""
import json, subprocess, re, sys, random
from pathlib import Path

BASE = Path(__file__).parent.parent
CONFIG = json.loads((BASE / "config.json").read_text())

GBP_COOKIES = "lc-main=en_GB; i18n-prefs=GBP"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Search queries targeting our price range (£5-10) across categories
# Amazon search URL with price filter: rh=p_36:500-1000 (pence)
SEARCH_QUERIES = {
    # Category | Channel | Search query
    "Kitchen|new_releases": "https://www.amazon.co.uk/s?k=kitchen+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Kitchen|bsr": "https://www.amazon.co.uk/s?k=kitchen+gadgets&rh=p_36%3A559-1000",
    "Garden|new_releases": "https://www.amazon.co.uk/s?k=garden+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Garden|bsr": "https://www.amazon.co.uk/s?k=garden+tools&rh=p_36%3A559-1000",
    "DIY|new_releases": "https://www.amazon.co.uk/s?k=diy+tools+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "DIY|bsr": "https://www.amazon.co.uk/s?k=diy+tools&rh=p_36%3A559-1000",
    "Bathroom|new_releases": "https://www.amazon.co.uk/s?k=bathroom+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Bathroom|bsr": "https://www.amazon.co.uk/s?k=bathroom+storage&rh=p_36%3A559-1000",
    "Cleaning|new_releases": "https://www.amazon.co.uk/s?k=cleaning+tools&rh=p_36%3A559-1000&s=date-desc-rank",
    "Cleaning|bsr": "https://www.amazon.co.uk/s?k=cleaning+supplies&rh=p_36%3A559-1000",
    "Office|new_releases": "https://www.amazon.co.uk/s?k=desk+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Office|bsr": "https://www.amazon.co.uk/s?k=office+supplies&rh=p_36%3A559-1000",
    "Automotive|new_releases": "https://www.amazon.co.uk/s?k=car+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Automotive|bsr": "https://www.amazon.co.uk/s?k=car+organiser&rh=p_36%3A559-1000",
    "Storage|new_releases": "https://www.amazon.co.uk/s?k=storage+organiser&rh=p_36%3A559-1000&s=date-desc-rank",
    "Storage|bsr": "https://www.amazon.co.uk/s?k=home+storage&rh=p_36%3A559-1000",
    "Crafts|new_releases": "https://www.amazon.co.uk/s?k=craft+supplies&rh=p_36%3A559-1000&s=date-desc-rank",
    "Crafts|bsr": "https://www.amazon.co.uk/s?k=art+supplies&rh=p_36%3A559-1000",
    "Lighting|new_releases": "https://www.amazon.co.uk/s?k=led+lights+home&rh=p_36%3A559-1000&s=date-desc-rank",
    "Lighting|bsr": "https://www.amazon.co.uk/s?k=night+light&rh=p_36%3A559-1000",
    "Pets|new_releases": "https://www.amazon.co.uk/s?k=pet+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Pets|bsr": "https://www.amazon.co.uk/s?k=dog+toys&rh=p_36%3A559-1000",
    "Sports|new_releases": "https://www.amazon.co.uk/s?k=sports+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Sports|bsr": "https://www.amazon.co.uk/s?k=fitness+accessories&rh=p_36%3A559-1000",
    "Bedding|new_releases": "https://www.amazon.co.uk/s?k=bedroom+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Bedding|bsr": "https://www.amazon.co.uk/s?k=bedding+accessories&rh=p_36%3A559-1000",
    "Home|new_releases": "https://www.amazon.co.uk/s?k=home+accessories&rh=p_36%3A559-1000&s=date-desc-rank",
    "Home|bsr": "https://www.amazon.co.uk/s?k=home+decor&rh=p_36%3A559-1000",
}

CHANNEL_NAMES = {
    "new_releases": "Amazon新品榜",
    "bsr": "Amazon畅销榜",
}


def _curl_fetch(url):
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


def _parse_search_results(html, category, channel_type):
    """Parse Amazon search results page."""
    products = []
    if not html or len(html) < 1000:
        return products

    import html as htmlmod

    # Search results use data-asin on result containers
    asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
    if not asins:
        asins = list(set(re.findall(r'/dp/([A-Z0-9]{10})', html)))

    # Titles - try multiple patterns
    titles = re.findall(r'<img[^>]*alt="([^"]{15,300})"', html)
    if not titles:
        titles = re.findall(r'<span[^>]*class="[^"]*a-text-normal[^"]*"[^>]*>([^<]+)</span>', html)

    # Prices - search results use a-price pattern
    prices = re.findall(r'<span[^>]*class="[^"]*a-price-whole[^"]*"[^>]*>(\d+)</span>', html)
    price_fracs = re.findall(r'<span[^>]*class="[^"]*a-price-fraction[^"]*"[^>]*>(\d+)</span>', html)
    
    # Fallback: £X.XX pattern
    if not prices:
        prices_raw = re.findall(r'£(\d+\.\d{2})', html)
    else:
        prices_raw = [f"{p}.{f}" for p, f in zip(prices, price_fracs)] if price_fracs else [f"{p}.00" for p in prices]

    # Reviews
    reviews = re.findall(r'>(\d[\d,]*)</span>\s*</a>', html)
    if not reviews:
        reviews = re.findall(r'(\d[\d,]+)\s*(?:ratings?|reviews?)', html, re.I)

    # Ratings
    ratings = re.findall(r'(\d+\.?\d?)\s*out of\s*5', html)

    seen_asins = set()
    for i, asin in enumerate(asins):
        if asin in seen_asins:
            continue
        seen_asins.add(asin)

        title = htmlmod.unescape(titles[i]).strip() if i < len(titles) else ""
        title = re.sub(r'\s+', ' ', title).strip()

        price_str = prices_raw[i] if i < len(prices_raw) else ""
        try:
            price = float(price_str)
        except ValueError:
            price = 0

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


def fetch(max_queries=10):
    """Fetch Amazon UK products via search with price filter."""
    all_products = []
    seen_asins = set()

    # Rotation
    rotation_file = BASE / "data" / "last_search_queries.json"
    last_queries = []
    if rotation_file.exists():
        try:
            last_queries = json.loads(rotation_file.read_text())
        except Exception:
            pass

    all_keys = list(SEARCH_QUERIES.keys())
    uncovered = [k for k in all_keys if k not in last_queries]
    if len(uncovered) >= max_queries:
        selected = random.sample(uncovered, max_queries)
    else:
        selected = uncovered[:]
        remaining = [k for k in all_keys if k not in selected]
        selected.extend(random.sample(remaining, min(max_queries - len(selected), len(remaining))))

    rotation_file.parent.mkdir(parents=True, exist_ok=True)
    rotation_file.write_text(json.dumps(selected))

    for key in selected:
        cat, ch = key.split("|")
        url = SEARCH_QUERIES[key]
        print(f"  Searching {cat} ({CHANNEL_NAMES[ch]})...", file=sys.stderr)

        html = _curl_fetch(url)
        if not html:
            print(f"  warn {key}: empty", file=sys.stderr)
            continue

        products = _parse_search_results(html, cat, ch)
        new_count = 0
        for p in products:
            if p["asin"] not in seen_asins:
                seen_asins.add(p["asin"])
                all_products.append(p)
                new_count += 1

        print(f"  ok {key}: {new_count} new", file=sys.stderr)

    for ch in CHANNEL_NAMES:
        count = sum(1 for p in all_products if p["channel"] == ch)
        print(f"  {CHANNEL_NAMES[ch]}: {count} products", file=sys.stderr)

    print(f"  Amazon UK total: {len(all_products)} products", file=sys.stderr)
    return all_products
