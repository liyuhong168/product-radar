#!/usr/bin/env python3
"""
competitor_monitor.py - Monitor competitors for already-selected products.
Scrapes Amazon UK via ScraperAPI, compares against historical snapshots,
and emits alerts for significant changes.
"""
import json, os, sys, re, time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote_plus

BASE = Path(__file__).parent
COMP_DIR = BASE / "data" / "competitors"
_API_KEY_FILE = Path.home() / ".hermes" / "scraperapi_key.txt"


def _load_api_key():
    if _API_KEY_FILE.exists():
        return _API_KEY_FILE.read_text().strip()
    return os.environ.get("SCRAPERAPI_KEY", "")


def _scraper_url(target_url, api_key):
    return f"http://api.scraperapi.com?api_key={api_key}&url={quote_plus(target_url)}"


def _fetch_page(url, api_key, max_retries=2):
    proxy_url = _scraper_url(url, api_key)
    for attempt in range(max_retries + 1):
        try:
            req = Request(proxy_url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"[WARN] Failed to fetch {url}: {e}", file=sys.stderr)
                return ""


def _parse_price(html):
    for pat in [
        r'<span[^>]*class="a-price-whole">(\d+)</span>.*?<span[^>]*class="a-price-fraction">(\d+)</span>',
        r'"priceAmount":\s*([\d.]+)',
    ]:
        m = re.search(pat, html, re.DOTALL)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                return float(f"{groups[0]}.{groups[1]}")
            return float(groups[0])
    return None


def _parse_reviews(html):
    for pat in [
        r'id="acrCustomerReviewText"[^>]*>([\d,]+)\s*review',
        r'"ratingCount":\s*(\d+)',
    ]:
        m = re.search(pat, html)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _parse_rating(html):
    for pat in [
        r'<span[^>]*class="a-icon-alt">([\d.]+)\s*out',
        r'"ratingValue":\s*([\d.]+)',
    ]:
        m = re.search(pat, html)
        if m:
            return float(m.group(1))
    return None


def _parse_bsr(html):
    patterns = [
        r'#(\d[\d,]*)\s+in\s+[^<]*(?:\(|$)',
        r'"bestSellerRank":\s*#?([\d,]+)',
        r'Best Sellers Rank:\s*#?([\d,]+)',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _parse_title(html):
    m = re.search(r'<span[^>]*id="productTitle"[^>]*>(.*?)</span>', html, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def scrape_product(asin, api_key):
    url = f"https://www.amazon.co.uk/dp/{asin}"
    html = _fetch_page(url, api_key)
    if not html:
        return {"asin": asin, "error": "fetch_failed"}
    return {
        "asin": asin,
        "title": _parse_title(html),
        "price": _parse_price(html),
        "reviews": _parse_reviews(html),
        "rating": _parse_rating(html),
        "bsr": _parse_bsr(html),
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
    }


def _save_snapshot(asin, data):
    asin_dir = COMP_DIR / asin
    asin_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    snap_file = asin_dir / f"{today}.json"
    existing = []
    if snap_file.exists():
        try:
            existing = json.loads(snap_file.read_text())
        except json.JSONDecodeError:
            existing = []
    existing.append(data)
    snap_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


def _load_previous_snapshots(asin, exclude_today=True):
    asin_dir = COMP_DIR / asin
    if not asin_dir.exists():
        return []
    today = datetime.now().strftime("%Y-%m-%d")
    snapshots = []
    for f in sorted(asin_dir.glob("*.json"), reverse=True):
        if exclude_today and f.stem == today:
            continue
        try:
            entries = json.loads(f.read_text())
            for entry in entries:
                entry["_file_date"] = f.stem
            snapshots.extend(entries)
        except json.JSONDecodeError:
            continue
    return snapshots


def _detect_alerts(asin, current, history):
    alerts = []
    if not history:
        alerts.append({"asin": asin, "type": "new_tracking", "severity": "info",
                        "message": f"Started tracking {asin} - no historical baseline yet"})
        return alerts

    prev = history[0]

    if current.get("price") and prev.get("price"):
        drop_pct = (prev["price"] - current["price"]) / prev["price"] * 100
        if drop_pct > 10:
            severity = "critical" if drop_pct > 25 else "warning"
            alerts.append({"asin": asin, "type": "price_drop", "severity": severity,
                "message": f"Price dropped {drop_pct:.0f}%",
                "old": prev["price"], "new": current["price"], "change_pct": round(drop_pct, 1)})

    if current.get("reviews") is not None:
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_old = [h for h in history if h.get("_file_date", "") <= week_ago]
        if week_old and week_old[-1].get("reviews") is not None:
            review_delta = current["reviews"] - week_old[-1]["reviews"]
            if review_delta > 50:
                alerts.append({"asin": asin, "type": "review_spike", "severity": "warning",
                    "message": f"Review count jumped +{review_delta} in 7 days",
                    "old": week_old[-1]["reviews"], "new": current["reviews"]})

    if current.get("bsr") and prev.get("bsr") and prev["bsr"] > 0:
        bsr_change_pct = (current["bsr"] - prev["bsr"]) / prev["bsr"] * 100
        if bsr_change_pct > 20:
            alerts.append({"asin": asin, "type": "bsr_drop", "severity": "warning",
                "message": f"BSR worsened {bsr_change_pct:.0f}%",
                "old": prev["bsr"], "new": current["bsr"], "change_pct": round(bsr_change_pct, 1)})
        elif bsr_change_pct < -20:
            alerts.append({"asin": asin, "type": "bsr_improvement", "severity": "info",
                "message": f"BSR improved {abs(bsr_change_pct):.0f}%",
                "old": prev["bsr"], "new": current["bsr"], "change_pct": round(bsr_change_pct, 1)})

    if current.get("rating") and prev.get("rating"):
        rd = current["rating"] - prev["rating"]
        if abs(rd) >= 0.3:
            alerts.append({"asin": asin, "type": "rating_change",
                "severity": "warning" if rd < 0 else "info",
                "message": f"Rating changed: {prev['rating']:.1f} -> {current['rating']:.1f}",
                "old": prev["rating"], "new": current["rating"]})

    if not alerts:
        alerts.append({"asin": asin, "type": "stable", "severity": "info",
                        "message": f"No significant changes for {asin}"})
    return alerts


def monitor_competitors(asin_list: list[str]) -> list[dict]:
    """Monitor competitors for a list of ASINs. Returns alerts with severity."""
    api_key = _load_api_key()
    if not api_key:
        print("[ERROR] No ScraperAPI key found.", file=sys.stderr)
        return [{"asin": a, "type": "error", "severity": "critical", "message": "No API key"} for a in asin_list]

    all_alerts = []
    for asin in asin_list:
        asin = asin.strip().upper()
        if not asin:
            continue
        print(f"[INFO] Scraping {asin}...", file=sys.stderr)
        data = scrape_product(asin, api_key)
        if "error" in data:
            all_alerts.append({"asin": asin, "type": "error", "severity": "critical",
                               "message": f"Failed to scrape: {data['error']}"})
            continue
        _save_snapshot(asin, data)
        history = _load_previous_snapshots(asin)
        alerts = _detect_alerts(asin, data, history)
        all_alerts.extend(alerts)
        time.sleep(2)
    return all_alerts


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 competitor_monitor.py <asin1> <asin2> ...")
        sys.exit(1)
    results = monitor_competitors(sys.argv[1:])
    print(json.dumps(results, indent=2, ensure_ascii=False))
