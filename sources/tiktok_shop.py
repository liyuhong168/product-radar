#!/usr/bin/env python3
"""TikTok Shop UK data fetcher - extracts trending product keywords from search"""
import json, subprocess, re, sys
from pathlib import Path

BASE = Path(__file__).parent.parent
CONFIG = json.loads((BASE / "config.json").read_text())
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


def _extract_products_from_search(text):
    """Extract product names from AnySearch result text.
    
    AnySearch returns article snippets, not product listings.
    We extract product mentions from the text content.
    """
    products = []
    if not text:
        return products

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip metadata lines
        skip = ['## search results', 'url:', 'date:', 'keywords:',
                'posted on', 'shopping', 'explore', 'see more']
        if any(line.lower().startswith(s) for s in skip):
            continue

        # Extract numbered product mentions: "1. Waterproof Headphones"
        numbered = re.match(r'^\d+\.?\s+(.+)', line)
        if numbered:
            name = numbered.group(1).strip()
            if len(name) > 5 and len(name) < 80:
                products.append(name)
            continue

        # Extract from "trending products" type content
        # Look for product-like phrases with descriptors
        product_patterns = [
            r'(?:waterproof|portable|reusable|silicone|stainless|adjustable|'
            r'folding|compact|led|magnetic|automatic|mini|large|smart|'
            r'eco|organic|premium|professional)\s+\w+(?:\s+\w+){0,3}',
            r'(?:set|pack|kit|organizer|holder|cleaner|brush|container|'
            r'bottle|light|lamp|mat|bag|cover|case|stand|mount|clip)\s+\w+',
        ]

        for pattern in product_patterns:
            matches = re.findall(pattern, line, re.I)
            for match in matches:
                match = match.strip()
                if 5 < len(match) < 60:
                    products.append(match)

    # Deduplicate
    seen = set()
    unique = []
    for p in products:
        key = p.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def fetch():
    """Fetch TikTok trending product keywords."""
    all_products = []
    seen_names = set()

    queries = [
        "TikTok Shop UK trending products under 10 pounds 2026",
        "TikTok made me buy it UK viral products summer 2026",
        "trending TikTok products UK home kitchen accessories gadgets",
        "TikTok viral products under 10 UK small items useful",
    ]

    for q in queries:
        print(f"  TikTok search: {q[:50]}...", file=sys.stderr)
        text = _run_anysearch(q)
        if not text:
            continue

        names = _extract_products_from_search(text)
        for name in names:
            name_lower = name.lower().strip()
            if name_lower not in seen_names and len(name_lower) > 5:
                seen_names.add(name_lower)
                all_products.append({
                    "name": name,
                    "price": 0,
                    "sources": ["TikTok趋势"],
                    "signal": "TikTok社交爆品信号",
                    "needs_price_check": True
                })

    print(f"  TikTok UK total: {len(all_products)} product keywords", file=sys.stderr)
    return all_products
