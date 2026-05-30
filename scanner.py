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
        if kw in text:
            return True, kw
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
    sourcing = 1.50

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
    """Score a product based on multiple signals."""
    s = CONFIG["scoring"]
    score = 50

    name = product.get("name", "")
    asin = product.get("asin", "")
    key = asin or name.lower().strip()

    sources = product.get("sources", [])
    if len(sources) >= 2:
        score += s["multi_source_boost"]
    if len(sources) >= 3:
        score += s["multi_source_boost"]

    rank = product.get("rank", 999)
    if rank and rank <= 50:
        score += s["bsr_top50_bonus"]
    elif rank and rank <= 100:
        score += s["bsr_top100_bonus"]

    if "tiktok" in str(sources).lower():
        score += s["tiktok_trending_bonus"]

    if product.get("google_trend") == "rising":
        score += s["google_rising_bonus"]

    if "reddit" in str(sources).lower():
        score += s["reddit_mention_bonus"]

    reviews = product.get("reviews", 0)
    if reviews and reviews < 100:
        score += s["low_review_bonus"]

    margin = product.get("profit_margin", 0)
    if margin >= 0.30:
        score += s["high_margin_bonus"]

    if key in history:
        hist = history[key]
        if len(hist) >= 2:
            recent = hist[-1]["rank"]
            older = hist[-2]["rank"]
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
