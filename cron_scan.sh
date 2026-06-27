#!/bin/bash
set -a; source /home/lee/.hermes/.env; set +a
export SCRAPER_APIKEY=***
export SCRAPER_API_KEY="$SCRAPER_APIKEY"  # Fix: Python reads SCRAPER_API_KEY (with underscore)
# Product Radar Daily Scan - Cron wrapper
# Runs scan + BSR enrichment + platform generation + deploy
set -e
cd /home/lee/product-radar

# All detail goes to log file; cron only sees the one-line result
LOG="/home/lee/product-radar/logs/cron_$(date '+%Y%m%d_%H%M%S').log"
mkdir -p /home/lee/product-radar/logs
find /home/lee/product-radar/logs -name "cron_*.log" -mtime +7 -delete 2>/dev/null

{
echo "🔍 选品雷达自动扫描 | $(date '+%Y-%m-%d %H:%M')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Run radar scan (timeout: 7 min)
echo ""
echo "📡 Step 1: 雷达扫描..."
timeout 900 python3 -u run_scan_v2.py 2>&1 || { echo "❌ 扫描超时或失败"; exit 1; }

# Get latest data file
LATEST=$(ls -t data/channels/*.json 2>/dev/null | grep -v rejected | grep -v trends | grep -v bsr_data | head -1)
if [ -z "$LATEST" ]; then
    echo "❌ 扫描失败：无数据文件"
    exit 1
fi

# Step 2: BSR enrichment using Playwright (timeout: 3 min)
echo ""
echo "📊 Step 2: BSR数据抓取..."
timeout 180 python3 bsr_scraper.py --enrich 2>&1 || echo "  ⚠️ BSR抓取失败（不影响主流程）"

# Step 3: Generate platform page
echo ""
echo "🔧 Step 3: 生成平台页面..."
timeout 60 python3 generate_platform.py 2>&1 || echo "  ⚠️ 平台生成失败"

# Extract summary
PRODUCTS=$(python3 -c "import json; d=json.load(open('$LATEST')); print(len(d.get('products',[])))")
SCANNED=$(python3 -c "import json; d=json.load(open('$LATEST')); print(d.get('stats',{}).get('total_scanned',0))")
DATE=$(python3 -c "import json; d=json.load(open('$LATEST')); print(d.get('scan_date',''))")
TIME=$(python3 -c "import json; d=json.load(open('$LATEST')); print(d.get('scan_time',''))")

echo ""
echo "📊 扫描结果：${SCANNED}个产品 → ${PRODUCTS}个通过筛选"
echo "📅 扫描时间：${DATE} ${TIME}"

# Top 3 products with BSR
echo ""
echo "🏆 Top 3 推荐："
python3 -c "
import json
d = json.load(open('$LATEST'))
for i, p in enumerate(d.get('products',[])[:3], 1):
    sig = p.get('signal_label', '?')
    sd = p.get('sd_label', '')
    bsr = p.get('bsr_rank', 'N/A')
    sub = p.get('bsr_sub_category', '')
    daily = p.get('estimated_daily_sales', 'N/A')
    print(f'  {i}. {p[\"name\"][:50]}')
    print(f'     £{p[\"price\"]} | 利润{p[\"profit_margin\"]*100:.0f}% | BSR#{bsr} ({sub}) | 日销≈{daily}')
    print(f'     {sig} {sd}')
"

# Step 4: Deploy to GitHub
echo ""
echo "📦 Step 4: 部署到 GitHub Pages..."
timeout 30 python3 github_api_push.py 2>&1 || {
    # Fallback to git push
    timeout 30 git add data/ output/ status.json -f 2>/dev/null
    git diff --cached --quiet && echo "  无变更" && exit 0
    timeout 15 git commit -m "auto-scan $(date -u '+%Y-%m-%d %H:%M')" 2>/dev/null
    timeout 30 git pull --rebase 2>/dev/null || true
    timeout 30 git push origin main 2>&1
}

echo ""
echo "✅ 部署完成：https://liyuhong168.github.io/product-radar/platform.html"

} > "$LOG" 2>&1 || {
    # On failure, output error for cron alert
    echo "❌ 选品雷达扫描失败 | $(date '+%Y-%m-%d %H:%M')"
    tail -5 "$LOG"
    exit 1
}

# On success, one-line summary for cron delivery
PRODUCTS=$(python3 -c "import json; d=json.load(open('$(ls -t data/channels/*.json 2>/dev/null | grep -v rejected | grep -v trends | grep -v bsr_data | head -1)')); print(len(d.get('products',[])))")
echo "✅ 选品雷达扫描完成 | $(date '+%Y-%m-%d %H:%M') | ${PRODUCTS}个产品通过筛选（含BSR数据）→ 已部署GitHub"
