#!/usr/bin/env python3
"""
Product Radar v2 - Multi-source Channel Aggregation
Sources: Amazon (New/BSR/Wished/Gifts), TikTok, HotUKDeals, Temu, Etsy, YouTube, Google Trends, Reddit
"""
import json, sys, os
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from scanner import is_forbidden, calc_profit
from sources.amazon_uk import fetch as fetch_amazon
from sources.tiktok_shop import fetch as fetch_tiktok
from sources.google_trends import fetch_demand_signals, extract_trending_keywords
from sources.reddit_demand import fetch_demand_signals as fetch_reddit
from sources.anysearch_trends import fetch_trend_signals
from scoring_engine import score_all_products
from market_intelligence import analyze_market, get_product_sd_score, get_product_divergence_score
from gap_opportunity import detect_gaps


def match_keywords_to_products(keywords, products, source_tag):
    """Improved keyword-to-product matcher with word boundary and multi-hit requirement."""
    import re
    kw_set = set()
    kw_phrases = set()
    for kw_item in keywords:
        name = kw_item.get("name", "").lower().strip() if isinstance(kw_item, dict) else str(kw_item).lower().strip()
        if len(name) > 4:
            kw_phrases.add(name)  # Full phrase match
        for word in name.split():
            word = word.strip()
            if len(word) >= 5 and word.isalpha():  # Only real words, min 5 chars
                kw_set.add(word)

    matched = []
    for p in products:
        p_name = p.get("name", "").lower()
        # Word boundary matching for single words
        word_hits = 0
        for kw in kw_set:
            if re.search(r'(?<![a-z])' + re.escape(kw) + r'(?![a-z])', p_name):
                word_hits += 1
        # Phrase matching (more reliable)
        phrase_hits = sum(1 for kw in kw_phrases if kw in p_name)
        total_hits = word_hits + phrase_hits * 2  # Phrases count double

        if total_hits >= 2:  # Require at least 2 signal strength
            if source_tag not in p.get("sources", []):
                p.setdefault("sources", []).append(source_tag)
            matched.append(p)
    return matched


def enrich_from_trend_data(products, trend_data):
    """Add trend-based signals to products (HotUKDeals, Temu, Etsy, YouTube).
    Uses improved matching: requires category keyword in product name, not just category field."""
    source_signals = trend_data.get("source_signals", {})

    source_map = {
        "hotukdeals": "HotUKDeals热帖",
        "temu": "Temu热销",
        "etsy": "Etsy趋势",
        "youtube": "YouTube种草",
    }

    # Build keyword sets per source from trend data
    demand_keywords = set()
    for kw in trend_data.get("demand_keywords", []):
        if len(kw) > 4:
            demand_keywords.add(kw.lower())

    for source_key, source_tag in source_map.items():
        if source_key in source_signals:
            cats = source_signals[source_key]
            for p in products:
                name_lower = p.get("name", "").lower()
                category = p.get("category", "").lower()
                # Match: keyword must appear in product NAME (not just category)
                matched = False
                for cat in cats:
                    cat_lower = cat.lower() if isinstance(cat, str) else str(cat).lower()
                    if len(cat_lower) >= 5 and cat_lower in name_lower:
                        matched = True
                        break
                    # Also check category field for exact category match
                    if len(cat_lower) >= 5 and cat_lower in category:
                        # But also require at least one name keyword
                        name_words = set(w for w in name_lower.split() if len(w) >= 5)
                        cat_words = set(w for w in cat_lower.split() if len(w) >= 4)
                        if name_words & cat_words:
                            matched = True
                            break
                if matched:
                    if source_tag not in p.get("sources", []):
                        p.setdefault("sources", []).append(source_tag)

    return products


def enrich_google_trends(products, gtrends_text):
    if not gtrends_text:
        return products
    import re
    keywords = extract_trending_keywords(gtrends_text)
    gtrends_lower = gtrends_text.lower()
    for p in products:
        name_lower = p.get("name", "").lower()
        words = [w for w in name_lower.split() if len(w) >= 5 and w.isalpha()]
        match_count = 0
        for kw in keywords:
            if len(kw) >= 5 and re.search(r'(?<![a-z])' + re.escape(kw) + r'(?![a-z])', name_lower):
                match_count += 1
        for word in words[:5]:
            if len(word) >= 5 and re.search(r'(?<![a-z])' + re.escape(word) + r'(?![a-z])', gtrends_lower):
                match_count += 1
        if match_count >= 2:
            p["google_trend"] = "rising"
            if "Google趋势" not in p.get("sources", []):
                p.setdefault("sources", []).append("Google趋势")
    return products


def enrich_reddit(products, reddit_text):
    if not reddit_text: return products
    import re
    reddit_lower = reddit_text.lower()
    generic = {'that', 'this', 'with', 'from', 'have', 'been', 'your', 'they', 'will', 'more', 'than', 'what', 'when', 'very', 'just', 'like', 'would', 'could', 'should', 'about', 'these', 'those', 'here', 'there', 'some', 'each', 'much', 'many'}
    for p in products:
        words = [w for w in p.get("name", "").lower().split() if len(w) >= 5 and w.isalpha()]
        match = sum(1 for word in words[:5]
                    if word not in generic
                    and re.search(r'(?<![a-z])' + re.escape(word) + r'(?![a-z])', reddit_lower))
        if match >= 2:
            if "Reddit需求" not in p.get("sources", []):
                p.setdefault("sources", []).append("Reddit需求")
    return products


def filter_products(products, config):
    passed, rejected = [], []
    from datetime import datetime
    month = datetime.now().month
    season = "summer" if month in (6,7,8) else "winter" if month in (12,1,2) else "spring" if month in (3,4,5) else "autumn"
    
    seasonal = config.get("seasonal_categories", {})
    off_season_key = f"{season}_cold"
    off_season_kw = set(kw.lower() for kw in seasonal.get(off_season_key, []))
    forbidden_brands = set(b.lower() for b in config.get("forbidden_brands", []))
    max_reviews = config.get("max_reviews", 300)

    for p in products:
        name, category = p.get("name", ""), p.get("category", "")
        name_lower = name.lower()
        reviews = p.get("reviews", 0)

        # 1. 禁选品类/关键词
        forbidden, reason = is_forbidden(name, category)
        if forbidden:
            rejected.append({"name": name[:60], "reason": f"禁选: {reason}", "asin": p.get("asin")}); continue

        # 2. 大品牌排除
        brand_hit = None
        for brand in forbidden_brands:
            if brand in name_lower:
                brand_hit = brand; break
        if brand_hit:
            rejected.append({"name": name[:60], "reason": f"大牌: {brand_hit}", "asin": p.get("asin")}); continue

        # 3. 评论数范围（排除红海+排除无验证产品）
        max_reviews = config.get("max_reviews", 100)
        min_reviews = 5  # 至少5条评论，确保有基本需求验证
        if reviews > max_reviews:
            rejected.append({"name": name[:60], "reason": f"评论{reviews}>{max_reviews}(红海)", "asin": p.get("asin")}); continue
        if reviews < min_reviews and "new_releases" not in p.get("channel", ""):
            # 新品榜允许0评论，其他渠道需要基本验证
            rejected.append({"name": name[:60], "reason": f"评论{reviews}<{min_reviews}(无验证)", "asin": p.get("asin")}); continue

        # 3b. 评分过滤（排除退货风险品）
        min_rating = config.get("min_rating", 4.0)
        rating = p.get("rating", 0)
        if rating and rating < min_rating:
            rejected.append({"name": name[:60], "reason": f"评分{rating}<{min_rating}(退货风险)", "asin": p.get("asin")}); continue

        # 4. 价格区间
        price = p.get("price", 0)
        if price < config["price_range"]["min"] or price > config["price_range"]["max"]:
            rejected.append({"name": name[:60], "reason": f"£{price} 不在区间", "asin": p.get("asin")}); continue

        # 5. 利润率
        profit = calc_profit(price, category)
        p["profit_margin"] = profit["margin"]
        p["net_profit"] = profit["net_profit"]
        p["cost_breakdown"] = profit["breakdown"]
        if profit["margin"] < config["min_profit_margin"]:
            rejected.append({"name": name[:60], "reason": f"利润率{profit['margin']*100:.1f}%", "asin": p.get("asin")}); continue

        # 6. 过季产品标记（不排除，但降权）
        is_off_season = any(kw in name_lower for kw in off_season_kw)
        if is_off_season:
            p["off_season"] = True
        else:
            p["off_season"] = False

        passed.append(p)
    return passed, rejected


def dedup_products(products):
    by_asin = {}
    result = []
    for p in products:
        asin = p.get("asin", "")
        if not asin: result.append(p); continue
        if asin in by_asin:
            existing = by_asin[asin]
            for src in p.get("sources", []):
                if src not in existing.get("sources", []):
                    existing.setdefault("sources", []).append(src)
            if p.get("channel") == "new_releases" and existing.get("channel") not in ("new_releases",):
                existing["channel"] = "new_releases"
                existing["channel_name"] = "Amazon新品榜"
            if p.get("channel") == "wished" and existing.get("channel") not in ("new_releases", "wished"):
                existing["channel"] = "wished"
                existing["channel_name"] = "Amazon心愿榜"
        else:
            by_asin[asin] = p
            result.append(p)
    return result


def load_history(days=7):
    hist_dir = BASE / "data" / "history"
    history = {}
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)
    for f in sorted(hist_dir.glob("*.json")):
        try:
            d = datetime.strptime(f.stem, "%Y-%m-%d")
            if d >= cutoff:
                data = json.loads(f.read_text())
                for item in data:
                    key = item.get("asin") or item.get("name", "").lower().strip()
                    if key not in history: history[key] = []
                    history[key].append({"date": f.stem, "rank": item.get("rank"), "score": item.get("score", 0)})
        except (ValueError, json.JSONDecodeError): continue
    return history


def assign_channel_tags(p):
    """Assign channel_tags array based on product data."""
    sources = [s.lower() for s in p.get("sources", [])]
    channel = p.get("channel", "other")
    tags = [channel]

    if any("tiktok" in s for s in sources): tags.append("tiktok_verified")
    if any("hotukdeals" in s for s in sources): tags.append("hotukdeals")
    if any("temu" in s for s in sources): tags.append("temu_trending")
    if any("etsy" in s for s in sources): tags.append("etsy_trending")
    if any("youtube" in s for s in sources): tags.append("youtube_review")
    if p.get("google_trend") == "rising": tags.append("google_trends")
    if len(set(sources)) >= 2:
        p["is_multi"] = True
        tags.append("multi_source")

    p["channel_tags"] = list(set(tags))
    return p


def main():
    now = datetime.now()
    scan_date = now.strftime("%Y-%m-%d")
    scan_time = now.strftime("%H:%M")
    scan_ts = now.strftime("%Y-%m-%d_%H%M")  # Timestamp for filenames
    config = json.loads((BASE / "config.json").read_text())

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Product Radar v2 | {scan_date} {scan_time}", file=sys.stderr)
    print(f"  Sources: Amazon+TikTok+HotUKDeals+Temu+Etsy+YouTube+Google+Reddit", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    # 1. Amazon (New/BSR/Wished/Gifts)
    print("[1/7] Amazon UK (New+BSR+Wished+Gifts)...", file=sys.stderr)
    amazon_products = fetch_amazon(max_per_channel_type=8)  # 每类扫8个品类
    print(f"  Amazon: {len(amazon_products)} products", file=sys.stderr)

    # 2. AnySearch trends (TikTok+HotUKDeals+Temu+Etsy+YouTube+Google+Reddit)
    print("\n[2/7] AnySearch 多源趋势分析...", file=sys.stderr)
    trend_data, trend_raw = fetch_trend_signals()
    top_cats = sorted(trend_data.get("category_scores", {}).items(), key=lambda x: -x[1])[:6]
    print(f"  Top categories:", file=sys.stderr)
    for cat, score in top_cats:
        cv = "✓" if cat in trend_data.get("cross_validated", {}) else " "
        print(f"    [{cv}] {cat}: {score}/100", file=sys.stderr)

    # 3. TikTok keyword matching
    print("\n[3/7] TikTok UK...", file=sys.stderr)
    tiktok_products = fetch_tiktok()
    tiktok_matched = match_keywords_to_products(tiktok_products, amazon_products, "TikTok趋势")
    print(f"  TikTok → {len(tiktok_matched)} products", file=sys.stderr)

    # 4. Google Trends
    print("\n[4/7] Google Trends UK...", file=sys.stderr)
    gtrends_text = fetch_demand_signals()
    amazon_products = enrich_google_trends(amazon_products, gtrends_text)
    gt_count = sum(1 for p in amazon_products if p.get("google_trend") == "rising")
    print(f"  Google Trends → {gt_count} products", file=sys.stderr)

    # 5. Reddit
    print("\n[5/7] Reddit demand...", file=sys.stderr)
    reddit_text = fetch_reddit()
    amazon_products = enrich_reddit(amazon_products, reddit_text)

    # 6. Enrich with AnySearch source signals
    print("\n[6/7] Enriching with trend signals...", file=sys.stderr)
    amazon_products = enrich_from_trend_data(amazon_products, trend_data)
    for src_tag in ["HotUKDeals热帖", "Temu热销", "Etsy趋势", "YouTube种草"]:
        cnt = sum(1 for p in amazon_products if src_tag in p.get("sources", []))
        if cnt: print(f"  {src_tag}: {cnt} products", file=sys.stderr)

    # Dedup
    products = dedup_products(amazon_products)
    print(f"  After dedup: {len(products)}", file=sys.stderr)

    # 7. Filter + Score
    print("\n[7/7] Filtering & Scoring...", file=sys.stderr)
    passed, rejected = filter_products(products, config)
    print(f"  Passed: {len(passed)} | Rejected: {len(rejected)}", file=sys.stderr)

    history = load_history(days=7)

    # 7b. Market Intelligence (supply-demand + trend divergence)
    print("\n[7b] Market Intelligence...", file=sys.stderr)
    market = analyze_market(products, trend_data, history_days=3)
    sd_ratios = market["sd_ratios"]
    divergences = market["divergences"]
    if sd_ratios:
        top_sd = sorted(sd_ratios.items(), key=lambda x: -x[1]["ratio"])[:5]
        print(f"  Supply-Demand top categories:", file=sys.stderr)
        for cat, info in top_sd:
            print(f"    {info['label']} {cat}: ratio={info['ratio']} (demand={info['demand']} supply={info['supply']})", file=sys.stderr)
    if divergences:
        print(f"  Trend divergences: {len(divergences)} categories", file=sys.stderr)

    # Enrich products with market intelligence before scoring
    for p in passed:
        sd_bonus, sd_label, sd_info = get_product_sd_score(p, sd_ratios)
        p["sd_score"] = sd_bonus
        p["sd_label"] = sd_label
        p["sd_info"] = sd_info
        
        div_bonus, div_label, div_info = get_product_divergence_score(p, divergences)
        p["div_score"] = div_bonus
        p["div_label"] = div_label
        p["div_info"] = div_info

    # 7c. Gap Opportunity Detection (cross-platform demand gaps)
    print("\n[7c] Gap Opportunity Detection...", file=sys.stderr)
    gaps = detect_gaps(trend_data, sd_ratios, products, max_keywords=6)
    if gaps:
        print(f"  🎯 {len(gaps)} gap opportunities found!", file=sys.stderr)
        for g in gaps[:3]:
            ext_platforms = [v["platform_name"] for v in g["external_platforms"].values() if v["found"]]
            print(f"    {g['keyword']} → Amazon:{g['amazon_supply']['level']} | External: {', '.join(ext_platforms)}", file=sys.stderr)

    passed = score_all_products(passed, trend_data=trend_data, history=history)

    # Assign channel tags
    for p in passed:
        assign_channel_tags(p)

    print(f"\n  Top 10:", file=sys.stderr)
    for p in passed[:10]:
        src_tags = ", ".join(p.get("sources", [])[:3])
        print(f"    [{p['score']:3d}] £{p['price']:.2f} {p['profit_margin']*100:.0f}% | {src_tags} | {p['name'][:45]}", file=sys.stderr)

    # Channel counts
    channel_counts = {}
    for p in passed:
        for ch in p.get("channel_tags", [p.get("channel", "other")]):
            channel_counts[ch] = channel_counts.get(ch, 0) + 1

    stats = {
        "total_scanned": len(products),
        "passed_filter": len(passed),
        "rejected": len(rejected),
        "channels": channel_counts,
        "trend_categories": dict(top_cats),
        "supply_demand": {cat: info for cat, info in sorted(sd_ratios.items(), key=lambda x: -x[1]["ratio"])[:8]} if sd_ratios else {},
        "divergences": divergences if divergences else {},
        "gap_opportunities": len(gaps) if gaps else 0,
    }

    print(f"\n  Channels:", file=sys.stderr)
    for ch, cnt in sorted(channel_counts.items(), key=lambda x: -x[1]):
        print(f"    {ch}: {cnt}", file=sys.stderr)

    # Save (use scan_ts for unique filenames, scan_date for display)
    data = {
        "scan_date": scan_date, "scan_time": scan_time,
        "scan_ts": scan_ts,
        "stats": stats, "products": passed,
        "gaps": gaps if gaps else [],
        "trend_summary": {
            "top_categories": top_cats,
            "cross_validated": list(trend_data.get("cross_validated", {}).keys()),
            "demand_keywords": trend_data.get("demand_keywords", [])[:10],
            "season": trend_data.get("season", ""),
            "sources_scanned": list(trend_data.get("source_signals", {}).keys()),
        },
    }

    data_dir = BASE / "data" / "channels"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / f"{scan_ts}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / f"{scan_ts}-rejected.json").write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / f"{scan_ts}-trends.json").write_text(json.dumps(trend_data, ensure_ascii=False, indent=2), encoding="utf-8")

    hist_dir = BASE / "data" / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hist_data = [{"asin": p.get("asin",""), "name": p.get("name",""), "price": p.get("price",0),
                  "rank": p.get("rank"), "reviews": p.get("reviews"), "score": p.get("score",0),
                  "sources": p.get("sources",[]), "channel": p.get("channel","")} for p in passed]
    (hist_dir / f"{scan_ts}.json").write_text(json.dumps(hist_data, ensure_ascii=False, indent=2), encoding="utf-8")

    from generate_html_v2 import generate_html
    output_html = generate_html(str(data_dir / f"{scan_ts}.json"))

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  ✅ {len(passed)} scored products | {len(channel_counts)} channels", file=sys.stderr)
    print(f"  📊 {output_html}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    print(json.dumps({"date": scan_date, "scanned": len(products), "passed": len(passed),
                       "rejected": len(rejected), "channels": channel_counts,
                       "top_categories": dict(top_cats)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
