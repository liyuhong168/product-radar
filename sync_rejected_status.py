#!/usr/bin/env python3
"""
同步 kanban 看板的"不考虑"状态到 rejected_by_user.json。

流程：
1. 读取 data/kanban_status.json 获取所有 status="rejected" 的 ASIN
2. 从 data/channels/ + data/history/ + data/discovery/ 中查找产品详情
3. 合并写入 rejected_by_user.json（保留已存在的条目，回填 [待补充] 条目）
"""
import json
import sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
KANBAN_FILE = BASE / "data" / "kanban_status.json"
REJECTED_FILE = BASE / "rejected_by_user.json"
CHANNELS_DIR = BASE / "data" / "channels"
HISTORY_DIR = BASE / "data" / "history"
DISCOVERY_DIR = BASE / "data" / "discovery"


def get_data_files():
    """收集所有可能包含产品详情的 JSON 文件"""
    files = []
    for d in [CHANNELS_DIR, HISTORY_DIR, DISCOVERY_DIR]:
        if d.exists():
            for f in sorted(d.glob("*.json")):
                name = f.name
                if "-rejected" not in name and "-trends" not in name and "-raw" not in name:
                    files.append(f)
    return files


def extract_product_details(data_files):
    """从所有数据文件中提取产品详情"""
    products = {}
    for f in data_files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        items = []
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            for key in ["products", "items", "insights", "data"]:
                if key in raw and isinstance(raw[key], list):
                    items = raw[key]
                    break

        for item in items:
            if not isinstance(item, dict):
                continue
            asin = item.get("asin") or item.get("ASIN") or ""
            if not asin or len(asin) < 8:
                continue

            if asin not in products:
                products[asin] = {
                    "name": item.get("name") or item.get("title") or item.get("product_name", ""),
                    "category": (item.get("category") or item.get("cat") or
                                 item.get("category_name", "Unknown")),
                    "channel": item.get("channel") or item.get("source") or item.get("channel_name", ""),
                    "price": item.get("price") or item.get("selling_price", 0),
                    "reviews": item.get("reviews") or item.get("review_count", 0),
                    "rating": item.get("rating") or item.get("star_rating", 0),
                }

    return products


def sync():
    print("=== 同步 kanban 不考虑状态到 rejected_by_user.json ===", file=sys.stderr)

    # 1. 读取 kanban 状态
    if not KANBAN_FILE.exists():
        print("❌ kanban_status.json 不存在", file=sys.stderr)
        return False

    kanban = json.loads(KANBAN_FILE.read_text(encoding="utf-8"))
    rejected_asins = [k for k, v in kanban.items() if v == "rejected"]
    print(f"  kanban 中 rejected: {len(rejected_asins)} 个", file=sys.stderr)

    if not rejected_asins:
        print("  ℹ️ 没有 rejected 产品", file=sys.stderr)
        return True

    # 2. 提取产品详情
    data_files = get_data_files()
    print(f"  数据源: {len(data_files)} 个文件", file=sys.stderr)
    product_details = extract_product_details(data_files)
    print(f"  提取了 {len(product_details)} 个不重复产品", file=sys.stderr)

    # 3. 读取现有数据
    existing = {}
    if REJECTED_FILE.exists():
        existing = json.loads(REJECTED_FILE.read_text(encoding="utf-8"))

    # 4. 合并/回填
    added = 0
    backfilled = 0
    kept = 0

    for asin in rejected_asins:
        # 检查是否已存在且不是 [待补充]
        if asin in existing:
            existing_name = existing[asin].get("name", "")
            if not existing_name.startswith("[待补充]"):
                kept += 1
                continue
            # 需要回填
            detail = product_details.get(asin, {})
            name = (detail.get("name") or "").strip()
            if name:
                existing[asin].update({
                    "name": name,
                    "category": detail.get("category", "Unknown"),
                    "channel": detail.get("channel", ""),
                    "price": detail.get("price", 0),
                    "reviews": detail.get("reviews", 0),
                    "rating": detail.get("rating", 0),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                })
                backfilled += 1
                print(f"  🔄 回填 {asin}: {name[:50]}", file=sys.stderr)
            else:
                kept += 1
            continue

        # 新增
        detail = product_details.get(asin, {})
        name = (detail.get("name") or "").strip()
        entry = {
            "name": name if name else f"[待补充] ASIN:{asin}",
            "category": detail.get("category", "Unknown") if name else "Unknown",
            "channel": detail.get("channel", ""),
            "price": detail.get("price", 0),
            "reviews": detail.get("reviews", 0),
            "rating": detail.get("rating", 0),
            "sources": [],
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        existing[asin] = entry
        added += 1
        if not name:
            print(f"  ⚠️ 新增 {asin}: 未找到产品详情", file=sys.stderr)
        else:
            print(f"  ✅ 新增 {asin}: {name[:50]}", file=sys.stderr)

    # 5. 写回
    REJECTED_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8"
    )

    print(f"\n✅ 同步完成:" , file=sys.stderr)
    print(f"   新增: {added} | 回填: {backfilled} | 保持: {kept}", file=sys.stderr)
    print(f"   总计: {len(existing)} 个", file=sys.stderr)
    return True


if __name__ == "__main__":
    success = sync()
    sys.exit(0 if success else 1)