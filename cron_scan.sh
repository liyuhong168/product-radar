#!/bin/bash
# Product Radar Daily Scan - Cron wrapper
# Runs scan + deploy, outputs summary for cron delivery
set -e
cd /home/lee/product-radar

echo "🔍 选品雷达自动扫描 | $(date '+%Y-%m-%d %H:%M')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Run scan
python3 run_scan_v2.py 2>/dev/null

# Get latest data file
LATEST=$(ls -t data/channels/*.json 2>/dev/null | grep -v rejected | grep -v trends | head -1)
if [ -z "$LATEST" ]; then
    echo "❌ 扫描失败：无数据文件"
    exit 1
fi

# Extract summary
PRODUCTS=$(python3 -c "import json; d=json.load(open('$LATEST')); print(len(d.get('products',[])))")
SCANNED=$(python3 -c "import json; d=json.load(open('$LATEST')); print(d.get('stats',{}).get('total_scanned',0))")
DATE=$(python3 -c "import json; d=json.load(open('$LATEST')); print(d.get('scan_date',''))")
TIME=$(python3 -c "import json; d=json.load(open('$LATEST')); print(d.get('scan_time',''))")

echo ""
echo "📊 扫描结果：${SCANNED}个产品 → ${PRODUCTS}个通过筛选"
echo "📅 扫描时间：${DATE} ${TIME}"

# Top 3 products
echo ""
echo "🏆 Top 3 推荐："
python3 -c "
import json
d = json.load(open('$LATEST'))
for i, p in enumerate(d.get('products',[])[:3], 1):
    sig = p.get('signal_label', '?')
    sd = p.get('sd_label', '')
    print(f'  {i}. {p[\"name\"][:50]}')
    print(f'     £{p[\"price\"]} | 利润{p[\"profit_margin\"]*100:.0f}% | 评分{p[\"score\"]} | {sig} {sd}')
"

# 飞书推送
echo ""
echo "📨 推送到飞书..."
python3 feishu_push.py 2>&1 || echo "  ⚠️ 飞书推送失败（不影响扫描）"

# Deploy to GitHub
echo ""
echo "📦 部署到 GitHub Pages..."
git add data/ output/ status.json -f 2>/dev/null
git diff --cached --quiet && echo "  无变更" && exit 0
git commit -m "auto-scan $(date -u '+%Y-%m-%d %H:%M')" 2>/dev/null
git pull --rebase 2>/dev/null || true
git push 2>/dev/null
echo "  ✅ 已部署：https://liyuhong168.github.io/product-radar/v2.html"
