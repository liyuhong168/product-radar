"""Shared constants for product-radar — single source of truth."""

# Event keywords for filtering, limiting, and tagging
# Used by: run_scan_v2.py, scoring_engine.py, generate_platform.py

EVENT_KEYWORDS_SET = {
    'world cup', 'euro 2024', 'euro 2025', 'euro 2026',
    'olympic', 'olympics', 'jubilee', 'coronation',
    'christmas', 'halloween', 'easter', 'valentine',
    "mother's day", "father's day", 'black friday', 'prime day',
}

# Map keywords to event type groups (for limiting)
EVENT_KEYWORDS_MAP = {
    'world cup': 'world_cup',
    'euro 2024': 'euro', 'euro 2025': 'euro', 'euro 2026': 'euro',
    'olympic': 'olympics', 'olympics': 'olympics',
    'jubilee': 'royal', 'coronation': 'royal',
    'christmas': 'christmas', 'halloween': 'halloween',
    'easter': 'easter', 'valentine': 'valentine',
    "mother's day": 'mothers_day', "father's day": 'fathers_day',
    'black friday': 'black_friday', 'prime day': 'prime_day',
}
