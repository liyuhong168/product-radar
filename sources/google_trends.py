#!/usr/bin/env python3
"""Google Trends UK demand signal fetcher - extracts trending keywords"""
import json, subprocess, re, sys
from pathlib import Path

BASE = Path(__file__).parent.parent
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")


def _run_anysearch(query, domain="web", max_results=5):
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search", query,
             "--domain", domain, "--max_results", str(max_results), "--zone", "intl"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  AnySearch error: {e}", file=sys.stderr)
    return ""


def fetch_demand_signals():
    """Fetch Google Trends UK rising product categories."""
    queries = [
        "Google Trends UK trending products rising summer 2026",
        "UK consumer trending products summer 2026 popular",
        "trending products UK summer 2026 what people buying",
    ]

    signals = []
    for q in queries:
        print(f"  Google Trends: {q[:50]}...", file=sys.stderr)
        text = _run_anysearch(q, domain="ecommerce")
        if text:
            signals.append(text)

    combined = "\n".join(signals)
    print(f"  Google Trends signals: {len(combined)} chars", file=sys.stderr)
    return combined


def extract_trending_keywords(signals_text):
    """Extract trending product keywords from Google Trends signals."""
    if not signals_text:
        return []

    keywords = []
    # Summer trending product categories in UK
    trend_words = [
        'garden', 'outdoor', 'bbq', 'camping', 'travel', 'beach', 'picnic',
        'summer', 'cooling', 'fan', 'water bottle', 'sunglasses', 'sun',
        'storage', 'organizer', 'cleaning', 'kitchen', 'bathroom',
        'fitness', 'yoga', 'exercise', 'sport', 'cycling',
        'world cup', 'football', 'euro', 'tournament',
        'festival', 'party', 'decoration', 'led', 'solar',
        'pool', 'inflatable', 'swim', 'towel',
        'barbecue', 'grill', 'patio', 'fence',
        'hose', 'sprinkler', 'lawn', 'mower',
        'tent', 'sleeping bag', 'backpack',
        'phone holder', 'car accessory', 'phone mount',
    ]

    text_lower = signals_text.lower()
    for word in trend_words:
        if word in text_lower:
            keywords.append(word)

    return list(set(keywords))[:20]
