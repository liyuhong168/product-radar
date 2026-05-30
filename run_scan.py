#!/usr/bin/env python3
"""
Product Radar - Main scan runner
Usage: python3 run_scan.py
"""
import json, sys, os, re
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from scanner import load_history, is_forbidden, calc_profit, score_product, generate_report
from sources.amazon_uk import fetch as fetch_amazon
from sources.tiktok_shop import fetch as fetch_tiktok
from sources.google_trends import fetch_demand_signals, extract_trending_keywords
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
    """Cross-reference Amazon products with TikTok/Google Trends/Reddit signals."""
    gtrends_lower = gtrends_text.lower() if gtrends_text else ""
    reddit_lower = reddit_text.lower() if reddit_text else ""

    # Extract trending keywords from Google Trends
    gtrends_keywords = extract_trending_keywords(gtrends_text)

    for p in products:
        name_lower = p.get("name", "").lower()
        words = [w for w in name_lower.split() if len(w) > 3]
        matched = False

        # Check Google Trends keywords - require 2+ matches for confidence
        gt_match_count = 0
        for kw in gtrends_keywords:
            if kw in name_lower:
                gt_match_count += 1
        # Also check raw text for product keywords
        for word in words[:5]:
            if len(word) > 4 and word in gtrends_lower:
                gt_match_count += 1

        if gt_match_count >= 2:
            p["google_trend"] = "rising"
            if "Google趋势" not in str(p.get("sources", [])):
                p.setdefault("sources", []).append("Google趋势")

        # Check Reddit - require specific product words (not generic)
        reddit_generic = {'that', 'this', 'with', 'from', 'have', 'been', 'your',
                          'they', 'will', 'more', 'than', 'what', 'when', 'very',
                          'just', 'like', 'would', 'could', 'should', 'about'}
        reddit_match = 0
        for word in words[:5]:
            if word in reddit_lower and len(word) > 4 and word not in reddit_generic:
                reddit_match += 1
        if reddit_match >= 2:
            if "Reddit需求" not in str(p.get("sources", [])):
                p.setdefault("sources", []).append("Reddit需求")

    return products


def match_tiktok_to_amazon(tiktok_products, amazon_products):
    """Match TikTok trending categories/keywords to Amazon products."""
    matched_count = 0

    # Build a set of all TikTok keywords (phrases and individual words)
    tiktok_keywords = set()
    for tp in tiktok_products:
        name = tp.get("name", "").lower().strip()
        # Add full phrase
        if len(name) > 3:
            tiktok_keywords.add(name)
        # Add individual words
        for word in name.split():
            if len(word) > 4:
                tiktok_keywords.add(word)

    for ap in amazon_products:
        ap_name = ap.get("name", "").lower()
        ap_words = set(ap_name.split())

        # Check for keyword overlap
        matches = 0
        for kw in tiktok_keywords:
            if kw in ap_name:
                matches += 1
            elif len(kw) > 5 and any(w.startswith(kw[:5]) for w in ap_words):
                matches += 1  # Partial match for longer keywords

        if matches >= 1:
            if "TikTok趋势" not in str(ap.get("sources", [])):
                ap.setdefault("sources", []).append("TikTok趋势")
                ap["signal"] = ap.get("signal", "") + " + TikTok验证"
                matched_count += 1

    return matched_count


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Product Radar Scan | {now}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    # Step 1: Fetch from all sources
    print("[1/5] Multi-source data collection...", file=sys.stderr)

    print("\n--- Amazon UK ---", file=sys.stderr)
    amazon_products = fetch_amazon()

    print("\n--- TikTok Shop UK ---", file=sys.stderr)
    tiktok_products = fetch_tiktok()

    print("\n--- Google Trends UK ---", file=sys.stderr)
    gtrends_text = fetch_demand_signals()

    print("\n--- Reddit Demand ---", file=sys.stderr)
    reddit_text = fetch_reddit()

    print(f"\nRaw: Amazon {len(amazon_products)} | TikTok keywords {len(tiktok_products)}", file=sys.stderr)

    # Step 2: Match TikTok keywords to Amazon products
    print("\n[2/5] TikTok → Amazon cross-match...", file=sys.stderr)
    tiktok_matched = match_tiktok_to_amazon(tiktok_products, amazon_products)
    print(f"  TikTok signals matched to {tiktok_matched} Amazon products", file=sys.stderr)

    # Step 3: Dedup
    print("\n[3/5] Dedup and merge...", file=sys.stderr)
    all_products = dedup_products(amazon_products)
    print(f"  After dedup: {len(all_products)}", file=sys.stderr)

    # Step 4: Enrich with Google Trends + Reddit
    print("\n[4/5] Google Trends + Reddit cross-validation...", file=sys.stderr)
    enriched = enrich_with_demand_signals(all_products, gtrends_text, reddit_text)

    # Count how many got Google Trends signal
    gt_count = sum(1 for p in enriched if p.get("google_trend") == "rising")
    print(f"  Google Trends signals matched to {gt_count} products", file=sys.stderr)

    # Step 5: Load history
    print("\n[5/5] Historical trend comparison...", file=sys.stderr)
    history = load_history(days=7)
    print(f"  History: {len(history)} products tracked", file=sys.stderr)

    # Generate report
    print("\nGenerating report...", file=sys.stderr)
    report_text, report_path = generate_report(enriched, history)

    print(f"\nReport saved: {report_path}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)
    print(report_text)


if __name__ == "__main__":
    main()
