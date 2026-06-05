"""Translate English product titles to Chinese for 1688 search."""

# Common product keywords mapping
KEYWORD_MAP = {
    # Electronics
    "charger": "充电器",
    "cable": "数据线",
    "adapter": "适配器",
    "hub": "集线器",
    "stand": "支架",
    "holder": "支架",
    "mount": "支架",
    "dock": "扩展坞",
    "case": "保护壳",
    "cover": "保护套",
    "protector": "保护膜",
    "screen protector": "屏幕保护膜",
    "tempered glass": "钢化膜",
    "headphones": "耳机",
    "earbuds": "耳机",
    "speaker": "音箱",
    "light": "灯",
    "led": "LED灯",
    "lamp": "台灯",
    "strip": "灯带",
    "bulb": "灯泡",
    "fan": "风扇",
    "heater": "加热器",
    "humidifier": "加湿器",
    "purifier": "净化器",
    "vacuum": "吸尘器",
    
    # Home & Kitchen
    "organizer": "收纳盒",
    "storage": "收纳",
    "basket": "篮子",
    "shelf": "架子",
    "rack": "架子",
    "hook": "挂钩",
    "hanger": "衣架",
    "container": "容器",
    "bottle": "瓶子",
    "cup": "杯子",
    "mug": "马克杯",
    "plate": "盘子",
    "bowl": "碗",
    "knife": "刀",
    "scissors": "剪刀",
    "tool": "工具",
    "brush": "刷子",
    "sponge": "海绵",
    "towel": "毛巾",
    "mat": "垫子",
    "rug": "地毯",
    "curtain": "窗帘",
    "pillow": "枕头",
    "blanket": "毯子",
    
    # Fashion & Accessories
    "bag": "包",
    "wallet": "钱包",
    "belt": "皮带",
    "watch": "手表",
    "ring": "戒指",
    "necklace": "项链",
    "bracelet": "手链",
    "earring": "耳环",
    "glasses": "眼镜",
    "sunglasses": "太阳镜",
    "hat": "帽子",
    "cap": "帽子",
    "scarf": "围巾",
    "gloves": "手套",
    "socks": "袜子",
    
    # Sports & Outdoor
    "yoga": "瑜伽",
    "mat": "垫子",
    "ball": "球",
    "rope": "绳子",
    "band": "弹力带",
    "weight": "哑铃",
    "dumbbell": "哑铃",
    "tent": "帐篷",
    "backpack": "背包",
    "bottle": "水壶",
    "filter": "滤水器",
    
    # Pet Supplies
    "leash": "牵引绳",
    "collar": "项圈",
    "toy": "玩具",
    "bed": "宠物床",
    "feeder": "喂食器",
    "water": "饮水器",
    "brush": "梳子",
    "shampoo": "洗发水",
    
    # Office & Stationery
    "pen": "笔",
    "pencil": "铅笔",
    "notebook": "笔记本",
    "paper": "纸",
    "tape": "胶带",
    "glue": "胶水",
    "sticker": "贴纸",
    "marker": "记号笔",
    "eraser": "橡皮",
    "ruler": "尺子",
    "scissors": "剪刀",
    " Stapler": "订书机",
    "clip": "夹子",
    "pin": "图钉",
    
    # Car & Motorcycle
    "car": "汽车",
    "motorcycle": "摩托车",
    "bike": "自行车",
    "tire": "轮胎",
    "wheel": "轮子",
    "mirror": "后视镜",
    "light": "车灯",
    "cover": "车衣",
    "mat": "脚垫",
    "seat": "座椅",
    "phone": "手机",
    "holder": "支架",
    "charger": "充电器",
    
    # Garden & Outdoor
    "plant": "植物",
    "pot": "花盆",
    "seed": "种子",
    "soil": "土壤",
    "fertilizer": "肥料",
    "watering": "浇水",
    "hose": "水管",
    "sprinkler": "喷头",
    "light": "花园灯",
    "fence": "栅栏",
    "bird": "鸟",
    "feeder": "喂鸟器",
    
    # Baby & Kids
    "baby": "婴儿",
    "child": "儿童",
    "kid": "儿童",
    "toy": "玩具",
    "doll": "娃娃",
    "puzzle": "拼图",
    "game": "游戏",
    "book": "书",
    "coloring": "涂色",
    "crayon": "蜡笔",
    
    # Beauty & Personal Care
    "makeup": "化妆品",
    "lipstick": "口红",
    "mascara": "睫毛膏",
    "foundation": "粉底",
    "powder": "粉饼",
    "brush": "化妆刷",
    "comb": "梳子",
    "hair": "头发",
    "dryer": "吹风机",
    "straightener": "直发器",
    "curler": "卷发器",
    "shaver": "剃须刀",
    "trimmer": "修剪器",
    
    # Common adjectives
    "portable": "便携",
    "mini": "迷你",
    "large": "大号",
    "small": "小号",
    "medium": "中号",
    "set": "套装",
    "pack": "包装",
    "kit": "套装",
    "bundle": "组合",
    "pair": "对",
    "piece": "件",
    "unit": "个",
    
    # Materials
    "stainless steel": "不锈钢",
    "plastic": "塑料",
    "silicone": "硅胶",
    "leather": "皮革",
    "cotton": "棉",
    "wool": "羊毛",
    "silk": "丝绸",
    "nylon": "尼龙",
    "polyester": "聚酯纤维",
    "rubber": "橡胶",
    "wood": "木",
    "metal": "金属",
    "glass": "玻璃",
    "ceramic": "陶瓷",
    
    # Colors
    "black": "黑色",
    "white": "白色",
    "red": "红色",
    "blue": "蓝色",
    "green": "绿色",
    "yellow": "黄色",
    "pink": "粉色",
    "purple": "紫色",
    "orange": "橙色",
    "brown": "棕色",
    "gray": "灰色",
    "grey": "灰色",
    "gold": "金色",
    "silver": "银色",
}

def translate_title_to_chinese(title: str) -> str:
    """Translate English product title to Chinese keywords for 1688 search.
    
    Uses keyword mapping for common product terms.
    Falls back to extracting key nouns if no direct translation.
    """
    if not title:
        return ""
    
    title_lower = title.lower()
    chinese_keywords = []
    
    # First try exact phrase matches (longer phrases first)
    sorted_phrases = sorted(KEYWORD_MAP.keys(), key=len, reverse=True)
    matched_positions = set()
    
    for phrase in sorted_phrases:
        pos = title_lower.find(phrase)
        if pos != -1:
            # Check if this position is not already matched
            phrase_range = set(range(pos, pos + len(phrase)))
            if not phrase_range & matched_positions:
                chinese_keywords.append(KEYWORD_MAP[phrase])
                matched_positions.update(phrase_range)
    
    # If we got some keywords, return them
    if chinese_keywords:
        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in chinese_keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        return " ".join(unique_keywords[:5])  # Limit to 5 keywords
    
    # Fallback: try to extract nouns (words > 3 chars, not common adjectives)
    words = title.split()
    common_words = {"the", "and", "for", "with", "from", "this", "that", "these", "those", 
                    "new", "old", "big", "small", "good", "bad", "best", "worst", "more", "most"}
    nouns = [w for w in words if len(w) > 3 and w.lower() not in common_words]
    
    if nouns:
        # Return first 3 nouns as placeholder
        return " ".join(nouns[:3])
    
    # Last resort: return first few words
    return " ".join(words[:3])


if __name__ == "__main__":
    # Test
    test_titles = [
        "USB C Charger 20W Fast Charging Adapter",
        "Silicone Phone Case for iPhone 15 Pro Max",
        "Stainless Steel Water Bottle 500ml",
        "LED Strip Lights 10m RGB Color Changing",
        "Yoga Mat Non-Slip Exercise Fitness Mat",
        "Car Phone Mount Holder Dashboard",
        "Kitchen Organizer Storage Rack Shelf",
        "Wireless Bluetooth Earbuds Headphones",
    ]
    
    for title in test_titles:
        translated = translate_title_to_chinese(title)
        print(f"{title}")
        print(f"  → {translated}")
        print()
