#!/usr/bin/env python3
"""
AnySearch trend fetcher - uses AnySearch CLI for trend signals
Searches multiple queries to build a trend score per product category.
"""
import json, subprocess, re, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent.parent
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")


def _run_anysearch(query, domain="general", max_results=8, freshness="week"):
    """Run AnySearch CLI and return results text."""
    try:
        cmd = ["python3", ANYSEARCH, "search", query,
               "--domain", domain, "--max_results", str(max_results)]
        if freshness:
            cmd.extend(["--freshness", freshness])
        cmd.extend(["--zone", "intl"])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  AnySearch error: {e}", file=sys.stderr)
    return ""


def fetch_trend_signals():
    """Fetch trend signals from multiple AnySearch queries.
    
    Returns a dict of category -> trend data with scores.
    """
    now = datetime.now()
    month = now.strftime("%B")  # e.g., "May"
    year = now.strftime("%Y")
    season = _get_season(now.month)

    # Query set: each query targets a different angle
    queries = [
        # TikTok trending products UK
        (f"TikTok Shop UK trending products {season} {year}", "ecommerce"),
        (f"TikTok viral products UK under £10 useful {year}", "ecommerce"),
        ("TikTok made me buy it UK 2026 best products", "ecommerce"),
        # Google Trends / demand signals
        (f"UK trending products {season} {year} popular buying", "general"),
        (f"Amazon UK new releases trending {month} {year}", "general"),
        # Reddit demand
        ("site:reddit.com UK Amazon best cheap finds under £10", "general"),
        ("site:reddit.com CasualUK small purchases improved life", "general"),
        # Seasonal
        (f"{season} products UK home garden outdoor trending", "general"),
        # Competitor / market signals
        (f"Amazon UK best sellers small items {year} trending", "ecommerce"),
        (f"UK consumer trends {year} popular products accessories", "general"),
    ]

    all_results = []
    for q, domain in queries:
        print(f"  AnySearch: {q[:60]}...", file=sys.stderr)
        text = _run_anysearch(q, domain=domain)
        if text:
            all_results.append({"query": q, "text": text, "domain": domain})

    # Extract trending categories and products
    trend_data = _analyze_trends(all_results)
    
    return trend_data, all_results


def _get_season(month):
    if month in (3, 4, 5): return "spring"
    if month in (6, 7, 8): return "summer"
    if month in (9, 10, 11): return "autumn"
    return "winter"


def _analyze_trends(results):
    """Analyze search results to extract trending categories and score them."""
    # Known product categories to match against
    category_keywords = {
        "kitchen": ["kitchen", "cooking", "baking", " utensil", "gadget", "organiser", "spice"],
        "garden": ["garden", "outdoor", "plant", "flower", "patio", "bbq", "grill", "solar light"],
        "bathroom": ["bathroom", "shower", "toilet", "towel", "soap", "mirror"],
        "cleaning": ["cleaning", "cleaner", "vacuum", "mop", "duster", "organiser"],
        "car": ["car", "automotive", "vehicle", "dashboard", "phone holder", "organiser"],
        "office": ["desk", "office", "stationery", "pen", "notebook", "organiser", "laptop"],
        "storage": ["storage", "organiser", "box", "basket", "shelf", "drawer"],
        "lighting": ["led", "light", "lamp", "night light", "strip", "fairy"],
        "pets": ["pet", "dog", "cat", "toy", "collar", "leash", "bed"],
        "sports": ["fitness", "yoga", "gym", "exercise", "sport", "water bottle"],
        "crafts": ["craft", "art", "paint", "brush", "stickers", "tape"],
        "bedding": ["bedding", "pillow", "blanket", "sheet", "duvet", "cushion"],
        "travel": ["travel", "luggage", "packing", "passport", "neck pillow"],
        "phone": ["phone", "case", "charger", "cable", "holder", "stand", "ring light"],
        "beauty": ["makeup", "brush", "mirror", "hair", "nail", "skincare"],
        "home decor": ["decor", "wall art", "candle", "vase", "frame", "mirror"],
    }

    # Seasonal boost keywords
    season_month = datetime.now().month
    seasonal = set()
    if season_month in (6, 7, 8):
        seasonal = {"garden", "outdoor", "bbq", "travel", "sports", "water bottle", "solar light"}
    elif season_month in (11, 12, 1):
        seasonal = {"christmas", "gift", "candle", "decor", "lighting", "blanket"}
    elif season_month in (3, 4, 5):
        seasonal = {"garden", "cleaning", "storage", "organiser", "easter"}

    # Count category mentions across all results
    category_scores = {}
    category_evidence = {}

    for result in results:
        text_lower = result["text"].lower()
        for cat, keywords in category_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    category_scores[cat] = category_scores.get(cat, 0) + 1
                    category_evidence.setdefault(cat, set()).add(kw)

    # Apply seasonal boost
    for cat in category_scores:
        if cat in seasonal or any(sk in category_evidence.get(cat, set()) for sk in seasonal):
            category_scores[cat] = int(category_scores[cat] * 1.3)

    # Normalize to 0-100
    if category_scores:
        max_score = max(category_scores.values())
        for cat in category_scores:
            category_scores[cat] = round((category_scores[cat] / max_score) * 100)

    return {
        "category_scores": category_scores,
        "category_evidence": {k: list(v) for k, v in category_evidence.items()},
        "season": _get_season(season_month),
        "total_queries": len(results),
        "total_results_chars": sum(len(r["text"]) for r in results),
    }


def match_product_to_trends(product, trend_data):
    """Score a product against trend data. Returns (score_bonus, signals)."""
    name_lower = product.get("name", "").lower()
    category = product.get("category", "").lower()
    score_bonus = 0
    signals = []

    cat_scores = trend_data.get("category_scores", {})
    cat_evidence = trend_data.get("category_evidence", {})

    # Match product category to trend categories
    for cat, trend_score in cat_scores.items():
        # Check if product category matches
        if cat in category or any(kw in name_lower for kw in cat_evidence.get(cat, [])):
            if trend_score >= 70:
                score_bonus += 20
                signals.append(f"🔥 热门品类({cat})")
            elif trend_score >= 40:
                score_bonus += 10
                signals.append(f"📈 趋势品类({cat})")

    # Check for trending keywords in product name
    trending_phrases = [
        "viral", "tiktok", "trending", "must have", "life changing",
        "aesthetic", "minimalist", "eco friendly", "reusable", "portable",
        "mini", "compact", "multifunction", "3 in 1", "2 in 1",
    ]
    for phrase in trending_phrases:
        if phrase in name_lower:
            score_bonus += 5
            signals.append(f"✨ 趋势词({phrase})")

    return min(score_bonus, 30), signals  # Cap at 30


def get_trending_keywords(trend_data):
    """Extract top trending keywords for display."""
    evidence = trend_data.get("category_evidence", {})
    all_kw = []
    for cat, kws in evidence.items():
        all_kw.extend(kws)
    return list(set(all_kw))[:20]


if __name__ == "__main__":
    # Test: fetch and print trend data
    trend_data, raw = fetch_trend_signals()
    print(json.dumps(trend_data, ensure_ascii=False, indent=2))
