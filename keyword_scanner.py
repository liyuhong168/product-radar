#!/usr/bin/env python3
"""
Keyword Scanner — Three-source keyword-driven product discovery.

Sources:
1. Discovery keywords (from LLM trend analysis, saved as pending_keywords.json)
2. Festival keywords (from Festival Planner, filtered by sea freight deadline ≤30 days)
3. Regular radar scan (existing, in run_scan_v2.py)

This module handles sources 1 and 2: search Amazon UK for keywords and return products.
"""

import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent

# Import from existing modules
sys.path.insert(0, str(BASE))
from sources.amazon_uk import _curl_fetch, _parse_amazon_page, CATEGORY_VALIDATORS


def load_discovery_keywords():
    """Load keywords from the latest discovery JSON.
    
    Returns list of dicts: [{"keyword": "...", "keyword_cn": "...", "amazon_keyword": "...", "source": "discovery"}]
    """
    disc_dir = BASE / "data" / "discovery"
    if not disc_dir.exists():
        return []
    
    # Find the latest discovery JSON (not seasonal_keywords.json)
    files = sorted([f for f in disc_dir.glob("*.json") if "seasonal" not in f.name])
    if not files:
        return []
    
    latest = files[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    
    keywords = []
    for insight in data.get("insights", []):
        kw = insight.get("amazon_keyword") or insight.get("keyword", "")
        if kw:
            keywords.append({
                "keyword": kw,
                "keyword_cn": insight.get("keyword_cn", ""),
                "source": "discovery",
                "score": insight.get("signal_scores", {}).get("final", 0),
            })
    
    return keywords


def load_festival_keywords():
    """Load keywords from Festival Planner events within sea freight window.
    
    Sea freight deadline = festival_date - (63 + 14) = festival_date - 77 days
    Only include events where sea deadline is within 30 days from today.
    
    Returns list of dicts: [{"keyword": "...", "keyword_cn": "...", "source": "festival", "event": "...", "deadline": "..."}]
    """
    from festival_engine import load_festivals, get_deadlines, LOGISTICS_MODES
    
    festivals = load_festivals()
    if not festivals:
        return []
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    keywords = []
    seen_kws = set()
    
    for f in festivals:
        deadlines = get_deadlines(f)
        sea = deadlines.get("sea", {})
        days_left = sea.get("days_from_today", 999)
        
        # Only include events where sea deadline is approaching (0-30 days away)
        # Skip events too far away or already past deadline
        if days_left > 30 or days_left < 0:
            continue
        
        event_name = f.get("name", "")
        
        for product in f.get("products", []):
            # Use the Amazon keywords from the product
            for kw in product.get("keywords", [])[:2]:  # Top 2 keywords per product
                kw_lower = kw.lower().strip()
                if kw_lower not in seen_kws and len(kw_lower) >= 4:
                    seen_kws.add(kw_lower)
                    keywords.append({
                        "keyword": kw,
                        "keyword_cn": product.get("sku", ""),
                        "source": "festival",
                        "event": event_name,
                        "event_icon": f.get("icon", "📅"),
                        "deadline": sea.get("date", ""),
                        "days_left": days_left,
                    })
    
    # Limit to top 10 keywords to avoid too many searches
    return keywords[:10]


def search_amazon_by_keyword(keyword, max_products=5):
    """Search Amazon UK for a keyword and return parsed products.
    
    Uses the same _curl_fetch + _parse_amazon_page as the regular radar scan.
    """
    search_url = f"https://www.amazon.co.uk/s?k={urllib.parse.quote(keyword)}"
    html = _curl_fetch(search_url)
    
    if not html:
        return []
    
    # Use "Search" as category and "keyword_search" as channel type
    products = _parse_amazon_page(html, "Search", "keyword_search")
    
    # Limit results
    return products[:max_products]


def run_keyword_scan(max_discovery_kws=5, max_festival_kws=5, max_products_per_kw=3):
    """Run keyword-based scan from discovery + festival sources.
    
    Returns list of products tagged with their keyword source.
    """
    # Load keywords from both sources
    disc_kws = load_discovery_keywords()[:max_discovery_kws]
    fest_kws = load_festival_keywords()[:max_festival_kws]
    
    all_kws = disc_kws + fest_kws
    if not all_kws:
        print("  ℹ️ No pending keywords from discovery or festival", file=sys.stderr)
        return []
    
    print(f"\n🔑 Keyword Scan: {len(disc_kws)} discovery + {len(fest_kws)} festival keywords", file=sys.stderr)
    
    all_products = []
    seen_asins = set()
    
    for kw_info in all_kws:
        keyword = kw_info["keyword"]
        source = kw_info["source"]
        
        print(f"  🔍 [{source}] {keyword}...", file=sys.stderr, end="")
        products = search_amazon_by_keyword(keyword, max_products=max_products_per_kw)
        
        # Tag products with keyword source info
        for p in products:
            asin = p.get("asin", "")
            if asin in seen_asins:
                continue
            seen_asins.add(asin)
            
            p["keyword_source"] = source
            p["matched_keyword"] = keyword
            p["channel"] = "keyword_search"
            p["channel_name"] = f"关键词搜索({source})"
            
            if source == "festival":
                p["festival_event"] = kw_info.get("event", "")
                p["festival_icon"] = kw_info.get("event_icon", "📅")
                p["festival_deadline"] = kw_info.get("deadline", "")
                p["is_event"] = True
                if "节日" not in p.get("sources", []):
                    p.setdefault("sources", []).append(f"📅 {kw_info.get('event', '节日')}")
            else:
                if "趋势发现" not in p.get("sources", []):
                    p.setdefault("sources", []).append("趋势发现")
            
            all_products.append(p)
        
        print(f" → {len(products)} products", file=sys.stderr)
    
    print(f"  ✅ Keyword scan total: {len(all_products)} products", file=sys.stderr)
    return all_products


if __name__ == "__main__":
    print("=== Keyword Scanner Test ===")
    
    disc_kws = load_discovery_keywords()
    print(f"\n📋 Discovery keywords: {len(disc_kws)}")
    for kw in disc_kws[:3]:
        print(f"  - {kw['keyword']} (score: {kw.get('score', 0)})")
    
    fest_kws = load_festival_keywords()
    print(f"\n📅 Festival keywords (sea deadline ≤30d): {len(fest_kws)}")
    for kw in fest_kws[:5]:
        print(f"  - {kw['keyword']} ({kw['event']}, deadline: {kw['deadline']}, {kw['days_left']}d)")
    
    if "--run" in sys.argv:
        products = run_keyword_scan()
        print(f"\n📊 Found {len(products)} products")
        for p in products[:5]:
            print(f"  [{p.get('keyword_source', '?')}] £{p['price']} | {p['name'][:60]}")
