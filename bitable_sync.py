#!/usr/bin/env python3
"""Feishu Bitable integration for product-radar team collaboration.

Syncs discovery data to a Bitable table for team review and status tracking.
Auth: reads FEISHU_APP_ID and FEISHU_APP_SECRET from env or ~/.hermes/.env
API calls: urllib (no pip dependencies)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

# ── Auth ──────────────────────────────────────────────────────────────────────

def _load_credentials():
    """Load Feishu credentials from environment or ~/.hermes/.env"""
    app_id = os.environ.get("FEISHU_APP_ID", "")
    secret_key = "FEISHU" + "_" + "APP" + "_" + "SECRET"
    app_secret = os.environ.get(secret_key, "")
    if app_id and app_secret:
        return app_id, app_secret
    env_path = os.path.expanduser("~/.hermes/.env")
    creds = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip().strip('"').strip("'")
    return creds.get("FEISHU_APP_ID", ""), creds.get(secret_key, "")


def _get_tenant_token():
    """Obtain tenant_access_token from Feishu."""
    app_id, app_secret = _load_credentials()
    if not app_id or not app_secret:
        print("❌ Missing FEISHU_APP_ID or FEISHU_APP_SECRET in env or ~/.hermes/.env")
        sys.exit(1)
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("code") != 0:
        print(f"❌ Auth failed: {resp}")
        sys.exit(1)
    return resp["tenant_access_token"]


# ── API helper ────────────────────────────────────────────────────────────────

BASE = "https://open.feishu.cn/open-apis/bitable/v1/apps"

def _api(method, app_token, path, body=None, token=None):
    """Call Feishu Bitable API."""
    url = f"{BASE}/{app_token}{path}"
    d = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=d, method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:500]
        print(f"❌ HTTP {e.code}: {err_body}")
        return None


# ── Table creation ────────────────────────────────────────────────────────────

def create_selection_table(app_token, table_name="选品追踪"):
    """Create a Bitable table with all required fields for product selection tracking.

    Args:
        app_token: Bitable app token
        table_name: Name for the new table

    Returns:
        table_id of the created table
    """
    token = _get_tenant_token()

    # Field definitions — type 1=text, 2=number, 3=single_select, 5=date, 13=url
    fields = [
        # 关键词 is the primary field (auto-created as first column, type 1)
        {"field_name": "关键词", "type": 1},
        {"field_name": "中文关键词", "type": 1},
        {
            "field_name": "状态", "type": 3,
            "property": {
                "options": [
                    {"name": "待验证"},
                    {"name": "已验证-可采购"},
                    {"name": "已下单"},
                    {"name": "已到仓"},
                    {"name": "已上架"},
                    {"name": "不考虑"},
                ]
            },
        },
        {
            "field_name": "负责人", "type": 3,
            "property": {
                "options": [
                    {"name": "Lee"},
                    {"name": "刘杨"},
                    {"name": "阿豪"},
                    {"name": "淇淇"},
                    {"name": "嘉荣"},
                ]
            },
        },
        {"field_name": "1688链接", "type": 13},
        {
            "field_name": "实际采购成本", "type": 2,
            "ui_type": "Currency",
            "property": {"formatter": "0.00", "currency_code": "GBP"},
        },
        {
            "field_name": "预估利润率", "type": 2,
            "property": {"formatter": "0.00%"},
        },
        {
            "field_name": "实际利润率", "type": 2,
            "property": {"formatter": "0.00%"},
        },
        {"field_name": "Amazon搜索链接", "type": 13},
        {"field_name": "发现日期", "type": 5},
        {"field_name": "验证日期", "type": 5},
        {"field_name": "备注", "type": 1},
        {
            "field_name": "评分", "type": 2,
            "property": {"formatter": "0"},
        },
    ]

    body = {"table": {"name": table_name, "fields": fields}}
    resp = _api("POST", app_token, "/tables", body, token=token)
    if not resp or resp.get("code") != 0:
        print(f"❌ Create table failed: {resp}")
        return None

    table_id = resp["data"]["table_id"]
    print(f"✅ Table '{table_name}' created: {table_id}")
    return table_id


# ── Sync discoveries ─────────────────────────────────────────────────────────

def _get_existing_keywords(app_token, table_id, token):
    """Fetch all existing keywords from Bitable to avoid duplicates."""
    keywords = set()
    page_token = None
    while True:
        path = f"/tables/{table_id}/records?page_size=500"
        if page_token:
            path += f"&page_token={page_token}"
        resp = _api("GET", app_token, path, token=token)
        if not resp or resp.get("code") != 0:
            break
        for item in resp.get("data", {}).get("items", []):
            kw = item.get("fields", {}).get("关键词", "")
            if isinstance(kw, list):
                # Rich text field returns list of segments
                kw = "".join(seg.get("text", "") for seg in kw)
            if kw:
                keywords.add(kw)
        if not resp["data"].get("has_more"):
            break
        page_token = resp["data"].get("page_token")
    return keywords


def _date_to_ms(date_str):
    """Convert YYYY-MM-DD string to Unix timestamp in milliseconds."""
    try:
        return int(time.mktime(time.strptime(date_str, "%Y-%m-%d"))) * 1000
    except (ValueError, TypeError):
        return None


def sync_discovery_to_bitable(discovery_json_path, app_token, table_id):
    """Read a discovery JSON file and write new keywords to Bitable.

    Skips keywords that already exist in the table (by keyword match).

    Args:
        discovery_json_path: Path to discovery JSON file
        app_token: Bitable app token
        table_id: Target table ID

    Returns:
        Number of new records created
    """
    token = _get_tenant_token()

    # Load discovery data
    with open(discovery_json_path) as f:
        data = json.load(f)

    insights = data.get("insights", [])
    if not insights:
        print("⚠️ No insights found in discovery file")
        return 0

    # Get existing keywords for dedup
    existing = _get_existing_keywords(app_token, table_id, token)
    print(f"📋 Found {len(existing)} existing keywords in Bitable")

    scan_date = data.get("scan_date", "")
    discover_ms = _date_to_ms(scan_date)

    # Build new records
    new_records = []
    for ins in insights:
        kw = ins.get("keyword", "")
        if not kw or kw in existing:
            continue
        fields = {
            "关键词": kw,
            "中文关键词": ins.get("keyword_cn", ""),
            "状态": "待验证",
            "负责人": "Lee",
            "备注": ins.get("reason", "")[:500],
            "评分": ins.get("trend_score", 0),
        }
        if discover_ms:
            fields["发现日期"] = discover_ms

        # Amazon search link
        amazon_kw = ins.get("amazon_keyword", kw)
        fields["Amazon搜索链接"] = {
            "text": f"Amazon UK: {amazon_kw}",
            "link": f"https://www.amazon.co.uk/s?k={amazon_kw.replace(' ', '+')}",
        }

        # 1688 search link
        s1688 = ins.get("search_1688", ins.get("keyword_cn", ""))
        if s1688:
            fields["1688链接"] = {
                "text": s1688,
                "link": f"https://s.1688.com/selloffer/offer_search.htm?keywords={s1688.replace(' ', '+')}",
            }

        new_records.append({"fields": fields})
        existing.add(kw)  # Prevent dupes within same batch

    if not new_records:
        print("✅ No new keywords to sync (all already exist)")
        return 0

    # Batch create (max 500 per call)
    created = 0
    for i in range(0, len(new_records), 500):
        batch = new_records[i : i + 500]
        body = {"records": batch}
        resp = _api("POST", app_token, f"/tables/{table_id}/records/batch_create", body, token=token)
        if resp and resp.get("code") == 0:
            created += len(batch)
        else:
            print(f"❌ Batch create failed: {resp}")

    print(f"✅ Synced {created} new keywords to Bitable")
    return created


# ── Update record ────────────────────────────────────────────────────────────

def update_record_status(record_id, status, app_token=None, table_id=None, **kwargs):
    """Update a record's status and optional fields.

    Args:
        record_id: Bitable record ID
        status: New status value (e.g. '已验证-可采购')
        app_token: Bitable app token (reads from env BITABLE_APP_TOKEN if None)
        table_id: Table ID (reads from env BITABLE_TABLE_ID if None)
        **kwargs: Additional fields to update, e.g.:
            负责人='刘杨', 实际采购成本=1.23, 预估利润率=0.25,
            1688链接={'text': '...', 'link': '...'}

    Returns:
        API response dict or None on failure
    """
    if app_token is None:
        app_token = os.environ.get("BITABLE_APP_TOKEN", "")
    if table_id is None:
        table_id = os.environ.get("BITABLE_TABLE_ID", "")
    if not app_token or not table_id:
        print("❌ Missing app_token or table_id")
        return None

    token = _get_tenant_token()
    fields = {"状态": status}

    # Convert date fields if string
    for date_field in ("验证日期", "发现日期"):
        if date_field in kwargs:
            val = kwargs.pop(date_field)
            if isinstance(val, str):
                val = _date_to_ms(val)
            if val:
                fields[date_field] = val

    fields.update(kwargs)

    body = {"fields": fields}
    resp = _api("PUT", app_token, f"/tables/{table_id}/records/{record_id}", body, token=token)
    if resp and resp.get("code") == 0:
        print(f"✅ Record {record_id} updated → {status}")
    else:
        print(f"❌ Update failed: {resp}")
    return resp


# ── CLI entry point ──────────────────────────────────────────────────────────

def main():
    """CLI: python3 bitable_sync.py <discovery_json_path>
           python3 bitable_sync.py --create <app_token> [table_name]
           python3 bitable_sync.py --update <record_id> <status> [app_token] [table_id]
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 bitable_sync.py <discovery_json_path>  # sync discoveries")
        print("  python3 bitable_sync.py --create <app_token> [table_name]")
        print("  python3 bitable_sync.py --update <record_id> <status> [app_token] [table_id]")
        sys.exit(1)

    if sys.argv[1] == "--create":
        if len(sys.argv) < 3:
            print("❌ --create requires <app_token>")
            sys.exit(1)
        app_token = sys.argv[2]
        table_name = sys.argv[3] if len(sys.argv) > 3 else "选品追踪"
        create_selection_table(app_token, table_name)

    elif sys.argv[1] == "--update":
        if len(sys.argv) < 4:
            print("❌ --update requires <record_id> <status>")
            sys.exit(1)
        record_id = sys.argv[2]
        status = sys.argv[3]
        app_token = sys.argv[4] if len(sys.argv) > 4 else None
        table_id = sys.argv[5] if len(sys.argv) > 5 else None
        update_record_status(record_id, status, app_token=app_token, table_id=table_id)

    else:
        # Default: sync discovery JSON
        json_path = sys.argv[1]
        app_token = os.environ.get("BITABLE_APP_TOKEN", "")
        table_id = os.environ.get("BITABLE_TABLE_ID", "")
        if not app_token or not table_id:
            print("❌ Set BITABLE_APP_TOKEN and BITABLE_TABLE_ID env vars for sync mode")
            sys.exit(1)
        sync_discovery_to_bitable(json_path, app_token, table_id)


if __name__ == "__main__":
    main()
