#!/usr/bin/env python3
"""TikTok Shop UK data fetcher - uses AnySearch + web scraping"""
import json, subprocess, re, sys
from pathlib import Path

BASE = Path(__file__).parent.parent
CONFIG = json.loads((BASE / "config.json").read_text())
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _curl_fetch(url):
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--compressed",
             "--connect-timeout", "10", "--max-time", "30",
             "-H", f"User-Agent: {USER_AGENT}",
             url],
            capture_output=True, text=True, timeout=45
        )
        return result.stdout
    except Exception as e:
        print(f"  curl error: {e}", file=sys.stderr)
    return ""


def _run_anysearch(query, max_results=5):
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search", query,
             "--domain", "ecommerce", "--max_results", str(max_results), "--zone", "intl"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  AnySearch error: {e}", file=sys.stderr)
    return ""


def _parse_tiktok_platform(html, source_name):
    """Try to extract product data from TikTok data platform HTML."""
    products = []
    if not html or len(html) < 500:
        return products

    # These platforms use JavaScript rendering, so HTML might be minimal
    # Try to find JSON data embedded in script tags
    json_blocks = re.findall(r'(?:window\.__INITIAL_STATE__|window\.__NUXT__|__NEXT_DATA__)\s*=\s*({.*?});', html, re.DOTALL)
    for block in json_blocks:
        try:
            data = json.loads(block)
            # Try to find product arrays in the JSON
            _extract_from_json(data, products, source_name)
        except json.JSONDecodeError:
            pass

    # Also try to find product patterns in raw HTML
    price_matches = re.findall(r'[£$](\d+\.?\d*)', html)
    name_matches = re.findall(r'"title"\s*:\s*"([^"]{10,200})"', html)
    for i, name in enumerate(name_matches[:20]):
        price = float(price_matches[i]) if i < len(price_matches) else 0
        if price > 0:
            products.append({
                "name": name[:100],
                "price": price,
                "sources": [source_name],
                "signal": f"{source_name} trending"
            })

    return products


def _extract_from_json(data, products, source_name, depth=0):
    """Recursively extract products from JSON data."""
    if depth > 10:
        return
    if isinstance(data, dict):
        # Look for product-like objects
        if "title" in data and ("price" in data or "sold" in data):
            name = data.get("title", "")
            price = 0
            if "price" in data:
                try:
                    price = float(data["price"])
                except (ValueError, TypeError):
                    pass
            if "price_str" in data:
                m = re.search(r'(\d+\.?\d*)', str(data["price_str"]))
                if m:
                    price = float(m.group(1))
            if name and price > 0:
                products.append({
                    "name": str(name)[:100],
                    "price": price,
                    "sources": [source_name],
                    "signal": f"{source_name} trending"
                })
        for v in data.values():
            _extract_from_json(v, products, source_name, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _extract_from_json(item, products, source_name, depth + 1)


def fetch():
    """Fetch TikTok Shop UK trending products."""
    all_products = []

    # Try TikTok data platforms with curl
    tikkok_urls = [
        ("FastMoss", "https://fastmoss.com/uk/ranking/product"),
        ("Kalodata", "https://www.kalodata.com/ranking/uk"),
    ]

    for name, url in tikkok_urls:
        print(f"  Trying {name}...", file=sys.stderr)
        html = _curl_fetch(url)
        products = _parse_tiktok_platform(html, name)
        for p in products:
            p["signal"] = "TikTok viral signal"
            all_products.extend(products)
        print(f"  {name}: {len(products)} products", file=sys.stderr)

    # Primary method: AnySearch for TikTok trending products
    queries = [
        "TikTok Shop UK best sellers trending products under 10 pounds 2026",
        "TikTok made me buy it UK viral products summer 2026",
        "TikTok trending products UK home accessories gadgets 2026",
        "trending TikTok products under 10 UK small items useful",
    ]

    seen_names = set()
    for q in queries:
        print(f"  AnySearch: {q[:50]}...", file=sys.stderr)
        text = _run_anysearch(q)
        if not text:
            continue

        # Parse search results for product mentions
        lines = text.split("\n")
        current = {}
        for line in lines:
            line = line.strip()
            if not line:
                if current.get("name") and current.get("name").lower() not in seen_names:
                    current.setdefault("sources", []).append("TikTok趋势")
                    current["signal"] = "TikTok社交爆品信号"
                    all_products.append(current)
                    seen_names.add(current["name"].lower())
                current = {}
                continue

            # Price
            price_match = re.search(r'£(\d+\.?\d*)', line)
            if price_match:
                price = float(price_match.group(1))
                if CONFIG["price_range"]["min"] <= price <= CONFIG["price_range"]["max"]:
                    current["price"] = price

            # Product name (skip generic lines)
            if len(line) > 15 and not line.startswith("http"):
                skip = ['search results', 'tiktok shop', 'ranking', 'platform',
                        'login', 'sign up', 'filter', 'discover', 'explore',
                        'results', 'page', 'www.', '.com']
                if not any(s in line.lower() for s in skip):
                    if "name" not in current:
                        current["name"] = line[:100]

        if current.get("name") and current.get("name").lower() not in seen_names:
            current.setdefault("sources", []).append("TikTok趋势")
            current["signal"] = "TikTok社交爆品信号"
            all_products.append(current)
            seen_names.add(current["name"].lower())

    print(f"  TikTok UK total: {len(all_products)} products", file=sys.stderr)
    return all_products
