#!/usr/bin/env python3
"""
Keyword Matcher — Auto-match discovery keywords to Amazon UK products.

Uses AnySearch to find Amazon UK products matching a keyword,
parses results into structured product data with market summary.
Optionally uses ScraperAPI for deeper extraction.

Usage:
    python3 keyword_matcher.py "garden tool set"
    python3 keyword_matcher.py "silicone kitchen gadgets" 10
"""
import json, subprocess, re, sys, statistics
from pathlib import Path

BASE = Path(__file__).parent
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")
SCRAPERAPI_KEY_FILE = Path.home() / ".hermes" / "scraperapi_key.txt"


def _get_scraperapi_key():
    """Read ScraperAPI key if available."""
    if SCRAPERAPI_KEY_FILE.exists():
        key = SCRAPERAPI_KEY_FILE.read_text().strip()
        if key:
            return key
    return None


def _run_anysearch(query, max_results=10):
    """Run AnySearch CLI and return raw output."""
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search", query,
             "--domain", "ecommerce", "--max_results", str(max_results),
             "--zone", "intl"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  AnySearch error: {e}", file=sys.stderr)
    return ""


def _parse_products_from_text(text, keyword):
    """Extract product-like entries from AnySearch result text."""
    products = []

    asins = list(set(re.findall(r'(?:/dp/|asin[=:]?\s*)([A-Z0-9]{10})', text, re.I)))

    price_pattern = re.compile(r'£(\d+\.?\d{0,2})')
    prices = [float(m.group(1)) for m in price_pattern.finditer(text)]

    rating_pattern = re.compile(r'(\d+\.?\d?)\s*(?:out of|/)\s*5')
    ratings = [float(m.group(1)) for m in rating_pattern.finditer(text)]

    review_pattern = re.compile(r'([\d,]+)\s*(?:reviews?|ratings?|stars?)', re.I)
    reviews = []
    for m in review_pattern.finditer(text):
        try:
            reviews.append(int(m.group(1).replace(",", "")))
        except ValueError:
            pass

    first_kw = keyword.split()[0] if keyword.split() else keyword
    name_pattern = re.compile(
        r'(?:^|\n)\s*(?:\d+[.\)]\s*)?(.+?(?:' + re.escape(first_kw) +
        r').{5,120})', re.I | re.MULTILINE
    )
    names = [m.group(1).strip() for m in name_pattern.finditer(text)]

    if asins:
        seen = set()
        for asin in asins:
            if asin in seen:
                continue
            seen.add(asin)
            idx = len(products)
            p = {
                "asin": asin,
                "name": names[idx] if idx < len(names) else "",
                "price": prices[idx] if idx < len(prices) else 0,
                "reviews": reviews[idx] if idx < len(reviews) else 0,
                "rating": ratings[idx] if idx < len(ratings) else 0,
                "url": f"https://www.amazon.co.uk/dp/{asin}",
            }
            products.append(p)
    else:
        chunks = re.split(r'\n(?=\d+[.\)]\s)', text)
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 20:
                continue
            p_name = ""
            m = re.match(r'\d+[.\)]\s*(.{10,150})', chunk)
            if m:
                p_name = m.group(1).strip()
            p_price = 0
            pm = price_pattern.search(chunk)
            if pm:
                p_price = float(pm.group(1))
            p_reviews = 0
            rm = re.search(r'([\d,]+)\s*(?:reviews?|ratings?)', chunk, re.I)
            if rm:
                try:
                    p_reviews = int(rm.group(1).replace(",", ""))
                except ValueError:
                    pass
            p_rating = 0
            gm = rating_pattern.search(chunk)
            if gm:
                p_rating = float(gm.group(1))
            if p_name or p_price > 0:
                products.append({
                    "asin": "", "name": p_name[:120],
                    "price": p_price, "reviews": p_reviews,
                    "rating": p_rating, "url": "",
                })

    return products


def _scraperapi_search(keyword, max_results=5, api_key=None):
    """Search Amazon UK via ScraperAPI for structured results."""
    import urllib.request, urllib.parse
    search_url = f"https://www.amazon.co.uk/s?k={urllib.parse.quote_plus(keyword)}&rh=p_36:559-1000"
    api_url = f"http://api.scraperapi.com?api_key={api_key}&url={urllib.parse.quote(search_url)}&country_code=gb"
    try:
        req = urllib.request.Request(api_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ScraperAPI error: {e}", file=sys.stderr)
        return []
    return _parse_amazon_html(html, keyword, max_results)


def _parse_amazon_html(html, keyword, max_results=5):
    """Parse Amazon UK search results HTML into product list."""
    import html as htmlmod
    products = []
    asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
    if not asins:
        asins = list(set(re.findall(r'/dp/([A-Z0-9]{10})', html)))
    titles = re.findall(r'<img[^>]*alt="([^"]{15,300})"', html)
    if not titles:
        titles = re.findall(r'<span[^>]*class="[^"]*a-text-normal[^"]*"[^>]*>([^<]+)</span>', html)
    price_wholes = re.findall(r'<span[^>]*class="[^"]*a-price-whole[^"]*"[^>]*>(\d+)</span>', html)
    price_fracs = re.findall(r'<span[^>]*class="[^"]*a-price-fraction[^"]*"[^>]*>(\d+)</span>', html)
    if price_wholes:
        prices = [f"{p}.{f}" for p, f in zip(price_wholes, price_fracs)] if price_fracs else [f"{p}.00" for p in price_wholes]
    else:
        prices = re.findall(r'£(\d+\.?\d{0,2})', html)
    reviews_raw = re.findall(r'>([\d,]+)</span>\s*</a>', html)
    if not reviews_raw:
        reviews_raw = re.findall(r'([\d,]+)\s*(?:ratings?|reviews?)', html, re.I)
    ratings_raw = re.findall(r'(\d+\.?\d?)\s*out of\s*5', html)
    seen = set()
    for i, asin in enumerate(asins):
        if asin in seen or len(products) >= max_results:
            continue
        seen.add(asin)
        name = htmlmod.unescape(titles[i]).strip() if i < len(titles) else ""
        name = re.sub(r'\s+', ' ', name).strip()
        try:
            price = float(prices[i]) if i < len(prices) else 0
        except (ValueError, IndexError):
            price = 0
        try:
            rev_count = int(reviews_raw[i].replace(",", "")) if i < len(reviews_raw) else 0
        except (ValueError, IndexError):
            rev_count = 0
        try:
            rating = float(ratings_raw[i]) if i < len(ratings_raw) else 0
        except (ValueError, IndexError):
            rating = 0
        if name and price > 0:
            products.append({
                "asin": asin, "name": name[:120], "price": price,
                "reviews": rev_count, "rating": rating,
                "url": f"https://www.amazon.co.uk/dp/{asin}",
            })
    return products


def match_keyword_to_products(keyword, max_results=5):
    """Match a discovery keyword to Amazon UK products.

    Args:
        keyword: search keyword (e.g. "silicone kitchen gadgets")
        max_results: max products to return

    Returns:
        list of product dicts: [{asin, name, price, reviews, rating, url}, ...]
    """
    products = []

    # Strategy 1: ScraperAPI if available
    api_key = _get_scraperapi_key()
    if api_key:
        print(f"  [{keyword}] Using ScraperAPI...", file=sys.stderr)
        products = _scraperapi_search(keyword, max_results, api_key)

    # Strategy 2: AnySearch (always available, unlimited)
    if len(products) < max_results:
        print(f"  [{keyword}] Using AnySearch...", file=sys.stderr)
        query = f"Amazon UK {keyword} price reviews rating buy"
        text = _run_anysearch(query, max_results=max_results * 2)
        if text:
            anysearch_products = _parse_products_from_text(text, keyword)
            existing_asins = {p["asin"] for p in products if p["asin"]}
            for p in anysearch_products:
                if p["asin"] and p["asin"] in existing_asins:
                    continue
                if p["asin"]:
                    existing_asins.add(p["asin"])
                products.append(p)

    products = products[:max_results]

    summary = _compute_market_summary(products, keyword)
    print(f"  [{keyword}] Market: avg_reviews={summary['avg_reviews']} "
          f"median_price=£{summary['median_price']} "
          f"gap={summary['gap_level']}", file=sys.stderr)

    return products


def _compute_market_summary(products, keyword):
    """Compute market summary from matched products."""
    if not products:
        return {
            "keyword": keyword, "product_count": 0,
            "avg_reviews": 0, "median_price": 0, "avg_rating": 0,
            "top_seller_review_count": 0, "price_range": [0, 0],
            "gap_level": "unknown",
        }
    prices = [p["price"] for p in products if p["price"] > 0]
    reviews = [p["reviews"] for p in products if p["reviews"] > 0]
    ratings = [p["rating"] for p in products if p["rating"] > 0]
    avg_reviews = round(statistics.mean(reviews)) if reviews else 0
    med_price = round(statistics.median(prices), 2) if prices else 0
    avg_rating = round(statistics.mean(ratings), 1) if ratings else 0
    top_reviews = max(reviews) if reviews else 0
    if avg_reviews < 50:
        gap_level = "blue_ocean"
    elif avg_reviews < 200:
        gap_level = "emerging"
    elif avg_reviews < 1000:
        gap_level = "competitive"
    else:
        gap_level = "red_ocean"
    return {
        "keyword": keyword, "product_count": len(products),
        "avg_reviews": avg_reviews, "median_price": med_price,
        "avg_rating": avg_rating, "top_seller_review_count": top_reviews,
        "price_range": [round(min(prices), 2), round(max(prices), 2)] if prices else [0, 0],
        "gap_level": gap_level,
    }


def get_market_summary(keyword, max_results=5):
    """Public helper: run match + return both products and summary dict."""
    products = match_keyword_to_products(keyword, max_results)
    summary = _compute_market_summary(products, keyword)
    return products, summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 keyword_matcher.py <keyword> [max_results]")
        print("Example: python3 keyword_matcher.py 'garden tool set' 5")
        sys.exit(1)
    kw = sys.argv[1]
    max_r = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(f"=== Matching: '{kw}' (max {max_r} results) ===")
    results = match_keyword_to_products(kw, max_r)
    print(f"\n--- Products ({len(results)}) ---")
    for i, p in enumerate(results, 1):
        print(f"  {i}. {p['name'][:80]}")
        print(f"     £{p['price']} | {p['reviews']} reviews | {p['rating']}★ | {p['asin']}")
    if not results:
        print("  (no products found)")
    summary = _compute_market_summary(results, kw)
    print(f"\n--- Market Summary ---")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
