#!/usr/bin/env python3
"""
三店运营OA — 统一部署脚本
1. 从 kj-news-radar (GitHub) 拉取最新内容 → output/radar/
2. 从 product-analysis (本地) 复制最新内容 → output/analysis/
3. 生成 OA 门户页 → output/index.html
4. 推送到 product-radar repo → GitHub Pages 自动部署

用法: python3 deploy_oa.py ["commit message"]
"""
import json, os, sys, base64, urllib.request, shutil
from pathlib import Path

BASE = Path(__file__).parent
OUTPUT = BASE / 'output'
REPO = 'liyuhong168/product-radar'
BRANCH = 'main'

# ── 数据源配置 ── 新增板块只需在这里加一项 ──
SOURCES = [
    {
        "name": "radar",
        "type": "github",
        "owner": "liyuhong168",
        "repo": "kj-news-radar",
        "ref": "master",
        "target_dir": OUTPUT / "radar",
        "files": [
            "index.html",
            "assets/styles.css",
            "assets/logo.svg",
            "assets/app.js",
            "data/archive.json",
            "data/latest-24h-all.json",
            "data/latest-24h.json",
            "data/policy-calendar.json",
            "data/source-status.json",
            "data/title-zh-cache.json",
        ]
    },
    {
        "name": "analysis",
        "type": "local",
        "source_dir": Path("/home/lee/product-analysis/gh-pages"),
        "target_dir": OUTPUT / "analysis",
    }
]


# ══════════════════════════════════════════
# GitHub API Helpers
# ══════════════════════════════════════════

def get_token():
    with open(os.path.expanduser('~/.git-credentials')) as f:
        raw = f.read().strip()
        # format: https://user:token@github.com
        return raw.split('@')[0].split(':')[-1]

def gh_api(method, path, data=None):
    token = get_token()
    headers = {'Authorization': f'token {token}', 'Content-Type': 'application/json', 'User-Agent': 'deploy-oa'}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f'https://api.github.com{path}', headers=headers, data=body)
    if method != 'POST':
        req.get_method = lambda: method
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read())
    except urllib.request.HTTPError as e:
        err = e.read().decode()
        print(f"  ⚠️ GitHub API error {e.code}: {err[:200]}")
        return None
    except Exception as e:
        print(f"  ⚠️ GitHub API error: {e}")
        return None


# ══════════════════════════════════════════
# Fetch Content Sources
# ══════════════════════════════════════════

def fetch_file_via_api(owner, repo, ref, path):
    """Download a single file from GitHub via Contents API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'deploy-oa',
            'Accept': 'application/vnd.github.v3+json',
        })
        resp = urllib.request.urlopen(req, timeout=30)
        j = json.loads(resp.read())
        if 'content' in j:
            return base64.b64decode(j['content'])
        else:
            print(f"    ⚠️  {path}: 返回格式异常")
            return None
    except urllib.request.HTTPError as e:
        if e.code == 404:
            print(f"    ⚠️  {path}: 文件不存在")
        elif e.code == 403:
            print(f"    ⚠️  {path}: API限流")
        else:
            print(f"    ⚠️  {path}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"    ⚠️  {path}: {e}")
        return None

def fetch_from_github(source):
    """Fetch files from a GitHub repo."""
    owner = source["owner"]
    repo = source["repo"]
    ref = source["ref"]
    target = source["target_dir"]
    files = source["files"]
    
    print(f"\n  📥 拉取 [{source['name']}] ({owner}/{repo}@{ref})")
    count = 0
    for rel_path in files:
        content = fetch_file_via_api(owner, repo, ref, rel_path)
        if content is None:
            continue
        dest = target / rel_path
        os.makedirs(dest.parent, exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(content)
        count += 1
    print(f"     ✅ 已同步 {count}/{len(files)} 个文件 → {target}")
    
    # Post-process: inject shared theme into radar pages
    if source["name"] == "radar":
        post_process_radar(target)
    
    return count > 0


def post_process_radar(target):
    """Post-process fetched radar files to use the OA design system."""
    import re
    css_path = target / "assets" / "styles.css"
    html_path = target / "index.html"
    
    # 1. Inject shared theme CSS link into HTML
    if html_path.exists():
        html = html_path.read_text(encoding='utf-8')
        if 'shared/oa-theme.css' not in html:
            # Match actual link format (with optional ?v=NN cache buster)
            match = re.search(r'<link\s+[^>]*href="(\.\/)?assets/styles\.css[^"]*"', html)
            if match:
                old_link = match.group(0)
                new_link = old_link.replace(
                    'href="', 'rel="stylesheet" href="../shared/oa-theme.css">\n<link href="'
                ).replace('">', '">', 1)
                # Safer: just insert before the existing link
                html = html.replace(
                    match.group(0),
                    f'<link rel="stylesheet" href="../shared/oa-theme.css">\n{match.group(0)}'
                )
                html_path.write_text(html, encoding='utf-8')
                print(f"     🎨 注入设计系统 → {html_path.name}")
    
    # 2. Map radar CSS variables to design system tokens
    if css_path.exists():
        css = css_path.read_text(encoding='utf-8')
        original = css
        css = css.replace('--bg: #f6f6f2;', '--bg: var(--oa-bg);')
        css = css.replace('--surface: #ffffff;', '--surface: var(--oa-surface);')
        css = css.replace('--ink: #171717;', '--ink: var(--oa-text);')
        css = css.replace('--muted: #66645f;', '--muted: var(--oa-sub);')
        css = css.replace('--line: #d9d6ce;', '--line: var(--oa-border);')
        css = css.replace('--accent: #126a73;', '--accent: var(--oa-primary);')
        css = css.replace('--accent-warm: #b55231;', '--accent-warm: var(--oa-secondary);')
        css = css.replace('--good: #1f7a4d;', '--good: var(--oa-green);')
        css = css.replace('--warn: #9a6700;', '--warn: var(--oa-orange);')
        css = css.replace('--bad: #b42318;', '--bad: var(--oa-red);')
        css = css.replace('--radius: 8px;', '--radius: var(--oa-radius);')
        # Also map surface-soft
        if '--surface-soft:' in css:
            css = css.replace('--surface-soft: #fbfaf7;', '--surface-soft: #f0f0f5;')
        
        if css != original:
            css_path.write_text(css, encoding='utf-8')
            print(f"     🎨 映射设计系统色板 → {css_path.name}")
    
    # 3. Unify page width with other OA pages
    if css_path.exists():
        css = css_path.read_text(encoding='utf-8')
        original = css
        css = css.replace('max-width: 1120px;', 'max-width: 1400px;')
        if css != original:
            css_path.write_text(css, encoding='utf-8')
            print(f"     📐 统一页面宽度 → {css_path.name}")
    
    # 4. Normalize heading sizes for cross-page consistency
    if css_path.exists():
        css = css_path.read_text(encoding='utf-8')
        original = css
        # Hero h1 → 24px to match other OA pages
        css = re.sub(r'\.hero h1 \{[^}]*font-size:\s*36px[^}]*\}',
                     '.hero h1 { margin: 6px 0 0; font-size: 24px; line-height: 1.2; overflow-wrap: break-word; }',
                     css)
        # Section h2 headings → 16px
        css = re.sub(r'\.(cross-picks-head|policy-head|list-head) h2 \{[^}]*font-size:\s*22px[^}]*\}',
                     r'.\1 h2 { margin: 4px 0 0; font-size: 16px; font-weight: 700; line-height: 1.3; }',
                     css)
        css = re.sub(r'\.action-head h2 \{[^}]*font-size:\s*22px[^}]*\}',
                     '.action-head h2 { margin: 4px 0 0; font-size: 16px; font-weight: 700; line-height: 1.3; }',
                     css)
        # Responsive: also normalize mobile h1 size
        css = css.replace(
            '.hero h1 { font-size: 26px; }',
            '.hero h1 { font-size: 22px; }'
        )
        if css != original:
            css_path.write_text(css, encoding='utf-8')
            print(f"     🔤 统一标题字号 → {css_path.name}")

def fetch_from_local(source):
    """Copy files from a local directory."""
    src = source["source_dir"]
    dst = source["target_dir"]
    
    print(f"\n  📥 复制 [{source['name']}] ({src})")
    if not src.exists():
        print(f"    ⚠️ 源目录不存在: {src}")
        return False
    
    # Remove old and copy all
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    
    total = sum(1 for _ in dst.rglob('*') if _.is_file())
    print(f"     ✅ 已复制 {total} 个文件 → {dst}")
    
    # Post-process: inject radar-style layout into analysis page
    if source["name"] == "analysis":
        post_process_analysis(dst)
    
    return True


def post_process_analysis(target):
    """Transform analysis page HTML to use radar-style hero + layout."""
    import re
    html_path = target / "index.html"
    if not html_path.exists():
        return
    
    html = html_path.read_text(encoding='utf-8')
    original = html
    
    # If already has radar-style shell, skip
    if '<main class="shell">' in html:
        print("     ✅ 已应用雷达布局，跳过")
        return
    
    # 1. Inject oa-theme.css if missing
    if 'shared/oa-theme.css' not in html:
        html = html.replace(
            '</title>',
            '</title>\n<link rel="stylesheet" href="../shared/oa-theme.css">'
        )
    
    # 2. Transform body wrapper — replace old hero + section with radar style
    old_start = '''</head><body>
<div class="oa-shell">
  <div class="oa-hero">
    <div class="oa-hero-text">
      <div class="oa-eyebrow">亚马逊英国站 · 运营决策</div>
      <h1 class="oa-hero-title">产品运营/补货分析</h1>
      <p class="oa-hero-sub">75 个产品 · 分析日期'''
    
    # Find the actual sub text after the above
    # We need to match from the oa-eyebrow through the entire header+filters+section
    # Use a regex approach for the whole block
    pattern = r'</head><body>\n<div class="oa-shell">\n  <div class="oa-hero">\n    <div class="oa-hero-text">\n      <div class="oa-eyebrow">亚马逊英国站 · 运营决策</div>\n      <h1 class="oa-hero-title">产品运营/补货分析</h1>\n      <p class="oa-hero-sub">(.*?)</p>\n    </div>\n  </div>\n\n  <div class="filter-bar">\n    <div class="store-tabs"><span class="store-tab active" onclick="filterByStore\(\'all\',this\)">全部</span><span class="store-tab" onclick="filterByStore\(\'007\',this\)">007店</span><span class="store-tab" onclick="filterByStore\(\'027\',this\)">027店</span><span class="store-tab" onclick="filterByStore\(\'322\',this\)">322店</span></div>\n    <input id="searchInput" type="text" placeholder="搜索ASIN/品名..." oninput="filterTable\(\)">\n    <span id="resultCount" class="result-count">\d+ 个产品</span>\n  </div>\n\n  <div class="oa-section">\n    <div class="oa-section-header">\n      <h2 class="oa-section-title">产品库存监控</h2>\n    </div>\n    <div class="oa-card oa-table-wrap" style="padding:0">\n      <table id="productTable" class="oa-table">'
    
    match = re.search(pattern, html)
    if not match:
        print("     ⚠️ 无法匹配旧布局模式，跳过")
        return
    
    hero_sub = match.group(1)
    old_block = match.group(0)
    
    # Count products from table
    product_count_match = re.search(r'<span id="resultCount" class="result-count">(\d+) 个产品</span>', html)
    product_count = product_count_match.group(1) if product_count_match else '75'
    
    new_block = f'''</head><body>
<main class="shell">

  <header class="hero" id="sectionTop">
    <div class="hero-main">
      <div class="hero-headline">
        <div class="hero-logo" style="font-size:36px;width:52px;height:52px;display:flex;align-items:center;justify-content:center;background:var(--oa-surface);border:1px solid var(--oa-border);border-radius:14px;box-shadow:var(--oa-shadow);flex-shrink:0;">📊</div>
        <div>
          <p class="hero-tag">PRODUCT ANALYSIS</p>
          <h1>产品运营/补货分析</h1>
        </div>
      </div>
      <p class="hero-sub">{hero_sub}</p>
    </div>
    <div class="hero-aside">
      <div class="hero-meta">
        <span class="updated-label">分析时间</span>
        <span class="updated">{hero_sub.split("·")[1].strip() if "·" in hero_sub else hero_sub}</span>
      </div>
    </div>
  </header>

  <section class="primary-controls">
    <div class="store-tabs">
      <span class="store-tab active" onclick="filterByStore('all',this)">全部</span>
      <span class="store-tab" onclick="filterByStore('007',this)">007店</span>
      <span class="store-tab" onclick="filterByStore('027',this)">027店</span>
      <span class="store-tab" onclick="filterByStore('322',this)">322店</span>
    </div>
    <div class="search-wrap">
      <input id="searchInput" type="text" placeholder="搜索ASIN/品名..." oninput="filterTable()">
      <span id="resultCount" class="result-count">{product_count} 个产品</span>
    </div>
  </section>

  <section class="cross-picks-wrap" aria-label="产品库存监控">
    <div class="cross-picks-head">
      <div>
        <p class="section-eyebrow">INVENTORY MONITOR</p>
        <h2>产品库存监控</h2>
      </div>
    </div>
    <div class="cross-picks-sub">实时库存监控 · 断货预警 · 补货建议</div>
    <div class="oa-card" style="padding:0;border-radius:var(--oa-radius,12px);overflow:hidden;">
      <table id="productTable" class="oa-table">'''
    
    html = html.replace(old_block, new_block, 1)
    
    # 3. Replace footer/closing
    old_end = r'''      </table>
    </div>
  </div>

  <div class="oa-footer">
    <span>Hermes Agent · 已分析 \d+ 个产品</span>
  </div>
</div>
</body></html>'''
    
    match_end = re.search(old_end, html)
    if match_end:
        footer_text_match = re.search(r'Hermes Agent · 已分析 (\d+) 个产品', match_end.group(0))
        footer_count = footer_text_match.group(1) if footer_text_match else product_count
        
        new_end = f'''      </table>
    </div>
  </section>

  <footer class="site-footer">
    <div class="footer-inner">
      <span>Hermes Agent · 已分析 {footer_count} 个产品</span>
    </div>
  </footer>

</main>
</body></html>'''
        html = html.replace(match_end.group(0), new_end, 1)
    
    if html != original:
        html_path.write_text(html, encoding='utf-8')
        print(f"     🏗️ 应用雷达布局 → {html_path.name} ({len(html)} chars)")
    else:
        print("     ⚠️ 未检测到变更")


# ══════════════════════════════════════════
# Push to GitHub
# ══════════════════════════════════════════

def collect_files():
    """Collect all files to push from output/ and data/ directories."""
    files = []
    
    # Walk output/ recursively (portal, radar, analysis, platform)
    for root, dirs, filenames in os.walk(OUTPUT):
        for fname in filenames:
            if not (fname.endswith('.html') or fname.endswith('.json') or
                    fname.endswith('.css') or fname.endswith('.svg') or
                    fname.endswith('.js') or fname.endswith('.md')):
                continue
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, BASE)
            files.append((rel_path, abs_path))
    
    # Include data files (for date picker, etc.)
    for subdir in ('data/channels', 'data/history', 'data/discovery'):
        full = BASE / subdir
        if not full.exists():
            continue
        for fname in sorted(os.listdir(full))[-12:]:
            if not (fname.endswith('.json') or fname.endswith('.html')):
                continue
            abs_path = str(full / fname)
            files.append((f'{subdir}/{fname}', abs_path))
    
    # Root-level files
    for f in ('status.json',):
        fp = BASE / f
        if fp.exists():
            files.append((f, str(fp)))
    
    # Shared design system
    shared_dir = BASE / 'shared'
    if shared_dir.exists():
        for fname in os.listdir(shared_dir):
            if fname.endswith('.css') or fname.endswith('.svg') or fname.endswith('.js'):
                files.append((f'shared/{fname}', str(shared_dir / fname)))
    
    return files

def push_files(files, message):
    """Push files to GitHub repo via API."""
    if not files:
        print("  无文件可推送")
        return
    
    print(f"\n  📤 推送到 {REPO} ({len(files)} 个文件)...")
    
    # Get current HEAD
    ref_data = gh_api('GET', f'/repos/{REPO}/git/refs/heads/{BRANCH}')
    if not ref_data:
        print("  ❌ 无法获取HEAD引用，推送终止")
        return False
    head_sha = ref_data['object']['sha']
    
    commit_data = gh_api('GET', f'/repos/{REPO}/git/commits/{head_sha}')
    if not commit_data:
        print("  ❌ 无法获取当前commit，推送终止")
        return False
    base_tree = commit_data['tree']['sha']
    
    # Upload blobs in batches of 5
    tree_items = []
    batch = []
    for rel_path, abs_path in files:
        if not os.path.exists(abs_path):
            continue
        batch.append((rel_path, abs_path))
        if len(batch) >= 5:
            items = _upload_batch(batch)
            if items:
                tree_items.extend(items)
            batch = []
    if batch:
        items = _upload_batch(batch)
        if items:
            tree_items.extend(items)
    
    if not tree_items:
        print("  无变更")
        return True
    
    # Create tree
    tree = gh_api('POST', f'/repos/{REPO}/git/trees', {
        'base_tree': base_tree, 'tree': tree_items
    })
    if not tree:
        print("  ❌ tree创建失败")
        return False
    
    # Create commit
    new_commit = gh_api('POST', f'/repos/{REPO}/git/commits', {
        'message': message, 'tree': tree['sha'], 'parents': [head_sha]
    })
    if not new_commit:
        print("  ❌ commit创建失败")
        return False
    
    # Update ref
    result = gh_api('PATCH', f'/repos/{REPO}/git/refs/heads/{BRANCH}', {
        'sha': new_commit['sha']
    })
    if result:
        print(f"  ✅ 已部署 {len(tree_items)} 个文件 ({message})")
        return True
    else:
        print("  ❌ ref更新失败")
        return False

def _upload_batch(batch):
    items = []
    for rel_path, abs_path in batch:
        with open(abs_path, 'rb') as f:
            content = f.read()
        blob = gh_api('POST', f'/repos/{REPO}/git/blobs', {
            'content': base64.b64encode(content).decode(), 'encoding': 'base64'
        })
        if blob:
            items.append({'path': rel_path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    return items


# ══════════════════════════════════════════
# Main
# ══════════════════════════════════════════

def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else '🔄 OA统一部署'
    
    print("=" * 54)
    print("  三店运营OA — 统一部署")
    print("=" * 54)
    
    # Step 1: Fetch content from sources
    print("\n📦 Step 1/4: 拉取各板块内容")
    for source in SOURCES:
        if source["type"] == "github":
            fetch_from_github(source)
        elif source["type"] == "local":
            fetch_from_local(source)
    
    # Step 2: Run platform scanner (if exists)
    print("\n🔍 Step 2/4: 生成选品平台")
    scanner = BASE / 'generate_platform.py'
    if scanner.exists():
        os.chdir(BASE)
        ret = os.system(f'python3 {scanner}')
        if ret != 0:
            print("  ⚠️ 选品平台生成异常，继续部署")
        else:
            print("  ✅ 选品平台已生成")
    else:
        print("  跳过（generate_platform.py 不存在）")
    
    # Step 3: Generate portal page
    print("\n🏠 Step 3/4: 生成OA门户页")
    portal = BASE / 'generate_portal.py'
    if portal.exists():
        os.chdir(BASE)
        ret = os.system(f'python3 {portal}')
        if ret != 0:
            print("  ❌ 门户页生成失败")
            return 1
    else:
        print("  ❌ generate_portal.py 不存在")
        return 1
    
    # Step 4: Push to GitHub
    print("\n🚀 Step 4/4: 推送到GitHub")
    files = collect_files()
    if not push_files(files, msg):
        return 1
    
    print("\n" + "=" * 54)
    print("  ✅ 部署完成！等待 GitHub Actions 构建 Pages...")
    print(f"  🌐 https://liyuhong168.github.io/product-radar/")
    print("=" * 54)
    return 0


if __name__ == '__main__':
    sys.exit(main())
