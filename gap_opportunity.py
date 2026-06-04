#!/usr/bin/env python3
"""
Gap Opportunity Detector v5 — Category Gap Analysis (final)

Strategy: Use data we ALREADY HAVE (accurate, no noise).
1. AnySearch trend data → category heat scores + evidence keywords
2. Amazon scan data → products per category + review counts
3. Cross-reference: high heat + low Amazon product count = gap

Also: For high-heat categories, generate specific product suggestions
based on evidence keywords + predefined patterns for 1688 search.
"""
import json, re, sys
from pathlib import Path

BASE = Path(__file__).parent

# Product suggestions per category (for 1688 search)
CATEGORY_PRODUCTS = {
    "pets": ["dog chew toy", "cat interactive toy", "pet grooming brush", "dog harness", "cat bed", "pet water fountain", "dog lead", "cat scratching post"],
    "kitchen": ["spice rack", "silicone utensil set", "measuring cup", "vegetable peeler", "oil dispenser", "garlic press", "dish rack"],
    "garden": ["solar garden light", "bird feeder", "garden tool set", "plant pot holder", "hose nozzle", "garden kneeler"],
    "bathroom": ["shower caddy", "soap dispenser", "bathroom shelf", "toilet brush holder", "towel rail", "bath mat"],
    "cleaning": ["lint roller", "microfiber cloth", "duster extendable", "grout brush", "drain cover"],
    "storage": ["drawer divider", "under bed storage", "wardrobe organizer", "cable management box", "shoe rack"],
    "lighting": ["led strip usb", "night light sensor", "fairy lights battery", "desk lamp", "book light"],
    "office": ["desk organizer", "monitor stand", "pen holder", "laptop stand", "cable clip"],
    "sports": ["resistance band set", "yoga mat", "foam roller", "jump rope", "gym bag"],
    "crafts": ["vinyl sticker", "washi tape", "paint brush set", "craft knife", "cutting mat"],
    "home decor": ["wall shelf floating", "photo frame", "candle holder", "artificial plant", "wall hook"],
    "eco": ["reusable food wrap", "bamboo cutlery", "steel straw set", "beeswax wrap", "compost bin"],
    "car": ["phone holder mount", "boot organiser", "seat gap filler", "car sun shade", "tyre gauge"],
    "beauty": ["makeup brush set", "nail art kit", "hair accessories", "mirror vanity", "storage organiser"],
    "phone": ["phone case", "charger cable", "phone stand", "earbuds case", "screen protector"],
}


def analyze_gaps(trend_data, sd_ratios, amazon_products):
    """Analyze category-level gaps using existing data.
    
    Returns list of gap opportunities at category level with specific
    product suggestions for each.
    """
    cat_scores = trend_data.get("category_scores", {})
    cat_evidence = trend_data.get("category_evidence", {})
    cross_validated = trend_data.get("cross_validated", {})
    
    # Count Amazon products per category
    cat_product_count = {}
    cat_review_count = {}
    cat_products = {}
    
    for p in amazon_products:
        cat = p.get("category", "").lower().strip()
        if not cat:
            continue
        cat_product_count[cat] = cat_product_count.get(cat, 0) + 1
        cat_review_count[cat] = cat_review_count.get(cat, 0) + p.get("reviews", 0)
        cat_products.setdefault(cat, []).append(p["name"][:50])
    
    gaps = []
    
    for cat, heat in cat_scores.items():
        if heat < 40:
            continue
        
        # Find matching Amazon category
        amazon_count = 0
        amazon_reviews = 0
        matched_cat = None
        for acat in cat_product_count:
            if cat in acat or acat in cat:
                amazon_count = cat_product_count[acat]
                amazon_reviews = cat_review_count[acat]
                matched_cat = acat
                break
        
        # Determine gap level
        if amazon_count == 0:
            gap_level = "strong"
        elif amazon_count <= 3:
            gap_level = "moderate"
        elif amazon_count <= 8:
            gap_level = "weak"
        else:
            continue  # Not a gap
        
        # Get evidence keywords
        evidence = cat_evidence.get(cat, [])
        is_cross_validated = cat in cross_validated
        
        # Generate product suggestions
        suggestions = CATEGORY_PRODUCTS.get(cat, [])
        # Add evidence keywords that look like products
        for kw in evidence:
            if len(kw) >= 5 and len(kw.split()) >= 2:
                suggestions.append(kw)
        
        # Score
        score = 0
        score += min(heat // 3, 30)  # Heat contribution
        if gap_level == "strong":
            score += 30
        elif gap_level == "moderate":
            score += 15
        if is_cross_validated:
            score += 15  # Multiple sources confirm
        
        # SD ratio bonus
        sd_info = sd_ratios.get(cat, {})
        if sd_info.get("level") == "deep_blue":
            score += 10
        
        gap = {
            "keyword": cat,
            "category": cat,
            "heat": heat,
            "score": score,
            "gap_level": gap_level,
            "amazon_count": amazon_count,
            "amazon_reviews": amazon_reviews,
            "evidence": evidence[:5],
            "is_cross_validated": is_cross_validated,
            "cross_sources": cross_validated.get(cat, 0),
            "suggestions": list(set(suggestions))[:8],
            "sd_info": sd_info,
            "source": "category_analysis",
        }
        
        # URLs for the first suggestion
        first_suggest = suggestions[0] if suggestions else cat
        gap["url_1688"] = f"https://s.1688.com/selloffer/offer_search.htm?keywords={first_suggest}"
        gap["url_amazon"] = f"https://www.amazon.co.uk/s?k={first_suggest.replace(' ', '+')}"
        gap["url_google"] = f"https://trends.google.com/trends/explore?q={first_suggest.replace(' ', '+')}&geo=GB"
        
        gaps.append(gap)
    
    gaps.sort(key=lambda x: -x["score"])
    return gaps


if __name__ == "__main__":
    data_dir = BASE / "data" / "channels"
    latest = sorted([f for f in data_dir.glob("*.json") if "-rejected" not in f.name and "-trends" not in f.name])
    if not latest:
        print("No data files found"); sys.exit(1)
    
    data_file = latest[-1]
    data = json.loads(data_file.read_text())
    
    trend_file = str(data_file).replace(".json", "-trends.json")
    trend_data = json.loads(Path(trend_file).read_text()) if Path(trend_file).exists() else {}
    
    products = data.get("products", [])
    sd_ratios = data.get("stats", {}).get("supply_demand", {})
    
    print(f"Data: {data_file.name} | Products: {len(products)} | Categories: {len(trend_data.get('category_scores', {}))}")
    
    gaps = analyze_gaps(trend_data, sd_ratios, products)
    
    print(f"\n{'='*60}")
    print(f"Category Gap Opportunities: {len(gaps)}")
    print(f"{'='*60}")
    for g in gaps:
        label = {"strong": "🟢 强缺口", "moderate": "🟡 中等缺口", "weak": "🟠 弱缺口"}
        cv = "🔗多源验证" if g["is_cross_validated"] else ""
        print(f"\n{label[g['gap_level']]} {g['category']} (score={g['score']}, heat={g['heat']}) {cv}")
        print(f"  Amazon: {g['amazon_count']}个产品, {g['amazon_reviews']}条评论")
        print(f"  证据关键词: {', '.join(g['evidence'][:3])}")
        print(f"  建议产品: {', '.join(g['suggestions'][:5])}")
        print(f"  1688: {g['url_1688'][:60]}")
