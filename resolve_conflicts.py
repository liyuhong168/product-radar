#!/usr/bin/env python3
"""Resolve git merge conflicts in analysis/index.html and oa-theme.css by keeping the radar-style layout."""

import re

# --- Fix analysis/index.html ---
path = "/home/lee/product-radar/output/analysis/index.html"
with open(path, encoding='utf-8') as f:
    html = f.read()

original = html

# Conflict 1: body start — keep my version (radar-style, the ====== ... >>>>>> block)
conflict1_start = '''<<<<<<< HEAD
<div class="oa-shell">
  <div class="oa-hero">
    <div class="oa-hero-text">
      <div class="oa-eyebrow">亚马逊英国站 · 运营决策</div>
      <h1 class="oa-hero-title">产品运营/补货分析</h1>
      <p class="oa-hero-sub">75 个产品 · 分析日期: 2026-07-10 13:43 · 数据来源: 领星ERP + Amazon UK</p>
    </div>
  </div>

  <div class="filter-bar">
    <div class="store-tabs"><span class="store-tab active" onclick="filterByStore('all',this)">全部</span><span class="store-tab" onclick="filterByStore('007',this)">007店</span><span class="store-tab" onclick="filterByStore('027',this)">027店</span><span class="store-tab" onclick="filterByStore('322',this)">322店</span></div>
    <input id="searchInput" type="text" placeholder="搜索ASIN/品名..." oninput="filterTable()">
    <span id="resultCount" class="result-count">75 个产品</span>
  </div>

  <div class="oa-section">
    <div class="oa-section-header">
      <h2 class="oa-section-title">产品库存监控</h2>
    </div>
    <div class="oa-card oa-table-wrap" style="padding:0">
======='''

conflict1_replacement = '''<main class="shell">

  <header class="hero" id="sectionTop">
    <div class="hero-main">
      <div class="hero-headline">
        <div class="hero-logo" style="font-size:36px;width:52px;height:52px;display:flex;align-items:center;justify-content:center;background:var(--oa-surface);border:1px solid var(--oa-border);border-radius:14px;box-shadow:var(--oa-shadow);flex-shrink:0;">📊</div>
        <div>
          <p class="hero-tag">PRODUCT ANALYSIS</p>
          <h1>产品运营/补货分析</h1>
        </div>
      </div>
      <p class="hero-sub">75 个产品 · 分析日期: 2026-07-10 13:43 · 数据来源: 领星ERP + Amazon UK</p>
    </div>
    <div class="hero-aside">
      <div class="hero-meta">
        <span class="updated-label">分析时间</span>
        <span class="updated">2026-07-10 13:43</span>
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
      <span id="resultCount" class="result-count">75 个产品</span>
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
'''

assert conflict1_start in html, "Conflict 1 marker not found!"
html = html.replace(conflict1_start, conflict1_replacement, 1)
print("✅ Conflict 1 resolved")

# Conflict 2: footer — keep my version
conflict2_start = '''<<<<<<< HEAD
  </div>

  <div class="oa-footer">
    <span>Hermes Agent · 已分析 75 个产品</span>
  </div>
</div>
=======
  </section>

  <footer class="site-footer">
    <div class="footer-inner">
      <span>Hermes Agent · 已分析 75 个产品</span>
    </div>
  </footer>

</main>
'''

assert conflict2_start in html, "Conflict 2 marker not found!"
# Keep the radar-style footer and close the section
html = html.replace(conflict2_start, '''  </section>

  <footer class="site-footer">
    <div class="footer-inner">
      <span>Hermes Agent · 已分析 75 个产品</span>
    </div>
  </footer>

</main>
''', 1)
print("✅ Conflict 2 resolved")

# Also remove any lingering >>>>>>> markers
html = html.replace('>>>>>>> 5a4253e (产品分析页雷达布局对齐 + 共享布局组件)', '')
html = html.replace('>>>>>>> 5a4253e', '')

if html != original:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ Written {path} ({len(html)} chars)")
else:
    print("⚠️ No changes")

# --- Fix shared/oa-theme.css ---
css_path = "/home/lee/product-radar/shared/oa-theme.css"
with open(css_path, encoding='utf-8') as f:
    css = f.read()

original_css = css

# The CSS might have conflicts too - let's check
if '<<<<<<<' in css:
    # Resolve by keeping my version (the radar-style components)
    # The conflict is likely in the radar components section
    css = css.replace('<<<<<<< HEAD', '')
    css = css.replace('=======', '')
    css = css.replace('>>>>>>> 5a4253e (产品分析页雷达布局对齐 + 共享布局组件)', '')
    css = css.replace('>>>>>>> 5a4253e', '')
    print("✅ CSS conflict markers removed")
    
    if css != original_css:
        with open(css_path, 'w', encoding='utf-8') as f:
            f.write(css)
        print(f"✅ Written {css_path} ({len(css)} chars)")
else:
    print("✅ No CSS conflicts found")
