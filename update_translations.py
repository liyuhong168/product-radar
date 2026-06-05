#!/usr/bin/env python3
"""Update existing data files with Chinese translations for 1688 search."""

import json
from pathlib import Path
from translate import translate_title_to_chinese

DATA_DIR = Path(__file__).parent / "data" / "channels"

def update_data_files():
    """Add name_cn field to all products in data files."""
    updated_count = 0
    
    for json_file in DATA_DIR.glob("*.json"):
        if "-rejected" in json_file.name or "-trends" in json_file.name:
            continue
        
        print(f"Processing: {json_file.name}")
        data = json.loads(json_file.read_text(encoding="utf-8"))
        
        if "products" not in data:
            continue
        
        modified = False
        for product in data["products"]:
            if "name_cn" not in product:
                name = product.get("name", "")
                product["name_cn"] = translate_title_to_chinese(name)
                modified = True
                updated_count += 1
        
        if modified:
            json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  Updated {len(data['products'])} products")
    
    print(f"\nTotal: Updated {updated_count} products")

if __name__ == "__main__":
    update_data_files()
