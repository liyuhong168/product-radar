#!/usr/bin/env python3
"""
Product Radar - Core scanner engine
Scoring, filtering, trend detection, report generation.
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
    for kw in CONFIG["forbidden_keywords"]:
        # Use word-boundary matching to avoid false positives
        # e.g., "paint" should not match "painter" or "painters"
        import re
        pattern = r'(?<![a-z])' + re.escape(kw.strip()) + r'(?![a-z])' if kw.strip().isalpha() else re.escape(kw)
        if re.search(pattern, text):
            return True, kw

    # Volume/weight detection - use config limits
    import re
    max_ml = 100   # ≤100ml liquids OK, >100ml reject (conservative for small items)
    max_l = 0.1    # 100ml = 0.1L
    max_kg = CONFIG.get("max_weight_g", 300) / 1000  # 300g = 0.3kg

    # Volume: "2.5 litre", "10L", "500ml"
    vol_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:l\b|litre|litres|liter|liters)', text)
    if vol_match and float(vol_match.group(1)) > max_l:
        return True, f"体积 {vol_match.group(0)} (>{max_l*1000:.0f}ml)"

    ml_match = re.search(r'(\d+)\s*ml', text)
    if ml_match and int(ml_match.group(1)) > max_ml:
        return True, f"体积 {ml_match.group(0)} (>{max_ml}ml)"

    # Weight: "5kg", "500g"
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*kg', text)
    if kg_match and float(kg_match.group(1)) > max_kg:
        return True, f"重量 {kg_match.group(0)} (>{max_kg*1000:.0f}g)"

    g_match = re.search(r'(\d+)\s*(?:g\b|grams?)', text)
    if g_match and int(g_match.group(1)) > CONFIG.get("max_weight_g", 300):
        return True, f"重量 {g_match.group(0)} (>{CONFIG.get('max_weight_g', 300)}g)"

    return False, None


def calc_profit(price_gbp, category="general"):
    """Calculate profit margin for a given price."""
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
    storage = price_gbp * c["storage_rate"]
    dsc = c["digital_service_fee"]
    sourcing = c.get("sourcing_cost", 1.00)

    total_cost = vat + commission + fba + ads + returns + storage + dsc + sourcing
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
            "storage": round(storage, 2),
            "dsc": dsc,
            "sourcing": sourcing,
            "total_cost": round(total_cost, 2)
        }
    }


def score_product(product, history):
    """Score a product based on multiple signals.
    Priority: New Releases > TikTok > Google Trends >> BSR (reference only)
    """
    s = CONFIG["scoring"]
    score = 50

    name = product.get("name", "")
    asin = product.get("asin", "")
    key = asin or name.lower().strip()
    sources = product.get("sources", [])
    sources_str = str(sources).lower()

    # High priority signals (primary)
    is_new_release = "new" in sources_str or "new release" in sources_str
    is_tiktok = "tiktok" in sources_str
    is_google_rising = product.get("google_trend") == "rising"

    if is_new_release:
        score += s.get("new_releases_bonus", 25)
    if is_tiktok:
        score += s.get("tiktok_trending_bonus", 25)
    if is_google_rising:
        score += s.get("google_rising_bonus", 20)

    # Multi-source boost (strong signal)
    if len(sources) >= 2:
        score += s.get("multi_source_boost", 20)
    if len(sources) >= 3:
        score += s.get("multi_source_boost", 20)

    # BSR - reference only, low weight
    rank = product.get("rank", 999)
    if rank and rank <= 50:
        score += s.get("bsr_top50_bonus", 5)
    elif rank and rank <= 100:
        score += s.get("bsr_top100_bonus", 3)

    # Secondary signals
    if "reddit" in sources_str:
        score += s.get("reddit_mention_bonus", 5)

    reviews = product.get("reviews", 0)
    if reviews and reviews < 100:
        score += s.get("low_review_bonus", 15)

    margin = product.get("profit_margin", 0)
    if margin >= 0.30:
        score += s.get("high_margin_bonus", 10)

    # Historical trend
    if key in history:
        hist = history[key]
        if len(hist) >= 2:
            recent = hist[-1].get("rank")
            older = hist[-2].get("rank")
            if recent and older and recent < older:
                score += 15
            if len(hist) >= 3:
                scores = [h["score"] for h in hist[-3:]]
                if all(scores[i] <= scores[i+1] for i in range(len(scores)-1)):
                    score += 10

    return score


def generate_report(all_products, history):
    """Generate markdown report from scored products."""
    now = datetime.now().strftime("%Y-%m-%d")
    cfg = CONFIG

    valid = []
    rejected = []

    for p in all_products:
        forbidden, reason = is_forbidden(p.get("name", ""), p.get("category", ""))
        if forbidden:
            rejected.append({"name": p["name"], "reason": f"禁选品类: {reason}"})
            continue

        price = p.get("price", 0)
        if price < cfg["price_range"]["min"] or price > cfg["price_range"]["max"]:
            rejected.append({"name": p["name"], "reason": f"价格 \u00a3{price} 不在区间"})
            continue

        profit = calc_profit(price, p.get("category", ""))
        p["profit_margin"] = profit["margin"]
        p["net_profit"] = profit["net_profit"]
        p["cost_breakdown"] = profit["breakdown"]

        if profit["margin"] < cfg["min_profit_margin"]:
            rejected.append({"name": p["name"], "reason": f"利润率{profit['margin']*100:.1f}%<20%"})
            continue

        # Demand signal filter - must have at least one primary signal
        # (New Release, TikTok, or Google Trends)
        sources_str = str(p.get("sources", [])).lower()
        has_new_release = "new" in sources_str
        has_tiktok = "tiktok" in sources_str
        has_google = p.get("google_trend") == "rising"

        if cfg.get("demand_signal_required") and not (has_new_release or has_tiktok or has_google):
            rejected.append({"name": p["name"], "reason": "无需求信号(仅BSR,非新品/非趋势)"})
            continue

        p["score"] = score_product(p, history)
        valid.append(p)

    valid.sort(key=lambda x: -x["score"])
    max_rec = cfg["output"]["max_recommendations"]
    top = valid[:max_rec]

    lines = []
    lines.append(f"# \U0001f50d 选品雷达 | {now}\n")

    # Source summary
    source_counts = {}
    for p in all_products:
        for src in p.get("sources", []):
            source_counts[src] = source_counts.get(src, 0) + 1
    lines.append("## \U0001f4e1 数据来源")
    for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- **{src}**: {count} 条")
    lines.append(f"\n扫描: {len(all_products)} | 通过: {len(valid)} | 过滤: {len(rejected)}\n")

    # Trending up
    trending_up = []
    new_entries = []
    for p in valid:
        key = p.get("asin") or p.get("name", "").lower().strip()
        if key in history:
            hist = history[key]
            if len(hist) >= 2 and hist[-1].get("rank") and hist[-2].get("rank"):
                if hist[-1]["rank"] < hist[-2]["rank"]:
                    trending_up.append(p)
        else:
            new_entries.append(p)

    if trending_up:
        lines.append("## \U0001f4c8 排名上升中")
        for p in trending_up[:5]:
            key = p.get("asin") or p.get("name", "").lower().strip()
            hist = history.get(key, [])
            old_r = hist[-2]["rank"] if len(hist) >= 2 else "?"
            new_r = hist[-1]["rank"] if hist else "?"
            lines.append(f"- **{p['name'][:50]}** #{old_r}\u2192#{new_r} (利润率{p['profit_margin']*100:.0f}%)")
        lines.append("")

    if new_entries:
        lines.append("## \U0001f195 新发现")
        for p in new_entries[:8]:
            sources_str = "+".join(p.get("sources", [])[:2])
            lines.append(f"- **{p['name'][:50]}** ({sources_str}, 利润率{p['profit_margin']*100:.0f}%)")
        lines.append("")

    # Top recommendations
    lines.append(f"## \U0001f3c6 Top {len(top)} 推荐\n")
    for i, p in enumerate(top, 1):
        stars = "\u2b50" * min(5, max(1, (p["score"] - 40) // 10 + 1))
        lines.append(f"### {i}. {p['name'][:60]} {stars}")
        lines.append(f"- **评分**: {p['score']}")
        lines.append(f"- **来源**: {' + '.join(p.get('sources', ['未知']))}")
        if p.get("asin"):
            lines.append(f"- **ASIN**: {p['asin']}")
        lines.append(f"- **售价**: \u00a3{p['price']:.2f}")
        lines.append(f"- **竞争**: {p.get('review_info', '待验证')}")
        lines.append(f"- **利润率**: {p['profit_margin']*100:.1f}% (\u00a3{p['net_profit']:.2f})")
        bd = p.get("cost_breakdown", {})
        lines.append(f"- **成本**: VAT \u00a3{bd.get('vat',0):.2f} + 佣金 \u00a3{bd.get('commission',0):.2f} + FBA \u00a3{bd.get('fba',0):.2f} + 广告 \u00a3{bd.get('ads',0):.2f} + 采购 \u00a3{bd.get('sourcing',0):.2f}")
        lines.append(f"- **信号**: {p.get('signal', '多源验证')}")
        lines.append("")

    if rejected:
        lines.append(f"## \u274c 未通过筛选 ({len(rejected)})")
        for r in rejected[:15]:
            lines.append(f"- {r['name'][:40]} \u2192 {r['reason']}")
        lines.append("")

    # Save snapshot
    snapshot = [{
        "asin": p.get("asin", ""),
        "name": p.get("name", ""),
        "price": p.get("price", 0),
        "rank": p.get("rank"),
        "reviews": p.get("reviews"),
        "rating": p.get("rating", 0),
        "review_info": p.get("review_info", ""),
        "score": p.get("score", 0),
        "sources": p.get("sources", []),
        "profit_margin": p.get("profit_margin", 0),
        "net_profit": p.get("net_profit", 0),
        "category": p.get("category", ""),
        "signal": p.get("signal", ""),
        "cost_breakdown": p.get("cost_breakdown", {})
    } for p in top]

    snap_path = BASE / CONFIG["output"]["snapshot_dir"] / f"{now}.json"
    snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))

    hist_path = BASE / CONFIG["output"]["history_dir"] / f"{now}.json"
    all_hist = [{
        "asin": p.get("asin", ""),
        "name": p.get("name", ""),
        "price": p.get("price", 0),
        "rank": p.get("rank"),
        "reviews": p.get("reviews"),
        "score": p.get("score", 0),
        "sources": p.get("sources", [])
    } for p in valid]
    hist_path.write_text(json.dumps(all_hist, ensure_ascii=False, indent=2))

    report_text = "\n".join(lines)
    report_path = BASE / CONFIG["output"]["report_dir"] / f"report-{now}.md"
    report_path.write_text(report_text)

    return report_text, str(report_path)
