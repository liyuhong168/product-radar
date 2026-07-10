#!/usr/bin/env python3
"""Transform analysis page HTML to use radar-style hero + layout."""
import re

SRC = "/home/lee/product-analysis/gh-pages/index.html"

with open(SRC, encoding='utf-8') as f:
    html = f.read()

original = html

# ─── Patch 1: Replace body wrapper + hero + filter-bar + section-heading ───

old_start = '''</head><body>
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
      <table id="productTable" class="oa-table">'''

new_start = '''</head><body>
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
      <table id="productTable" class="oa-table">'''

assert old_start in html, "Patch 1: old_start not found!"
html = html.replace(old_start, new_start, 1)
print("✅ Patch 1 applied: hero + filter + section heading transformed to radar style")

# ─── Patch 2: Replace footer/closing ───

old_end = '''      </table>
    </div>
  </div>

  <div class="oa-footer">
    <span>Hermes Agent · 已分析 75 个产品</span>
  </div>
</div>
</body></html>'''

new_end = '''      </table>
    </div>
  </section>

  <footer class="site-footer">
    <div class="footer-inner">
      <span>Hermes Agent · 已分析 75 个产品</span>
    </div>
  </footer>

</main>
</body></html>'''

assert old_end in html, "Patch 2: old_end not found!"
html = html.replace(old_end, new_end, 1)
print("✅ Patch 2 applied: footer closing transformed to radar style")

# ─── Write result ───
if html != original:
    with open(SRC, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ File written: {SRC} ({len(html)} chars, was {len(original)})")
else:
    print("\n⚠️ No changes made")
