#!/usr/bin/env python3
"""
Product Radar v2 - Channel Aggregation HTML Dashboard
Generates a tabbed, filterable product dashboard with review status tracking.
"""
import json, sys, html as htmlmod, re
from datetime import datetime
from pathlib import Path
from translate import translate_title_to_chinese

BASE = Path(__file__).parent

# Channel config: tab_id -> (emoji, label, color)
CHANNELS = {
    "new_releases":   ("🆕", "Amazon新品榜", "#007AFF"),
    "bsr":            ("📈", "Amazon畅销榜", "#FF9500"),
    "wished":         ("💝", "Amazon心愿榜", "#FF6B9D"),
    "gifts":          ("🎁", "Amazon送礼榜", "#AF52DE"),
    "tiktok_verified":("🎵", "TikTok热品",   "#FF2D55"),
    "hotukdeals":     ("🔥", "HotUKDeals",   "#FF3B30"),
    "temu_trending":  ("🛒", "Temu热销",     "#FF9500"),
    "etsy_trending":  ("🎨", "Etsy趋势",     "#FF6B9D"),
    "youtube_review": ("▶️", "YouTube种草",  "#FF0000"),
    "google_trends":  ("📊", "Google趋势",   "#34C759"),
    "gap_opportunity":("🎯", "缺口机会",     "#5856D6"),
    "multi_source":   ("🔗", "多源验证",     "#5856D6"),
    "all":            ("📋", "全部",         "#8e8e93"),
}

STATUS_CONFIG = {
    "pending":   ("待评估",   "#8e8e93"),
    "supplier":  ("找供应商", "#007AFF"),
    "sample":    ("已采样",   "#FF9500"),
    "listed":    ("已上架",   "#34C759"),
    "rejected":  ("不考虑",   "#FF3B30"),
}


def _render_header(data):
    d = data.get("scan_date", "")
    t = data.get("scan_time", "")
    stats = data.get("stats", {})
    total = stats.get("total_scanned", 0)
    passed = stats.get("passed_filter", 0)
    ch_counts = stats.get("channels", {})
    trend_cats = stats.get("trend_categories", {})

    badges = ""
    for ch_id, (emoji, label, color) in CHANNELS.items():
        if ch_id == "all":
            continue
        cnt = ch_counts.get(ch_id, 0)
        if cnt > 0:
            badges += f'<span class="stat-badge" style="background:{color}15;color:{color}">{emoji} {label}: {cnt}</span>'

    # Trending categories section
    trend_html = ""
    if trend_cats:
        trend_items = "".join(
            f'<span class="trend-chip">{cat} <b>{score}</b></span>'
            for cat, score in sorted(trend_cats.items(), key=lambda x: -x[1])[:6]
        )
        trend_html = f'<div class="trend-section"><span class="trend-label">📊 AnySearch趋势:</span> {trend_items}</div>'

    # Supply-Demand section
    sd_data = stats.get("supply_demand", {})
    sd_html = ""
    if sd_data:
        sd_items = "".join(
            f'<span class="trend-chip">{info["label"]} {cat} <b>{info["ratio"]}</b></span>'
            for cat, info in list(sd_data.items())[:6]
        )
        sd_html = f'<div class="trend-section"><span class="trend-label">🌊 供需比:</span> {sd_items}</div>'

    return f"""
    <header class="header">
        <div class="header-top">
            <h1>🔍 选品雷达 <span class="version">v3</span></h1>
            <div class="scan-info">{d} {t} · 扫描 {total} · 通过 {passed}</div>
            <div class="date-picker" id="datePicker"></div>
        </div>
        <div class="stat-badges">{badges}</div>
        {trend_html}
        {sd_html}
    </header>"""


def _render_tabs(data):
    ch_counts = data.get("stats", {}).get("channels", {})
    tabs = ""
    for ch_id, (emoji, label, color) in CHANNELS.items():
        cnt = ch_counts.get(ch_id, len(data.get("products", [])) if ch_id == "all" else 0)
        active = ' active' if ch_id == "all" else ''
        tabs += f'<button class="tab{active}" data-channel="{ch_id}" style="--ch-color:{color}">{emoji} {label} <span class="tab-count">{cnt}</span></button>'

    # Status filter tabs
    status_tabs = '<div class="status-filter">'
    status_tabs += '<span class="filter-label">状态:</span>'
    for sid, (slabel, scolor) in STATUS_CONFIG.items():
        status_tabs += f'<button class="status-tab" data-status="{sid}" style="--s-color:{scolor}">{slabel}</button>'
    status_tabs += '<button class="status-tab active" data-status="all">全部</button>'
    status_tabs += '</div>'

    return f"""
    <nav class="tab-bar">
        <div class="channel-tabs">{tabs}</div>
        {status_tabs}
    </nav>"""


def _render_filters():
    return """
    <div class="filter-bar">
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="🔍 搜索产品名称..." />
        </div>
        <div class="filter-group">
            <label>价格:</label>
            <select id="filterPrice">
                <option value="all">全部</option>
                <option value="5-7">£5-7</option>
                <option value="7-8.5">£7-8.5</option>
                <option value="8.5-10">£8.5-10</option>
            </select>
        </div>
        <div class="filter-group">
            <label>利润率:</label>
            <select id="filterMargin">
                <option value="all">全部</option>
                <option value="30">≥30%</option>
                <option value="25">≥25%</option>
                <option value="20">≥20%</option>
            </select>
        </div>
        <div class="filter-group">
            <label>品类:</label>
            <select id="filterCategory">
                <option value="all">全部</option>
            </select>
        </div>
        <div class="filter-group">
            <label>排序:</label>
            <select id="sortBy">
                <option value="score">评分↓</option>
                <option value="margin">利润率↓</option>
                <option value="price">价格↑</option>
                <option value="reviews">评论数↑</option>
            </select>
        </div>
        <button class="btn-export" onclick="exportCSV()">📥 导出CSV</button>
        <button class="btn-export" onclick="promptForToken()" style="background:#5856d6;margin-left:4px">🔑 设置Token</button>
        <span id="syncStatus" style="font-size:12px;color:#8e8e93;margin-left:8px"></span>
    </div>"""


def _render_product_grid():
    return '<div class="product-grid" id="productGrid"></div>'


def _render_empty_state():
    return """
    <div class="empty-state" id="emptyState" style="display:none">
        <div class="empty-icon">📦</div>
        <p>没有匹配的产品</p>
        <p class="empty-hint">尝试调整筛选条件</p>
    </div>"""


CSS = """
:root {
    --bg: #f5f5f7;
    --card-bg: #ffffff;
    --text: #1d1d1f;
    --text-secondary: #6e6e73;
    --border: #e5e5ea;
    --radius: 16px;
    --shadow: 0 2px 12px rgba(0,0,0,0.08);
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Noto Sans SC', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
}
.container { max-width: 1440px; margin: 0 auto; padding: 24px; }

/* Header */
.header { margin-bottom: 20px; }
.header-top { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }
.header h1 { font-size: 28px; font-weight: 700; }
.version {
    font-size: 12px; background: #007AFF; color: white;
    padding: 2px 8px; border-radius: 8px; vertical-align: middle;
}
.date-picker {
    display: inline-flex; align-items: center; gap: 6px;
    margin-left: 12px;
}
.date-picker select {
    padding: 4px 10px; border: 2px solid #007AFF; border-radius: 8px;
    font-size: 13px; background: white; color: #007AFF;
    font-weight: 600; cursor: pointer; outline: none;
}
.date-picker label { font-size: 12px; color: var(--text-secondary); }
.scan-info { color: var(--text-secondary); font-size: 14px; }
.stat-badges { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
.stat-badge {
    padding: 6px 14px; border-radius: 20px;
    font-size: 13px; font-weight: 600;
}
.trend-section {
    margin-top: 10px; display: flex; align-items: center;
    gap: 8px; flex-wrap: wrap;
}
.trend-label { font-size: 13px; color: var(--text-secondary); font-weight: 600; }
.trend-chip {
    padding: 4px 12px; border-radius: 14px;
    background: #f0f0f5; font-size: 12px;
    color: var(--text-secondary);
}
.trend-chip b { color: #FF9500; margin-left: 4px; }

/* Tab Bar */
.tab-bar { margin-bottom: 16px; }
.channel-tabs { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; }
.tab {
    padding: 10px 18px; border: none; border-radius: 12px;
    background: var(--card-bg); color: var(--text-secondary);
    font-size: 14px; font-weight: 600; cursor: pointer;
    white-space: nowrap; transition: all 0.2s;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.tab:hover { background: #e8e8ed; }
.tab.active {
    background: var(--ch-color, #007AFF);
    color: white;
}
.tab-count {
    display: inline-block; min-width: 20px;
    background: rgba(255,255,255,0.3); border-radius: 10px;
    padding: 0 6px; font-size: 12px; text-align: center;
}
.tab:not(.active) .tab-count { background: #e5e5ea; }

/* Status Filter */
.status-filter {
    display: flex; align-items: center; gap: 8px;
    margin-top: 10px; flex-wrap: wrap;
}
.filter-label { font-size: 13px; color: var(--text-secondary); font-weight: 600; }
.status-tab {
    padding: 5px 12px; border: 2px solid var(--s-color, #8e8e93);
    border-radius: 16px; background: transparent;
    color: var(--s-color, #8e8e93); font-size: 12px;
    font-weight: 600; cursor: pointer; transition: all 0.2s;
}
.status-tab:hover, .status-tab.active {
    background: var(--s-color, #8e8e93);
    color: white;
}

/* Filter Bar */
.filter-bar {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 20px; flex-wrap: wrap;
    padding: 12px 16px; background: var(--card-bg);
    border-radius: var(--radius); box-shadow: var(--shadow);
}
.search-box { flex: 1; min-width: 200px; }
.search-box input {
    width: 100%; padding: 8px 14px; border: 2px solid var(--border);
    border-radius: 10px; font-size: 14px; outline: none;
    transition: border-color 0.2s;
}
.search-box input:focus { border-color: #007AFF; }
.filter-group { display: flex; align-items: center; gap: 6px; }
.filter-group label { font-size: 13px; color: var(--text-secondary); font-weight: 600; }
.filter-group select {
    padding: 7px 12px; border: 2px solid var(--border);
    border-radius: 10px; font-size: 13px; background: white;
    cursor: pointer; outline: none;
}
.btn-export {
    padding: 8px 16px; border: none; border-radius: 10px;
    background: #007AFF; color: white; font-size: 13px;
    font-weight: 600; cursor: pointer; transition: opacity 0.2s;
}
.btn-export:hover { opacity: 0.85; }

/* Product Grid */
.product-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
}

/* Product Card */
.product-card {
    background: var(--card-bg);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 18px;
    transition: transform 0.2s, box-shadow 0.2s;
    display: flex; flex-direction: column; gap: 10px;
    border-left: 4px solid transparent;
}
.product-card:hover { transform: translateY(-2px); box-shadow: 0 4px 20px rgba(0,0,0,0.12); }
.product-card[data-status="listed"] { border-left-color: #34C759; opacity: 0.7; }
.product-card[data-status="rejected"] { border-left-color: #FF3B30; opacity: 0.5; }

.card-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.channel-badge {
    padding: 3px 10px; border-radius: 8px;
    font-size: 11px; font-weight: 700;
    background: var(--ch-color, #007AFF); color: white;
}
.signal-badges { display: flex; gap: 4px; }
.signal-badge {
    padding: 2px 8px; border-radius: 6px;
    font-size: 10px; font-weight: 600;
    background: #f0f0f5; color: var(--text-secondary);
}
.signal-badge.tiktok { background: #FF2D5515; color: #FF2D55; }
.signal-badge.google { background: #34C75915; color: #34C759; }
.signal-badge.multi { background: #AF52DE15; color: #AF52DE; }
.signal-badge.sd-deep-blue { background: #007AFF15; color: #007AFF; font-weight: 700; }
.signal-badge.sd-balanced { background: #8e8e9315; color: #8e8e93; }
.signal-badge.sd-red-ocean { background: #FF3B3015; color: #FF3B30; }
.signal-badge.div-up { background: #34C75915; color: #34C759; }
.signal-badge.div-down { background: #FF3B3015; color: #FF3B30; }

/* Score Badge */
.score-badge {
    padding: 4px 12px; border-radius: 10px;
    font-size: 14px; font-weight: 700;
    white-space: nowrap; flex-shrink: 0;
}
.score-badge.score-hot { background: #FF2D5515; color: #FF2D55; }
.score-badge.score-high { background: #FF950015; color: #FF9500; }
.score-badge.score-mid { background: #007AFF15; color: #007AFF; }
.score-badge.score-low { background: #f0f0f5; color: #8e8e93; }
.score-label {
    font-size: 12px; font-weight: 600;
    color: var(--text-secondary);
    white-space: nowrap;
}
.score-detail {
    font-size: 11px; color: var(--text-secondary);
    background: #f8f8fa; padding: 6px 10px;
    border-radius: 8px; line-height: 1.8;
    display: -webkit-box; -webkit-line-clamp: 3;
    -webkit-box-orient: vertical; overflow: hidden;
}

.product-image {
    margin: 8px 0;
    text-align: center;
    cursor: pointer;
}
.product-image img {
    max-width: 100%;
    max-height: 180px;
    object-fit: contain;
    border-radius: 8px;
    transition: transform 0.2s;
}
.product-image img:hover {
    transform: scale(1.02);
}
.img-placeholder {
    width: 100%;
    height: 120px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #f5f5f7;
    border-radius: 8px;
    color: #8e8e93;
    font-size: 28px;
}
.img-placeholder small {
    font-size: 11px;
    margin-top: 4px;
    color: #aeaeb2;
}

.product-name {
    font-size: 15px; font-weight: 600; line-height: 1.4;
    display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden;
}
.product-name a { color: var(--text); text-decoration: none; }
.product-name a:hover { color: #007AFF; }

.product-meta {
    display: flex; gap: 16px; font-size: 13px;
    color: var(--text-secondary);
}
.product-meta span { white-space: nowrap; }

/* Profit Bar */
.profit-section { display: flex; align-items: center; gap: 10px; }
.profit-bar-bg {
    flex: 1; height: 8px; background: #e5e5ea;
    border-radius: 4px; overflow: hidden;
}
.profit-bar {
    height: 100%; border-radius: 4px;
    transition: width 0.3s;
}
.profit-text { font-size: 14px; font-weight: 700; white-space: nowrap; }
.profit-text.high { color: #34C759; }
.profit-text.mid { color: #FF9500; }
.profit-text.low { color: #FF3B30; }

/* Cost Breakdown */
.cost-toggle {
    font-size: 12px; color: #007AFF; cursor: pointer;
    border: none; background: #f0f4ff; padding: 4px 10px;
    border-radius: 8px; transition: background 0.2s;
}
.cost-toggle:hover { background: #dce5ff; }
.cost-detail {
    display: none; font-size: 12px; color: var(--text-secondary);
    background: #f5f5f7; padding: 10px 12px; border-radius: 8px;
    line-height: 1.8; margin-top: 4px;
    border-left: 3px solid #007AFF;
}
.cost-detail.show { display: block; }

/* Status Buttons */
.status-btns {
    display: flex; gap: 6px; flex-wrap: wrap;
    margin-top: auto; padding-top: 10px;
    border-top: 1px solid var(--border);
}
.status-btn {
    padding: 5px 10px; border: 2px solid var(--s-color, #8e8e93);
    border-radius: 10px; background: transparent;
    color: var(--s-color, #8e8e93); font-size: 11px;
    font-weight: 600; cursor: pointer; transition: all 0.15s;
}
.status-btn:hover, .status-btn.active {
    background: var(--s-color, #8e8e93);
    color: white;
}

/* Signal Confidence */
.signal-confidence {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 8px;
    font-size: 11px; font-weight: 700;
}
.signal-confidence.strong { background: #FF2D5515; color: #FF2D55; }
.signal-confidence.medium { background: #FF950015; color: #FF9500; }
.signal-confidence.weak { background: #FFCC0015; color: #998500; }
.signal-confidence.none { background: #f0f0f5; color: #8e8e93; }

/* 1688 Button */
.btn-1688 {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 5px 12px; border: 2px solid #FF6A00;
    border-radius: 10px; background: transparent;
    color: #FF6A00; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: all 0.15s; text-decoration: none;
}
.btn-1688:hover { background: #FF6A00; color: white; }

/* Sourcing Tiers */
.sourcing-tiers {
    display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px;
}
.tier-chip {
    padding: 3px 8px; border-radius: 6px;
    font-size: 11px; background: #f5f5f7;
    color: var(--text-secondary);
}
.tier-chip .tier-label { font-weight: 700; }
.tier-chip .tier-margin { color: #34C759; font-weight: 600; }
.tier-chip .tier-margin.mid { color: #FF9500; }
.tier-chip .tier-margin.low { color: #FF3B30; }

/* Empty State */
.empty-state {
    text-align: center; padding: 60px 20px;
    color: var(--text-secondary);
}
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-hint { font-size: 13px; margin-top: 8px; }

/* Gap Opportunity Cards */
.gap-card {
    background: var(--card-bg);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 18px;
    border-left: 4px solid #5856D6;
    display: flex; flex-direction: column; gap: 10px;
}
.gap-card:hover { transform: translateY(-2px); box-shadow: 0 4px 20px rgba(0,0,0,0.12); }
.gap-keyword {
    font-size: 18px; font-weight: 700; color: #5856D6;
}
.gap-meta {
    display: flex; gap: 12px; font-size: 13px; color: var(--text-secondary);
    flex-wrap: wrap;
}
.gap-meta span { white-space: nowrap; }
.gap-platforms {
    display: flex; gap: 6px; flex-wrap: wrap;
}
.gap-platform {
    padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 600;
}
.gap-platform.found { background: #34C75915; color: #34C759; }
.gap-platform.not-found { background: #f0f0f5; color: #8e8e93; }
.gap-amazon-supply {
    padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 600;
}
.gap-amazon-supply.none { background: #34C75915; color: #34C759; }
.gap-amazon-supply.low { background: #FF950015; color: #FF9500; }
.gap-amazon-supply.medium { background: #FF3B3015; color: #FF3B30; }
.gap-amazon-supply.high { background: #FF3B3015; color: #FF3B30; }
.gap-actions {
    display: flex; gap: 8px; flex-wrap: wrap; margin-top: auto;
    padding-top: 10px; border-top: 1px solid var(--border);
}

/* Responsive */
@media (max-width: 768px) {
    .container { padding: 12px; }
    .header h1 { font-size: 22px; }
    .product-grid { grid-template-columns: 1fr; }
    .filter-bar { flex-direction: column; }
    .search-box { min-width: 100%; }
}
"""

JS = """
// Data from Python
let products = DATA.products || [];
const statusKey = 'productRadar_v2_status';
const scans = DATA.available_scans || [];

// Check URL parameter for date
const urlParams = new URLSearchParams(window.location.search);
const requestedDate = urlParams.get('date');

// If date parameter exists, load that date's data from embedded scans
if (requestedDate && scans.length > 0) {
    const targetScan = scans.find(s => s.ts === requestedDate);
    if (targetScan && targetScan.ts !== DATA.scan_ts) {
        const jsonFile = 'data/channels/' + targetScan.file;
        fetch(jsonFile)
            .then(response => {
                if (!response.ok) throw new Error('Failed to load');
                return response.json();
            })
            .then(newData => {
                // Update DATA and products reference
                Object.assign(DATA, newData);
                products = newData.products || [];
                DATA.products = products;
                DATA.stats = newData.stats || {};
                DATA.gaps = newData.gaps || [];
                DATA.trend_summary = newData.trend_summary || {};
                // Update header stats
                updateHeaderStats();
                // Re-render
                renderProducts();
            })
            .catch(err => {
                console.error('Failed to load date data:', err);
            });
    }
}

function updateHeaderStats() {
    const stats = DATA.stats || {};
    const total = stats.total_scanned || 0;
    const passed = products.length;
    const header = document.querySelector('.banner');
    if (header) {
        const subtitle = header.querySelector('.subtitle') || header.querySelectorAll('div')[1];
        if (subtitle) subtitle.textContent = `${DATA.scan_date} ${DATA.scan_time} · 扫描 ${total} · 通过 ${passed}`;
    }
    // Update tab counts
    const gapCount = (DATA.gaps || []).length;
    document.querySelectorAll('.tab').forEach(tab => {
        const ch = tab.dataset.channel;
        let cnt = 0;
        if (ch === 'all') cnt = products.length;
        else if (ch === 'gap_opportunity') cnt = gapCount;
        else products.forEach(p => {
            const tags = p.channel_tags || [p.channel];
            if (tags.includes(ch)) cnt++;
        });
        const badge = tab.querySelector('.tab-count') || tab;
        badge.textContent = badge.textContent.replace(/\d+/, cnt);
    });
}

// Date picker
if (scans.length > 1) {
    const picker = document.getElementById('datePicker');
    const currentTs = requestedDate || DATA.scan_ts || '';
    let html = '<label>📅 扫描日期:</label><select id="dateSelect" onchange="switchDate(this.value)">';
    scans.forEach(s => {
        const sel = s.ts === currentTs ? ' selected' : '';
        html += `<option value="${s.file}"${sel}>${s.date} ${s.time} (${s.count}个)</option>`;
    });
    html += '</select>';
    picker.innerHTML = html;
}
function switchDate(file) {
    // Navigate to v2.html with date parameter
    const base = file.replace('.json', '');
    window.location.href = 'v2.html?date=' + encodeURIComponent(base);
}

// Load status: merge server-side (from status.json) with localStorage (local overrides)
function loadStatus() {
    let server = {};
    try { server = DATA.status || {}; } catch {}
    let local = {};
    try { local = JSON.parse(localStorage.getItem(statusKey) || '{}'); } catch {}
    return {...server, ...local};
}
function saveStatus(status) {
    localStorage.setItem(statusKey, JSON.stringify(status));
    scheduleSyncToGitHub(status);
}

// Auto-sync to GitHub (debounced - waits 3s after last change)
let syncTimer = null;
let syncPending = false;
function scheduleSyncToGitHub(status) {
    if (syncTimer) clearTimeout(syncTimer);
    syncTimer = setTimeout(() => syncToGitHub(status), 3000);
    document.getElementById('syncStatus').textContent = '⏳ 待同步...';
}

// Token management
function getGitHubToken() {
    return localStorage.getItem('github_token') || '';
}
function setGitHubToken(token) {
    localStorage.setItem('github_token', token);
    alert('Token已保存到浏览器');
}
function promptForToken() {
    const token = prompt('请输入GitHub Token (仅需public_repo权限):');
    if (token) {
        setGitHubToken(token);
    }
    return token;
}

async function syncToGitHub(status) {
    let token = getGitHubToken();
    if (!token) {
        token = promptForToken();
        if (!token) {
            document.getElementById('syncStatus').textContent = '⚠️ 未配置token';
            return;
        }
    }
    const el = document.getElementById('syncStatus');
    el.textContent = '☁️ 同步中...';
    el.style.color = '#FF9500';

    try {
        // Trigger GitHub Actions workflow for each status change
        const results = [];
        for (const [asin, newStatus] of Object.entries(status)) {
            const apiUrl = 'https://api.github.com/repos/liyuhong168/product-radar/actions/workflows/update-status.yml/dispatches';
            const res = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Authorization': `token ${token}`,
                    'Accept': 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    ref: 'main',
                    inputs: { asin, status: newStatus }
                }),
            });
            results.push({ asin, ok: res.ok, status: res.status });
        }

        const allOk = results.every(r => r.ok);
        if (allOk) {
            el.textContent = '✅ 已提交同步';
            el.style.color = '#34C759';
            // Update local DATA
            DATA.status = {...DATA.status, ...status};
        } else {
            const failed = results.filter(r => !r.ok);
            el.textContent = `❌ 同步失败 (${failed[0].status})`;
            el.style.color = '#FF3B30';
        }
    } catch(e) {
        el.textContent = `❌ 网络错误`;
        el.style.color = '#FF3B30';
    }
    setTimeout(() => { el.textContent = ''; }, 5000);
}

// Tab switching
let currentChannel = 'all';
let currentStatus = 'all';

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentChannel = tab.dataset.channel;
        renderProducts();
    });
});

document.querySelectorAll('.status-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.status-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentStatus = tab.dataset.status;
        renderProducts();
    });
});

// Filters
document.getElementById('searchInput').addEventListener('input', renderProducts);
document.getElementById('filterPrice').addEventListener('change', renderProducts);
document.getElementById('filterMargin').addEventListener('change', renderProducts);
document.getElementById('filterCategory').addEventListener('change', renderProducts);
document.getElementById('sortBy').addEventListener('change', renderProducts);

// Populate category filter
const categories = [...new Set(products.map(p => p.category).filter(Boolean))].sort();
const catSelect = document.getElementById('filterCategory');
categories.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c; opt.textContent = c;
    catSelect.appendChild(opt);
});

// Mark status
function markStatus(asin, status) {
    const s = loadStatus();
    if (s[asin] === status) { delete s[asin]; } // toggle off
    else { s[asin] = status; }
    saveStatus(s);
    renderProducts();
}

// Toggle cost detail
function toggleCost(asin) {
    const el = document.getElementById('cost-' + asin);
    el.classList.toggle('show');
}

// Get filtered products
function getFiltered() {
    const search = document.getElementById('searchInput').value.toLowerCase();
    const priceRange = document.getElementById('filterPrice').value;
    const minMargin = parseFloat(document.getElementById('filterMargin').value) || 0;
    const category = document.getElementById('filterCategory').value;
    const status = loadStatus();

    return products.filter(p => {
        // Channel filter - use channel_tags array instead of single channel
        if (currentChannel !== 'all') {
            const tags = p.channel_tags || [p.channel];
            if (!tags.includes(currentChannel)) return false;
        }

        // Status filter
        if (currentStatus !== 'all') {
            const ps = status[p.asin] || 'pending';
            if (ps !== currentStatus) return false;
        }

        // Search
        if (search && !p.name.toLowerCase().includes(search)) return false;

        // Price
        if (priceRange !== 'all') {
            const [min, max] = priceRange.split('-').map(Number);
            if (p.price < min || p.price > max) return false;
        }

        // Margin
        if (minMargin && (p.profit_margin * 100) < minMargin) return false;

        // Category
        if (category !== 'all' && p.category !== category) return false;

        return true;
    });

    // Sort
    const sortBy = document.getElementById('sortBy').value;
    filtered.sort((a, b) => {
        switch(sortBy) {
            case 'score': return (b.score || 50) - (a.score || 50);
            case 'margin': return (b.profit_margin || 0) - (a.profit_margin || 0);
            case 'price': return (a.price || 0) - (b.price || 0);
            case 'reviews': return (a.reviews || 0) - (b.reviews || 0);
            default: return (b.score || 50) - (a.score || 50);
        }
    });

    return filtered;
}

// Render products
function renderProducts() {
    const grid = document.getElementById('productGrid');
    const filtered = getFiltered();
    const status = loadStatus();

    // Gap opportunity mode
    if (currentChannel === 'gap_opportunity') {
        renderGaps(grid);
        return;
    }

    const isEmpty = filtered.length === 0;

    document.getElementById('emptyState').style.display = isEmpty ? 'block' : 'none';
    grid.style.display = isEmpty ? 'none' : 'grid';

    // Update tab counts using channel_tags
    const gapCount = (DATA.gaps || []).length;
    document.querySelectorAll('.tab').forEach(tab => {
        const ch = tab.dataset.channel;
        let cnt = 0;
        if (ch === 'all') {
            cnt = products.length;
        } else if (ch === 'gap_opportunity') {
            cnt = gapCount;
        } else {
            products.forEach(p => {
                const tags = p.channel_tags || [p.channel];
                if (tags.includes(ch)) cnt++;
            });
        }
        tab.querySelector('.tab-count').textContent = cnt;
    });

    grid.innerHTML = filtered.map(p => {
        const s = status[p.asin] || 'pending';
        const margin = (p.profit_margin * 100).toFixed(1);
        const marginClass = margin >= 30 ? 'high' : margin >= 20 ? 'mid' : 'low';
        const marginWidth = Math.min(100, Math.max(5, margin * 2));
        const ch = CHANNELS[p.channel] || CHANNELS['all'];
        const bd = p.cost_breakdown || {};

        const signals = [];
        if (p.sources && p.sources.includes('TikTok趋势')) signals.push('<span class="signal-badge tiktok">TikTok</span>');
        if (p.google_trend === 'rising') signals.push('<span class="signal-badge google">Google↑</span>');

        // Signal confidence (replaces old multi-source badge)
        const sigLevel = p.signal_level || 'none';
        const sigLabel = p.signal_label || '⚪ 无信号';
        const extSrcs = (p.external_sources || []).join('+');
        const confidenceHtml = `<span class="signal-confidence ${sigLevel}" title="外部信号: ${extSrcs || '无'}">${sigLabel}</span>`;

        // Supply-Demand badge
        const sdLabel = p.sd_label || '';
        const sdScore = p.sd_score || 0;
        let sdHtml = '';
        if (sdLabel) {
            const sdClass = sdScore >= 10 ? 'deep-blue' : sdScore >= 0 ? 'balanced' : 'red-ocean';
            sdHtml = `<span class="signal-badge sd-${sdClass}">${sdLabel}</span>`;
        }

        // Trend Divergence badge
        const divLabel = p.div_label || '';
        const divScore = p.div_score || 0;
        let divHtml = '';
        if (divLabel) {
            const divClass = divScore > 0 ? 'div-up' : divScore < 0 ? 'div-down' : '';
            divHtml = `<span class="signal-badge ${divClass}">${divLabel}</span>`;
        }

        // 1688 search URL - use Chinese translation if available
        const searchName = encodeURIComponent(p.name_cn || p.name);
        const url1688 = `https://s.1688.com/selloffer/offer_search.htm?keywords=${searchName}`;

        // 3-tier sourcing profit estimates
        const tiers = DATA.tiers || [];
        let tiersHtml = '';
        if (tiers.length > 0 && bd.vat !== undefined) {
            const tierParts = tiers.map(t => {
                const tierCost = bd.vat + bd.commission + bd.fba + bd.ads + bd.returns + t.cost;
                const tierNet = p.price - tierCost;
                const tierMargin = (tierNet / p.price * 100).toFixed(1);
                const mClass = tierMargin >= 25 ? '' : tierMargin >= 20 ? ' mid' : ' low';
                return `<span class="tier-chip"><span class="tier-label">${t.label}</span> £${t.cost} → <span class="tier-margin${mClass}">${tierMargin}%</span></span>`;
            }).join('');
            tiersHtml = `<div class="sourcing-tiers">${tierParts}</div>`;
        }

        // Score display - cap at 99 for visual balance
        const score = p.score || 30;
        const displayScore = score > 99 ? '99+' : score;
        const stars = p.stars || 1;
        const starStr = '⭐'.repeat(stars);
        let scoreClass = 'low';
        let scoreLabel = '💤 优先级低';
        if (score >= 100) { scoreClass = 'hot'; scoreLabel = '🔥 强烈推荐'; }
        else if (score >= 80) { scoreClass = 'high'; scoreLabel = '⭐ 值得关注'; }
        else if (score >= 60) { scoreClass = 'mid'; scoreLabel = '👍 可以考虑'; }
        else if (score >= 40) { scoreClass = 'low'; scoreLabel = '👀 待观察'; }

        const scoreBreakdown = p.score_breakdown ? Object.entries(p.score_breakdown).map(([k,v]) => `+${v} ${k}`).join(' | ') : '';

        const statusBtns = Object.entries(STATUS_CONFIG).map(([sid, [slabel, scolor]]) => {
            const active = s === sid ? ' active' : '';
            return `<button class="status-btn${active}" style="--s-color:${scolor}" onclick="markStatus('${p.asin}','${sid}')">${slabel}</button>`;
        }).join('');

        const costLine = bd.vat !== undefined ?
            `VAT £${bd.vat} + 佣金 £${bd.commission} + FBA £${bd.fba} + 广告 £${bd.ads} + 退货 £${bd.returns} + 采购 £${bd.sourcing}` : '';

        return `
        <div class="product-card" data-status="${s}" data-asin="${p.asin}">
            <div class="card-header">
                <span class="channel-badge" style="background:${ch[2]}">${ch[0]} ${ch[1]}</span>
                <span class="score-badge score-${scoreClass}" title="${scoreBreakdown}">${displayScore}分 ${starStr}</span>
            </div>
            <div class="product-image" onclick="window.open('${p.amazon_url}', '_blank')">
                ${p.image_url ? `<img src="${p.image_url}" alt="${escHtml(p.name)}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'img-placeholder\\'>📷</div>'">` : `<div class="img-placeholder">📷<br><small>下次扫描显示图片</small></div>`}
            </div>
            <div class="product-name">
                <a href="${p.amazon_url}" target="_blank" rel="noopener">${escHtml(p.name)}</a>
            </div>
            <div class="product-meta">
                <span>💷 £${p.price.toFixed(2)}</span>
                <span>⭐ ${p.rating || '-'}★</span>
                <span>💬 ${p.reviews || 0}</span>
                <span>📁 ${p.category || '-'}</span>
            </div>
            <div class="signal-badges">${signals.join('')}</div>
            <div class="profit-section">
                <div class="profit-bar-bg">
                    <div class="profit-bar" style="width:${marginWidth}%;background:${margin >= 30 ? '#34C759' : margin >= 20 ? '#FF9500' : '#FF3B30'}"></div>
                </div>
                <span class="profit-text ${marginClass}">${margin}% (£${p.net_profit.toFixed(2)})</span>
            </div>
            ${costLine ? `<button class="cost-toggle" onclick="toggleCost('${p.asin}')">📋 成本明细 ▾</button>
            <div class="cost-detail" id="cost-${p.asin}">${costLine}<br>总计: £${bd.total_cost} · 净利: £${p.net_profit.toFixed(2)}</div>` : ''}
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <a class="btn-1688" href="${url1688}" target="_blank" rel="noopener">🔍 1688找货源</a>
            </div>
            ${tiersHtml}
            <div class="status-btns">${statusBtns}</div>
        </div>`;
    }).join('');
}

function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// Render gap opportunities
function renderGaps(grid) {
    const gaps = DATA.gaps || [];
    const isEmpty = gaps.length === 0;
    document.getElementById('emptyState').style.display = isEmpty ? 'block' : 'none';
    grid.style.display = isEmpty ? 'none' : 'grid';

    if (isEmpty) { grid.innerHTML = ''; return; }

    const levelLabels = {strong: '🟢 强缺口', moderate: '🟡 中等缺口', weak: '🟠 弱缺口'};
    const levelColors = {strong: '#34C759', moderate: '#FF9500', weak: '#FF9500'};

    grid.innerHTML = gaps.map(g => {
        const level = g.gap_level || 'weak';
        const label = levelLabels[level] || level;
        const color = levelColors[level] || '#8e8e93';
        const cv = g.is_cross_validated ? `<span class="signal-badge multi">🔗 ${g.cross_sources}源验证</span>` : '';
        const sdLabel = g.sd_info ? g.sd_info.label : '';

        const suggestions = (g.suggestions || []).slice(0, 5);
        const suggestHtml = suggestions.map(s => {
            const url = `https://s.1688.com/selloffer/offer_search.htm?keywords=${encodeURIComponent(s)}`;
            return `<a href="${url}" target="_blank" rel="noopener" class="gap-platform found" style="text-decoration:none">${s}</a>`;
        }).join('');

        return `
        <div class="gap-card" style="border-left-color:${color}">
            <div class="gap-keyword">🎯 ${escHtml(g.category)}</div>
            <div class="gap-meta">
                <span style="color:${color};font-weight:700">${label}</span>
                <span>📊 热度: ${g.heat}</span>
                <span>🏆 评分: ${g.score}</span>
                ${cv}
                ${sdLabel ? `<span>${sdLabel}</span>` : ''}
            </div>
            <div style="font-size:13px;color:#6e6e73">
                Amazon: ${g.amazon_count}个产品 / ${g.amazon_reviews}条评论
                ${g.evidence && g.evidence.length > 0 ? `<br>趋势证据: ${g.evidence.slice(0,3).join(', ')}` : ''}
            </div>
            <div style="font-size:12px;font-weight:600;color:#8e8e93;margin-top:4px">📦 建议产品（点击搜1688）:</div>
            <div class="gap-platforms">${suggestHtml}</div>
            <div class="gap-actions">
                <a class="btn-1688" href="${g.url_1688}" target="_blank" rel="noopener">🔍 1688找货源</a>
                <a class="btn-1688" href="${g.url_amazon}" target="_blank" rel="noopener" style="border-color:#007AFF;color:#007AFF">📦 查Amazon</a>
                <a class="btn-1688" href="${g.url_google}" target="_blank" rel="noopener" style="border-color:#34C759;color:#34C759">📈 Google趋势</a>
            </div>
        </div>`;
    }).join('');
}

// Export CSV
function exportCSV() {
    const status = loadStatus();
    const rows = [['ASIN','产品名','价格','利润率','净利','品类','渠道','状态','链接']];
    products.forEach(p => {
        const s = status[p.asin] || 'pending';
        rows.push([
            p.asin, `"${p.name}"`, p.price,
            (p.profit_margin*100).toFixed(1)+'%',
            p.net_profit.toFixed(2), p.category || '',
            p.channel_name || p.channel,
            STATUS_CONFIG[s] ? STATUS_CONFIG[s][0] : s,
            p.amazon_url
        ]);
    });
    const csv = rows.map(r => r.join(',')).join('\\n');
    const blob = new Blob(['\\uFEFF' + csv], {type:'text/csv;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `选品雷达_${DATA.scan_date}.csv`;
    a.click();
}

// Status summary
function updateStatusSummary() {
    const status = loadStatus();
    const counts = {};
    Object.values(status).forEach(s => { counts[s] = (counts[s]||0) + 1; });
    // Could render a summary bar - placeholder for now
}

// Initial render
renderProducts();
"""


def _build_product_list(data):
    """Build the product list for the HTML, adding computed fields."""
    products = data.get("products", [])
    # Tag multi-source products
    for p in products:
        sources = p.get("sources", [])
        if len(sources) >= 2:
            p["is_multi"] = True
        else:
            p["is_multi"] = False
    return products


def generate_html(data_file, output_file=None):
    """Generate the v2 HTML dashboard from a JSON data file.
    Also scans for all available data files to build a date index."""
    config = json.loads((BASE / "config.json").read_text())
    data = json.loads(Path(data_file).read_text())
    products = _build_product_list(data)

    # Add 'all' channel count
    stats = data.get("stats", {})
    stats["channels"]["all"] = len(products)

    # Inject sourcing tiers from config
    data["tiers"] = config.get("sourcing_tiers", [])

    # Inject shared team status from status.json
    status_file = BASE / "status.json"
    if status_file.exists():
        try:
            data["status"] = json.loads(status_file.read_text())
        except Exception:
            data["status"] = {}
    else:
        data["status"] = {}

    # Scan all available data files for date picker
    data_dir = BASE / "data" / "channels"
    available_scans = []
    for f in sorted(data_dir.glob("*.json"), reverse=True):
        if "-rejected" in f.name or "-trends" in f.name:
            continue
        try:
            scan_data = json.loads(f.read_text())
            ts = scan_data.get("scan_ts", f.stem)  # Fallback to filename stem for old files
            date = scan_data.get("scan_date", f.stem[:10])
            time_str = scan_data.get("scan_time", "")
            count = len(scan_data.get("products", []))
            available_scans.append({"ts": ts, "date": date, "time": time_str, "count": count, "file": f.name})
        except Exception:
            continue
    data["available_scans"] = available_scans

    if not output_file:
        output_file = str(BASE / "output" / "v2.html")

    js_data = json.dumps(data, ensure_ascii=False)

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>选品雷达 v3 | {data.get('scan_date', '')}</title>
    <style>{CSS}</style>
</head>
<body>
    <div class="container">
        {_render_header(data)}
        {_render_tabs(data)}
        {_render_filters()}
        {_render_product_grid()}
        {_render_empty_state()}
    </div>
    <script>const DATA = {js_data};
const CHANNELS = {json.dumps({k: list(v) for k, v in CHANNELS.items()})};
const STATUS_CONFIG = {json.dumps({k: list(v) for k, v in STATUS_CONFIG.items()})};
    </script>
    <script>{JS}</script>
</body>
</html>"""

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text(page, encoding="utf-8")
    print(f"  HTML saved: {output_file}", file=sys.stderr)

    # Also save per-scan HTML (for date picker navigation)
    # Also save per-scan HTML (for date picker navigation)
    scan_ts = data.get("scan_ts", "")
    if not scan_ts:
        scan_ts = Path(data_file).stem
    per_scan_file = str(BASE / "output" / f"{scan_ts}.html")
    Path(per_scan_file).write_text(page, encoding="utf-8")
    print(f"  Per-scan HTML: {per_scan_file}", file=sys.stderr)

    # Generate missing per-scan HTML files for other dates (date picker support)
    for scan_info in available_scans:
        other_ts = scan_info["ts"]
        other_html = BASE / "output" / f"{other_ts}.html"
        if not other_html.exists():
            other_data_file = data_dir / scan_info["file"]
            if other_data_file.exists():
                try:
                    _generate_single(other_data_file, str(other_html), config)
                    print(f"  Backfill HTML: {other_html.name}", file=sys.stderr)
                except Exception:
                    pass

    return output_file


def _generate_single(data_file, output_file, config):
    """Generate a single per-scan HTML file (for date picker backfill)."""
    data = json.loads(Path(data_file).read_text())
    products = _build_product_list(data)
    stats = data.get("stats", {})
    stats["channels"]["all"] = len(products)
    data["tiers"] = config.get("sourcing_tiers", [])
    data["available_scans"] = []  # Not needed for per-scan pages
    # Inject shared team status
    status_file = BASE / "status.json"
    if status_file.exists():
        try:
            data["status"] = json.loads(status_file.read_text())
        except Exception:
            data["status"] = {}
    else:
        data["status"] = {}
    js_data = json.dumps(data, ensure_ascii=False)
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>选品雷达 v3 | {data.get('scan_date', '')}</title>
    <style>{CSS}</style>
</head>
<body>
    <div class="container">
        {_render_header(data)}
        {_render_tabs(data)}
        {_render_filters()}
        {_render_product_grid()}
        {_render_empty_state()}
    </div>
    <p style="text-align:center;padding:20px"><a href="v2.html">← 返回最新扫描</a></p>
    <script>const DATA = {js_data};
const CHANNELS = {json.dumps({k: list(v) for k, v in CHANNELS.items()})};
const STATUS_CONFIG = {json.dumps({k: list(v) for k, v in STATUS_CONFIG.items()})};
    </script>
    <script>{JS}</script>
</body>
</html>"""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text(page, encoding="utf-8")


def generate_from_products(products, stats=None, output_file=None):
    """Generate HTML directly from a product list (used by run_scan_v2)."""
    now = datetime.now()
    data = {
        "scan_date": now.strftime("%Y-%m-%d"),
        "scan_time": now.strftime("%H:%M"),
        "scan_ts": now.strftime("%Y-%m-%d_%H%M"),
        "stats": stats or {},
        "products": products,
    }

    # Save data JSON alongside HTML
    data_dir = BASE / "data" / "channels"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_file = data_dir / f"{now.strftime('%Y-%m-%d')}.json"
    data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return generate_html(str(data_file), output_file)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_html_v2.py <data.json> [output.html]")
        sys.exit(1)
    data_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    generate_html(data_file, output_file)
