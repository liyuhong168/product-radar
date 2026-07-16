#!/usr/bin/env python3
"""
Amazon项目运营OA — 门户页生成器 v3.0
生成 output/index.html (左侧导航 + 右侧iframe内容区)
模块配置可扩展，新增板块只需加一项
UI: Apple-inspired design system, refined spacing & typography
"""
import os, json, html as htmlmod
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
OUTPUT_DIR = BASE / 'output'

# ── 模块配置 ── 新增板块只需在这里加一项 ──
MODULES = [
    {
        "group": "核心业务",
        "items": [
            {"key": "radar",    "label": "跨境雷达", "icon": "📡", "url": "radar/",       "desc": "24h跨境电商情报聚合"},
            {"key": "platform", "label": "选品平台", "icon": "🎯", "url": "platform.html", "desc": "产品发现、扫描、看板管理"},
            {"key": "analysis", "label": "补货跟进", "icon": "📦", "url": "analysis/",    "desc": "运营数据与补货分析"},
        ]
    },
    {
        "group": "扩展板块（待添加）",
        "items": []
    }
]

SYSTEM_NAME = "Amazon项目运营OA"
SYSTEM_SUB  = ""
THEME_COLOR = "#1a1a2e"

def build_html():
    now = datetime.now()
    nav_items = []
    for group in MODULES:
        if group["items"]:
            nav_items.append(f'<div class="oa-nav-group-label">{htmlmod.escape(group["group"])}</div>')
            for m in group["items"]:
                nav_items.append(
                    f'<a class="oa-nav-item" data-key="{m["key"]}" href="#" '
                    f'onclick="return switchModule(\'{m["key"]}\',\'{htmlmod.escape(m["url"])}\')">'
                    f'<span class="oa-nav-icon">{m["icon"]}</span>'
                    f'<span class="oa-nav-label">{htmlmod.escape(m["label"])}</span>'
                    f'</a>'
                )
        else:
            nav_items.append(f'<div class="nav-group-label dim">{htmlmod.escape(group["group"])}</div>')
            nav_items.append(f'<div class="oa-nav-empty">暂无板块</div>')

    first = MODULES[0]["items"][0]

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{SYSTEM_NAME}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📋</text></svg>">
<link rel="stylesheet" href="shared/oa-theme.css?v=12">

</head>
<body class="oa-portal-page">

<!-- Sidebar -->
<div id="sidebar-overlay" class="oa-sidebar-overlay" onclick="toggleSidebar()"></div>
<aside id="sidebar" class="oa-sidebar">
    <div class="oa-sidebar-header">
        <div class="logo">
            <span class="logo-icon">📋</span>
            <div class="logo-text">
                <span class="logo-title">{htmlmod.escape(SYSTEM_NAME)}</span>
                <span class="logo-sub">{htmlmod.escape(SYSTEM_SUB)}</span>
            </div>
        </div>
    </div>
    <nav id="nav" class="oa-nav">
        {''.join(nav_items)}
    </nav>
    <div class="oa-sidebar-footer">
        Amazon项目运营OA v3.0 · {now.strftime('%Y-%m-%d')}
    </div>
</aside>

<!-- Main -->
<div id="main" class="oa-main">
    <div id="topbar" class="oa-topbar">
        <div class="oa-topbar-left">
            <button id="menuBtn" class="oa-menu-btn" onclick="toggleSidebar()" aria-label="菜单">☰</button>
            <div class="module-title">
                <span class="dot"></span>
                <span id="current-module">{htmlmod.escape(first["label"])}</span>
            </div>
        </div>
        <div class="topbar-right">
            <span class="last-update" id="last-update"></span>
            <span id="clock" class="oa-clock">--:--:--</span>
        </div>
    </div>
    <div id="content-wrap" class="oa-content-wrap">
        <div id="loading" class="oa-loading">
            <div class="spinner"></div>
            <span class="load-text">加载中…</span>
        </div>
        <iframe id="content-frame" class="oa-content-frame" src="{htmlmod.escape(first["url"])}" loading="eager"></iframe>
    </div>
</div>

<script>
// ── Navigation ──
const MODULES = {json.dumps([m for g in MODULES for m in g["items"]], ensure_ascii=False)};
const LABEL_MAP = {{}};
MODULES.forEach(m => {{ LABEL_MAP[m.key] = m.label; }});

const frame = document.getElementById('content-frame');
const loading = document.getElementById('loading');
const titleEl = document.getElementById('current-module');
const updateEl = document.getElementById('last-update');
let currentKey = localStorage.getItem('oa_module') || '{first["key"]}';
let loadTimer = null;

function toggleSidebar() {{
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebar-overlay').classList.toggle('show');
}}

function switchModule(key, url) {{
    // Close sidebar on mobile
    if (window.innerWidth <= 768) {{
        document.getElementById('sidebar').classList.remove('open');
        document.getElementById('sidebar-overlay').classList.remove('show');
    }}
    // Update nav active state
    document.querySelectorAll('.oa-nav-item').forEach(el => {{
        el.classList.toggle('active', el.dataset.key === key);
    }});
    // Update title
    titleEl.textContent = LABEL_MAP[key] || key;
    // Show loading with brief delay to avoid flash on fast loads
    clearTimeout(loadTimer);
    loadTimer = setTimeout(() => loading.classList.add('show'), 150);
    // Set iframe src
    frame.src = url;
    // Save preference
    localStorage.setItem('oa_module', key);
    currentKey = key;
    return false;
}}

// Iframe load complete → hide loading
frame.addEventListener('load', function() {{
    clearTimeout(loadTimer);
    loading.classList.remove('show');
    updateEl.textContent = '已加载 ' + new Date().toLocaleTimeString('zh-CN', {{hour:'2-digit',minute:'2-digit'}});
    // Phase 3 Step 4: 请求子页面高度（postMessage）
    try {{ frame.contentWindow.postMessage({{type: 'oa-get-height'}}, '*'); }} catch(e) {{}}
}});

// Phase 3 Step 4: 接收子页面高度，动态调整 iframe
window.addEventListener('message', function(e) {{
    if (e.data && e.data.type === 'oa-set-height' && e.data.height > 100) {{
        frame.style.height = e.data.height + 'px';
    }}
}});

// Handle iframe load error
frame.addEventListener('error', function() {{
    clearTimeout(loadTimer);
    loading.classList.remove('show');
    updateEl.textContent = '加载失败';
}});

// Restore last module on page load
window.addEventListener('DOMContentLoaded', function() {{
    const saved = localStorage.getItem('oa_module');
    if (saved) {{
        const item = MODULES.find(m => m.key === saved);
        if (item) {{
            switchModule(item.key, item.url);
        }}
    }}
    // Set active for current
    document.querySelectorAll('.oa-nav-item').forEach(el => {{
        el.classList.toggle('active', el.dataset.key === currentKey);
    }});
}});

// ── Live Clock ──
function updateClock() {{
    const now = new Date();
    document.getElementById('clock').textContent =
        now.getFullYear() + '-' +
        String(now.getMonth()+1).padStart(2,'0') + '-' +
        String(now.getDate()).padStart(2,'0') + ' ' +
        String(now.getHours()).padStart(2,'0') + ':' +
        String(now.getMinutes()).padStart(2,'0') + ':' +
        String(now.getSeconds()).padStart(2,'0');
}}
updateClock();
setInterval(updateClock, 1000);

// ── Keyboard shortcuts ──
document.addEventListener('keydown', function(e) {{
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const items = document.querySelectorAll('.oa-nav-item');
    const idx = Array.from(items).findIndex(el => el.classList.contains('active'));
    if (e.key === 'ArrowDown' && idx < items.length - 1) {{
        e.preventDefault();
        items[idx+1].click();
    }} else if (e.key === 'ArrowUp' && idx > 0) {{
        e.preventDefault();
        items[idx-1].click();
    }}
}});
</script>
</body>
</html>"""
    return html_out


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html = build_html()
    out_path = OUTPUT_DIR / 'index.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    size = os.path.getsize(out_path)
    print(f"  ✅ OA门户页已生成: {out_path} ({size/1024:.1f}KB)")
    return out_path


if __name__ == '__main__':
    main()
