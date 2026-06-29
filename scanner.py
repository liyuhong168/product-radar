#!/usr/bin/env python3
"""Product Radar - Core utilities
Provides: is_forbidden (keyword/category filter), calc_profit (margin calculator).
Scoring is handled by scoring_engine.py.
"""
import json, os, sys, re
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent
CONFIG = json.loads((BASE / "config.json").read_text())


def load_history(days=7):
    """Load recent snapshots for trend detection."""
    hist_dir = BASE / CONFIG["output"]["history_dir"]
    history = {}
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
                        "price": item.get("price"),
                        "reviews": item.get("reviews"),
                        "score": item.get("score", 0)
                    })
        except (ValueError, json.JSONDecodeError):
            continue
    return history


def is_forbidden(name, category=""):
    """Check if product matches forbidden categories."""
    text = (name + " " + category).lower()

    # --- Shared keyword sets ---
    PET_KEYWORDS = {'cat', 'dog', 'pet', 'kitten', 'puppy', 'ferret', 'rabbit', 'hamster', 'catnip', 'silvervine'}
    PARTY_KEYWORDS = {'party', 'decoration', 'costume', 'pirate', 'halloween', 'christmas', 'birthday', 'fancy dress', 'bachelorette', 'wedding'}
    PARTY_EXEMPT_KW = {'kids', 'dress', 'shirt', 'children', 'trousers'}  # clothing keywords exempted when party context

    has_party = any(kw in text for kw in PARTY_KEYWORDS)

    # --- Special handling: "toy" ---
    has_toy = bool(re.search(r'(?<![a-z])toy(?:s)?(?![a-z])', text))
    if has_toy:
        has_pet = any(re.search(r'(?<![a-z])' + re.escape(kw) + r'(?![a-z])', text) for kw in PET_KEYWORDS)
        if not has_pet and not has_party:
            return True, "toy (非宠物/节日)"

    # --- Oversized bathroom products (too large for FBA small standard) ---
    OVERSIZE_HINTS = {'large capacity', 'extra large', '6 slot', '6 slots', '7 slot', '7 slots',
                      '8 slot', '8 slots', '9 slot', '9 slots', '10 slot', '10 slots',
                      'extra tall', 'super large', 'jumbo'}
    BATHROOM_HINTS = {'toothbrush', 'bathroom', 'shower', 'holder', 'organiser', 'organizer'}
    is_oversize_bathroom = (
        any(kw in text for kw in OVERSIZE_HINTS) and
        any(kw in text for kw in BATHROOM_HINTS)
    )

    # --- Main keyword loop ---
    for kw in CONFIG["forbidden_keywords"]:
        if kw == "toy":
            continue
        # Party exemption: skip clothing keywords for party/costume items
        if kw in PARTY_EXEMPT_KW and has_party:
            continue
        # Oversize bathroom filter
        if kw == "electric" and is_oversize_bathroom:
            return True, f"oversize: {kw} + 体积过大"
        # Word-boundary matching
        pattern = r'(?<![a-z])' + re.escape(kw.strip()) + r'(?![a-z])' if kw.strip().isalpha() else re.escape(kw)
        if re.search(pattern, text):
            return True, kw

    # --- Volume/weight detection ---
    max_ml = 0
    max_l = 0
    max_kg = CONFIG.get("max_weight_g", 300) / 1000
    CONTAINER_KEYWORDS = {'bottle', 'flask', 'tumbler', 'jug', 'carafe', 'pitcher', 'thermos', 'canteen', 'watering can'}
    is_container = any(kw in text for kw in CONTAINER_KEYWORDS)

    if not is_container:
        vol_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:l\b|litre|litres|liter|liters)', text)
        if vol_match and float(vol_match.group(1)) > max_l:
            return True, f"体积 {vol_match.group(0)} (>{max_l*1000:.0f}ml)"
        ml_match = re.search(r'(\d+)\s*ml', text)
        if ml_match and int(ml_match.group(1)) > max_ml:
            return True, f"体积 {ml_match.group(0)} (>{max_ml}ml)"

    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*kg', text)
    if kg_match and float(kg_match.group(1)) > max_kg:
        return True, f"重量 {kg_match.group(0)} (>{max_kg*1000:.0f}g)"
    g_match = re.search(r'(\d+)\s*(?:g\b|grams?)', text)
    if g_match and int(g_match.group(1)) > CONFIG.get("max_weight_g", 300):
        return True, f"重量 {g_match.group(0)} (>{CONFIG.get('max_weight_g', 300)}g)"

    return False, None


def calc_profit(price_gbp, category="general"):
    c = CONFIG["cost_structure"]
    comm_rate = c["commission_rate"]
    if "home" in category.lower() or "kitchen" in category.lower():
        comm_rate = c["commission_home"]
    elif "pet" in category.lower():
        comm_rate = c["commission_pets"]

    vat = price_gbp * c["vat_rate"]
    commission = price_gbp * comm_rate
    fba = c["fba_small_standard"]
    ads = price_gbp * c["ad_rate"]
    returns = price_gbp * c["return_rate"]
    sourcing = c.get("sourcing_cost", 0.80)

    total_cost = vat + commission + fba + ads + returns + sourcing
    net_profit = price_gbp - total_cost
    margin = net_profit / price_gbp if price_gbp > 0 else 0
    return {
        "net_profit": round(net_profit, 2),
        "margin": round(margin, 3),
        "breakdown": {
            "vat": round(vat, 2),
            "commission": round(commission, 2),
            "fba": fba,
            "ads": round(ads, 2),
            "returns": round(returns, 2),
            "sourcing": sourcing,
            "total_cost": round(total_cost, 2)
        }
    }
