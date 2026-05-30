#!/usr/bin/env python3
"""
Product Radar v2 - Channel Aggregation with Multi-Factor Scoring
Scans multiple channels, scores with weighted signals, generates dashboard.
"""
import json, sys, os
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from scanner import is_forbidden, calc_profit
from sources.amazon_uk import fetch as fetch_amazon
from sources.tiktok_shop import fetch as fetch_tiktok
from sources.google_trends import fetch_demand_signals, extract_trending_keywords
from sources.reddit_demand import fetch_demand_signals as fetch_reddit
from sources.anysearch_trends import fetch_trend_signals
from scoring_engine import score_all_products


def match_tiktok_to_amazon(tiktok_products, amazon_products):
    """Match TikTok trending categories to Amazon products."""
    tiktok_keywords = set()
    for tp in tiktok_products:
        name = tp.get("name", "").lower().strip()
        if len(name) > 3:
            tiktok_keywords.add(name)
        for word in name.split():
            if len(word) > 4:
                tiktok_keywords.add(word)

    matched = []
    for ap in amazon_products:
        ap_name = ap.get("name", "").lower()
        matches = 0
        for kw in tiktok_keywords:
            if kw in ap_name:
                matches += 1
            elif len(kw) > 5 and any(w.startswith(kw[:5]) for w in ap_name.split()):
                matches += 1
        if matches >= 1:
            if "TikTok趋势" not in ap.get("sources", []):
                ap.setdefault("sources", []).append("TikTok趋势")
            matched.append(ap)
    return matched


def enrich_google_trends(products, gtrends_text):
    """Add Google Trends signals to products."""
    if not gtrends_text:
        return products
    keywords = extract_trending_keywords(gtrends_text)
    gtrends_lower = gtrends_text.lower()

    for p in products:
        name_lower = p.get("name", "").lower()
        words = [w for w in name_lower.split() if len(w) > 3]
        match_count = 0
        for kw in keywords:
            if kw in name_lower:
                match_count += 1
        for word in words[:5]:
            if len(word) > 4 and word in gtrends_lower:
                match_count += 1
        if match_count >= 2:
            p["google_trend"] = "rising"
            if "Google趋势" not in p.get("sources", []):
                p.setdefault("sources", []).append("Google趋势")
    return products


def enrich_reddit(products, reddit_text):
    """Add Reddit demand signals to products."""
    if not reddit_text:
        return products
    reddit_lower = reddit_text.lower()
    generic = {'that', 'this', 'with', 'from', 'have', 'been', 'your',
               'they', 'will', 'more', 'than', 'what', 'when', 'very',
               'just', 'like', 'would', 'could', 'should', 'about'}

    for p in products:
        words = [w for w in p.get("name", "").lower().split() if len(w) > 3]
        match = 0
        for word in words[:5]:
            if word in reddit_lower and len(word) > 4 and word not in generic:
                match += 1
        if match >= 2:
            if "Reddit需求" not in p.get("sources", []):
                p.setdefault("sources", []).append("Reddit需求")
    return products


def filter_products(products, config):
    """Apply all filters. Returns (passed, rejected)."""
    passed = []
    rejected = []

    for p in products:
        name = p.get("name", "")
        category = p.get("category", "")

        # Forbidden check
        forbidden, reason = is_forbidden(name, category)
        if forbidden:
            rejected.append({"name": name[:60], "reason": f"禁选: {reason}", "asin": p.get("asin")})
            continue

        # Price check
        price = p.get("price", 0)
        if price < config["price_range"]["min"] or price > config["price_range"]["max"]:
            rejected.append({"name": name[:60], "reason": f"£{price} 不在区间", "asin": p.get("asin")})
            continue

        # Profit calculation
        profit = calc_profit(price, category)
        p["profit_margin"] = profit["margin"]
        p["net_profit"] = profit["net_profit"]
        p["cost_breakdown"] = profit["breakdown"]

        if profit["margin"] < config["min_profit_margin"]:
            rejected.append({"name": name[:60], "reason": f"利润率{profit['margin']*100:.1f}%", "asin": p.get("asin")})
            continue

        passed.append(p)

    return passed, rejected


def dedup_products(products):
    """Deduplicate by ASIN, merging sources."""
    by_asin = {}
    result = []
    for p in products:
        asin = p.get("asin", "")
        if not asin:
            result.append(p)
            continue
        if asin in by_asin:
            existing = by_asin[asin]
            for src in p.get("sources", []):
                if src not in existing.get("sources", []):
                    existing.setdefault("sources", []).append(src)
            # Keep the channel with more signal
            if p.get("channel") == "new_releases" and existing.get("channel") != "new_releases":
                existing["channel"] = "new_releases"
                existing["channel_name"] = "Amazon新品榜"
        else:
            by_asin[asin] = p
            result.append(p)
    return result


def load_history(days=7):
    """Load recent scan history for trend detection."""
    hist_dir = BASE / "data" / "history"
    history = {}
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)
    for f in sorted(hist_dir.glob("*.json")):
        try:
            d = datetime.strptime(f.stem, "%Y-%m-%d")
            if d >= cutoff:
                data = json.loads(f.read_text())
                for item in data:
                    key = item.get("asin") or item.get("name", "").lower().strip()
                    if key not in history:
                        history[key] = []
                    history[key].append({
                        "date": f.stem,
                        "rank": item.get("rank"),
                        "score": item.get("score", 0),
                    })
        except (ValueError, json.JSONDecodeError):
            continue
    return history


def main():
    now = datetime.now()
    scan_date = now.strftime("%Y-%m-%d")
    scan_time = now.strftime("%H:%M")
    config = json.loads((BASE / "config.json").read_text())

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Product Radar v2 | {scan_date} {scan_time}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    # === Step 1: Fetch Amazon ===
    print("[1/7] Amazon UK (品类页)...", file=sys.stderr)
    amazon_products = fetch_amazon(max_per_channel_type=6)
    print(f"  Amazon: {len(amazon_products)} products", file=sys.stderr)

    # === Step 2: Fetch AnySearch trends ===
    print("\n[2/7] AnySearch 趋势分析...", file=sys.stderr)
    trend_data, trend_raw = fetch_trend_signals()
    top_cats = sorted(trend_data.get("category_scores", {}).items(), key=lambda x: -x[1])[:5]
    print(f"  Top trending categories:", file=sys.stderr)
    for cat, score in top_cats:
        print(f"    {cat}: {score}/100", file=sys.stderr)

    # === Step 3: Fetch TikTok ===
    print("\n[3/7] TikTok UK trends...", file=sys.stderr)
    tiktok_products = fetch_tiktok()

    # === Step 4: Fetch Google Trends ===
    print("\n[4/7] Google Trends UK...", file=sys.stderr)
    gtrends_text = fetch_demand_signals()

    # === Step 5: Fetch Reddit ===
    print("\n[5/7] Reddit demand...", file=sys.stderr)
    reddit_text = fetch_reddit()

    # === Step 6: Cross-match ===
    print("\n[6/7] Cross-matching signals...", file=sys.stderr)
    tiktok_matched = match_tiktok_to_amazon(tiktok_products, amazon_products)
    print(f"  TikTok → {len(tiktok_matched)} products", file=sys.stderr)

    amazon_products = enrich_google_trends(amazon_products, gtrends_text)
    gt_count = sum(1 for p in amazon_products if p.get("google_trend") == "rising")
    print(f"  Google Trends → {gt_count} products", file=sys.stderr)

    amazon_products = enrich_reddit(amazon_products, reddit_text)
    reddit_count = sum(1 for p in amazon_products if "Reddit需求" in str(p.get("sources", [])))
    print(f"  Reddit → {reddit_count} products", file=sys.stderr)

    # Dedup
    products = dedup_products(amazon_products)
    print(f"  After dedup: {len(products)}", file=sys.stderr)

    # === Step 7: Filter + Score ===
    print("\n[7/7] Filtering & Scoring...", file=sys.stderr)
    passed, rejected = filter_products(products, config)
    print(f"  Passed filter: {len(passed)} | Rejected: {len(rejected)}", file=sys.stderr)

    # Load history
    history = load_history(days=7)

    # Score all passed products
    passed = score_all_products(passed, trend_data=trend_data, history=history)

    # Show top scored products
    print(f"\n  Top scored products:", file=sys.stderr)
    for p in passed[:10]:
        print(f"    [{p['score']:3d}] £{p['price']:.2f} {p['profit_margin']*100:.0f}% | {p['name'][:50]}", file=sys.stderr)

    # === Build output ===
    # Assign channels for tabbed view
    output_products = []
    for p in passed:
        output_products.append(p)
        # Tag multi-source
        sources = [s.lower() for s in p.get("sources", [])]
        if any("tiktok" in s for s in sources):
            p_copy = dict(p)
            p_copy["channel"] = "tiktok_verified"
            p_copy["channel_name"] = "TikTok验证品"
            output_products.append(p_copy)
        if p.get("google_trend") == "rising":
            p_copy = dict(p)
            p_copy["channel"] = "google_trends"
            p_copy["channel_name"] = "Google趋势"
            output_products.append(p_copy)
        if len(p.get("sources", [])) >= 2:
            p["is_multi"] = True

    # Channel counts
    channel_counts = {}
    for p in output_products:
        ch = p.get("channel", "other")
        channel_counts[ch] = channel_counts.get(ch, 0) + 1

    stats = {
        "total_scanned": len(products),
        "passed_filter": len(passed),
        "rejected": len(rejected),
        "channels": channel_counts,
        "trend_categories": dict(top_cats),
    }

    print(f"\n  Channel breakdown:", file=sys.stderr)
    for ch, cnt in sorted(channel_counts.items(), key=lambda x: -x[1]):
        print(f"    {ch}: {cnt}", file=sys.stderr)

    # Save data
    data = {
        "scan_date": scan_date,
        "scan_time": scan_time,
        "stats": stats,
        "products": output_products,
        "trend_summary": {
            "top_categories": top_cats,
            "season": trend_data.get("season", ""),
            "total_queries": trend_data.get("total_queries", 0),
        },
    }

    data_dir = BASE / "data" / "channels"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_file = data_dir / f"{scan_date}.json"
    data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    rej_file = data_dir / f"{scan_date}-rejected.json"
    rej_file.write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save history
    hist_dir = BASE / "data" / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hist_file = hist_dir / f"{scan_date}.json"
    hist_data = [{
        "asin": p.get("asin", ""),
        "name": p.get("name", ""),
        "price": p.get("price", 0),
        "rank": p.get("rank"),
        "reviews": p.get("reviews"),
        "score": p.get("score", 0),
        "sources": p.get("sources", []),
        "channel": p.get("channel", ""),
    } for p in passed]
    hist_file.write_text(json.dumps(hist_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save trend data for reference
    trend_file = data_dir / f"{scan_date}-trends.json"
    trend_file.write_text(json.dumps(trend_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate HTML
    from generate_html_v2 import generate_html
    output_html = generate_html(str(data_file))

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  ✅ Done! {len(passed)} scored products in dashboard", file=sys.stderr)
    print(f"  📊 {output_html}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    print(json.dumps({
        "date": scan_date,
        "scanned": len(products),
        "passed": len(passed),
        "rejected": len(rejected),
        "channels": channel_counts,
        "top_categories": dict(top_cats),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
