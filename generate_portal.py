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
            {"key": "platform", "label": "选品平台", "icon": "🎯", "url": "platform.html", "desc": "产品发现、扫描、看板管理"},
            {"key": "radar",    "label": "跨境雷达", "icon": "📡", "url": "radar/",       "desc": "24h跨境电商情报聚合"},
            {"key": "analysis", "label": "产品分析", "icon": "📊", "url": "analysis/",    "desc": "运营数据与补货分析"},
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
            nav_items.append(f'<div class="nav-group-label">{htmlmod.escape(group["group"])}</div>')
            for m in group["items"]:
                nav_items.append(
                    f'<a class="nav-item" data-key="{m["key"]}" href="#" '
                    f'onclick="return switchModule(\'{m["key"]}\',\'{htmlmod.escape(m["url"])}\')">'
                    f'<span class="nav-icon">{m["icon"]}</span>'
                    f'<span class="nav-label">{htmlmod.escape(m["label"])}</span>'
                    f'</a>'
                )
        else:
            nav_items.append(f'<div class="nav-group-label dim">{htmlmod.escape(group["group"])}</div>')
            nav_items.append(f'<div class="nav-empty">暂无板块</div>')

    first = MODULES[0]["items"][0]

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{SYSTEM_NAME}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📋</text></svg>">
<link rel="stylesheet" href="shared/oa-theme.css">
<style>
/* ── Reset & Base ── */
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ height:100%; overflow:hidden; }}
body {{ display:flex; font-family:var(--oa-font); background:var(--oa-bg); color:var(--oa-text); -webkit-font-smoothing:antialiased; }}

/* ── Sidebar Overlay (mobile only) ── */
#sidebar-overlay {{
    display:none; position:fixed; inset:0; z-index:150;
    background:rgba(0,0,0,0.45);
    opacity:0; pointer-events:none;
    transition:opacity .25s ease;
    backdrop-filter:blur(2px);
    -webkit-backdrop-filter:blur(2px);
}}
#sidebar-overlay.show {{
    opacity:1; pointer-events:auto;
}}

/* ── Hamburger Menu Button ── */
#menuBtn {{
    display:none; /* hidden on desktop */
}}

/* ── Sidebar ── */
#sidebar {{
    width:240px; min-width:240px; height:100vh;
    background:var(--oa-sidebar-bg);
    color:#fff;
    display:flex; flex-direction:column;
    user-select:none;
    overflow:hidden;
    z-index:100;
}}
.sidebar-header {{
    padding:22px 18px 14px;
    border-bottom:1px solid rgba(255,255,255,0.06);
    flex-shrink:0;
}}
.sidebar-header .logo {{
    font-size:24px; font-weight:700; display:flex; align-items:center; gap:12px;
}}
.sidebar-header .logo-icon {{ font-size:26px; }}
.sidebar-header .logo-text {{ display:flex; flex-direction:row; align-items:baseline; gap:8px; }}
.sidebar-header .logo-title {{ font-size:16px; font-weight:700; letter-spacing:0.3px; }}
.sidebar-header .logo-sub {{ font-size:10.5px; color:rgba(255,255,255,0.35); letter-spacing:0.6px; }}

#nav {{ flex:1; overflow-y:auto; padding:10px 0; scrollbar-width:thin; scrollbar-color:rgba(255,255,255,0.12) transparent; }}
#nav::-webkit-scrollbar {{ width:4px; }}
#nav::-webkit-scrollbar-thumb {{ background:rgba(255,255,255,0.12); border-radius:2px; }}
#nav::-webkit-scrollbar-thumb:hover {{ background:rgba(255,255,255,0.2); }}

.nav-group-label {{
    font-size:9.5px; text-transform:uppercase; letter-spacing:1.2px;
    color:rgba(255,255,255,0.25); padding:16px 18px 6px; font-weight:600;
}}
.nav-group-label.dim {{ color:rgba(255,255,255,0.12); }}

.nav-item {{
    display:flex; align-items:center; gap:12px;
    padding:11px 18px; margin:2px 10px; border-radius:8px;
    color:rgba(255,255,255,0.6); text-decoration:none;
    transition:all .15s ease; cursor:pointer;
    font-size:14px; font-weight:500; position:relative;
}}
.nav-item:hover {{ background:var(--oa-sidebar-hover); color:rgba(255,255,255,0.85); }}
.nav-item.active {{
    background:var(--oa-sidebar-active); color:#fff;
}}
.nav-item.active::before {{
    content:''; position:absolute; left:-6px; top:50%; transform:translateY(-50%);
    width:3px; height:20px; border-radius:2px;
    background:var(--oa-sidebar-accent, #6366f1);
}}
.nav-icon {{ font-size:18px; width:24px; text-align:center; flex-shrink:0; opacity:0.8; }}
.nav-item.active .nav-icon {{ opacity:1; }}
.nav-label {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.nav-empty {{ font-size:12px; color:rgba(255,255,255,0.18); padding:8px 18px 16px; font-style:italic; }}

.sidebar-footer {{
    padding:12px 18px;
    border-top:1px solid rgba(255,255,255,0.06);
    font-size:10.5px; color:rgba(255,255,255,0.25);
    flex-shrink:0;
}}

/* ── Main Area ── */
#main {{
    flex:1; display:flex; flex-direction:column; overflow:hidden;
    background:var(--oa-bg);
}}
#topbar {{
    display:flex; align-items:center; justify-content:space-between;
    padding:0 28px; height:50px; min-height:50px;
    background:rgba(255,255,255,0.82);
    backdrop-filter:blur(16px) saturate(1.2);
    -webkit-backdrop-filter:blur(16px) saturate(1.2);
    border-bottom:1px solid rgba(0,0,0,0.06);
    z-index:50;
}}
#topbar .module-title {{
    font-size:14px; font-weight:600; color:var(--oa-text);
    display:flex; align-items:center; gap:10px;
}}
#topbar .module-title .dot {{
    width:7px; height:7px; border-radius:50%; background:var(--oa-green);
    display:inline-block; flex-shrink:0;
    animation: dot-pulse 2s ease-in-out infinite;
}}
@keyframes dot-pulse {{
    0%,100% {{ opacity:1; }} 50% {{ opacity:0.4; }}
}}
#topbar .topbar-right {{
    display:flex; align-items:center; gap:20px; font-size:13px; color:var(--oa-sub);
}}
#topbar .last-update {{ font-size:12px; color:var(--oa-light); }}
#clock {{
    font-variant-numeric:tabular-nums; font-weight:500;
    font-size:13px; color:var(--oa-sub);
}}

#content-wrap {{
    flex:1; position:relative; overflow:hidden;
    margin:0; padding:0;
}}
#content-frame {{
    width:100%; height:100%; border:none; display:block;
}}

/* ── Loading overlay ── */
#loading {{
    position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
    flex-direction:column; gap:16px;
    background:var(--oa-bg); z-index:20; opacity:0; pointer-events:none;
    transition:opacity .25s ease;
}}
#loading.show {{ opacity:1; pointer-events:auto; }}
#loading .spinner {{
    width:28px; height:28px;
    border:3px solid var(--oa-border-2);
    border-top-color:var(--oa-primary);
    border-radius:50%; animation:spin .7s linear infinite;
}}
#loading .load-text {{
    font-size:12px; color:var(--oa-sub); letter-spacing:0.3px;
}}
@keyframes spin {{ to {{ transform:rotate(360deg); }} }}

/* ── Mobile Responsive ── */
@media (max-width: 768px) {{
    body {{ overflow:auto; }}

    #sidebar-overlay {{ display:block; }}

    #sidebar {{
        position:fixed; left:0; top:0; z-index:200;
        transform:translateX(-100%);
        transition:transform .25s cubic-bezier(.4,0,.2,1);
    }}
    #sidebar.open {{
        transform:translateX(0);
    }}

    #menuBtn {{
        display:flex; align-items:center; justify-content:center;
        width:36px; height:36px; border:none; border-radius:8px;
        background:var(--oa-surface-2); color:var(--oa-text);
        font-size:20px; cursor:pointer; flex-shrink:0;
        transition:background .15s;
    }}
    #menuBtn:hover {{ background:var(--oa-surface-3); }}

    .topbar-left {{
        display:flex; align-items:center; gap:10px; flex:1; min-width:0;
    }}

    #main {{
        margin-left:0; width:100%;
    }}

    #topbar {{ padding:0 12px; }}
    #topbar .last-update {{ display:none; }}
    #topbar .topbar-right {{ gap:8px; }}

    #current-module {{ font-size:13px; }}

    #content-frame {{
        height:100%;
    }}
}}
@media (max-width: 480px) {{
    #menuBtn {{ width:32px; height:32px; font-size:18px; }}
    #topbar {{ padding:0 8px; }}
    #clock {{ font-size:12px; }}
}}
</style>
</head>
<body>

<!-- Sidebar -->
<div id="sidebar-overlay" onclick="toggleSidebar()"></div>
<aside id="sidebar">
    <div class="sidebar-header">
        <div class="logo">
            <span class="logo-icon">📋</span>
            <div class="logo-text">
                <span class="logo-title">{htmlmod.escape(SYSTEM_NAME)}</span>
                <span class="logo-sub">{htmlmod.escape(SYSTEM_SUB)}</span>
            </div>
        </div>
    </div>
    <nav id="nav">
        {''.join(nav_items)}
    </nav>
    <div class="sidebar-footer">
        Amazon项目运营OA v3.0 · {now.strftime('%Y-%m-%d')}
    </div>
</aside>

<!-- Main -->
<div id="main">
    <div id="topbar">
        <div class="topbar-left">
            <button id="menuBtn" onclick="toggleSidebar()" aria-label="菜单">☰</button>
            <div class="module-title">
                <span class="dot"></span>
                <span id="current-module">{htmlmod.escape(first["label"])}</span>
            </div>
        </div>
        <div class="topbar-right">
            <span class="last-update" id="last-update"></span>
            <span id="clock">--:--:--</span>
        </div>
    </div>
    <div id="content-wrap">
        <div id="loading">
            <div class="spinner"></div>
            <span class="load-text">加载中…</span>
        </div>
        <iframe id="content-frame" src="{htmlmod.escape(first["url"])}" loading="eager"></iframe>
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
    document.querySelectorAll('.nav-item').forEach(el => {{
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
    document.querySelectorAll('.nav-item').forEach(el => {{
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
    const items = document.querySelectorAll('.nav-item');
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
