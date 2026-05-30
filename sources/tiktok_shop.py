#!/usr/bin/env python3
"""TikTok Shop UK data fetcher - extracts trending product CATEGORIES"""
import json, subprocess, re, sys
from pathlib import Path

BASE = Path(__file__).parent.parent
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")


def _run_anysearch(query, domain="ecommerce", max_results=5):
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


def _extract_trending_categories(text):
    """Extract trending product category keywords from search results.
    
    Returns a list of category keywords that can be matched against Amazon products.
    """
    if not text:
        return []

    categories = set()
    text_lower = text.lower()

    # Known TikTok trending product categories
    known_categories = [
        'kitchen gadgets', 'kitchen accessories', 'kitchen utensils',
        'cleaning', 'organizer', 'storage', 'home decor',
        'phone case', 'phone accessories', 'phone holder',
        'beauty tools', 'skincare', 'hair care',
        'fitness', 'yoga', 'exercise',
        'car accessories', 'car organizer',
        'garden', 'outdoor', 'camping',
        'led lights', 'solar lights', 'string lights',
        'water bottle', 'lunch box',
        'pet accessories', 'dog toys',
        'craft supplies', 'stationery', 'art supplies',
        'travel accessories', 'packing cubes',
        'usb gadgets', 'tech accessories',
        'wall art', 'posters', 'stickers',
        'candles', 'home fragrance',
        'bathroom accessories', 'shower',
        'desk accessories', 'office supplies',
        'reusable', 'eco friendly', 'sustainable',
        'personalized', 'custom',
        'tote bag', 'makeup bag', 'storage bag',
        'phone stand', 'laptop stand',
        'mini', 'portable', 'compact',
    ]

    for cat in known_categories:
        if cat in text_lower:
            categories.add(cat)

    # Also extract from numbered lists in the text
    # "1. Unique mobile phone cases" → "phone cases"
    for m in re.finditer(r'\d+[\.\)]\s*([A-Za-z][a-z]+(?:\s+[a-z]+){1,4})', text):
        phrase = m.group(1).strip().lower()
        if len(phrase) > 5 and len(phrase) < 40:
            categories.add(phrase)

    # Extract from "X trending products" patterns
    for m in re.finditer(r'(?:trending|popular|viral|best selling)\s+([a-z\s]+?)(?:\s+on\s|\s+in\s|\s+for\s|\.|,)', text_lower):
        phrase = m.group(1).strip()
        if 3 < len(phrase) < 30:
            categories.add(phrase)

    return list(categories)


def fetch():
    """Fetch TikTok trending categories for cross-matching with Amazon."""
    all_categories = set()

    queries = [
        "TikTok Shop UK trending products under 10 pounds 2026",
        "TikTok made me buy it UK viral products summer 2026",
        "trending TikTok products UK home kitchen accessories gadgets",
        "TikTok viral products under 10 UK small items useful",
    ]

    for q in queries:
        print(f"  TikTok search: {q[:50]}...", file=sys.stderr)
        text = _run_anysearch(q)
        cats = _extract_trending_categories(text)
        all_categories.update(cats)

    print(f"  TikTok UK: {len(all_categories)} trending categories", file=sys.stderr)

    # Return as product-like entries for the matcher
    products = []
    for cat in all_categories:
        products.append({
            "name": cat,
            "price": 0,
            "sources": ["TikTok趋势"],
            "signal": "TikTok品类趋势",
            "is_category": True
        })

    return products
