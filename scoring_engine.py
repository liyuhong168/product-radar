#!/usr/bin/env python3
"""
Product Radar v2 - Multi-factor scoring engine v2
Includes: Amazon (New/BSR/Wished/Gifts), TikTok, HotUKDeals, Temu, Etsy, YouTube, Google Trends, Reddit
"""
import json, sys
from pathlib import Path

BASE = Path(__file__).parent
CONFIG = json.loads((BASE / "config.json").read_text())

# Scoring weights - easily tunifiable
WEIGHTS = {
    # Source signals
    "new_releases": 25,      # Amazon New Releases
    "wished": 20,            # Amazon Most Wished For (demand signal)
    "gifts": 15,             # Amazon Gift Ideas
    "tiktok": 25,            # TikTok trend match
    "google_rising": 20,     # Google Trends rising
    "reddit": 10,            # Reddit demand
    "hotukdeals": 15,        # HotUKDeals popular
    "temu": 15,              # Temu trending
    "etsy": 10,              # Etsy trending
    "youtube": 10,           # YouTube haul/review

    # Multi-source boost
    "dual_source": 15,
    "triple_source": 25,

    # Competition
    "ultra_low_compete": 20, # <50 reviews
    "low_compete": 15,       # 50-100 reviews
    "mid_compete": 5,        # 100-300 reviews

    # Profit
    "ultra_margin": 15,      # >=35%
    "high_margin": 10,       # >=30%
    "good_margin": 5,        # >=25%

    # Rating
    "high_rating": 5,        # >=4.5 stars

    # AnySearch trend
    "hot_category": 20,      # category heat >=70
    "trend_category": 10,    # category heat 40-69
    "demand_keyword": 8,     # trending keyword match
    "cross_validated": 5,    # cross-source category validation

    # History
    "rank_improving": 15,
    "consistent_growth": 10,
}


def score_product(product, trend_data=None, history=None):
    """Calculate multi-factor weighted score."""
    breakdown = {}
    total = 50  # Base

    name = product.get("name", "").lower()
    sources = [x.lower() for x in product.get("sources", [])]
    sources_str = " ".join(sources)
    reviews = product.get("reviews", 0)
    rating = product.get("rating", 0)
    margin = product.get("profit_margin", 0)
    channel = product.get("channel", "")

    # === Source Signals ===
    if "new_releases" in channel:
        pts = WEIGHTS["new_releases"]
        total += pts; breakdown["🆕 新品榜"] = pts

    if "wished" in channel:
        pts = WEIGHTS["wished"]
        total += pts; breakdown["💝 心愿榜"] = pts

    if "gifts" in channel:
        pts = WEIGHTS["gifts"]
        total += pts; breakdown["🎁 送礼榜"] = pts

    if "tiktok" in sources_str:
        pts = WEIGHTS["tiktok"]
        total += pts; breakdown["🎵 TikTok"] = pts

    if product.get("google_trend") == "rising":
        pts = WEIGHTS["google_rising"]
        total += pts; breakdown["📊 Google↑"] = pts

    if "reddit" in sources_str:
        pts = WEIGHTS["reddit"]
        total += pts; breakdown["💬 Reddit"] = pts

    if any("hotukdeals" in s for s in sources):
        pts = WEIGHTS["hotukdeals"]
        total += pts; breakdown["🔥 HotUKDeals"] = pts

    if any("temu" in s for s in sources):
        pts = WEIGHTS["temu"]
        total += pts; breakdown["🛒 Temu"] = pts

    if any("etsy" in s for s in sources):
        pts = WEIGHTS["etsy"]
        total += pts; breakdown["🎨 Etsy"] = pts

    if any("youtube" in s for s in sources):
        pts = WEIGHTS["youtube"]
        total += pts; breakdown["▶️ YouTube"] = pts

    # === Multi-source boost ===
    unique_sources = len(set(sources))
    if unique_sources >= 3:
        pts = WEIGHTS["triple_source"]
        total += pts; breakdown["🔗 三源验证"] = pts
    elif unique_sources >= 2:
        pts = WEIGHTS["dual_source"]
        total += pts; breakdown["🔗 双源验证"] = pts

    # === AnySearch Trend Signals ===
    if trend_data:
        cat_scores = trend_data.get("category_scores", {})
        cat_evidence = trend_data.get("category_evidence", {})
        cross_validated = trend_data.get("cross_validated", {})
        category = product.get("category", "").lower()

        for cat, tscore in cat_scores.items():
            if cat in category or any(kw in name for kw in cat_evidence.get(cat, [])):
                if tscore >= 70:
                    label = "🔥 多源热门" if cat in cross_validated else "🔥 热门品类"
                    pts = WEIGHTS["hot_category"]
                    if cat in cross_validated:
                        pts += cross_validated[cat] * 3
                    total += pts; breakdown[label + f"({cat})"] = pts
                elif tscore >= 40:
                    pts = WEIGHTS["trend_category"]
                    total += pts; breakdown[f"📈 趋势({cat})"] = pts
                break

        # Demand keywords
        for kw in trend_data.get("demand_keywords", []):
            if kw in name:
                pts = WEIGHTS["demand_keyword"]
                total += pts; breakdown[f"✨ 热词"] = pts
                break

    # === Competition ===
    if reviews and reviews < 50:
        pts = WEIGHTS["ultra_low_compete"]
        total += pts; breakdown["🟢 超低竞争"] = pts
    elif reviews and reviews < 100:
        pts = WEIGHTS["low_compete"]
        total += pts; breakdown["🟡 低竞争"] = pts
    elif reviews and reviews < 300:
        pts = WEIGHTS["mid_compete"]
        total += pts; breakdown["⚪ 中等竞争"] = pts

    if rating and rating >= 4.5:
        pts = WEIGHTS["high_rating"]
        total += pts; breakdown["⭐ 高评分"] = pts

    # === Profit ===
    if margin >= 0.35:
        pts = WEIGHTS["ultra_margin"]
        total += pts; breakdown["💰 超高利润"] = pts
    elif margin >= 0.30:
        pts = WEIGHTS["high_margin"]
        total += pts; breakdown["💰 高利润"] = pts
    elif margin >= 0.25:
        pts = WEIGHTS["good_margin"]
        total += pts; breakdown["💰 较好利润"] = pts

    # === Seasonal ===
    from datetime import datetime
    month = datetime.now().month
    season = "summer" if month in (6,7,8) else "winter" if month in (12,1,2) else "spring" if month in (3,4,5) else "autumn"
    seasonal_cfg = CONFIG.get("seasonal_categories", {})
    hot_kw = set(kw.lower() for kw in seasonal_cfg.get(f"{season}_hot", []))
    
    name_for_season = product.get("name", "").lower() + " " + product.get("category", "").lower()
    is_seasonal_hot = any(kw in name_for_season for kw in hot_kw)
    is_off_season = product.get("off_season", False)
    
    if is_seasonal_hot and not is_off_season:
        pts = 15
        total += pts; breakdown[f"🌴 当季热门({season})"] = pts
    
    if is_off_season:
        pts = -30
        total += pts; breakdown["❄️ 过季降权"] = pts

    # === History ===
    if history:
        key = product.get("asin") or product.get("name", "").lower().strip()
        if key in history:
            hist = history[key]
            if len(hist) >= 2:
                recent = hist[-1].get("rank")
                older = hist[-2].get("rank")
                if recent and older and recent < older:
                    pts = WEIGHTS["rank_improving"]
                    total += pts; breakdown["📈 排名上升"] = pts
                if len(hist) >= 3:
                    scores = [h.get("score", 0) for h in hist[-3:]]
                    if all(scores[i] <= scores[i+1] for i in range(len(scores)-1)):
                        pts = WEIGHTS["consistent_growth"]
                        total += pts; breakdown["📊 持续上升"] = pts

    return total, breakdown


def score_all_products(products, trend_data=None, history=None):
    """Score all products and add score fields."""
    for p in products:
        score, breakdown = score_product(p, trend_data, history)
        p["score"] = score
        p["score_breakdown"] = breakdown

        if score >= 120:
            p["stars"] = 5
        elif score >= 100:
            p["stars"] = 4
        elif score >= 80:
            p["stars"] = 3
        elif score >= 60:
            p["stars"] = 2
        else:
            p["stars"] = 1

    products.sort(key=lambda x: -x.get("score", 0))
    return products


def get_score_label(score):
    if score >= 120: return "🔥 强烈推荐", "#FF2D55"
    elif score >= 100: return "⭐ 值得关注", "#FF9500"
    elif score >= 80: return "👍 可以考虑", "#007AFF"
    elif score >= 60: return "👀 待观察", "#8e8e93"
    else: return "💤 优先级低", "#c7c7cc"
