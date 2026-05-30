#!/usr/bin/env python3
"""
Product Radar - Main scan runner
Scans Amazon UK, TikTok Shop UK, Google Trends, Reddit for product opportunities.
Usage: python3 run_scan.py
"""
import json, sys, os
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from scanner import load_history, is_forbidden, calc_profit, score_product, generate_report
from sources.amazon_uk import fetch as fetch_amazon
from sources.tiktok_shop import fetch as fetch_tiktok
from sources.google_trends import fetch_demand_signals as fetch_gtrends
from sources.reddit_demand import fetch_demand_signals as fetch_reddit


def dedup_products(all_products):
    """Merge products found by multiple sources."""
    by_asin = {}
    by_name = {}
    merged = []

    for p in all_products:
        asin = p.get("asin", "")
        name_key = p.get("name", "").lower().strip()[:40]

        if asin and asin in by_asin:
            existing = by_asin[asin]
            for src in p.get("sources", []):
                if src not in existing["sources"]:
                    existing["sources"].append(src)
            if p.get("price") and not existing.get("price"):
                existing["price"] = p["price"]
            if p.get("reviews") and not existing.get("reviews"):
                existing["reviews"] = p["reviews"]
            continue

        if name_key and name_key in by_name:
            existing = by_name[name_key]
            for src in p.get("sources", []):
                if src not in existing["sources"]:
                    existing["sources"].append(src)
            continue

        if asin:
            by_asin[asin] = p
        if name_key:
            by_name[name_key] = p
        merged.append(p)

    return merged


def enrich_with_demand_signals(products, gtrends_text, reddit_text):
    """Cross-reference products with demand signals."""
    gtrends_lower = gtrends_text.lower() if gtrends_text else ""
    reddit_lower = reddit_text.lower() if reddit_text else ""

    for p in products:
        name_lower = p.get("name", "").lower()
        words = [w for w in name_lower.split() if len(w) > 3]
        for word in words[:3]:
            if word in gtrends_lower:
                p["google_trend"] = "rising"
                p["signal"] = p.get("signal", "") + " + Google趋势"
                break
        for word in words[:3]:
            if word in reddit_lower:
                p["reddit_context"] = "Reddit用户讨论中"
                p["signal"] = p.get("signal", "") + " + Reddit需求"
                if "reddit" not in str(p.get("sources", [])):
                    p.setdefault("sources", []).append("Reddit需求")
                break

    return products


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Product Radar Scan | {now}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    # Step 1: Fetch from all sources
    print("[1/5] Multi-source data collection...", file=sys.stderr)
    all_products = []

    print("\n--- Amazon UK ---", file=sys.stderr)
    amazon_products = fetch_amazon()
    all_products.extend(amazon_products)

    print("\n--- TikTok Shop UK ---", file=sys.stderr)
    tiktok_products = fetch_tiktok()
    all_products.extend(tiktok_products)

    print("\n--- Google Trends UK ---", file=sys.stderr)
    gtrends_text = fetch_gtrends()

    print("\n--- Reddit Demand ---", file=sys.stderr)
    reddit_text = fetch_reddit()

    amazon_count = len([p for p in all_products if any("Amazon" in s for s in p.get("sources", []))])
    tiktok_count = len([p for p in all_products if any("TikTok" in s for s in p.get("sources", []))])
    print(f"\nRaw data: Amazon {amazon_count} | TikTok {tiktok_count}", file=sys.stderr)

    # Step 2: Dedup and merge
    print("\n[2/5] Dedup and merge...", file=sys.stderr)
    merged = dedup_products(all_products)
    print(f"  After dedup: {len(merged)}", file=sys.stderr)

    # Step 3: Enrich with demand signals
    print("\n[3/5] Demand signal cross-validation...", file=sys.stderr)
    enriched = enrich_with_demand_signals(merged, gtrends_text, reddit_text)

    # Step 4: Load history for trend detection
    print("\n[4/5] Historical trend comparison...", file=sys.stderr)
    history = load_history(days=7)
    print(f"  History: {len(history)} products tracked", file=sys.stderr)

    # Step 5: Generate report
    print("\n[5/5] Generating report...", file=sys.stderr)
    report_text, report_path = generate_report(enriched, history)

    print(f"\nReport saved: {report_path}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    # Output report to stdout
    print(report_text)


if __name__ == "__main__":
    main()
