#!/usr/bin/env python3
"""platform_search.py — Build a client-side search index for platform.html.

Combines discovery insights + channel scan products into a single searchable JSON.
Embeds into platform.html for instant client-side filtering.

Usage: python3 platform_search.py > output/search_index.json
"""
import json, sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent


def build_search_index():
    """Build a unified search index from all available data."""
    entries = []

    # Discovery keywords
    disc_dir = BASE / "data" / "discovery"
    if disc_dir.exists():
        for f in sorted(disc_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for ins in data.get("insights", []):
                    entries.append({
                        "type": "discovery",
                        "keyword": ins.get("keyword", ""),
                        "keyword_cn": ins.get("keyword_cn", ""),
                        "category": "",
                        "price": 0,
                        "score": ins.get("trend_score", 0),
                        "direction": ins.get("trend_direction", ""),
                        "date": data.get("scan_date", ""),
                        "reason": ins.get("reason", ""),
                        "action": ins.get("action", ""),
                    })
            except (json.JSONDecodeError, KeyError):
                continue

    # Radar products (latest per date)
    channels_dir = BASE / "data" / "channels"
    if channels_dir.exists():
        seen_dates = set()
        for f in sorted(channels_dir.glob("*.json"), reverse=True):
            if "rejected" in f.name or "trends" in f.name:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                scan_date = data.get("scan_date", "")
                if scan_date in seen_dates:
                    continue
                seen_dates.add(scan_date)
                for p in data.get("products", []):
                    entries.append({
                        "type": "radar",
                        "keyword": p.get("name", "")[:80],
                        "keyword_cn": "",
                        "category": p.get("category", ""),
                        "price": p.get("price", 0),
                        "score": p.get("score", 0),
                        "direction": "",
                        "date": scan_date,
                        "reason": p.get("signal_label", ""),
                        "action": "",
                        "asin": p.get("asin", ""),
                        "reviews": p.get("reviews", 0),
                        "rating": p.get("rating", 0),
                        "profit_margin": p.get("profit_margin", 0),
                    })
            except (json.JSONDecodeError, KeyError):
                continue

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": len(entries),
        "entries": entries,
    }


if __name__ == "__main__":
    index = build_search_index()
    output = json.dumps(index, ensure_ascii=False, indent=2)
    if "--stats" in sys.argv:
        disc = sum(1 for e in index["entries"] if e["type"] == "discovery")
        radar = sum(1 for e in index["entries"] if e["type"] == "radar")
        cats = set(e["category"] for e in index["entries"] if e["category"])
        print(f"Total: {index['total']} entries ({disc} discovery, {radar} radar)")
        print(f"Categories: {len(cats)}")
    else:
        print(output)
