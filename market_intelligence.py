#!/usr/bin/env python3
"""
Market Intelligence Module — Supply-Demand Index + Trend Divergence
Computes supply-demand ratios per category and detects trend divergences.
"""
import json, math
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).parent


def compute_category_supply(products):
    """Compute total review count per category from Amazon scraped products.
    This represents market supply intensity — more reviews = more established competition.
    """
    cat_reviews = {}
    cat_product_count = {}
    for p in products:
        cat = p.get("category", "").lower().strip()
        if not cat:
            continue
        reviews = p.get("reviews", 0)
        cat_reviews[cat] = cat_reviews.get(cat, 0) + reviews
        cat_product_count[cat] = cat_product_count.get(cat, 0) + 1
    return cat_reviews, cat_product_count


def compute_supply_demand_ratio(cat_reviews, trend_data):
    """Compute supply-demand ratio per category.
    
    Demand = AnySearch category heat score (0-100)
    Supply = ln(total_reviews_in_category + 1)
    Ratio = demand / supply
    
    Interpretation:
    > 5 → 🌊 Deep blue ocean (high demand, low supply)
    > 3 → 💧 Light blue ocean
    > 1 → ⚖️ Balanced
    < 1 → 🔴 Red ocean (high supply relative to demand)
    """
    cat_scores = trend_data.get("category_scores", {})
    ratios = {}
    
    for cat, demand_score in cat_scores.items():
        # Try exact match, then partial match
        total_reviews = cat_reviews.get(cat, 0)
        if total_reviews == 0:
            # Try partial matching (e.g., "pets" matches "pets" in cat_reviews)
            for scraped_cat, revs in cat_reviews.items():
                if cat in scraped_cat or scraped_cat in cat:
                    total_reviews = revs
                    break
        
        supply = math.log(total_reviews + 1)  # ln(0+1)=0, ln(100+1)=4.6, ln(1000+1)=6.9
        if supply == 0:
            # No supply data for this category — can't compute ratio
            # But if demand is high, it's potentially blue ocean (no competition found)
            if demand_score >= 50:
                ratios[cat] = {"ratio": 99, "demand": demand_score, "supply": 0, "label": "🌊 无竞品", "level": "deep_blue"}
            continue
        
        ratio = demand_score / supply
        
        if ratio > 5:
            label, level = "🌊 深蓝海", "deep_blue"
        elif ratio > 3:
            label, level = "💧 浅蓝海", "light_blue"
        elif ratio > 1:
            label, level = "⚖️ 平衡", "balanced"
        else:
            label, level = "🔴 红海", "red_ocean"
        
        ratios[cat] = {
            "ratio": round(ratio, 1),
            "demand": demand_score,
            "supply": total_reviews,
            "label": label,
            "level": level,
        }
    
    return ratios


def compute_trend_divergence(trend_data, history_days=3):
    """Detect trend divergence: Google Trends (category heat) vs Amazon BSR movement.
    
    Compares current AnySearch category scores with historical data.
    If category heat is rising but BSR ranks are stable → demand-first window.
    
    Returns dict of category -> divergence info.
    """
    # Load historical trend data
    hist_dir = BASE / "data" / "channels"
    history = []
    
    for f in sorted(hist_dir.glob("*-trends.json"))[-history_days:]:
        try:
            data = json.loads(f.read_text())
            date_str = f.stem.replace("-trends", "")
            history.append({"date": date_str, "data": data})
        except (json.JSONDecodeError, Exception):
            continue
    
    if len(history) < 2:
        return {}  # Need at least 2 data points
    
    current = history[-1]["data"]
    previous = history[-2]["data"]
    
    current_scores = current.get("category_scores", {})
    previous_scores = previous.get("category_scores", {})
    
    divergences = {}
    
    for cat, current_score in current_scores.items():
        prev_score = previous_scores.get(cat, 0)
        if prev_score == 0:
            continue
        
        # Heat change rate
        heat_change = (current_score - prev_score) / max(prev_score, 1)
        
        if heat_change > 0.3:
            direction = "rising"
        elif heat_change < -0.2:
            direction = "falling"
        else:
            direction = "stable"
        
        divergences[cat] = {
            "current_heat": current_score,
            "previous_heat": prev_score,
            "heat_change_pct": round(heat_change * 100, 1),
            "direction": direction,
            "dates": [history[-2]["date"], history[-1]["date"]],
        }
    
    return divergences


def get_product_sd_score(product, sd_ratios):
    """Get supply-demand score bonus for a product based on its category."""
    name_lower = product.get("name", "").lower()
    category = product.get("category", "").lower()
    
    best_match = None
    best_ratio = 0
    
    for cat, info in sd_ratios.items():
        # Match by category field or product name keywords
        if cat in category or any(kw in name_lower for kw in cat.split("_")):
            if info["ratio"] > best_ratio:
                best_ratio = info["ratio"]
                best_match = info
    
    if not best_match:
        return 0, "", {}
    
    ratio = best_match["ratio"]
    if ratio > 5:
        return 20, "🌊 深蓝海", best_match
    elif ratio > 3:
        return 10, "💧 浅蓝海", best_match
    elif ratio > 1:
        return 0, "⚖️ 平衡", best_match
    else:
        return -15, "🔴 红海", best_match


def get_product_divergence_score(product, divergences):
    """Get trend divergence score for a product."""
    category = product.get("category", "").lower()
    
    for cat, info in divergences.items():
        if cat in category or category in cat:
            direction = info["direction"]
            if direction == "rising":
                return 15, f"📈 品类升温({info['heat_change_pct']:+.0f}%)", info
            elif direction == "falling":
                return -10, f"📉 品类降温({info['heat_change_pct']:+.0f}%)", info
    
    return 0, "", {}


def analyze_market(products, trend_data, history_days=3):
    """Full market intelligence analysis. Returns all computed data."""
    cat_reviews, cat_counts = compute_category_supply(products)
    sd_ratios = compute_supply_demand_ratio(cat_reviews, trend_data)
    divergences = compute_trend_divergence(trend_data, history_days)
    
    return {
        "category_reviews": cat_reviews,
        "category_counts": cat_counts,
        "sd_ratios": sd_ratios,
        "divergences": divergences,
    }


if __name__ == "__main__":
    # Quick test
    import sys
    data_file = sys.argv[1] if len(sys.argv) > 1 else str(BASE / "data/channels/2026-06-04.json")
    data = json.loads(Path(data_file).read_text())
    products = data.get("products", [])
    
    trend_file = data_file.replace(".json", "-trends.json")
    trend_data = json.loads(Path(trend_file).read_text()) if Path(trend_file).exists() else {}
    
    result = analyze_market(products, trend_data)
    
    print("=== Supply-Demand Ratios ===")
    for cat, info in sorted(result["sd_ratios"].items(), key=lambda x: -x[1]["ratio"]):
        print(f"  {info['label']} {cat}: ratio={info['ratio']} demand={info['demand']} supply={info['supply']}")
    
    print("\n=== Trend Divergences ===")
    for cat, info in result["divergences"].items():
        print(f"  {cat}: {info['direction']} ({info['heat_change_pct']:+.0f}%) {info['previous_heat']}→{info['current_heat']}")
