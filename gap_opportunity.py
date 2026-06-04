#!/usr/bin/env python3
"""
Gap Opportunity Detector — Cross-platform demand gap analysis
Finds products trending on external platforms (TikTok/Google) that have weak Amazon supply.

Logic:
  External demand signal (TikTok/Google hot) + Other UK platforms selling + Amazon low supply = Gap opportunity

Data sources:
  - AnySearch trend data (already fetched in main scan)
  - AnySearch CLI for eBay/Etsy/Argos queries
  - Amazon category supply data (from main scan)
"""
import json, subprocess, re, sys
from pathlib import Path

BASE = Path(__file__).parent
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")

# UK platforms to check for external supply
EXTERNAL_PLATFORMS = {
    "ebay": {
        "domain": "ecommerce",
        "query_template": "site:ebay.co.uk {keyword} buy",
        "name": "eBay UK",
    },
    "etsy": {
        "domain": "ecommerce",
        "query_template": "site:etsy.com/uk {keyword}",
        "name": "Etsy UK",
    },
    "argos": {
        "domain": "ecommerce",
        "query_template": "site:argos.co.uk {keyword}",
        "name": "Argos",
    },
}

# Product-related keywords to extract from trend evidence
PRODUCT_KEYWORDS = {
    "kitchen": ["kitchen gadget", "cooking tool", "spice rack", "utensil holder", "measuring cup"],
    "garden": ["garden tool", "plant pot", "solar light", "bird feeder", "watering can"],
    "bathroom": ["shower caddy", "toilet brush", "soap dispenser", "bathroom shelf", "towel rack"],
    "cleaning": ["cleaning brush", "lint roller", "duster", "organizer", "storage box"],
    "car": ["car organizer", "phone holder", "car charger", "dashboard camera", "car seat cover"],
    "office": ["desk organizer", "pen holder", "laptop stand", "monitor riser", "file holder"],
    "storage": ["storage box", "drawer organizer", "shelf", "basket", "container"],
    "lighting": ["led strip", "night light", "fairy lights", "desk lamp", "solar light"],
    "pets": ["dog toy", "cat bed", "pet collar", "grooming tool", "pet feeder"],
    "sports": ["yoga mat", "resistance band", "water bottle", "gym bag", "exercise mat"],
    "crafts": ["craft kit", "painting set", "stickers", "tape", "scissors"],
    "bedding": ["pillow", "blanket", "sheet set", "cushion cover", "mattress topper"],
    "home decor": ["wall art", "candle holder", "vase", "photo frame", "mirror"],
    "eco": ["reusable bag", "bamboo set", "beeswax wrap", "steel straw", "compost bin"],
    "phone": ["phone case", "charger cable", "phone stand", "screen protector", "earbuds"],
}


def _run_anysearch(query, domain="ecommerce", max_results=5):
    """Run a single AnySearch query."""
    try:
        cmd = ["python3", ANYSEARCH, "search", query,
               "--domain", domain, "--max_results", str(max_results),
               "--freshness", "week", "--zone", "intl"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  AnySearch error: {e}", file=sys.stderr)
    return ""


def extract_product_keywords(trend_data, sd_ratios, min_heat=40):
    """Extract candidate product keywords from trend data.
    
    Strategy: Use category evidence keywords + predefined product keywords
    for categories with high trend heat.
    """
    cat_scores = trend_data.get("category_scores", {})
    cat_evidence = trend_data.get("category_evidence", {})
    
    candidates = []
    
    for cat, heat in cat_scores.items():
        if heat < min_heat:
            continue
        
        # Get evidence keywords for this category
        evidence = cat_evidence.get(cat, [])
        
        # Get predefined product keywords
        product_kws = PRODUCT_KEYWORDS.get(cat, [])
        
        # Combine: use evidence keywords that look like product names
        for kw in evidence:
            if len(kw) >= 5 and any(c.isalpha() for c in kw):
                candidates.append({
                    "keyword": kw,
                    "category": cat,
                    "heat": heat,
                    "source": "evidence",
                })
        
        # Add predefined product keywords
        for kw in product_kws:
            candidates.append({
                "keyword": kw,
                "category": cat,
                "heat": heat,
                "source": "predefined",
            })
    
    # Also add demand keywords that look like products
    for kw in trend_data.get("demand_keywords", []):
        # Filter noise
        if len(kw) < 8 or len(kw) > 50:
            continue
        if any(skip in kw for skip in ["how to", "best way", "here are", "check out", "analyze", "review", "guide"]):
            continue
        candidates.append({
            "keyword": kw,
            "category": "unknown",
            "heat": 50,
            "source": "demand_keyword",
        })
    
    return candidates


def check_external_supply(keyword, platforms=None):
    """Check if a keyword has products on external UK platforms.
    Returns dict of platform -> {found: bool, count: int, sample: str}.
    """
    if platforms is None:
        platforms = ["ebay", "etsy"]
    
    results = {}
    
    for platform in platforms:
        config = EXTERNAL_PLATFORMS.get(platform)
        if not config:
            continue
        
        query = config["query_template"].format(keyword=keyword)
        text = _run_anysearch(query, domain=config["domain"])
        
        if text:
            # Count product-like results (links with product titles)
            link_count = len(re.findall(r'https?://', text))
            has_products = link_count >= 2  # At least 2 results = products exist
            
            # Extract a sample product title
            sample = ""
            for line in text.split("\n")[:5]:
                line = line.strip()
                if len(line) > 15 and not line.startswith("http") and not line.startswith("["):
                    sample = line[:80]
                    break
            
            results[platform] = {
                "found": has_products,
                "result_count": link_count,
                "sample": sample,
                "platform_name": config["name"],
            }
        else:
            results[platform] = {"found": False, "result_count": 0, "sample": "", "platform_name": config["name"]}
    
    return results


def check_amazon_supply(keyword, amazon_products):
    """Estimate Amazon supply for a keyword based on existing scan data.
    Returns supply level: 'none', 'low', 'medium', 'high'.
    """
    keyword_lower = keyword.lower()
    match_count = 0
    total_reviews = 0
    
    for p in amazon_products:
        name = p.get("name", "").lower()
        # Check if keyword appears in product name
        if any(kw in name for kw in keyword_lower.split() if len(kw) >= 4):
            match_count += 1
            total_reviews += p.get("reviews", 0)
    
    if match_count == 0:
        return {"level": "none", "count": 0, "reviews": 0}
    elif match_count <= 3:
        return {"level": "low", "count": match_count, "reviews": total_reviews}
    elif match_count <= 10:
        return {"level": "medium", "count": match_count, "reviews": total_reviews}
    else:
        return {"level": "high", "count": match_count, "reviews": total_reviews}


def detect_gaps(trend_data, sd_ratios, amazon_products, max_keywords=8):
    """Main entry: detect cross-platform demand gaps.
    
    Returns list of gap opportunities, sorted by score.
    """
    print("  Extracting candidate keywords...", file=sys.stderr)
    candidates = extract_product_keywords(trend_data, sd_ratios)
    
    # Deduplicate and prioritize by heat
    seen = set()
    unique = []
    for c in candidates:
        kw = c["keyword"].lower().strip()
        if kw not in seen and len(kw) >= 5:
            seen.add(kw)
            unique.append(c)
    
    # Sort by heat, take top N
    unique.sort(key=lambda x: -x["heat"])
    top_candidates = unique[:max_keywords]
    
    print(f"  Checking {len(top_candidates)} keywords for gaps...", file=sys.stderr)
    
    gaps = []
    
    for candidate in top_candidates:
        keyword = candidate["keyword"]
        heat = candidate["heat"]
        category = candidate["category"]
        
        print(f"    Checking: {keyword} (heat={heat})...", file=sys.stderr)
        
        # Check Amazon supply
        amazon_supply = check_amazon_supply(keyword, amazon_products)
        
        # Skip if Amazon already has high supply
        if amazon_supply["level"] in ("high", "medium"):
            continue
        
        # Check external platforms
        external = check_external_supply(keyword, ["ebay", "etsy"])
        
        has_external = any(v["found"] for v in external.values())
        
        if not has_external:
            continue
        
        # Score the opportunity
        score = 0
        score += min(heat // 5, 20)  # Heat contribution (max 20)
        
        if amazon_supply["level"] == "none":
            score += 30  # No Amazon supply = biggest opportunity
        elif amazon_supply["level"] == "low":
            score += 15  # Low supply = still good
        
        ext_count = sum(1 for v in external.values() if v["found"])
        score += ext_count * 10  # More platforms = stronger signal
        
        # SD ratio bonus
        sd_info = sd_ratios.get(category, {})
        if sd_info.get("level") == "deep_blue":
            score += 15
        elif sd_info.get("level") == "light_blue":
            score += 8
        
        gap = {
            "keyword": keyword,
            "category": category,
            "heat": heat,
            "score": score,
            "amazon_supply": amazon_supply,
            "external_platforms": external,
            "external_count": ext_count,
            "sd_info": sd_info,
            "source": candidate["source"],
            "search_1688": f"https://s.1688.com/selloffer/offer_search.htm?keywords={keyword}",
            "search_amazon": f"https://www.amazon.co.uk/s?k={keyword.replace(' ', '+')}",
        }
        gaps.append(gap)
    
    # Sort by score
    gaps.sort(key=lambda x: -x["score"])
    
    print(f"  Found {len(gaps)} gap opportunities", file=sys.stderr)
    return gaps


if __name__ == "__main__":
    # Quick test
    data_file = sys.argv[1] if len(sys.argv) > 1 else str(BASE / "data/channels/2026-06-04_1756.json")
    data = json.loads(Path(data_file).read_text())
    products = data.get("products", [])
    
    trend_file = data_file.replace(".json", "-trends.json")
    trend_data = json.loads(Path(trend_file).read_text()) if Path(trend_file).exists() else {}
    
    sd_ratios = data.get("stats", {}).get("supply_demand", {})
    
    gaps = detect_gaps(trend_data, sd_ratios, products, max_keywords=5)
    
    print(f"\n=== Gap Opportunities ({len(gaps)}) ===")
    for g in gaps:
        print(f"\n🎯 {g['keyword']} (score={g['score']})")
        print(f"   Category: {g['category']} | Heat: {g['heat']}")
        print(f"   Amazon: {g['amazon_supply']['level']} ({g['amazon_supply']['count']} products)")
        for platform, info in g['external_platforms'].items():
            status = "✅" if info['found'] else "❌"
            print(f"   {info['platform_name']}: {status} ({info['result_count']} results)")
        print(f"   1688: {g['search_1688']}")
