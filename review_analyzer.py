#!/usr/bin/env python3
"""
Review Analyzer — Extract negative review themes for differentiation insights.

Uses AnySearch to find common complaints/problems for a product keyword on
Amazon UK, then summarizes themes and suggests differentiation opportunities.

Usage:
    python3 review_analyzer.py "silicone kitchen gadgets"
    python3 review_analyzer.py "garden tool set" 10
"""
import json, subprocess, re, sys, collections
from pathlib import Path

ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")

# Common complaint categories and trigger words
COMPLAINT_PATTERNS = {
    "durability":       r"(break|broke|broken|flimsy|cheap|fell apart|poor quality|won.?t last|durab|not durable|wear.?out|disintegrat)",
    "size/fit":         r"(too small|too big|size.?off|doesn.?t fit|smaller than|larger than|misleading size|not as (pictured|described)|dimension)",
    "smell/odor":       r"(smell|smell[sy]|odor|chemical smell|stink|stank|pungent|fume)",
    "functionality":    r"(doesn.?t work|doesn.?t function|useless|not work|defective|faulty|malfunction|does nothing)",
    "material quality": r"(thin|thinner|flimsy|feels cheap|cheap material|low quality|poor material|feels like plastic|not (stainless|silicone|genuine))",
    "safety":           r"(sharp edge|cut myself|hazard|dangerous|burn|hot to touch|toxic|bpa|safety concern)",
    "color/appearance": r"(color.?off|faded|discolor|look.?cheap|not as (pictured|shown|photo)|different color|ugly)",
    "packaging":        r"(arrived damaged|poor packaging|broken in transit|missing parts|incomplete|no instruction)",
    "value for money":  r"(not worth|overpriced|waste of money|rip.?off|not worth the price|expected better for the price)",
    "comfort/ergonomics": r"(uncomfortable|hard to grip|slippery|hurts|painful|awkward|heavy|bulky)",
}


def _run_anysearch(query, max_results=12):
    """Run AnySearch CLI and return raw output."""
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search", query,
             "--domain", "ecommerce", "--max_results", str(max_results),
             "--zone", "intl"],
            capture_output=True, text=True, timeout=45
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  AnySearch error: {e}", file=sys.stderr)
    return ""


def _extract_complaints(text: str, keyword: str) -> tuple:
    """
    Scan text for complaint patterns. Returns {theme: count} and example snippets.
    """
    text_lower = text.lower()
    theme_hits = collections.defaultdict(int)
    theme_examples = {}

    for theme, pattern in COMPLAINT_PATTERNS.items():
        matches = list(re.finditer(pattern, text_lower))
        if matches:
            theme_hits[theme] += len(matches)
            # Grab first occurrence with some context (up to 120 chars)
            m = matches[0]
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            snippet = text[start:end].strip()
            snippet = re.sub(r'\s+', ' ', snippet)
            if theme not in theme_examples:
                theme_examples[theme] = snippet

    return dict(theme_hits), theme_examples


def analyze_negative_reviews(keyword: str, max_products: int = 5) -> dict:
    """
    Search for common negative reviews/feedback for a keyword on Amazon UK.
    Returns structured dict with negative_themes and differentiation_opportunities.
    """
    # Build search queries targeting review problems
    queries = [
        f'"{keyword}" amazon uk review problems issues complaints',
        f'"{keyword}" common complaints negative feedback',
        f'{keyword} amazon review worst one star two star',
    ]

    all_text = ""
    for q in queries:
        text = _run_anysearch(q, max_results=12)
        if text:
            all_text += "\n" + text

    if not all_text.strip():
        return {
            "keyword": keyword,
            "max_products": max_products,
            "negative_themes": [],
            "differentiation_opportunities": ["数据不足，无法分析差评。建议手动搜索 Amazon UK 查看 top 5 listing 的 1-3 星评论。"],
            "raw_snippet": ""
        }

    # Extract complaint themes
    theme_counts, theme_examples = _extract_complaints(all_text, keyword)

    # Calculate frequencies
    total_hits = sum(theme_counts.values()) or 1
    sorted_themes = sorted(theme_counts.items(), key=lambda x: -x[1])

    negative_themes = []
    for theme, count in sorted_themes[:8]:  # Top 8 themes
        freq_pct = round(count / total_hits * 100)
        negative_themes.append({
            "theme": theme,
            "frequency": f"{freq_pct}%",
            "raw_count": count,
            "example": theme_examples.get(theme, "")
        })

    # Generate differentiation opportunities based on found themes
    opportunities = _generate_opportunities(keyword, negative_themes)

    return {
        "keyword": keyword,
        "max_products": max_products,
        "negative_themes": negative_themes,
        "differentiation_opportunities": opportunities,
        "raw_snippet": all_text[:500]
    }


# --- Opportunity suggestions per theme ---
_OPPORTUNITY_MAP = {
    "durability":       "找加厚/加固材质，标注耐久测试数据",
    "size/fit":         "标注真实尺寸图 + 对比参照物照片",
    "smell/odor":       "强调无味/通过SGS检测/食品级材质",
    "functionality":    "简化操作，附视频演示+说明书",
    "material quality": "升级材质（如304不锈钢/铂金硅胶），突出材质认证",
    "safety":           "突出安全认证（CE/FDA/LFGB），圆角设计",
    "color/appearance": "使用实物拍摄图，避免过度修图",
    "packaging":       "加厚包装+开箱视频+防摔测试",
    "value for money":  "增加附加值（赠品/多件装），提升感知性价比",
    "comfort/ergonomics": "人体工学设计，防滑握把",
}


def _generate_opportunities(keyword: str, themes: list) -> list:
    """Generate actionable differentiation tips from negative themes."""
    tips = []
    for t in themes:
        theme = t["theme"]
        if theme in _OPPORTUNITY_MAP:
            tips.append(f"【{theme}】{_OPPORTUNITY_MAP[theme]}")
    if not tips:
        tips.append("数据中未提取到明显差评主题，建议手动查看 Amazon 1-3 星评论。")
    return tips


def get_differentiation_tips(keyword: str, max_products: int = 5) -> str:
    """
    Convenience wrapper: returns a concise Chinese summary string.
    Example: '前5名差评集中在：1.耐用性差(38%) 2.尺寸偏小(22%) 3.气味重(15%)。建议：找加厚款+标注真实尺寸'
    """
    result = analyze_negative_reviews(keyword, max_products)
    themes = result["negative_themes"]

    if not themes:
        return f"[{keyword}] 差评数据不足，建议手动查看 Amazon UK 1-3 星评论。"

    # Theme name Chinese mapping
    _zh = {
        "durability": "耐用性差",
        "size/fit": "尺寸偏差",
        "smell/odor": "异味问题",
        "functionality": "功能缺陷",
        "material quality": "材质廉价",
        "safety": "安全隐患",
        "color/appearance": "色差/外观差",
        "packaging": "包装破损",
        "value for money": "性价比低",
        "comfort/ergonomics": "手感差",
    }

    # Top 3 themes
    top3 = []
    for t in themes[:3]:
        zh_name = _zh.get(t["theme"], t["theme"])
        top3.append(f"{zh_name}({t['frequency']})")

    theme_str = " ".join(f"{i+1}.{s}" for i, s in enumerate(top3))

    # Top suggestion from opportunities
    opps = result["differentiation_opportunities"]
    opp_str = opps[0].split("】")[-1] if opps and "】" in opps[0] else (opps[0] if opps else "待分析")

    return f"差评集中在：{theme_str}。建议：{opp_str}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 review_analyzer.py <keyword> [max_products]")
        print('  e.g. python3 review_analyzer.py "silicone kitchen gadgets"')
        sys.exit(1)

    kw = sys.argv[1]
    mp = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"[*] Analyzing negative reviews for: {kw}", file=sys.stderr)
    result = analyze_negative_reviews(kw, mp)

    # Print human-readable summary
    print(get_differentiation_tips(kw, mp))
    print()

    # Print full JSON for programmatic use
    print(json.dumps(result, ensure_ascii=False, indent=2))
