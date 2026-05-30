#!/usr/bin/env python3
"""Reddit UK demand signal fetcher - find real user needs"""
import json, subprocess, re, sys
from pathlib import Path

BASE = Path(__file__).parent.parent
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")


def _run_anysearch(query, max_results=5):
    try:
        result = subprocess.run(
            ["python3", ANYSEARCH, "search", query,
             "--domain", "home", "--max_results", str(max_results), "--zone", "intl"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"  AnySearch error: {e}", file=sys.stderr)
    return ""


def fetch_demand_signals():
    """Fetch Reddit UK demand signals."""
    queries = [
        "reddit CasualUK best cheap finds Amazon under 10 pounds",
        "reddit AskUK what small item improved your life",
        "reddit FrugalUK best value small purchases Amazon",
        "site:reddit.com UK Amazon haul small items useful 2026",
    ]

    signals = []
    for q in queries:
        print(f"  Reddit: {q[:60]}...", file=sys.stderr)
        text = _run_anysearch(q)
        if text:
            signals.append(text)

    return "\n".join(signals)
