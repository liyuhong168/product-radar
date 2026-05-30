#!/usr/bin/env python3
"""Google Trends UK demand signal fetcher"""
import json, subprocess, re, sys
from pathlib import Path

BASE = Path(__file__).parent.parent
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")


def _run_anysearch(query, max_results=5):
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search", query,
             "--domain", "news", "--max_results", str(max_results), "--zone", "intl"],
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
        "Google Trends UK trending products rising 2026",
        "UK consumer search trends summer 2026 popular products",
        "what UK consumers searching for trending products 2026",
    ]

    signals = []
    for q in queries:
        print(f"  Google Trends: {q[:60]}...", file=sys.stderr)
        text = _run_anysearch(q)
        if text:
            signals.append(text)

    return "\n".join(signals)
