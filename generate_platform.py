#!/usr/bin/env python3
"""
Product Selection Platform — Unified HTML Generator V5
Discovery = keyword/demand-centric with Amazon/1688 search links
Radar = product-centric with simple cards
Kanban = pipeline board with metrics + search
Both sections support date filtering.
"""

import json
import urllib.parse, sys, html as htmlmod, glob
from datetime import datetime
from pathlib import Path

from season_engine import get_upcoming_events
from success_tracker import calculate_metrics
from platform_search import build_search_index
from festival_engine import load_festivals, generate_festival_html

BASE = Path(__file__).parent

STATUS_CONFIG = {
    "pending":   ("待评估",   "#8e8e93"),
    "supplier":  ("找供应商", "#007AFF"),
    "sample":    ("已采样",   "#FF9500"),
    "listed":    ("已上架",   "#34C759"),
    "rejected":  ("不考虑",   "#FF3B30"),
}

KANBAN_COLUMNS = [
    ("inbox",     "📥 收件箱",   "#007AFF"),
    ("starred",   "⭐ 值得做",   "#FF9500"),
    ("verified",  "✅ 已验证",   "#34C759"),
]


def _consolidate_past_months(data_dict):
    """Merge dates from past months (e.g. 2026-06-*) into monthly keys (e.g. 2026-06)."""
    current_month = datetime.now().strftime('%Y-%m')
    monthly = {}  # month_key -> merged data
    to_remove = []

    for date_key in list(data_dict.keys()):
        # Only process full date keys (YYYY-MM-DD)
        if not (len(date_key) == 10 and date_key[4] == '-' and date_key[7] == '-'):
            continue
        month_key = date_key[:7]
        if month_key >= current_month:
            continue  # current/future month, keep daily
        if month_key not in monthly:
            monthly[month_key] = {
                'products': [],
                'scan_date': month_key,
                'scan_time': '',
            }

        src = data_dict[date_key]
        # Merge products (dedup by ASIN)
        existing_asins = {p.get('asin') for p in monthly[month_key].get('products', []) if p.get('asin')}
        for p in src.get('products', []):
            if p.get('asin') and p['asin'] not in existing_asins:
                monthly[month_key].setdefault('products', []).append(p)
                existing_asins.add(p['asin'])
        # Merge insights (dedup by keyword)
        existing_kws = {i.get('keyword') for i in monthly[month_key].get('insights', []) if i.get('keyword')}
        for i in src.get('insights', []):
            if i.get('keyword') and i['keyword'] not in existing_kws:
                monthly[month_key].setdefault('insights', []).append(i)
                existing_kws.add(i['keyword'])
        # Carry over trend_forecast if any
        if src.get('trend_forecast') and not monthly[month_key].get('trend_forecast'):
            monthly[month_key]['trend_forecast'] = src['trend_forecast']

        to_remove.append(date_key)

    for d in to_remove:
        del data_dict[d]
    data_dict.update(monthly)
    return data_dict


def load_all_radar():
    """Load all radar scans, return dict keyed by date. Only include dates with new products. Merge same-day scans."""
    data_dir = BASE / 'data' / 'channels'
    result = {}
    for f in sorted(data_dir.glob('*.json')):
        if '-rejected' in f.name or '-trends' in f.name or '-raw' in f.name:
            continue
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if 'products' in data and data.get('scan_date'):
                date = data['scan_date']
                if date in result:
                    # 同一天的多个文件，合并产品（去重）
                    existing_asins = {p.get('asin') for p in result[date]['products'] if p.get('asin')}
                    for p in data['products']:
                        if p.get('asin') and p['asin'] not in existing_asins:
                            result[date]['products'].append(p)
                            existing_asins.add(p['asin'])
                else:
                    result[date] = data
        except (json.JSONDecodeError, KeyError):
            continue

    # 合并过去月份（如6月）到月度 key
    result = _consolidate_past_months(result)

    # 过滤：只保留有新品的日期/月份
    filtered = {}
    for date, data in result.items():
        products = data.get('products', [])
        new_products = [p for p in products if p.get('is_new') == True]
        if new_products:
            filtered[date] = data

    return filtered


def load_all_discovery():
    """Load all discovery data, return dict keyed by date."""
    disc_dir = BASE / 'data' / 'discovery'
    if not disc_dir.exists():
        return {}
    result = {}
    for f in sorted(disc_dir.glob('*.json')):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get('scan_date'):
                result[data['scan_date']] = data
        except (json.JSONDecodeError, KeyError):
            continue
    # 合并过去月份到月度 key
    result = _consolidate_past_months(result)
    return result


def generate_platform_html(radar_all=None, discovery_all=None, output_path=None):
    now = datetime.now()
    scan_date = now.strftime('%Y-%m-%d')
    scan_time = now.strftime('%H:%M')

    radar_all = radar_all or {}
    discovery_all = discovery_all or {}

    # Separate dates for radar and discovery
    radar_dates = sorted(radar_all.keys(), reverse=True)
    discovery_dates = sorted(discovery_all.keys(), reverse=True)
    # Keep all_dates for backward compatibility
    all_dates = sorted(set(radar_dates + discovery_dates), reverse=True)

    # Build radar JS data (minimal subset for client)
    radar_js = {}
    for date, data in radar_all.items():
        radar_js[date] = {
            'products': data.get('products', []),
            'stats': data.get('stats', {}),
            'scan_time': data.get('scan_time', ''),
        }

    # Build discovery JS data, converting products to insights format if needed
    discovery_js = {}
    for date, data in discovery_all.items():
        insights = data.get('insights', [])

        # If discovery file has products but no insights, convert them
        if not insights and 'products' in data:
            for p in data['products']:
                insights.append({
                    'keyword': p.get('name', '')[:40],
                    'keyword_cn': '',
                    'demand_signals': p.get('sources', []),
                    'trend_score': p.get('score', 0),
                    'trend_direction': 'stable',
                    'reason': p.get('reason', ''),
                    'action': '',
                    'amazon_keyword': p.get('name', '').split(',')[0].strip(),
                    'amazon_search_url': p.get('amazon_url', ''),
                    'search_1688': '',
                    'competition': '',
                })

        # Pre-encode 1688 search URLs in GBK
        for ins in insights:
            kw = ins.get('search_1688') or ins.get('keyword_cn') or ins.get('keyword') or ''
            if kw:
                gbk_kw = urllib.parse.quote(kw, encoding='gbk', safe='')
                ins['search_1688_url'] = f'https://s.1688.com/selloffer/offer_search.htm?keywords={gbk_kw}'
            else:
                ins['search_1688_url'] = ''

        discovery_js[date] = {
            'insights': insights,
            'trend_forecast': data.get('trend_forecast', ''),
            'scan_time': data.get('scan_time', ''),
        }

    # Serialize to JSON for embedding
    radar_json = json.dumps(radar_js, ensure_ascii=False)
    discovery_json = json.dumps(discovery_js, ensure_ascii=False)
    dates_json = json.dumps(all_dates, ensure_ascii=False)
    radar_dates_json = json.dumps(radar_dates, ensure_ascii=False)
    discovery_dates_json = json.dumps(discovery_dates, ensure_ascii=False)
    status_json = json.dumps(STATUS_CONFIG)

    # Load product status from status.json (GitHub-synced)
    prod_status = {}
    status_path = BASE / 'status.json'
    if status_path.exists():
        try:
            prod_status = json.loads(status_path.read_text())
        except Exception as e:
            print(f"⚠️ status.json load failed: {e}", file=sys.stderr)
    prod_status_json = json.dumps(prod_status, ensure_ascii=False)

    # Phase 2.3: 错误可观测化 — 收集加载失败信息供 debug 区展示
    _load_errors = []
    try:
        season_events = get_upcoming_events(90)
    except Exception as e:
        season_events = []
        _load_errors.append(f"season_events: {e}")
        print(f"⚠️ season_events load failed: {e}", file=sys.stderr)
    try:
        metrics = calculate_metrics()
    except Exception as e:
        metrics = {}
        _load_errors.append(f"metrics: {e}")
        print(f"⚠️ metrics load failed: {e}", file=sys.stderr)
    try:
        search_index = build_search_index()
    except Exception as e:
        search_index = {"generated": "", "total": 0, "entries": []}
        _load_errors.append(f"search_index: {e}")
        print(f"⚠️ search_index load failed: {e}", file=sys.stderr)

    season_json = json.dumps(season_events, ensure_ascii=False)
    metrics_json = json.dumps(metrics, ensure_ascii=False)
    search_json = json.dumps(search_index.get('entries', []), ensure_ascii=False)
    kanban_json = json.dumps(KANBAN_COLUMNS, ensure_ascii=False)
    
    # Load Festival Planner data
    try:
        festivals = load_festivals()
        festival_html = generate_festival_html(festivals)
        festival_count = len(festivals)
        # Serialize festivals for frontend kanban (minimal fields only)
        # Pre-encode 1688 URLs in GBK to avoid garbled text
        festivals_json = json.dumps([
            {"id": f.get("id",""), "name": f.get("name",""), "icon": f.get("icon",""),
             "date": f.get("date",""), "importance": f.get("importance",""),
             "products": [{"sku": p.get("sku",""), "keywords": p.get("keywords",[]),
                           "category": p.get("category",""), "margin": p.get("margin",""),
                           "sourcing": p.get("sourcing",""), "matchScore": p.get("matchScore",0),
                           "aliUrl": "https://s.1688.com/selloffer/offer_search.htm?keywords=" + urllib.parse.quote(
                               (p.get("sourcing","").split("1688:")[1].strip() if "1688:" in p.get("sourcing","") else p.get("sku","")),
                               encoding='gbk', safe='')}
                          for p in f.get("products",[])]}
            for f in festivals
        ], ensure_ascii=False)
    except Exception as e:
        festivals = []
        festivals_json = '[]'
        festival_html = '<div class="empty">节日数据加载失败</div>'
        festival_count = 0
        _load_errors.append(f"festivals: {e}")
        print(f"⚠️ festivals load failed: {e}", file=sys.stderr)

    _load_errors_json = json.dumps(_load_errors, ensure_ascii=False)

    # Phase 2.4: 读取看板注入配置（从 config.json）
    _default_inject = {"enabled": True, "festival": {"max_per_event": 3, "days_ahead": 30, "sea_deadline_days": 77}, "discovery": {"max_keywords": 5}, "radar": {"max_products": 10, "new_only": True}}
    kanban_inject = _default_inject
    _cfg_path = BASE / 'config.json'
    if _cfg_path.exists():
        try:
            _cfg = json.loads(_cfg_path.read_text())
            kanban_inject = _cfg.get('kanban_injection', _default_inject)
        except Exception as e:
            print(f"⚠️ kanban_injection config load failed: {e}", file=sys.stderr)
    inject_json = json.dumps(kanban_inject, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>选品平台 | {scan_date}</title>
<link rel='icon' type='image/svg+xml' href='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"%3E%3Ccircle cx="24" cy="24" r="22" fill="none" stroke="%235856D6" stroke-width="2"/%3E%3Ccircle cx="24" cy="24" r="3" fill="%235856D6"/%3E%3C/svg%3E'>
<link rel='stylesheet' href='shared/oa-theme.css'>

</head>
<body>
<main class="shell">

  <header class="hero" id="sectionTop">
    <div class="hero-main">
      <div class="hero-headline">
        <div class="hero-logo">🎯</div>
        <div>
          <p class="hero-tag">SELECTION PLATFORM</p>
          <h1>选品平台</h1>
        </div>
      </div>
      <p class="hero-sub">每天上下午定时运行、实时多源搜索、提供趋势选品方向</p>
    </div>
  </header>

<div class="date-bar">
  <label>📅 日期：</label>
  <select id="datePicker"></select>
  <div class="stats" id="dateStats"></div>
</div>

<div class="main-tabs">
  <button class="main-tab active" data-tab="discovery" style="--tc:var(--purple)">🔍 趋势发现 <span class="cnt" id="discCnt">0</span></button>
  <button class="main-tab" data-tab="radar" style="--tc:var(--blue)">📡 雷达扫描 <span class="cnt" id="radarCnt">0</span></button>
  <button class="main-tab" data-tab="festival" style="--tc:var(--orange)">📅 节日选品 <span class="cnt">{festival_count}</span></button>
  <button class="main-tab" data-tab="kanban" style="--tc:var(--green)">📋 选品看板</button>
  </div>

<!-- DISCOVERY -->
<div class="section active" id="sec-discovery">
  <div id="forecastArea"></div>
  <div id="seasonBar" class="season-bar"></div>
  <div class="insight-list" id="insightList"></div>
  <div class="empty" id="emptyDisc" style="display:none">
    <div style="font-size:48px;margin-bottom:12px">🔍</div>
    <p>该日期无趋势发现数据</p>
  </div>
</div>

<!-- RADAR -->
<div class="section" id="sec-radar">
  <div class="st-filter">
    <span class="lbl">状态:</span>
    <button class="st-tab" data-status="pending" style="--s-c:#8e8e93">待评估</button>
    <button class="st-tab" data-status="supplier" style="--s-c:#007AFF">找供应商</button>
    <button class="st-tab" data-status="sample" style="--s-c:#FF9500">已采样</button>
    <button class="st-tab" data-status="listed" style="--s-c:#34C759">已上架</button>
    <button class="st-tab" data-status="rejected" style="--s-c:#FF3B30">不考虑</button>
    <button class="st-tab active" data-status="all">全部</button>
  </div>
  <div class="filter-bar">
    <div class="search-box"><input type="text" id="radarSearch" placeholder="🔍 搜索产品名称..."/></div>
    <div class="fg"><label>利润率:</label><select id="fMargin"><option value="all">全部</option><option value="30">≥30%</option><option value="25">≥25%</option><option value="20">≥20%</option></select></div>
    <div class="fg"><label>排序:</label><select id="fSort"><option value="score">评分↓</option><option value="margin">利润率↓</option><option value="new">新发现优先</option></select></div>
    <button class="btn-export" onclick="exportCSV()">📥 导出CSV</button>
  </div>
  <div class="product-grid" id="radarGrid"></div>
  <div class="empty" id="emptyRadar" style="display:none">
    <div style="font-size:48px;margin-bottom:12px">📡</div>
    <p>该日期无雷达数据</p>
  </div>
</div>

<!-- FESTIVAL -->
<div class="section" id="sec-festival">
  {festival_html}
</div>

<!-- KANBAN -->
<div class="section" id="sec-kanban">
  <div class="metrics-row" id="metricsRow"></div>
  <div class="filter-bar">
    <div class="search-box"><input type="text" id="kanbanSearch" placeholder="🔍 搜索关键词..."/></div>
    <button class="btn-export" onclick="exportKanbanCSV()">📥 导出看板</button>
    <button class="btn-export" id="pauseInjectBtn" onclick="toggleInject()">⏸️ 暂停注入</button>
    <span id="syncStatus" style="font-size:11px;color:var(--muted);cursor:pointer;margin-left:8px" onclick="setSyncToken()" title="点击设置 GitHub Token 同步看板">⚪ 未同步</span>
  </div>
  <div class="kanban-board" id="kanbanBoard"></div>
</div>

</main>
<div class="search-overlay" id="searchOverlay">
  <div class="search-modal">
    <div class="search-modal-hd">
      <span style="font-size:18px">🔍</span>
      <input type="text" id="globalSearchInput" placeholder="搜索关键词、产品名称..." autocomplete="off"/>
      <button class="close-btn" onclick="toggleSearch()">ESC</button>
    </div>
    <div class="search-results" id="searchResults"></div>
  </div>
</div>

<script>
const RADAR_ALL = {radar_json};
const DISC_ALL = {discovery_json};
const DATES = {dates_json};
const RADAR_DATES = {radar_dates_json};
const DISC_DATES = {discovery_dates_json};
const STATUS = {status_json};
const PROD_STATUS = {prod_status_json};
const SEASON_EVENTS = {season_json};
const METRICS = {metrics_json};
const SEARCH_INDEX = {search_json};
const KANBAN_COLS = {kanban_json};
const FESTIVALS = {festivals_json};
const INJECT_CFG = {inject_json};
const SK = 'pp_v3_status';
const OLD_SK = 'productRadar_v2_status';
const SYNC_TOKEN_KEY='***';
const REPO = 'liyuhong168/product-radar';
const STATUS_FILE = 'data/kanban_status.json';
let SERVER_STATUS = {{}};  // From GitHub Pages
let syncing = false;

// Migrate old key
(function(){{try{{const o=JSON.parse(localStorage.getItem(OLD_SK)||'{{}}');const c=JSON.parse(localStorage.getItem(SK)||'{{}}');if(Object.keys(o).length>0&&Object.keys(c).length===0)localStorage.setItem(SK,JSON.stringify(o))}}catch(e){{}}}})();

// Fetch server status on load
async function fetchServerStatus() {{
  try {{
    const r = await fetch('https://liyuhong168.github.io/product-radar/' + STATUS_FILE + '?t=' + Date.now());
    if (r.ok) {{
      const data = await r.json();
      if (data && typeof data === 'object') {{
        SERVER_STATUS = data;
        const local = JSON.parse(localStorage.getItem(SK) || '{{}}');
        // Phase 2.2: 冲突检测 — 比较 _meta.ts，服务端更新时才覆盖本地
        var localTs = (local._meta && local._meta.ts) || 0;
        var serverTs = (data._meta && data._meta.ts) || 0;
        if (serverTs > localTs) {{
          var merged = Object.assign({{}}, PROD_STATUS, local, data);
          localStorage.setItem(SK, JSON.stringify(merged));
        }}
        const el = document.getElementById('syncStatus');
        if (el) {{ el.textContent = '✅ 已同步 ' + new Date().toLocaleTimeString('zh-CN',{{hour:'2-digit',minute:'2-digit'}}); el.style.color='#34C759'; }}
      }}
    }}
  }} catch(e) {{ console.warn('Sync fetch failed:', e); }}
}}
fetchServerStatus();

function getSt(){{try{{const local=JSON.parse(localStorage.getItem(SK)||'{{}}');return Object.assign({{}},PROD_STATUS,SERVER_STATUS,local)}}catch(e){{return Object.assign({{}},PROD_STATUS,SERVER_STATUS)}}}}
function saveSt(a,s,all){{
  var t = all || getSt();
  if(!all){{if(s==='pending')delete t[a];else t[a]=s;}}
  // Phase 2.2: 附加元数据（timestamp + source），用于冲突检测
  t._meta = {{ts: Date.now(), src: 'web'}};
  localStorage.setItem(SK, JSON.stringify(t));
  // Auto-sync to server
  syncToServer();
}}

async function syncToServer() {{
  const token = localStorage.getItem(SYNC_TOKEN_KEY);
  if (!token || syncing) return;
  syncing = true;
  const el = document.getElementById('syncStatus');
  if (el) {{ el.textContent = '⏳ 同步中...'; el.style.color='#FF9500'; }}
  try {{
    const status = JSON.parse(localStorage.getItem(SK) || '{{}}');
    // Phase 1 安全改造：改用 repository_dispatch 触发 Actions 写入
    // Token 仅需 Actions:write 权限，不再需要 contents:write
    // 实际文件写入由 Actions 内置 GITHUB_TOKEN 完成，带格式校验
    const res = await fetch('https://api.github.com/repos/' + REPO + '/dispatches', {{
      method: 'POST',
      headers: {{
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
      }},
      body: JSON.stringify({{
        event_type: 'status-sync',
        client_payload: {{ status: status }}
      }})
    }});
    if (res.ok || res.status === 204) {{
      if (el) {{ el.textContent = '✅ 已同步 ' + new Date().toLocaleTimeString('zh-CN',{{hour:'2-digit',minute:'2-digit'}}); el.style.color='#34C759'; }}
    }} else {{
      const err = await res.json().catch(() => ({{}}));
      if (el) {{ el.textContent = '❌ 同步失败'; el.style.color='#FF3B30'; }}
      console.error('Sync error:', err);
    }}
  }} catch(e) {{
    if (el) {{ el.textContent = '❌ 网络错误'; el.style.color='#FF3B30'; }}
  }}
  syncing = false;
}}

function setSyncToken() {{
  const current = localStorage.getItem(SYNC_TOKEN_KEY) || '';
  const token = prompt('输入 GitHub Token（仅需 Actions:write 权限，用于触发状态同步 workflow）：', current);
  if (token !== null) {{
    if (token === '') {{ localStorage.removeItem(SYNC_TOKEN_KEY); }}
    else {{ localStorage.setItem(SYNC_TOKEN_KEY, token); }}
    syncToServer();
  }}
}}
function esc(s){{const d=document.createElement('div');d.textContent=s||'';return d.innerHTML}}

let curDate = DATES[0] || '';
let curTab = 'discovery';

// ===== Date Picker (unified) =====
const picker = document.getElementById('datePicker');
const ALL_DATES = [...new Set([...DISC_DATES, ...RADAR_DATES])].sort().reverse();

function initDatePicker(dates, selectElem) {{
  selectElem.innerHTML = '';
  dates.forEach(d => {{
    const opt = document.createElement('option');
    opt.value = d; opt.textContent = d;
    selectElem.appendChild(opt);
  }});
}}

initDatePicker(ALL_DATES, picker);
picker.addEventListener('change', () => {{ curDate = picker.value; renderAll(); }});

// ===== Main Tabs =====
document.querySelector('.main-tabs').addEventListener('click', e => {{
  const t = e.target.closest('.main-tab'); if (!t) return;
  document.querySelectorAll('.main-tab').forEach(b => {{ b.classList.remove('active'); b.style.background='var(--card)'; b.style.color='var(--muted)' }});
  t.classList.add('active'); t.style.background='var(--tc)'; t.style.color='#fff';
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById('sec-'+t.dataset.tab).classList.add('active');
  
  // 切换Tab
  curTab = t.dataset.tab;
  
  if (t.dataset.tab === 'kanban') renderKanban();
  renderAll();
}});
document.querySelector('.main-tab.active').style.background='var(--tc)';
document.querySelector('.main-tab.active').style.color='#fff';

// ===== Season Events =====
function renderSeasonEvents() {{
  const bar = document.getElementById('seasonBar');
  if (!SEASON_EVENTS || !SEASON_EVENTS.length) {{ bar.innerHTML = ''; return; }}
  bar.innerHTML = SEASON_EVENTS.map(ev => {{
    const urgent = ev.days_until <= 30;
    const cats = (ev.recommended_categories || []).slice(0, 3).join(', ');
    return `<div class="event-chip ${{urgent ? 'urgent' : ''}}">
      <span class="ev-name">${{esc(ev.event_name)}}</span>
      <span class="ev-days">${{ev.days_until}}天</span>
      ${{cats ? `<span class="ev-cats">${{esc(cats)}}</span>` : ''}}
    </div>`;
  }}).join('');
}}

// ===== Render Discovery =====
function renderDiscovery() {{
  const list = document.getElementById('insightList');
  const empty = document.getElementById('emptyDisc');
  const forecastArea = document.getElementById('forecastArea');
  const discData = DISC_ALL[curDate];
  const insights = discData ? discData.insights || [] : [];
  const forecast = discData ? discData.trend_forecast || '' : '';

  document.getElementById('discCnt').textContent = insights.length;

  renderSeasonEvents();

  if (!insights.length) {{ list.innerHTML=''; empty.style.display='block'; forecastArea.innerHTML=''; return; }}
  empty.style.display='none';

  // Forecast
  forecastArea.innerHTML = forecast ? `<div class="forecast-card"><div class="forecast-title">🔮 未来趋势预测</div><div class="forecast-text">${{esc(forecast)}}</div></div>` : '';

  list.innerHTML = insights.map((ins, idx) => {{
    const score = ins.trend_score || 0;
    const scoreCls = score >= 80 ? 'hot' : score >= 50 ? 'warm' : 'cool';
    const dir = ins.trend_direction === 'rising' ? '📈' : ins.trend_direction === 'falling' ? '📉' : '➡️';
    const signals = (ins.demand_signals || []).map(s => `<span class="signal-chip">${{esc(s)}}</span>`).join('');

    // Signal bars (trend/gap/profit)
    let signalBarsHtml = '';
    if (ins.signal_scores) {{
      const ss = ins.signal_scores;
      const trendVal = ss.trend || ss.trend_score || 0;
      const gapVal = ss.gap || ss.gap_score || 0;
      const profitVal = ss.profit || ss.profit_score || 0;
      signalBarsHtml = `<div class="signal-bars">
        <div class="signal-bar-row"><span class="signal-bar-label">趋势</span><div class="signal-bar-track"><div class="signal-bar-fill trend" style="width:${{Math.min(trendVal, 100)}}%"></div></div><span class="signal-bar-val" style="color:#AF52DE">${{trendVal}}</span></div>
        <div class="signal-bar-row"><span class="signal-bar-label">缺口</span><div class="signal-bar-track"><div class="signal-bar-fill gap" style="width:${{Math.min(gapVal, 100)}}%"></div></div><span class="signal-bar-val" style="color:var(--blue)">${{gapVal}}</span></div>
        <div class="signal-bar-row"><span class="signal-bar-label">利润</span><div class="signal-bar-track"><div class="signal-bar-fill profit" style="width:${{Math.min(profitVal, 100)}}%"></div></div><span class="signal-bar-val" style="color:var(--green)">${{profitVal}}</span></div>
      </div>`;
    }}

    // Amazon search URL
    const amzKw = ins.amazon_keyword || ins.keyword || '';
    const amzUrl = ins.amazon_search_url || `https://www.amazon.co.uk/s?k=${{encodeURIComponent(amzKw)}}&i=kitchen`;
    // 1688 search
    const aliKw = ins.search_1688 || ins.keyword_cn || ins.keyword || '';
    const aliUrl = ins.search_1688_url || `https://s.1688.com/selloffer/offer_search.htm?keywords=${{encodeURIComponent(aliKw)}}`;
    // Google Trends
    const gtUrl = `https://trends.google.com/trends/explore?geo=GB&q=${{encodeURIComponent(amzKw)}}`;

    // Competition summary
    const compHtml = ins.competition ? `<div class="comp-box"><div class="label">📊 竞争格局</div><div class="text">${{esc(ins.competition)}}</div></div>` : '';

    // Radar cross-validation: find matching radar products
    let radarHtml = '';
    const kwLower = (ins.keyword || '').toLowerCase();
    const kwParts = kwLower.split(/\\s+/).filter(w => w.length >= 4);
    if (typeof RADAR_ALL !== 'undefined' && curDate) {{
      const radarData = RADAR_ALL[curDate];
      if (radarData && radarData.products) {{
        const matched = radarData.products.filter(p => {{
          const name = (p.name || '').toLowerCase();
          return kwParts.some(part => name.includes(part));
        }});
        if (matched.length > 0) {{
          radarHtml = `<div class="radar-match"><div class="label">📡 雷达验证（已找到${{matched.length}}个产品）</div>` +
            matched.map(p => {{
              const reviews = p.reviews || 0;
              const ocean = reviews < 20 ? '🌊蓝海' : reviews <= 50 ? '🟢低竞争' : '🟡中等';
              return `<div class="radar-product">✅ ${{esc((p.name||'').substring(0,45))}} — £${{(p.price||0).toFixed(2)}} | ${{reviews}}评论 ${{ocean}} | 利润率${{((p.profit_margin||0)*100).toFixed(0)}}%</div>`;
            }}).join('') + `</div>`;
        }}
      }}
    }}

    return `<div class="insight-card" data-idx="${{idx}}">
      <div class="insight-hd" onclick="this.parentElement.classList.toggle('open')">
        <div class="insight-score ${{scoreCls}}">${{score}}</div>
        <div class="insight-main">
          <div class="insight-kw">${{dir}} ${{esc(ins.keyword)}}</div>
          ${{ins.keyword_cn ? `<div class="insight-kw-cn">${{esc(ins.keyword_cn)}}</div>` : ''}}
          <div class="insight-signals">${{signals}}</div>
          ${{signalBarsHtml}}
        </div>
        <div class="insight-arrow">›</div>
      </div>
      <div class="insight-detail">
        <div class="detail-sec">
          <div class="detail-title">💡 选品理由</div>
          <div class="detail-text">${{esc(ins.reason)}}</div>
        </div>
        ${{ins.action ? `<div class="action-box"><div class="label">📋 行动建议</div><div class="text">${{esc(ins.action)}}</div></div>` : ''}}
        ${{compHtml}}
        ${{radarHtml}}
        <div class="search-btns">
          <a class="btn-search amazon" href="${{amzUrl}}" target="_blank">🛒 Amazon UK 搜索「${{esc(amzKw)}}」</a>
          <a class="btn-search alibaba" href="${{aliUrl}}" target="_blank">🏭 1688 搜索「${{esc(aliKw)}}」</a>
          <a class="btn-search google" href="${{gtUrl}}" target="_blank">📊 Google Trends</a>
        </div>
      </div>
    </div>`;
  }}).join('');
}}

// ===== Render Radar =====
let radarStatus = 'all';
function renderRadar() {{
  const grid = document.getElementById('radarGrid');
  const empty = document.getElementById('emptyRadar');
  const radarData = RADAR_ALL[curDate];
  const products = radarData ? radarData.products || [] : [];

  if (!products.length) {{ grid.innerHTML=''; empty.style.display='block'; return; }}
  empty.style.display='none';

  const search = document.getElementById('radarSearch').value.toLowerCase();
  const mf = document.getElementById('fMargin').value;
  const sf = document.getElementById('fSort').value;
  const sts = getSt();

  let filtered = products.filter(p => {{
    const st = sts[p.asin]||'pending';
    if (radarStatus==='all' && st==='rejected') return false;
    if (radarStatus==='all' && p.is_new===false) return false;
    if (radarStatus!=='all' && st!==radarStatus) return false;
    if (search && !p.name.toLowerCase().includes(search)) return false;
    if (mf!=='all') {{if((p.profit_margin||0)<Number(mf)/100)return false}}
    return true;
  }});
  document.getElementById('radarCnt').textContent = filtered.length;

  filtered.sort((a,b)=>{{
    if(sf==='score')return(b.score||0)-(a.score||0);
    if(sf==='margin')return(b.profit_margin||0)-(a.profit_margin||0);
    if(sf==='new'){{const an=a.is_new?1:0,bn=b.is_new?1:0;if(an!==bn)return bn-an;return(b.score||0)-(a.score||0)}}
    return 0;
  }});

  grid.innerHTML = filtered.map(p => {{
    const st=sts[p.asin]||'pending';
    const margin=((p.profit_margin||0)*100).toFixed(1);
    const mCls=margin>=30?'high':margin>=20?'mid':'low';
    const barC=margin>=30?'var(--green)':margin>=20?'var(--orange)':'var(--red)';
    const sc=p.score||0;
    const scCls=sc>=120?'hot':sc>=80?'high':sc>=40?'mid':'low';
    const badge=p.is_new?'<span class="badge-new">NEW</span>':(p.is_new===false?'<span class="badge-repeat">重复</span>':'');
    const img=p.image_url?`<div class="pc-img"><img src="${{p.image_url}}" alt="${{esc(p.name)}}" loading="lazy"/></div>`:'<div class="pc-img"><div class="ph">📦</div></div>';
    const url=p.amazon_url||(p.asin?`https://www.amazon.co.uk/dp/${{p.asin}}`:'#');
    const cb=p.cost_breakdown||{{}};
    const costH=cb.vat?`<button class="cost-tog" onclick="this.nextElementSibling.classList.toggle('show')">💰 成本明细</button><div class="cost-det">VAT: £${{cb.vat?.toFixed(2)||'-'}} · 佣金: £${{cb.commission?.toFixed(2)||'-'}} · FBA: £${{cb.fba?.toFixed(2)||'-'}}<br>广告: £${{cb.ads?.toFixed(2)||'-'}} · 退货: £${{cb.returns?.toFixed(2)||'-'}} · 采购: £${{cb.sourcing?.toFixed(2)||'-'}}<br><b>总成本: £${{cb.total_cost?.toFixed(2)||'-'}} · 净利润: £${{(p.net_profit||0).toFixed(2)}}</b></div>`:'';
    const sigs=(p.sources||[]).map(s=>{{let c='';if(s.includes('TikTok'))c='tiktok';if(s.includes('多源'))c='multi';return`<span class="sig ${{c}}">${{s}}</span>`}}).join('');
    const sd=p.sd_label?`<span class="sig sd">${{p.sd_label}}</span>`:'';
    return `<div class="pc" data-status="${{st}}" data-asin="${{p.asin||''}}">
      ${{badge}}
      <div class="card-hd"><span class="src-badge">📡 雷达</span><div class="sig-badges">${{sigs}}${{sd}}</div><span class="score-badge ${{scCls}}">${{sc}}分</span></div>
      ${{img}}
      <div class="pc-name"><a href="${{url}}" target="_blank">${{esc(p.name)}}</a></div>
      <div class="pc-meta"><span>💷 £${{(p.price||0).toFixed(2)}}</span><span>⭐ ${{p.rating||'-'}} (${{p.reviews||0}})</span>${{p.first_seen?`<span>发现: ${{p.first_seen}}</span>`:''}}</div>
      <div class="profit-bar-wrap"><div class="profit-bar-bg"><div class="profit-bar" style="width:${{Math.min(margin,50)*2}}%;background:${{barC}}"></div></div><span class="profit-txt ${{mCls}}">${{margin}}%</span></div>
      ${{costH}}
      <div class="status-btns">
        ${{Object.entries(STATUS).map(([k,[l,c]])=>`<button class="st-btn ${{st===k?'active':''}}" style="--s-c:${{c}}" onclick="setSt('${{p.asin}}','${{k}}',this)">${{l}}</button>`).join('')}}
        <a class="btn-amz" href="${{url}}" target="_blank">🛒 Amazon</a>
      </div>
    </div>`;
  }}).join('');
}}

function setSt(asin,s,btn){{saveSt(asin,s);const c=btn.closest('.pc');c.dataset.status=s;c.querySelectorAll('.st-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active')}}

document.querySelector('.st-filter').addEventListener('click',e=>{{const t=e.target.closest('.st-tab');if(!t)return;document.querySelectorAll('.st-tab').forEach(b=>b.classList.remove('active'));t.classList.add('active');radarStatus=t.dataset.status;renderRadar()}});
['radarSearch','fMargin','fSort'].forEach(id=>{{document.getElementById(id).addEventListener(id==='radarSearch'?'input':'change',renderRadar)}});

function exportCSV(){{
  const radarData=RADAR_ALL[curDate];if(!radarData)return;
  const sts=getSt();const rows=[['来源','ASIN','名称','价格','利润率','评分','状态','链接']];
  (radarData.products||[]).forEach(p=>{{const s=sts[p.asin]||'pending';rows.push(['雷达',p.asin||'',p.name||'',(p.price||0).toFixed(2),((p.profit_margin||0)*100).toFixed(1)+'%',p.score||0,STATUS[s]?.[0]||s,p.amazon_url||''])}});
  const csv=rows.map(r=>r.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(',')).join('\\n');
  const b=new Blob(['\\ufeff'+csv],{{type:'text/csv;charset=utf-8;'}});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='选品平台_'+curDate+'.csv';a.click();
}}

// ===== Kanban Board (V5.3 — Decision Inbox) =====
function renderKanban() {{
  const metricsRow = document.getElementById('metricsRow');
  const board = document.getElementById('kanbanBoard');
  const sts = getSt();

  // --- Collect items from 3 sources ---
  const inbox = [];
  const now = new Date();
  const today = now.toISOString().slice(0,10);
  // Phase 2.4: 注入开关（前端可暂停）
  const _doInject = INJECT_CFG.enabled !== false && localStorage.getItem('kanban_pause_inject') !== '1';

  // Source 1: Festival Planner (highest priority — has deadlines)
  if (_doInject && typeof FESTIVALS !== 'undefined') {{
    const eventCounts = {{}}; // limit per event
    FESTIVALS.forEach(f => {{
      const fDate = new Date(f.date);
      if (fDate < now) return;
      const seaDeadline = new Date(fDate);
      seaDeadline.setDate(seaDeadline.getDate() - INJECT_CFG.festival.sea_deadline_days);
      const daysLeft = Math.ceil((seaDeadline - now) / 86400000);
      if (daysLeft > INJECT_CFG.festival.days_ahead || daysLeft < -10) return;
      eventCounts[f.id] = 0;

      (f.products || []).forEach(p => {{
        if (eventCounts[f.id] >= INJECT_CFG.festival.max_per_event) return;
        const kw = (p.keywords || [])[0] || p.sku || '';
        if (!kw) return;
        const kbKey = 'kb_fest_' + f.id + '_' + kw.replace(/\\s+/g,'_').slice(0,20);
        if (sts[kbKey] === 'starred' || sts[kbKey] === 'verified' || sts[kbKey] === 'dismissed') return;

        eventCounts[f.id]++;
        inbox.push({{
          id: kbKey,
          name: kw,
          nameCn: p.sku || '',
          source: 'festival',
          score: p.matchScore ? p.matchScore * 20 : 50,
          profit: p.margin || '',
          deadline: f.date,
          deadlineLabel: f.icon + ' ' + f.name,
          daysLeft: daysLeft,
          eventName: f.name,
          eventIcon: f.icon || '📅',
          amazonKw: kw,
          aliUrl: p.aliUrl || '',
          sortWeight: daysLeft <= 7 ? 1000 : daysLeft <= 14 ? 500 : 100,
        }});
      }});
    }});
  }}

  // Source 2: Discovery keywords
  let discCount = 0;
  if (_doInject) Object.entries(DISC_ALL || {{}}).forEach(([date, dd]) => {{
    (dd.insights || []).forEach(ins => {{
      if (discCount >= INJECT_CFG.discovery.max_keywords) return;
      const kw = ins.keyword || '';
      if (!kw) return;
      const kbKey = 'kb_disc_' + kw.replace(/\\s+/g,'_').slice(0,30) + '_' + date;
      if (sts[kbKey] === 'starred' || sts[kbKey] === 'verified' || sts[kbKey] === 'dismissed') return;

      discCount++;
      const ss = ins.signal_scores || {{}};
      const aliKw = ins.search_1688 || '';
      inbox.push({{
        id: kbKey,
        name: ins.amazon_keyword || kw,
        nameCn: ins.keyword_cn || '',
        source: 'discovery',
        score: ss.final || ins.trend_score || 0,
        profit: ss.profit_window || '',
        gapLevel: ss.gap_level || '',
        amazonKw: ins.amazon_keyword || kw,
        aliKw: aliKw,
        aliUrl: ins.search_1688_url || '',
        date: date,
        sortWeight: (ss.final || 0) + 50,
      }});
    }});
  }});

  // Source 3: Radar products (only new)
  let radarCount = 0;
  if (_doInject) Object.entries(RADAR_ALL || {{}}).forEach(([date, rd]) => {{
    (rd.products || []).forEach(p => {{
      if (radarCount >= INJECT_CFG.radar.max_products) return;
      if (!p.asin || (INJECT_CFG.radar.new_only && p.is_new === false)) return;
      const kbKey = 'kb_radar_' + p.asin;
      if (sts[kbKey] === 'starred' || sts[kbKey] === 'verified' || sts[kbKey] === 'dismissed') return;

      radarCount++;
      inbox.push({{
        id: kbKey,
        name: p.name || '',
        nameCn: '',
        source: 'radar',
        asin: p.asin,
        score: p.score || 0,
        profit: p.profit_margin ? (p.profit_margin * 100).toFixed(0) + '%' : '',
        amazonKw: '',
        amazonUrl: p.amazon_url || 'https://www.amazon.co.uk/dp/' + p.asin,
        aliKw: '',
        aliUrl: '',
        date: date,
        sortWeight: p.score || 0,
      }});
    }});
  }});

  // --- Build starred and verified lists ---
  const starred = [];
  const verified = [];
  Object.entries(sts).forEach(([key, status]) => {{
    if (!key.startsWith('kb_')) return;
    const item = inbox.find(i => i.id === key);
    if (status === 'starred') {{
      if (item) starred.push(item);
      else starred.push({{id: key, name: key.replace(/kb_[^_]+_/,'').replace(/_/g,' '), source: 'unknown', score: 0, sortWeight: 0, amazonKw:'', aliUrl:''}});
    }}
    if (status === 'verified') {{
      if (item) verified.push(item);
      else verified.push({{id: key, name: key.replace(/kb_[^_]+_/,'').replace(/_/g,' '), source: 'unknown', score: 0, sortWeight: 0, amazonKw:'', aliUrl:''}});
    }}
  }});

  inbox.sort((a, b) => b.sortWeight - a.sortWeight);

  // --- Metrics ---
  const urgentCount = inbox.filter(i => i.source === 'festival' && i.daysLeft <= 7).length;
  const nearestDeadline = inbox.filter(i => i.deadline).sort((a,b) => a.daysLeft - b.daysLeft)[0];
  metricsRow.innerHTML = [
    {{n: inbox.length, l: '📥 收件箱'}},
    {{n: starred.length, l: '⭐ 值得做'}},
    {{n: verified.length, l: '✅ 已验证'}},
    {{n: urgentCount, l: '🔴 紧急(≤7天)', cls: urgentCount > 0 ? 'urgent' : ''}},
    {{n: nearestDeadline ? nearestDeadline.eventIcon + ' ' + nearestDeadline.eventName + ' ' + nearestDeadline.daysLeft + '天' : '—', l: '📅 最近截止'}},
  ].map(item => `<div class="metric-card ${{item.cls||''}}"><div class="big">${{item.n}}</div><div class="label">${{item.l}}</div></div>`).join('');

  // --- Unified card renderer ---
  function renderCard(item, colKey) {{
    const srcCls = item.source || 'radar';
    const srcLabel = {{festival:'📅 节日', discovery:'🔍 发现', radar:'📡 雷达'}}[srcCls] || '📡 其他';

    let deadlineHtml = '';
    if (item.daysLeft !== undefined) {{
      const dlCls = item.daysLeft <= 7 ? '' : 'ok';
      deadlineHtml = `<span class="kc-deadline ${{dlCls}}">${{item.eventIcon||'📅'}} ${{item.daysLeft}}天</span>`;
    }}

    let metricsHtml = '';
    if (item.score) metricsHtml += `<span class="kc-tag score">${{item.score}}分</span>`;
    if (item.profit) metricsHtml += `<span class="kc-tag profit">${{item.profit}}</span>`;
    if (item.gapLevel) metricsHtml += `<span class="kc-tag gap">${{item.gapLevel}}</span>`;

    // URLs
    const amazonUrl = item.amazonUrl || (item.amazonKw ? 'https://www.amazon.co.uk/s?k=' + encodeURIComponent(item.amazonKw) : '');
    const aliUrl = item.aliUrl || '';

    // Action buttons (different per column)
    let actionsHtml = '';
    if (amazonUrl) actionsHtml += `<a class="kc-btn" href="${{amazonUrl}}" target="_blank">🛒 Amazon</a>`;
    if (aliUrl) actionsHtml += `<a class="kc-btn" href="${{aliUrl}}" target="_blank">🏭 1688</a>`;

    if (colKey === 'inbox') {{
      actionsHtml += `<button class="kc-btn primary" onclick="event.stopPropagation();moveKanban('${{item.id}}','starred')">⭐ 值得做</button>`;
      actionsHtml += `<button class="kc-btn danger" onclick="event.stopPropagation();moveKanban('${{item.id}}','dismiss')">✕</button>`;
    }} else if (colKey === 'starred') {{
      actionsHtml += `<button class="kc-btn primary" onclick="event.stopPropagation();moveKanban('${{item.id}}','verified')">✅ 待验证</button>`;
      actionsHtml += `<button class="kc-btn danger" onclick="event.stopPropagation();moveKanban('${{item.id}}','dismiss')">✕</button>`;
    }} else {{ // verified
      actionsHtml += `<button class="kc-btn danger" onclick="event.stopPropagation();moveKanban('${{item.id}}','dismiss')">✕</button>`;
    }}

    return `<div class="kanban-card src-${{srcCls}}" data-id="${{item.id}}">
      <div class="kc-top">
        <span class="kc-src ${{srcCls}}">${{srcLabel}}</span>
        ${{deadlineHtml}}
      </div>
      <div class="kc-name" title="${{esc(item.name)}}">${{esc(item.name)}}</div>
      ${{item.nameCn ? `<div class="kc-cn">${{esc(item.nameCn)}}</div>` : ''}}
      ${{metricsHtml ? `<div class="kc-metrics">${{metricsHtml}}</div>` : ''}}
      <div class="kc-actions">${{actionsHtml}}</div>
    </div>`;
  }}

  // --- Build board ---
  const columns = [
    {{key:'inbox', label:'📥 收件箱', color:'#007AFF', items:inbox, empty:'三源自动注入，每天更新'}},
    {{key:'starred', label:'⭐ 值得做', color:'#FF9500', items:starred, empty:'点击卡片的"⭐ 值得做"按钮'}},
    {{key:'verified', label:'✅ 已验证', color:'#34C759', items:verified, empty:'团队确认可做后标记'}},
  ];

  board.innerHTML = columns.map(col => {{
    const cardsHtml = col.items.length > 0
      ? col.items.map(item => renderCard(item, col.key)).join('')
      : `<div class="kanban-empty">${{col.empty}}</div>`;
    return `<div class="kanban-col" data-status="${{col.key}}">
      <div class="kanban-col-hd"><span class="dot" style="background:${{col.color}}"></span>${{col.label}}<span class="cnt">${{col.items.length}}</span></div>
      <div class="kanban-cards">${{cardsHtml}}</div>
    </div>`;
  }}).join('');
}}

function moveKanban(id, target) {{
  const sts = getSt();
  if (target === 'dismiss') {{
    sts[id] = 'dismissed';
  }} else {{
    sts[id] = target;
  }}
  saveSt(null, null, sts);
  renderKanban();
}}

document.getElementById('kanbanSearch')?.addEventListener('input', renderKanban);

// Phase 2.4: 暂停/恢复看板注入
function toggleInject() {{
  var paused = localStorage.getItem('kanban_pause_inject') === '1';
  if (paused) {{ localStorage.removeItem('kanban_pause_inject'); }}
  else {{ localStorage.setItem('kanban_pause_inject', '1'); }}
  var btn = document.getElementById('pauseInjectBtn');
  if (btn) btn.textContent = paused ? '⏸️ 暂停注入' : '▶️ 恢复注入';
  renderKanban();
}}
// 初始化按钮状态
(function(){{var p=localStorage.getItem('kanban_pause_inject')==='1';var b=document.getElementById('pauseInjectBtn');if(b)b.textContent=p?'▶️ 恢复注入':'⏸️ 暂停注入';}})();

function exportKanbanCSV(){{
  const sts = getSt();
  const rows = [['状态','关键词','来源','评分','日期']];
  // Export inbox items
  Object.entries(DISC_ALL).forEach(([date, dd]) => {{
    (dd.insights || []).forEach(ins => {{
      const kbKey = 'kb_disc_' + (ins.keyword||'').replace(/\\s+/g,'_').slice(0,30) + '_' + date;
      rows.push([sts[kbKey]||'inbox', ins.keyword||'', 'discovery', ins.trend_score||0, date]);
    }});
  }});
  Object.entries(RADAR_ALL).forEach(([date, rd]) => {{
    (rd.products || []).forEach(p => {{
      const kbKey = 'kb_radar_' + (p.asin||'');
      rows.push([sts[kbKey]||'inbox', p.name||'', 'radar', p.score||0, date]);
    }});
  }});
  const csv = rows.map(r => r.map(c => '"'+String(c).replace(/"/g,'""')+'"').join(',')).join('\\n');
  const blob = new Blob(['\\uFEFF'+csv], {{type:'text/csv;charset=utf-8'}});
  const a = document.createElement('a');a.href=URL.createObjectURL(blob);a.download='kanban_'+new Date().toISOString().slice(0,10)+'.csv';a.click();
}}

// ===== Global Search =====
function toggleSearch() {{
  const overlay = document.getElementById('searchOverlay');
  const input = document.getElementById('globalSearchInput');
  if (overlay.classList.contains('open')) {{
    overlay.classList.remove('open');
  }} else {{
    overlay.classList.add('open');
    setTimeout(() => input.focus(), 100);
    globalSearch('');
  }}
}}

document.getElementById('searchOverlay').addEventListener('click', e => {{
  if (e.target === e.currentTarget) toggleSearch();
}});

document.getElementById('globalSearchInput').addEventListener('input', e => {{
  globalSearch(e.target.value);
}});

function globalSearch(query) {{
  const resultsEl = document.getElementById('searchResults');
  const q = (query || '').toLowerCase().trim();
  if (!q) {{
    resultsEl.innerHTML = `<div class="search-empty">输入关键词开始搜索（共 ${{SEARCH_INDEX.length}} 条记录）</div>`;
    return;
  }}
  const matches = SEARCH_INDEX.filter(e =>
    (e.keyword || '').toLowerCase().includes(q) ||
    (e.keyword_cn || '').toLowerCase().includes(q) ||
    (e.category || '').toLowerCase().includes(q) ||
    (e.reason || '').toLowerCase().includes(q)
  ).slice(0, 50);

  if (!matches.length) {{
    resultsEl.innerHTML = `<div class="search-empty">没有找到匹配「${{esc(query)}}」的结果</div>`;
    return;
  }}
  resultsEl.innerHTML = matches.map(e => {{
    const typeLabel = e.type === 'discovery' ? '趋势' : '雷达';
    const typeCls = e.type === 'discovery' ? 'discovery' : 'radar';
    return `<div class="search-result" onclick="searchNavigate('${{esc(e.type)}}','${{esc(e.date)}}')">
      <span class="sr-type ${{typeCls}}">${{typeLabel}}</span>
      <span class="sr-kw">${{esc(e.keyword)}}</span>
      <span class="sr-score">${{e.score || 0}}分</span>
      <span class="sr-date">${{e.date}}</span>
    </div>`;
  }}).join('');
}}

function searchNavigate(type, date) {{
  toggleSearch();
  // Switch to the right tab
  const tabBtn = document.querySelector(`.main-tab[data-tab="${{type === 'discovery' ? 'discovery' : 'radar'}}"]`);
  if (tabBtn) {{
    document.querySelectorAll('.main-tab').forEach(b => {{ b.classList.remove('active'); b.style.background='var(--card)'; b.style.color='var(--muted)' }});
    tabBtn.classList.add('active'); tabBtn.style.background='var(--tc)'; tabBtn.style.color='#fff';
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.getElementById('sec-'+tabBtn.dataset.tab).classList.add('active');
  }}
  // Switch date
  if (date && DATES.includes(date)) {{
    curDate = date;
    picker.value = date;
    renderAll();
  }}
}}

// Keyboard shortcut: Ctrl+K / Cmd+K
document.addEventListener('keydown', e => {{
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {{
    e.preventDefault();
    toggleSearch();
  }}
  if (e.key === 'Escape') {{
    const overlay = document.getElementById('searchOverlay');
    if (overlay.classList.contains('open')) toggleSearch();
  }}
}});

function renderAll() {{
  // Update stats
  const r = RADAR_ALL[curDate];
  const d = DISC_ALL[curDate];
  const rCnt = r ? (r.products||[]).length : 0;
  const dCnt = d ? (d.insights||[]).length : 0;
  const rTime = r ? r.scan_time : '';
  const dTime = d ? d.scan_time : '';
  let stats = [];
  if (dCnt) stats.push(`趋势发现 ${{dCnt}}个关键词 ${{dTime}}`);
  if (rCnt) stats.push(`雷达扫描 ${{rCnt}}个产品 ${{rTime}}`);
  document.getElementById('dateStats').textContent = stats.join(' · ') || '无数据';

  renderDiscovery();
  renderRadar();
}}

renderAll();

// Phase 3 Step 4: postMessage 高度自适应 — 响应父窗口请求 + 主动发送
function oaSendHeight() {{
    var h = Math.max(document.body.scrollHeight, document.body.offsetHeight, document.documentElement.scrollHeight);
    if (window.parent && window.parent !== window) {{
        window.parent.postMessage({{type: 'oa-set-height', height: h}}, '*');
    }}
}}
window.addEventListener('message', function(e) {{
    if (e.data && e.data.type === 'oa-get-height') oaSendHeight();
}});
oaSendHeight();
setTimeout(oaSendHeight, 500);
setTimeout(oaSendHeight, 2000);
</script>

<!-- Phase 2.3: Debug panel (?debug=1 to show) -->
<div id="debugPanel" style="display:none;position:fixed;bottom:0;left:0;right:0;background:#1d1d1f;color:#f5f5f7;padding:12px 20px;font-size:12px;font-family:monospace;z-index:9999;max-height:240px;overflow-y:auto;border-top:2px solid #FF9500">
  <div style="font-weight:bold;margin-bottom:8px;color:#FF9500">Data Load Status</div>
  <div id="debugContent"></div>
</div>
<script>
(function(){{
  var errs = { _load_errors_json };
  var el = document.getElementById('debugPanel');
  var dc = document.getElementById('debugContent');
  if (errs.length === 0) {{
    dc.innerHTML = '<span style="color:#34C759">All modules loaded OK</span>';
  }} else {{
    dc.innerHTML = errs.map(function(e) {{
      return '<div style="color:#FF3B30;padding:2px 0">FAIL: ' + e + '</div>';
    }}).join('');
  }}
  if (new URLSearchParams(location.search).get('debug') === '1') {{
    el.style.display = 'block';
  }}
}})();
</script>
</body>
</html>'''

    if not output_path:
        output_path = str(BASE / 'output' / 'platform.html')
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path


if __name__ == '__main__':
    radar_all = load_all_radar()
    discovery_all = load_all_discovery()
    out = generate_platform_html(radar_all, discovery_all)
    r_dates = len(radar_all)
    d_dates = len(discovery_all)
    print(f'✅ {out}', file=sys.stderr)
    print(f'   Radar: {r_dates} dates | Discovery: {d_dates} dates', file=sys.stderr)
    print(json.dumps({'output': out, 'radar_dates': r_dates, 'discovery_dates': d_dates}))
