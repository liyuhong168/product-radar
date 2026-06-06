#!/usr/bin/env python3
"""
Gap Opportunity Detector v6 — Evidence-Based Product Suggestions

Strategy: Use data we ALREADY HAVE (accurate, no noise).
1. AnySearch trend data → category heat scores + evidence keywords
2. Amazon scan data → products per category + review counts
3. Cross-reference: high heat + low Amazon product count = gap

Key improvement: Generate specific product suggestions from evidence keywords,
not generic category-level terms.
"""
import json, re, sys
from pathlib import Path

BASE = Path(__file__).parent

# Evidence keyword → specific product suggestion mapping
# Maps evidence keywords to concrete searchable product terms
EVIDENCE_TO_PRODUCT = {
    # Pets
    "collar": ["dog collar", "cat collar", "pet collar"],
    "leash": ["dog lead", "retractable leash", "training lead"],
    "grooming": ["pet grooming brush", "dog grooming kit", "deshedding tool"],
    "bed": ["cat bed", "dog bed", "pet cushion"],
    "feeder": ["pet feeder", "automatic cat feeder", "bird feeder"],
    "toy": ["dog chew toy", "cat interactive toy", "pet ball"],
    "scratching": ["cat scratching post", "cat scratch board"],
    "harness": ["dog harness", "cat harness", "no-pull harness"],
    "water": ["pet water fountain", "dog water bottle"],
    "treat": ["dog treat bag", "pet treat pouch"],
    "cat": ["cat toy", "cat bed", "cat collar", "cat scratcher"],
    "pet": ["pet grooming", "pet bed", "pet feeder"],
    
    # Crafts
    "craft": ["craft knife", "craft supplies", "DIY craft kit"],
    "art": ["art supplies", "paint set", "drawing kit"],
    "sticker": ["vinyl sticker", "decal sticker", "craft sticker"],
    "tape": ["washi tape", "decorative tape", "masking tape"],
    "paint": ["acrylic paint set", "paint brush set", "paint by numbers"],
    "bead": ["jewelry making beads", "bead set"],
    "yarn": ["knitting yarn", "crochet yarn"],
    "fabric": ["fabric material", "sewing fabric"],
    
    # Beauty
    "hair": ["hair clip", "hair accessories", "hair band", "hair tie"],
    "nail": ["nail art kit", "nail tools", "nail stickers"],
    "mirror": ["makeup mirror", "vanity mirror", "LED mirror"],
    "skincare": ["face roller", "gua sha", "face mask"],
    "makeup": ["makeup brush set", "makeup bag", "makeup organizer"],
    "eyebrow": ["eyebrow trimmer", "eyebrow stencil"],
    "lip": ["lip balm", "lip scrubber"],
    
    # Eco
    "eco": ["环保产品", "reusable bag", "bamboo products"],
    "reusable": ["reusable food wrap", "reusable straws", "reusable bags"],
    "bamboo": ["bamboo cutlery", "bamboo toothbrush", "bamboo organizer"],
    "beeswax": ["beeswax wrap", "beeswax candles"],
    "compost": ["compost bin", "kitchen compost"],
    "recycled": ["recycled products", "eco bag"],
    "sustainable": ["sustainable products", "eco friendly"],
    "organic": ["organic products", "organic cotton"],
    
    # Home Decor
    "wall art": ["wall art print", "wall hanging", "wall decal"],
    "decor": ["home decor", "room decor", "table decor"],
    "candle": ["candle holder", "scented candle", "candle set"],
    "clock": ["wall clock", "desk clock", "digital clock"],
    "frame": ["photo frame", "picture frame", "wall frame"],
    "vase": ["flower vase", "decorative vase"],
    "plant": ["artificial plant", "plant pot", "plant stand"],
    "shelf": ["floating shelf", "wall shelf", "corner shelf"],
    "hook": ["wall hook", "adhesive hook", "coat hook"],
    
    # Lighting
    "lamp": ["desk lamp", "night light", "table lamp"],
    "light": ["LED light", "fairy lights", "string lights"],
    "strip": ["LED strip", "LED strip light", "RGB strip"],
    "led": ["LED bulb", "LED light", "LED panel"],
    "solar": ["solar light", "solar garden light", "solar lamp"],
    "sensor": ["sensor light", "motion sensor light", "night sensor"],
    "fairy": ["fairy lights", "fairy light curtain"],
    
    # Car
    "car": ["car accessories", "car organizer", "car phone holder"],
    "motor": ["motorcycle accessories", "motorcycle cover"],
    "tyre": ["tyre inflator", "tyre pressure gauge", "tyre repair kit"],
    "seat": ["car seat cover", "car seat organizer"],
    "dash": ["dashboard camera", "dashboard mat"],
    "boot": ["boot organiser", "boot mat", "boot liner"],
    
    # Phone
    "earbuds": ["earbuds case", "wireless earbuds"],
    "phone": ["phone case", "phone holder", "phone stand"],
    "charger": ["phone charger", "wireless charger", "car charger"],
    "cable": ["charging cable", "USB cable", "phone cable"],
    "watch": ["watch band", "watch strap", "smart watch case"],
    
    # Kitchen
    "spice": ["spice rack", "spice jar set", "spice organizer"],
    "silicone": ["silicone utensil", "silicone mat", "silicone mould"],
    "measuring": ["measuring cup", "measuring spoon set", "kitchen scale"],
    "storage": ["food storage", "kitchen storage", "container set"],
    "rack": ["dish rack", "spice rack", "pot rack"],
    "baking": ["baking set", "baking tray", "cake mould"],
    
    # Garden
    "garden": ["garden tool set", "garden light", "garden decor"],
    "bird": ["bird feeder", "bird bath", "bird house"],
    "plant": ["plant pot", "plant stand", "plant hanger"],
    "hose": ["garden hose", "hose nozzle", "hose reel"],
    "seed": ["seed starter kit", "herb seed kit"],
    
    # Bathroom
    "shower": ["shower caddy", "shower head", "shower curtain"],
    "towel": ["towel rail", "towel rack", "towel hook"],
    "soap": ["soap dispenser", "soap dish", "soap holder"],
    "bath": ["bath mat", "bath caddy", "bath pillow"],
    
    # Office
    "desk": ["desk organizer", "desk lamp", "desk mat"],
    "pen": ["pen holder", "pen set", "fountain pen"],
    "monitor": ["monitor stand", "monitor riser", "monitor light"],
    "laptop": ["laptop stand", "laptop sleeve", "laptop cooler"],
    "office": ["办公用品", "desk organizer", "pen holder"],
    "stationery": ["文具", "notebook", "pen set"],
    
    # Sports
    "yoga": ["yoga mat", "yoga block", "yoga strap"],
    "gym": ["gym bag", "gym gloves", "gym towel"],
    "fitness": ["resistance band", "fitness tracker", "foam roller"],
    "running": ["running belt", "running light", "running armband"],
    
    # Seasonal / Gift
    "gift": ["礼物", "gift set", "gift box"],
    "seasonal": ["季节性产品", "seasonal decor", "holiday gift"],
    "party": ["party supplies", "party decoration", "party favours"],
    "wedding": ["wedding decor", "wedding favour", "wedding gift"],
    "birthday": ["birthday gift", "birthday decoration", "birthday card"],
    "christmas": ["christmas decoration", "christmas gift", "christmas stocking"],
    "halloween": ["halloween decoration", "halloween costume"],
    "easter": ["easter egg", "easter decoration"],
    "valentine": ["valentine gift", "valentine card"],
}


def analyze_gaps(trend_data, sd_ratios, amazon_products):
    """Analyze category-level gaps using existing data.
    
    Returns list of gap opportunities with evidence-based product suggestions.
    """
    cat_scores = trend_data.get("category_scores", {})
    cat_evidence = trend_data.get("category_evidence", {})
    cross_validated = trend_data.get("cross_validated", {})
    
    # Count Amazon products per category
    cat_product_count = {}
    cat_review_count = {}
    
    for p in amazon_products:
        cat = p.get("category", "").lower().strip()
        if not cat:
            continue
        cat_product_count[cat] = cat_product_count.get(cat, 0) + 1
        cat_review_count[cat] = cat_review_count.get(cat, 0) + p.get("reviews", 0)
    
    gaps = []
    
    for cat, heat in cat_scores.items():
        if heat < 40:
            continue
        
        # Find matching Amazon category
        amazon_count = 0
        amazon_reviews = 0
        for acat in cat_product_count:
            if cat in acat or acat in cat:
                amazon_count = cat_product_count[acat]
                amazon_reviews = cat_review_count[acat]
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
        
        # Generate specific product suggestions from evidence keywords
        suggestions = []
        for kw in evidence:
            kw_lower = kw.lower().strip()
            if kw_lower in EVIDENCE_TO_PRODUCT:
                suggestions.extend(EVIDENCE_TO_PRODUCT[kw_lower])
            elif len(kw_lower) >= 4:
                suggestions.append(kw_lower)
        
        # Deduplicate and limit
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            s_lower = s.lower()
            if s_lower not in seen:
                seen.add(s_lower)
                unique_suggestions.append(s)
        suggestions = unique_suggestions[:8]
        
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
        
        # Generate URLs using first suggestion (translate to Chinese for 1688)
        first_suggest = suggestions[0] if suggestions else cat
        from translate import translate_title_to_chinese
        cn_keyword = translate_title_to_chinese(first_suggest)
        url_1688_keyword = cn_keyword if cn_keyword else first_suggest
        
        # Pre-translate all suggestions to Chinese for 1688 links
        suggestions_cn = []
        for s in suggestions:
            if re.search(r'[\u4e00-\u9fff]', s):
                suggestions_cn.append(s)  # Already Chinese
            else:
                cn = translate_title_to_chinese(s)
                suggestions_cn.append(cn if cn else s)
        
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
            "suggestions": suggestions,
            "suggestions_cn": suggestions_cn,
            "sd_info": sd_info,
            "source": "category_analysis",
        }
        
        gap["url_1688"] = f"https://s.1688.com/selloffer/offer_search.htm?keywords={url_1688_keyword}"
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
        print(f"  1688: {g['url_1688'][:80]}")
