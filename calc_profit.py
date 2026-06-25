#!/usr/bin/env python3
"""统一利润计算 — 选品雷达和选品发现共用
用法: python3 calc_profit.py <price_gbp> [category]
输出: JSON格式的利润明细
"""
import json, sys

# 与 config.json / scanner.py 保持一致
COST = {
    "vat_rate": 0.167,
    "commission_rate": 0.15,
    "commission_home": 0.08,
    "commission_pets": 0.05,
    "ad_rate": 0.10,
    "return_rate": 0.02,
    "fba_small_standard": 1.46,
    "fba_large_standard": 2.46,
    "sourcing_cost": 0.80,
    "exchange_rate": 7.3,
}


def calc_profit(price_gbp, category="general", sourcing_gbp=None):
    """Calculate profit for a given price.
    
    Args:
        price_gbp: Amazon UK selling price in GBP
        category: product category (affects commission rate)
        sourcing_gbp: actual sourcing cost in GBP (if None, uses default £0.80)
    """
    comm_rate = COST["commission_rate"]
    cat_lower = category.lower()
    if "home" in cat_lower or "kitchen" in cat_lower:
        comm_rate = COST["commission_home"]
    elif "pet" in cat_lower:
        comm_rate = COST["commission_pets"]

    vat = price_gbp * COST["vat_rate"]
    commission = price_gbp * comm_rate
    fba = COST["fba_small_standard"]
    ads = price_gbp * COST["ad_rate"]
    returns = price_gbp * COST["return_rate"]
    sourcing = sourcing_gbp if sourcing_gbp is not None else COST["sourcing_cost"]

    total_cost = vat + commission + fba + ads + returns + sourcing
    net_profit = price_gbp - total_cost
    margin = net_profit / price_gbp if price_gbp > 0 else 0

    return {
        "net_profit": round(net_profit, 2),
        "margin": round(margin, 3),
        "margin_pct": f"{margin*100:.1f}%",
        "breakdown": {
            "vat": round(vat, 2),
            "commission": round(commission, 2),
            "fba": fba,
            "ads": round(ads, 2),
            "returns": round(returns, 2),
            "sourcing": round(sourcing, 2),
            "total_cost": round(total_cost, 2),
        }
    }


if __name__ == "__main__":
    price = float(sys.argv[1]) if len(sys.argv) > 1 else 7.50
    category = sys.argv[2] if len(sys.argv) > 2 else "general"
    result = calc_profit(price, category)
    print(json.dumps(result, ensure_ascii=False, indent=2))
