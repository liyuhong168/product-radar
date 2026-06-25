#!/usr/bin/env python3
"""BSR tracking and daily sales estimation module."""

import argparse
import glob
import json
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "channels")

CATEGORY_MULTIPLIERS = {
    "kitchen": 1.2,
    "garden": 0.8,
    "pets": 1.0,
    "general": 1.0,
}


def estimate_daily_sales(bsr: int, category: str = "general") -> int:
    """Estimate daily sales from BSR rank."""
    multiplier = CATEGORY_MULTIPLIERS.get(category.lower(), 1.0)

    if bsr < 100:
        base = 1500 + (100 - bsr) * 20
    elif bsr <= 50000:
        base = 150000 / bsr
    else:
        base = max(1, 150000 / bsr)

    return max(1, int(base * multiplier))


def _detect_bsr_trend(ranks: list[int]) -> str:
    """Detect BSR trend from rank history. Returns 'improving', 'declining', or 'stable'."""
    if len(ranks) < 2:
        return "unknown"
    recent = ranks[-3:] if len(ranks) >= 3 else ranks
    diffs = [recent[i] - recent[i + 1] for i in range(len(recent) - 1)]
    avg_diff = sum(diffs) / len(diffs)
    if avg_diff > 50:
        return "improving"
    elif avg_diff < -50:
        return "declining"
    return "stable"


def enrich_radar_with_bsr(radar_json_path: str) -> dict:
    """Enrich radar JSON products with BSR-based sales estimates.

    IMPORTANT: Only uses real Amazon BSR data (bsr_rank field from scraper).
    The 'rank' field is our internal scan ranking (1-N), NOT Amazon BSR.
    Never estimate daily sales from internal rank — it produces fantasy numbers.
    """
    with open(radar_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    products = data.get("products", [])
    enriched = 0
    for p in products:
        # Only use real Amazon BSR (stored in bsr_rank, NOT rank)
        bsr_rank = p.get("bsr_rank")
        if bsr_rank is None or not isinstance(bsr_rank, int) or bsr_rank <= 0:
            # No real BSR data — skip (don't fabricate numbers)
            p["estimated_daily_sales"] = None
            p["monthly_revenue_est"] = None
            p["bsr_trend"] = "no_data"
            continue

        category = p.get("category", "general").lower()
        daily = estimate_daily_sales(bsr_rank, category)
        price = p.get("price", 0) or 0

        p["estimated_daily_sales"] = daily
        p["monthly_revenue_est"] = round(daily * price * 30, 2)
        enriched += 1

        # Check BSR history if available
        history = p.get("rank_history", [])
        if history and isinstance(history, list):
            p["bsr_trend"] = _detect_bsr_trend(history)
        else:
            p["bsr_trend"] = "unknown"

    if enriched == 0:
        print("  ⚠️ No real BSR data found — all estimates set to None")
    else:
        print(f"  ✅ Enriched {enriched}/{len(products)} products with BSR estimates")

    return data


def backfill_bsr():
    """Enrich the latest radar JSON in data/channels/ with BSR estimates."""
    pattern = os.path.join(DATA_DIR, "*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        print("No radar JSON files found.")
        return

    latest = files[-1]
    print(f"Backfilling BSR estimates: {os.path.basename(latest)}")

    data = enrich_radar_with_bsr(latest)

    with open(latest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    enriched = sum(1 for p in data.get("products", []) if "estimated_daily_sales" in p)
    total = len(data.get("products", []))
    print(f"Enriched {enriched}/{total} products with BSR estimates.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BSR tracker & daily sales estimator")
    parser.add_argument("--backfill", action="store_true", help="Enrich latest radar JSON with BSR estimates")
    args = parser.parse_args()

    if args.backfill:
        backfill_bsr()
    else:
        parser.print_help()
