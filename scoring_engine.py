#!/usr/bin/env python3
"""
Product Radar v2 - Multi-factor scoring engine
Combines signals from all sources into a weighted score.
"""
import json, sys
from pathlib import Path

BASE = Path(__file__).parent
CONFIG = json.loads((BASE / "config.json").read_text())


def score_product(product, trend_data=None, history=None):
    """Calculate a multi-factor weighted score for a product.
    
    Scoring dimensions:
    1. Source signals (where the product was found)
    2. Trend signals (AnySearch, TikTok, Google Trends)
    3. Competition signals (review count, rating)
    4. Profit signals (margin %)
    5. Historical signals (rank trajectory)
    
    Returns: (total_score, score_breakdown)
    """
    s = CONFIG.get("scoring", {})
    breakdown = {}
    total = 50  # Base score

    name = product.get("name", "").lower()
    sources = [x.lower() for x in product.get("sources", [])]
    sources_str = " ".join(sources)
    reviews = product.get("reviews", 0)
    rating = product.get("rating", 0)
    margin = product.get("profit_margin", 0)
    channel = product.get("channel", "")

    # === 1. Source Signals ===
    if "new_releases" in channel or "new" in sources_str:
        pts = s.get("new_releases_bonus", 25)
        total += pts
        breakdown["新品榜"] = pts

    if "tiktok" in sources_str:
        pts = s.get("tiktok_trending_bonus", 25)
        total += pts
        breakdown["TikTok趋势"] = pts

    if product.get("google_trend") == "rising":
        pts = s.get("google_rising_bonus", 20)
        total += pts
        breakdown["Google趋势↑"] = pts

    if "reddit" in sources_str:
        pts = s.get("reddit_mention_bonus", 10)
        total += pts
        breakdown["Reddit需求"] = pts

    # === 2. AnySearch Trend Signals ===
    if trend_data:
        name_lower = product.get("name", "").lower()
        category = product.get("category", "").lower()
        cat_scores = trend_data.get("category_scores", {})
        cat_evidence = trend_data.get("category_evidence", {})

        for cat, tscore in cat_scores.items():
            if cat in category or any(kw in name_lower for kw in cat_evidence.get(cat, [])):
                if tscore >= 70:
                    pts = 20
                    total += pts
                    breakdown[f"AnySearch热门({cat})"] = pts
                elif tscore >= 40:
                    pts = 10
                    total += pts
                    breakdown[f"AnySearch趋势({cat})"] = pts
                break  # Only count best match

        # Trending keyword bonus
        trending_words = {"viral", "tiktok", "trending", "must have", "eco friendly",
                         "reusable", "portable", "mini", "compact", "multifunction"}
        for tw in trending_words:
            if tw in name_lower:
                pts = 5
                total += pts
                breakdown[f"趋势词({tw})"] = pts
                break

    # === 3. Multi-source boost ===
    unique_sources = len(set(sources))
    if unique_sources >= 3:
        pts = s.get("multi_source_boost", 20) + 5
        total += pts
        breakdown["三源验证"] = pts
    elif unique_sources >= 2:
        pts = s.get("multi_source_boost", 15)
        total += pts
        breakdown["双源验证"] = pts

    # === 4. Competition Signals ===
    if reviews and reviews < 50:
        pts = s.get("low_review_bonus", 15) + 5
        total += pts
        breakdown["超低竞争(<50)"] = pts
    elif reviews and reviews < 100:
        pts = s.get("low_review_bonus", 15)
        total += pts
        breakdown["低竞争(<100)"] = pts
    elif reviews and reviews < 300:
        pts = 5
        total += pts
        breakdown["中等竞争(<300)"] = pts

    if rating and rating >= 4.5:
        pts = 5
        total += pts
        breakdown["高评分(≥4.5)"] = pts

    # === 5. Profit Signals ===
    if margin >= 0.35:
        pts = s.get("high_margin_bonus", 10) + 5
        total += pts
        breakdown["超高利润(≥35%)"] = pts
    elif margin >= 0.30:
        pts = s.get("high_margin_bonus", 10)
        total += pts
        breakdown["高利润(≥30%)"] = pts
    elif margin >= 0.25:
        pts = 5
        total += pts
        breakdown["较好利润(≥25%)"] = pts

    # === 6. Historical Signals ===
    if history:
        key = product.get("asin") or product.get("name", "").lower().strip()
        if key in history:
            hist = history[key]
            if len(hist) >= 2:
                recent_rank = hist[-1].get("rank")
                older_rank = hist[-2].get("rank")
                if recent_rank and older_rank and recent_rank < older_rank:
                    pts = 15
                    total += pts
                    breakdown["排名上升"] = pts
                # Consistent improvement
                if len(hist) >= 3:
                    scores = [h.get("score", 0) for h in hist[-3:]]
                    if all(scores[i] <= scores[i+1] for i in range(len(scores)-1)):
                        pts = 10
                        total += pts
                        breakdown["持续上升"] = pts

    return total, breakdown


def score_all_products(products, trend_data=None, history=None):
    """Score all products and add score fields."""
    for p in products:
        score, breakdown = score_product(p, trend_data, history)
        p["score"] = score
        p["score_breakdown"] = breakdown

        # Generate star rating (1-5 stars based on score)
        if score >= 100:
            p["stars"] = 5
        elif score >= 85:
            p["stars"] = 4
        elif score >= 70:
            p["stars"] = 3
        elif score >= 55:
            p["stars"] = 2
        else:
            p["stars"] = 1

    # Sort by score descending
    products.sort(key=lambda x: -x.get("score", 0))
    return products


def get_score_label(score):
    """Return a human-readable label for a score."""
    if score >= 100:
        return "🔥 强烈推荐", "#FF2D55"
    elif score >= 85:
        return "⭐ 值得关注", "#FF9500"
    elif score >= 70:
        return "👍 可以考虑", "#007AFF"
    elif score >= 55:
        return "👀 待观察", "#8e8e93"
    else:
        return "💤 优先级低", "#c7c7cc"


if __name__ == "__main__":
    # Test scoring
    test_product = {
        "name": "Kitchen Storage Organizer Box",
        "category": "Kitchen",
        "channel": "new_releases",
        "sources": ["TikTok趋势", "Google趋势"],
        "google_trend": "rising",
        "reviews": 45,
        "rating": 4.3,
        "profit_margin": 0.32,
        "price": 7.99,
    }
    score, breakdown = score_product(test_product)
    print(f"Score: {score}")
    print(f"Breakdown: {json.dumps(breakdown, ensure_ascii=False, indent=2)}")
