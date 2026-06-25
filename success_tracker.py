#!/usr/bin/env python3
"""success_tracker.py — Track selection success rate metrics.

Reads all discovery JSONs + competitor data to calculate:
- discovery_count: total keywords discovered
- adopted_count: keywords with status updated (from Bitable if available)
- listed_count: products actually listed on Amazon
- keyword_hit_rate: % of discoveries that led to action

Usage: python3 success_tracker.py [--json]
"""
import json, os, sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent


def calculate_metrics():
    """Calculate selection pipeline metrics from available data."""
    disc_dir = BASE / "data" / "discovery"
    comp_dir = BASE / "data" / "competitors"
    channels_dir = BASE / "data" / "channels"

    metrics = {
        "discovery_count": 0,
        "adopted_count": 0,
        "listed_count": 0,
        "keyword_hit_rate": 0.0,
        "radar_total_scanned": 0,
        "radar_total_passed": 0,
        "unique_keywords": set(),
        "top_scored_keyword": None,
        "rising_trends": 0,
    }

    # Discovery metrics
    if disc_dir.exists():
        all_keywords = []
        for f in sorted(disc_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                insights = data.get("insights", [])
                metrics["discovery_count"] += len(insights)
                for ins in insights:
                    kw = ins.get("keyword", "")
                    score = ins.get("trend_score", 0)
                    direction = ins.get("trend_direction", "")
                    all_keywords.append({"keyword": kw, "score": score, "direction": direction, "date": data.get("scan_date", "")})
                    if direction == "rising":
                        metrics["rising_trends"] += 1
            except (json.JSONDecodeError, KeyError):
                continue

        metrics["unique_keywords"] = len(set(kw["keyword"] for kw in all_keywords))
        if all_keywords:
            best = max(all_keywords, key=lambda x: x["score"])
            metrics["top_scored_keyword"] = {
                "keyword": best["keyword"],
                "score": best["score"],
                "date": best["date"],
            }

    # Radar metrics
    if channels_dir.exists():
        for f in sorted(channels_dir.glob("*.json")):
            if "rejected" in f.name or "trends" in f.name:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                stats = data.get("stats", {})
                metrics["radar_total_scanned"] += stats.get("total_scanned", 0)
                metrics["radar_total_passed"] += stats.get("passed_filter", 0)
            except (json.JSONDecodeError, KeyError):
                continue

    # Competitor/listed metrics
    if comp_dir.exists():
        asins_seen = set()
        for d in comp_dir.iterdir():
            if d.is_dir():
                asins_seen.add(d.name)
        metrics["listed_count"] = len(asins_seen)

    # Hit rate
    if metrics["discovery_count"] > 0:
        metrics["keyword_hit_rate"] = round(
            (metrics["adopted_count"] + metrics["listed_count"]) / metrics["discovery_count"], 3
        )

    # Convert set to int for JSON serialization
    metrics["unique_keywords"] = metrics["unique_keywords"] if isinstance(metrics["unique_keywords"], int) else len(metrics["unique_keywords"])

    return metrics


if __name__ == "__main__":
    metrics = calculate_metrics()
    if "--json" in sys.argv:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print("📊 选品成功率指标")
        print(f"  发现关键词总数: {metrics['discovery_count']}")
        print(f"  唯一关键词: {metrics['unique_keywords']}")
        print(f"  上升趋势: {metrics['rising_trends']}")
        print(f"  已采纳: {metrics['adopted_count']}")
        print(f"  已上架: {metrics['listed_count']}")
        print(f"  命中率: {metrics['keyword_hit_rate']*100:.1f}%")
        print(f"  雷达扫描: {metrics['radar_total_scanned']} → 通过 {metrics['radar_total_passed']}")
        if metrics["top_scored_keyword"]:
            t = metrics["top_scored_keyword"]
            print(f"  最高评分: {t['keyword']} ({t['score']}) — {t['date']}")
