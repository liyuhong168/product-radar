#!/usr/bin/env python3
"""
Seasonal Sourcing Trigger — generates keyword reports for upcoming UK events.

Usage:
    python3 seasonal_trigger.py          # outputs report to stdout
    python3 seasonal_trigger.py --json   # JSON output for piping

Uses season_engine for event data and AnySearch CLI for trend discovery.
No pip dependencies — stdlib + subprocess only.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from season_engine import get_upcoming_events

ANYSEARCH_CLI = Path.home() / ".hermes" / "skills" / "search" / "anysearch" / "scripts" / "anysearch_cli.py"
KEYWORDS_FILE = BASE / "data" / "discovery" / "seasonal_keywords.json"


def _search_amazon_uk(query: str, max_results: int = 5) -> str:
    """Search Amazon UK via AnySearch CLI. Returns raw text results."""
    cmd = [
        sys.executable, str(ANYSEARCH_CLI), "search",
        f"Amazon UK {query} trending best sellers",
        "--domain", "ecommerce",
        "--zone", "intl",
        "--max_results", str(max_results),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  [AnySearch error for '{query}']: {result.stderr.strip()}", file=sys.stderr)
            return ""
        return result.stdout
    except Exception as e:
        print(f"  [AnySearch exception for '{query}']: {e}", file=sys.stderr)
        return ""


def _extract_keywords(text: str, category: str) -> list[str]:
    """Extract 3-5 candidate product keywords from AnySearch results."""
    if not text:
        return []

    # Common stop words to filter out
    stops = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "it", "as", "be", "was", "are",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "this", "that",
        "these", "those", "i", "you", "he", "she", "we", "they", "me", "him",
        "her", "us", "them", "my", "your", "his", "its", "our", "their",
        "amazon", "uk", "co", "www", "http", "https", "com", "best", "top",
        "buy", "shop", "sale", "price", "deal", "free", "delivery", "prime",
        "new", "review", "rating", "star", "stars", "product", "item",
    }

    # Find quoted phrases and product-like noun phrases
    candidates = []

    # Quoted strings (product names)
    for m in re.finditer(r'"([^"]{3,60})"', text):
        phrase = m.group(1).strip()
        if len(phrase.split()) <= 5:
            candidates.append(phrase)

    # Title-case multi-word phrases (likely product names)
    for m in re.finditer(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})', text):
        phrase = m.group(1).strip()
        words = phrase.lower().split()
        if words[0] not in stops and len(words) >= 2:
            candidates.append(phrase)

    # Single meaningful words (nouns-ish, >4 chars, not stop words)
    for m in re.finditer(r'\b([A-Za-z]{5,})\b', text):
        word = m.group(1).lower()
        if word not in stops and not word.startswith("http"):
            candidates.append(word)

    # Deduplicate, preserve order, limit to 5
    seen = set()
    keywords = []
    for c in candidates:
        key = c.lower().strip()
        if key not in seen and len(key) > 2:
            seen.add(key)
            keywords.append(c)
        if len(keywords) >= 5:
            break

    # Ensure at least the category itself is included
    if not keywords:
        keywords.append(category)

    return keywords[:5]


def _load_existing_keywords() -> dict:
    """Load previously saved keywords for dedup."""
    if KEYWORDS_FILE.exists():
        try:
            return json.loads(KEYWORDS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_keywords(all_keywords: dict):
    """Save keywords to JSON for dedup."""
    KEYWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYWORDS_FILE.write_text(json.dumps(all_keywords, indent=2, ensure_ascii=False))


def run(output_json: bool = False) -> str:
    """Main entry point. Returns formatted report string (empty if nothing to report)."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    events = get_upcoming_events(60)

    # Filter: only events not yet overdue
    actionable = [e for e in events if e["sourcing_urgency"] != "OVERDUE"]

    if not actionable:
        if output_json:
            return json.dumps({"events": [], "date": today.strftime("%Y-%m-%d")})
        return ""

    existing = _load_existing_keywords()
    report_lines = []
    all_new_keywords = {}

    for event in actionable:
        categories = event["recommended_categories"][:2]
        event_keywords = []

        for cat in categories:
            # Skip overly generic categories
            if cat.lower() in ("everything — best sellers", "everything"):
                continue

            raw = _search_amazon_uk(cat)
            kws = _extract_keywords(raw, cat)
            event_keywords.extend(kws)

        # Deduplicate keywords per event
        seen = set()
        unique_kws = []
        for kw in event_keywords:
            key = kw.lower()
            if key not in seen:
                seen.add(key)
                unique_kws.append(kw)

        # Filter out keywords already discovered
        new_kws = [kw for kw in unique_kws if kw.lower() not in existing]

        if output_json:
            all_new_keywords[event["event_name"]] = new_kws
            continue

        # Format report section
        report_lines.append(f"📅 {event['event_name']} ({event['days_until']}天后)")
        report_lines.append(
            f"空运DDL: {event['sourcing_deadline_air']} | "
            f"卡航DDL: {event['sourcing_deadline_rail']} | "
            f"状态: {event['sourcing_urgency']}"
        )
        report_lines.append(f"推荐品类: {', '.join(categories)}")

        if new_kws:
            report_lines.append("发现关键词:")
            for kw in new_kws:
                report_lines.append(f"  - {kw} (Amazon UK trend)")
        else:
            report_lines.append("发现关键词: (无新关键词)")

        report_lines.append("")  # blank line separator

        # Save to persistent dict
        for kw in new_kws:
            existing[kw.lower()] = {
                "keyword": kw,
                "event": event["event_name"],
                "discovered": today.strftime("%Y-%m-%d"),
                "urgency": event["sourcing_urgency"],
            }

    # Persist
    _save_keywords(existing)

    if output_json:
        return json.dumps({
            "date": today.strftime("%Y-%m-%d"),
            "events": [{
                "name": e["event_name"],
                "days_until": e["days_until"],
                "urgency": e["sourcing_urgency"],
                "categories": e["recommended_categories"][:2],
                "keywords": all_new_keywords.get(e["event_name"], []),
            } for e in actionable],
        }, indent=2, ensure_ascii=False)

    if not report_lines:
        return ""

    header = f"⏰ 季节选品提醒 | {today.strftime('%Y-%m-%d')}"
    return header + "\n\n" + "\n".join(report_lines)


if __name__ == "__main__":
    json_mode = "--json" in sys.argv
    output = run(output_json=json_mode)
    if output:
        print(output)
