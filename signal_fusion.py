#!/usr/bin/env python3
"""
Signal Fusion — Three-layer signal analysis for discovery keywords.

Layer 1 (Trend Score): Google Trends + TikTok + Amazon search volume signals
Layer 2 (Supply-Demand Gap): Amazon UK top-20 analysis — avg reviews, ratings, price
Layer 3 (Profit Window): Median competitor price → 1688 cost threshold for 20%+ margin

Final score = weighted average of all three layers (0-100).

Usage:
    python3 signal_fusion.py "silicone kitchen gadgets"
    python3 signal_fusion.py "garden tool set" --json
"""
import json, subprocess, re, sys, statistics
from pathlib import Path

BASE = Path(__file__).parent
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")

# Load cost structure from config
CONFIG = json.loads((BASE / "config.json").read_text())
COST = CONFIG["cost_structure"]
EXCHANGE_RATE = CONFIG.get("exchange_rate_cny_gbp", 7.3)
MIN_MARGIN = CONFIG.get("min_profit_margin", 0.2)
PRICE_MIN = CONFIG["price_range"]["min"]
PRICE_MAX = CONFIG["price_range"]["max"]

# Layer weights: trend=25%, gap=40%, profit=35%
WEIGHTS = {"trend": 0.25, "gap": 0.40, "profit": 0.35}


def _run_anysearch(query, domain="ecommerce", max_results=8):
    """Run AnySearch CLI."""
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search", query,
             "--domain", domain, "--max_results", str(max_results),
             "--zone", "intl"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  AnySearch error: {e}", file=sys.stderr)
    return ""


# ── Layer 1: Trend Score ──────────────────────────────────────────

TREND_SIGNALS = {
    "high": [
        "trending", "viral", "best seller", "bestseller", "hot selling",
        "top rated", "amazon choice", "amazon's choice", "movers and shakers",
        "rising", "popular", "must have", "tiktok made me buy",
        "new release", "frequently bought",
    ],
    "medium": [
        "recommended", "good reviews", "well reviewed", "top pick",
        "editor choice", "customer favourite", "highly rated",
        "increasing demand", "growing", "seasonal",
    ],
    "low": [
        "available", "in stock", "buy", "shop", "price",
    ],
}


def _score_trend_layer(keyword):
    """Layer 1: Score trend signals from Google Trends + TikTok + Amazon.

    Searches three sources via AnySearch, counts signal keyword hits.
    Returns score 0-100.
    """
    from datetime import datetime
    season_map = {6: "summer", 7: "summer", 8: "summer",
                  9: "autumn", 10: "autumn", 11: "autumn",
                  12: "winter", 1: "winter", 2: "winter",
                  3: "spring", 4: "spring", 5: "spring"}
    season = season_map.get(datetime.now().month, "summer")
    year = datetime.now().year

    queries = [
        (f"{keyword} trending Amazon UK {year}", "ecommerce"),
        (f"TikTok Shop UK {keyword} viral trending", "ecommerce"),
        (f"Google Trends UK {keyword} {season} {year} rising search volume", "general"),
    ]

    all_text = ""
    source_count = 0
    for q, domain in queries:
        text = _run_anysearch(q, domain=domain, max_results=5)
        if text:
            all_text += "\n" + text
            source_count += 1

    if not all_text:
        return {"score": 30, "sources_found": 0, "signals": []}

    text_lower = all_text.lower()

    high_hits = sum(1 for s in TREND_SIGNALS["high"] if s in text_lower)
    med_hits = sum(1 for s in TREND_SIGNALS["medium"] if s in text_lower)
    low_hits = sum(1 for s in TREND_SIGNALS["low"] if s in text_lower)

    raw = high_hits * 15 + med_hits * 8 + low_hits * 3
    base_score = min(raw, 80)
    source_bonus = min(source_count * 7, 20)
    score = min(base_score + source_bonus, 100)

    signals = []
    for s in TREND_SIGNALS["high"]:
        if s in text_lower:
            signals.append(f"🔥 {s}")
    for s in TREND_SIGNALS["medium"]:
        if s in text_lower:
            signals.append(f"📈 {s}")

    return {
        "score": score,
        "sources_found": source_count,
        "signals": signals[:10],
        "raw_hits": {"high": high_hits, "medium": med_hits, "low": low_hits},
    }


# ── Layer 2: Supply-Demand Gap ────────────────────────────────────

def _score_gap_layer(keyword):
    """Layer 2: Analyze Amazon UK top results for supply-demand gap.

    Uses keyword_matcher.get_market_summary() for real Amazon UK data via ScraperAPI.
    Falls back to AnySearch text parsing if ScraperAPI unavailable/fails.

    Returns score 0-100 and confidence ('high' or 'low').
    """
    # Strategy 1: Use keyword_matcher.get_market_summary() for real Amazon data
    try:
        from keyword_matcher import get_market_summary
        products, summary = get_market_summary(keyword, max_results=5)
        avg_reviews = summary.get("avg_reviews", 0)
        avg_rating = summary.get("avg_rating", 0)
        med_price = summary.get("median_price", 0)
        product_count = summary.get("product_count", 0)
        # If we got real products with reviews, this is high-confidence
        if product_count > 0 and avg_reviews > 0:
            confidence = "high"
        elif product_count > 0:
            confidence = "high"  # ScraperAPI worked, just no reviews parsed
        else:
            confidence = "low"   # No products from ScraperAPI
    except Exception as e:
        print(f"  keyword_matcher error: {e}", file=sys.stderr)
        # Fallback to AnySearch with improved parsing
        confidence = "low"
        query = f"Amazon UK {keyword} price reviews buy"
        text = _run_anysearch(query, domain="ecommerce", max_results=10)

        if not text:
            return {"score": 50, "avg_reviews": 0, "avg_rating": 0,
                    "median_price": 0, "gap_level": "unknown",
                    "products_found": 0, "confidence": "low"}

        review_matches = re.findall(r'([\d,]+)\s*(?:reviews?|ratings?)', text, re.I)
        reviews = []
        for m in review_matches:
            try:
                reviews.append(int(m.replace(",", "")))
            except ValueError:
                pass

        rating_matches = re.findall(r'(\d+\.?\d?)\s*(?:out of|/)\s*5', text)
        ratings = [float(r) for r in rating_matches if 1.0 <= float(r) <= 5.0]

        price_matches = re.findall(r'£(\d+\.?\d{0,2})', text)
        prices = [float(p) for p in price_matches if PRICE_MIN <= float(p) <= PRICE_MAX * 1.5]

        avg_reviews = round(statistics.mean(reviews)) if reviews else 0
        avg_rating = round(statistics.mean(ratings), 1) if ratings else 0
        med_price = round(statistics.median(prices), 2) if prices else 0
        product_count = len(set(re.findall(r'/dp/[A-Z0-9]{10}', text)))

    # Updated thresholds based on realistic Amazon UK data
    if avg_reviews < 30:
        gap_level = "blue_ocean"
        gap_score = 90
    elif avg_reviews < 100:
        gap_level = "emerging"
        gap_score = 70
    elif avg_reviews < 500:
        gap_level = "moderate"
        gap_score = 50
    else:
        gap_level = "red_ocean"
        gap_score = 10

    price_fit_bonus = 0
    if med_price > 0:
        if PRICE_MIN <= med_price <= PRICE_MAX:
            price_fit_bonus = 10
        elif med_price < PRICE_MIN:
            price_fit_bonus = -10
        else:
            price_fit_bonus = -5

    count_bonus = 0
    if product_count > 0:
        if product_count <= 5:
            count_bonus = 10
        elif product_count <= 10:
            count_bonus = 5
        else:
            count_bonus = -5

    score = max(0, min(100, gap_score + price_fit_bonus + count_bonus))

    return {
        "score": score,
        "avg_reviews": avg_reviews,
        "avg_rating": avg_rating,
        "median_price": med_price,
        "product_count": product_count,
        "gap_level": gap_level,
        "confidence": confidence,
    }


# ── Layer 3: Profit Window ────────────────────────────────────────

def _calc_sourcing_threshold(price_gbp, category="general"):
    """Reverse-engineer max 1688 cost (in CNY) for 20%+ margin at given price.

    Solves: margin = (price - all_costs) / price >= 0.20
    => all_costs <= price * 0.80
    => sourcing_gbp <= price * 0.80 - (vat + commission + fba + ads + returns)

    Returns max sourcing cost in GBP and CNY.
    """
    comm_rate = COST["commission_rate"]
    cat_lower = category.lower()
    if "home" in cat_lower or "kitchen" in cat_lower:
        comm_rate = COST["commission_home"]
    elif "pet" in cat_lower:
        comm_rate = COST["commission_pets"]

    vat = price_gbp * COST["vat_rate"]
    commission = price_gbp * comm_rate
    fba = COST["fba_small_standard"]
    ads = price_gbp * COST["ad_rate"]
    returns = price_gbp * COST["return_rate"]

    fixed_costs = vat + commission + fba + ads + returns
    max_sourcing_gbp = price_gbp * (1 - MIN_MARGIN) - fixed_costs
    max_sourcing_cny = max_sourcing_gbp * EXCHANGE_RATE

    return {
        "max_sourcing_gbp": round(max(max_sourcing_gbp, 0), 2),
        "max_sourcing_cny": round(max(max_sourcing_cny, 0), 1),
        "target_price_gbp": price_gbp,
        "fixed_costs_gbp": round(fixed_costs, 2),
    }


def _score_profit_layer(median_price, category="general"):
    """Layer 3: Calculate profit window based on median competitor price.

    Returns score 0-100.
    """
    if median_price <= 0:
        return {
            "score": 40, "median_price": 0, "in_target_range": False,
            "sourcing_threshold": None, "margin_at_target": None,
        }

    in_range = PRICE_MIN <= median_price <= PRICE_MAX
    sourcing = _calc_sourcing_threshold(median_price, category)
    margin_possible = sourcing["max_sourcing_gbp"] > 0

    if in_range and margin_possible:
        score = 85
        if sourcing["max_sourcing_cny"] >= 10:
            score = 95
        elif sourcing["max_sourcing_cny"] >= 5:
            score = 90
    elif in_range:
        score = 60
    elif median_price < PRICE_MIN:
        score = 25
    else:
        undercut_price = PRICE_MAX
        undercut_sourcing = _calc_sourcing_threshold(undercut_price, category)
        if undercut_sourcing["max_sourcing_cny"] >= 5:
            score = 55
        else:
            score = 30

    ideal_price = (PRICE_MIN + PRICE_MAX) / 2
    ideal_sourcing = _calc_sourcing_threshold(ideal_price, category)

    return {
        "score": score,
        "median_price": round(median_price, 2),
        "in_target_range": in_range,
        "sourcing_threshold": sourcing,
        "ideal_sourcing_threshold": ideal_sourcing,
    }


# ── Main Analysis Function ────────────────────────────────────────

def analyze_keyword(keyword):
    """Three-layer signal analysis for a discovery keyword.

    Args:
        keyword: e.g. "silicone kitchen gadgets"

    Returns:
        dict with keys:
        - keyword: input keyword
        - trend_score: Layer 1 score (0-100)
        - gap_score: Layer 2 score (0-100)
        - profit_score: Layer 3 score (0-100)
        - final_score: weighted average (0-100)
        - gap_level: "blue_ocean" / "emerging" / "moderate" / "competitive" / "red_ocean"
        - profit_window: dict with sourcing thresholds
        - recommendation: "STRONG_BUY" / "BUY" / "WATCH" / "SKIP"
        - details: full layer results
    """
    print(f"\n=== Analyzing: '{keyword}' ===", file=sys.stderr)

    # Layer 1: Trend
    print(f"  [1/3] Trend analysis...", file=sys.stderr)
    trend = _score_trend_layer(keyword)
    print(f"  Trend score: {trend['score']} ({trend['sources_found']} sources)", file=sys.stderr)

    # Layer 2: Supply-Demand Gap
    print(f"  [2/3] Supply-demand gap analysis...", file=sys.stderr)
    gap = _score_gap_layer(keyword)
    print(f"  Gap score: {gap['score']} (avg_reviews={gap['avg_reviews']}, "
          f"gap={gap['gap_level']})", file=sys.stderr)

    # Layer 3: Profit Window
    print(f"  [3/3] Profit window analysis...", file=sys.stderr)
    profit = _score_profit_layer(gap.get("median_price", 0))
    sourcing = profit.get("sourcing_threshold", {})
    if sourcing:
        print(f"  Profit score: {profit['score']} "
              f"(1688 threshold: ¥{sourcing.get('max_sourcing_cny', '?')})", file=sys.stderr)

    # Weighted final score
    final = round(
        trend["score"] * WEIGHTS["trend"] +
        gap["score"] * WEIGHTS["gap"] +
        profit["score"] * WEIGHTS["profit"],
        1
    )

    # Recommendation
    if final >= 75:
        recommendation = "STRONG_BUY"
    elif final >= 60:
        recommendation = "BUY"
    elif final >= 45:
        recommendation = "WATCH"
    else:
        recommendation = "SKIP"

    print(f"  >>> Final: {final} → {recommendation}", file=sys.stderr)

    confidence = gap.get("confidence", "low")

    return {
        "keyword": keyword,
        "trend_score": trend["score"],
        "gap_score": gap["score"],
        "profit_score": profit["score"],
        "final_score": final,
        "gap_level": gap["gap_level"],
        "profit_window": {
            "median_competitor_price": profit.get("median_price", 0),
            "in_target_range": profit.get("in_target_range", False),
            "max_1688_cost_cny": sourcing.get("max_sourcing_cny", 0) if sourcing else 0,
            "max_sourcing_gbp": sourcing.get("max_sourcing_gbp", 0) if sourcing else 0,
            "target_price": sourcing.get("target_price_gbp", 0) if sourcing else 0,
        },
        "recommendation": recommendation,
        "confidence": confidence,
        "weights": WEIGHTS,
        "details": {
            "trend": trend,
            "gap": gap,
            "profit": profit,
        },
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 signal_fusion.py <keyword> [--json]")
        print("Example: python3 signal_fusion.py 'silicone kitchen gadgets'")
        sys.exit(1)

    kw = sys.argv[1]
    output_json = "--json" in sys.argv

    result = analyze_keyword(kw)

    if output_json:
        compact = {k: v for k, v in result.items() if k != "details"}
        print(json.dumps(compact, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print(f"Keyword: {result['keyword']}")
        print(f"{'='*60}")
        print(f"  Trend Score:      {result['trend_score']}/100 (weight {WEIGHTS['trend']*100:.0f}%)")
        print(f"  Gap Score:        {result['gap_score']}/100 (weight {WEIGHTS['gap']*100:.0f}%)")
        print(f"  Profit Score:     {result['profit_score']}/100 (weight {WEIGHTS['profit']*100:.0f}%)")
        print(f"  {'─'*40}")
        print(f"  FINAL SCORE:      {result['final_score']}/100")
        print(f"  Gap Level:        {result['gap_level']}")
        print(f"  Recommendation:   {result['recommendation']}")

        pw = result["profit_window"]
        if pw["median_competitor_price"] > 0:
            print(f"\n  Profit Window:")
            print(f"    Median competitor price: £{pw['median_competitor_price']}")
            print(f"    In target range (£{PRICE_MIN}-£{PRICE_MAX}): {pw['in_target_range']}")
            print(f"    Max 1688 cost for 20%+ margin: ¥{pw['max_1688_cost_cny']}")
            print(f"    Max sourcing in GBP: £{pw['max_sourcing_gbp']}")

        trend = result["details"]["trend"]
        if trend.get("signals"):
            print(f"\n  Trend Signals: {', '.join(trend['signals'][:5])}")
