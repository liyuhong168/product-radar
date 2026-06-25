#!/usr/bin/env python3
"""
Deep Competitor Analysis — Analyze competitive landscape for a keyword on Amazon UK.

For a given keyword, searches Amazon UK, extracts product data, and calculates:
- Review concentration (CR5)
- Price range analysis
- Newcomer ratio (products with <100 reviews)
- Gap opportunity detection
- Competition level classification
- Differentiation tips

Usage:
    python3 deep_competitor.py "silicone kitchen gadgets"
    python3 deep_competitor.py "garden tools" --max 15
"""

import json
import re
import statistics
import subprocess
import sys
import urllib.parse
import urllib.request
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


def _run_anysearch(query, max_results=20):
    """Run AnySearch CLI and return raw output."""
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search", query,
             "--domain", "ecommerce", "--max_results", str(max_results),
             "--zone", "intl"],
            capture_output=True, text=True, timeout=45
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
    ratings = []
    for m in rating_pattern.finditer(text):
        val = float(m.group(1))
        if 0 < val <= 5.0:
            ratings.append(val)

    review_pattern = re.compile(r'([\d,]+)\s*(?:reviews?|ratings?|stars?)', re.I)
    reviews = []
    for m in review_pattern.finditer(text):
        try:
            reviews.append(int(m.group(1).replace(",", "")))
        except ValueError:
            pass

    first_kw = keyword.split()[0] if keyword.split() else keyword
    # Strip markdown headings, bullet markers, and other artifacts
    text_clean = re.sub(r'^#{1,4}\s*\d+\.?\s*', '', text, flags=re.MULTILINE)
    text_clean = re.sub(r'^\s*[-*]\s*(?:\*\*[^*]+\*\*\s*:?\s*)?', '', text_clean, flags=re.MULTILINE)
    name_pattern = re.compile(
        r'(?:^|\n)\s*(?:\d+[.\)]\s*)?(.{5,120}(?:' + re.escape(first_kw) +
        r').{5,120})', re.I | re.MULTILINE
    )
    raw_names = name_pattern.findall(text_clean)
    names = []
    for n in raw_names:
        n = n.strip()
        n = re.sub(r'^[-*]\s*', '', n)
        n = re.sub(r'\*\*([^*]+)\*\*', r'\1', n)
        if len(n) > 10:
            names.append(n)

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
                "bsr": None,
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
                if p_rating > 5.0:
                    p_rating = 0
            if p_name or p_price > 0:
                products.append({
                    "asin": "", "name": p_name[:120],
                    "price": p_price, "reviews": p_reviews,
                    "rating": p_rating, "bsr": None, "url": "",
                })

    return products


def _scraperapi_search(keyword, max_results=10, api_key=None):
    """Search Amazon UK via ScraperAPI for structured results."""
    search_url = f"https://www.amazon.co.uk/s?k={urllib.parse.quote_plus(keyword)}"
    api_url = (f"http://api.scraperapi.com?api_key={api_key}"
               f"&url={urllib.parse.quote(search_url)}&country_code=gb")
    try:
        req = urllib.request.Request(api_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ScraperAPI search error: {e}", file=sys.stderr)
        return []
    return _parse_amazon_html(html, keyword, max_results)


def _parse_amazon_html(html, keyword, max_results=10):
    """Parse Amazon UK search results HTML into product list."""
    import html as htmlmod
    products = []

    # Extract ASINs
    asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
    if not asins:
        asins = list(set(re.findall(r'/dp/([A-Z0-9]{10})', html)))

    # Extract titles
    titles = re.findall(r'<img[^>]*alt="([^"]{15,300})"', html)
    if not titles:
        titles = re.findall(r'<span[^>]*class="[^"]*a-text-normal[^"]*"[^>]*>([^<]+)</span>', html)

    # Extract prices
    price_wholes = re.findall(r'<span[^>]*class="[^"]*a-price-whole[^"]*"[^>]*>(\d+)</span>', html)
    price_fracs = re.findall(r'<span[^>]*class="[^"]*a-price-fraction[^"]*"[^>]*>(\d+)</span>', html)
    if price_wholes:
        prices = [f"{p}.{f}" for p, f in zip(price_wholes, price_fracs)] if price_fracs else [f"{p}.00" for p in price_wholes]
    else:
        prices = re.findall(r'£(\d+\.?\d{0,2})', html)

    # Extract review counts and ratings
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
            if rating > 5.0:
                rating = 0
        except (ValueError, IndexError):
            rating = 0
        if name and price > 0:
            products.append({
                "asin": asin, "name": name[:120], "price": price,
                "reviews": rev_count, "rating": rating, "bsr": None,
                "url": f"https://www.amazon.co.uk/dp/{asin}",
            })
    return products


def _extract_bsr_from_page(html):
    """Extract BSR from product page HTML."""
    patterns = [
        r'#([\d,]+)\s+in\s+[^<]*(?:\(|$)',
        r'"bestSellerRank":\s*#?([\d,]+)',
        r'Best Sellers Rank:\s*#?([\d,]+)',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _try_enrich_bsr(products, api_key=None, max_enrich=5):
    """Try to enrich top products with BSR data via ScraperAPI."""
    if not api_key:
        return
    enriched = 0
    for p in products:
        if enriched >= max_enrich:
            break
        if not p.get("asin"):
            continue
        url = f"https://www.amazon.co.uk/dp/{p['asin']}"
        api_url = (f"http://api.scraperapi.com?api_key={api_key}"
                   f"&url={urllib.parse.quote(url)}&country_code=gb")
        try:
            req = urllib.request.Request(api_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            bsr = _extract_bsr_from_page(html)
            if bsr:
                p["bsr"] = bsr
            enriched += 1
        except Exception:
            pass


def _compute_competitive_metrics(products, keyword):
    """Compute all competitive landscape metrics."""
    if not products:
        return {
            "keyword": keyword,
            "product_count": 0,
            "review_concentration": {"cr5": 0, "level": "unknown"},
            "price_range": {"min": 0, "max": 0, "median": 0},
            "newcomer_ratio": 0,
            "avg_rating": 0,
            "avg_reviews": 0,
            "gap_opportunity": False,
            "competition_level": "UNKNOWN",
            "differentiation_tips": [],
            "products": [],
        }

    # Extract valid data
    prices = [p["price"] for p in products if p["price"] and p["price"] > 0]
    reviews_list = [p["reviews"] for p in products if p["reviews"] and p["reviews"] > 0]
    ratings = [p["rating"] for p in products if p["rating"] and p["rating"] > 0]

    # Review concentration (CR5)
    sorted_reviews = sorted(reviews_list, reverse=True) if reviews_list else []
    total_reviews = sum(sorted_reviews)
    top5_reviews = sum(sorted_reviews[:5])
    cr5 = round(top5_reviews / total_reviews, 3) if total_reviews > 0 else 0

    if cr5 > 0.7:
        concentration_level = "monopoly"
    elif cr5 > 0.4:
        concentration_level = "concentrated"
    else:
        concentration_level = "distributed"

    # Price range
    min_price = round(min(prices), 2) if prices else 0
    max_price = round(max(prices), 2) if prices else 0
    median_price = round(statistics.median(prices), 2) if prices else 0

    # Newcomer ratio (products with <100 reviews)
    newcomers = sum(1 for r in reviews_list if r < 100)
    newcomer_ratio = round(newcomers / len(reviews_list), 2) if reviews_list else 0

    # Average metrics
    avg_rating = round(statistics.mean(ratings), 2) if ratings else 0
    avg_reviews = round(statistics.mean(reviews_list)) if reviews_list else 0

    # Gap opportunity
    gap_opportunity = newcomer_ratio > 0.3 and avg_reviews < 200

    # Competition level
    if cr5 > 0.7 or avg_reviews > 2000:
        competition_level = "MONOPOLY"
    elif cr5 > 0.4 or avg_reviews > 500:
        competition_level = "SATURATED"
    elif avg_reviews > 100 or newcomer_ratio < 0.4:
        competition_level = "MODERATE"
    else:
        competition_level = "OPEN"

    # Differentiation tips
    tips = []
    if avg_rating < 4.3:
        tips.append("Room for quality improvement — avg rating below 4.3")
    if max_price - min_price > median_price * 0.5:
        tips.append("Wide price spread — opportunity to position at mid-range")
    if newcomer_ratio > 0.3:
        tips.append("High newcomer presence — market is receptive to new entrants")
    if avg_reviews > 500:
        tips.append("Established market — focus on unique features or bundling")
    else:
        tips.append("Emerging market — early mover advantage possible")
    if not tips:
        tips.append("Standard competition — differentiate on quality, packaging, or service")

    return {
        "keyword": keyword,
        "product_count": len(products),
        "review_concentration": {
            "cr5": cr5,
            "level": concentration_level,
            "top5_reviews": top5_reviews,
            "total_reviews": total_reviews,
        },
        "price_range": {
            "min": min_price,
            "max": max_price,
            "median": median_price,
        },
        "newcomer_ratio": newcomer_ratio,
        "avg_rating": avg_rating,
        "avg_reviews": avg_reviews,
        "gap_opportunity": gap_opportunity,
        "competition_level": competition_level,
        "differentiation_tips": tips,
        "products": products,
    }


def analyze_competitor_landscape(keyword, max_results=10):
    """Analyze competitive landscape for a keyword on Amazon UK.

    Args:
        keyword: search keyword (e.g. "silicone kitchen gadgets")
        max_results: max products to analyze (default 10, up to 20)

    Returns:
        dict with competitive metrics and product list
    """
    max_results = min(max_results, 20)
    products = []

    # Strategy 1: ScraperAPI
    api_key = _get_scraperapi_key()
    if api_key:
        print(f"  [{keyword}] Searching via ScraperAPI...", file=sys.stderr)
        products = _scraperapi_search(keyword, max_results, api_key)

    # Strategy 2: AnySearch fallback
    if len(products) < max_results:
        print(f"  [{keyword}] Searching via AnySearch...", file=sys.stderr)
        # Try multiple query formulations for better results
        queries = [
            f"site:amazon.co.uk {keyword}",
            f"Amazon UK {keyword} price reviews buy",
        ]
        anysearch_products = []
        existing_asins = {p["asin"] for p in products if p["asin"]}
        for query in queries:
            if len(anysearch_products) + len(products) >= max_results:
                break
            text = _run_anysearch(query, max_results=max_results * 2)
            if text:
                batch = _parse_products_from_text(text, keyword)
                for p in batch:
                    if p["asin"] and p["asin"] in existing_asins:
                        continue
                    if p["asin"]:
                        existing_asins.add(p["asin"])
                    anysearch_products.append(p)
        products.extend(anysearch_products)

    products = products[:max_results]

    # Try to enrich top products with BSR
    if api_key and products:
        print(f"  [{keyword}] Enriching BSR for top products...", file=sys.stderr)
        _try_enrich_bsr(products, api_key, max_enrich=min(5, len(products)))

    # Compute metrics
    result = _compute_competitive_metrics(products, keyword)

    print(f"  [{keyword}] Competition: {result['competition_level']} "
          f"| CR5={result['review_concentration']['cr5']} "
          f"| newcomer_ratio={result['newcomer_ratio']} "
          f"| gap={'YES' if result['gap_opportunity'] else 'no'}",
          file=sys.stderr)

    return result


def _print_report(result):
    """Print a human-readable report."""
    print(f"\n{'='*60}")
    print(f"  COMPETITIVE LANDSCAPE: {result['keyword']}")
    print(f"{'='*60}")

    cr = result["review_concentration"]
    pr = result["price_range"]

    print(f"\n  Products analyzed:    {result['product_count']}")
    print(f"  Competition level:    {result['competition_level']}")
    print(f"  Gap opportunity:      {'✅ YES' if result['gap_opportunity'] else '❌ No'}")
    print(f"\n  Review concentration: CR5 = {cr['cr5']} ({cr['level']})")
    print(f"    Top 5 reviews:     {cr['top5_reviews']:,}")
    print(f"    Total reviews:     {cr['total_reviews']:,}")
    print(f"\n  Price range:          £{pr['min']} — £{pr['max']}")
    print(f"  Median price:        £{pr['median']}")
    print(f"\n  Newcomer ratio:      {result['newcomer_ratio']}")
    print(f"  Avg rating:          {result['avg_rating']}")
    print(f"  Avg reviews:         {result['avg_reviews']}")

    print(f"\n  Differentiation tips:")
    for tip in result["differentiation_tips"]:
        print(f"    • {tip}")

    print(f"\n  Top products:")
    for i, p in enumerate(result["products"][:10], 1):
        bsr_str = f" BSR#{p['bsr']}" if p.get("bsr") else ""
        print(f"    {i:2d}. {p['name'][:70]}")
        print(f"        £{p['price']} | {p['reviews']} reviews | {p['rating']}★{bsr_str} | {p['asin']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 deep_competitor.py <keyword> [--max N]")
        print('Example: python3 deep_competitor.py "silicone kitchen gadgets"')
        sys.exit(1)

    kw = sys.argv[1]
    max_r = 10
    if "--max" in sys.argv:
        idx = sys.argv.index("--max")
        if idx + 1 < len(sys.argv):
            max_r = int(sys.argv[idx + 1])

    result = analyze_competitor_landscape(kw, max_r)
    _print_report(result)

    # Also dump JSON
    out_path = BASE / "data" / "competitor_analysis" / f"{kw.replace(' ', '_')[:50]}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n  Full data saved to: {out_path}")
