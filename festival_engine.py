#!/usr/bin/env python3
"""
Festival Planner — 从 uk-festival-planner 提取数据，集成到选品平台
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent

# 物流模式配置
LOGISTICS_MODES = {
    "air": {"label": "空运", "icon": "✈️", "transit": 13, "leadTime": 19, "production": 3},
    "rail": {"label": "卡航", "icon": "🚂", "transit": 30, "leadTime": 36, "production": 3},
    "sea": {"label": "海运", "icon": "🚢", "transit": 60, "leadTime": 66, "production": 3},
}

# 里程碑配置
MILESTONES = [
    {"id": "selection", "name": "选品确认", "daysBeforeSource": "leadTime+14", "actions": "完成选品、打样确认、下采购单"},
    {"id": "airArrival", "name": "空运到仓", "daysBeforeSource": "transit", "actions": "空运{transit}天 + FBA入仓3天"},
    {"id": "truckShip", "name": "卡车发货", "daysBeforeSource": "leadTime", "actions": "{modeLabel}{transit}天 + FBA入仓3天"},
    {"id": "arrival", "name": "大货到仓", "daysBefore": 7, "actions": "大货入FBA仓，开始推广"},
    {"id": "festival", "name": "节日当天", "daysBefore": 0, "actions": "节日当天"},
]


def load_festivals():
    """加载 Festival 数据"""
    # 直接从 uk-festival-planner 读取原始 HTML
    html_file = Path('/home/lee/uk-festival-planner/index.html')
    if not html_file.exists():
        return []
    
    content = html_file.read_text(encoding='utf-8')
    
    # 找到 FESTIVALS 数组
    start = content.find('const FESTIVALS = [')
    if start == -1:
        return []
    
    # 找到对应的结束括号
    bracket_count = 0
    i = start + len('const FESTIVALS = ')
    end = None
    while i < len(content):
        if content[i] == '[':
            bracket_count += 1
        elif content[i] == ']':
            bracket_count -= 1
            if bracket_count == 0:
                end = i + 1
                break
        i += 1
    
    if not end:
        return []
    
    js_array = content[start + len('const FESTIVALS = '):end]
    
    # 使用 Node.js 解析 JS 数组
    import subprocess
    import tempfile
    try:
        # 写入临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(f'const FESTIVALS = {js_array};\n')
            f.write('console.log(JSON.stringify(FESTIVALS));\n')
            temp_file = f.name
        
        result = subprocess.run(
            ['node', temp_file],
            capture_output=True, text=True, timeout=30
        )
        
        # 清理临时文件
        import os
        os.unlink(temp_file)
        
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"Node.js 解析失败: {e}")
    
    return []


def get_urgency(festival, logistics="air"):
    """计算节日紧急度"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    f_date = datetime.strptime(festival['date'], '%Y-%m-%d')
    
    if f_date < today:
        return "past"
    
    # 计算选品截止日
    mode = LOGISTICS_MODES[logistics]
    deadline = f_date - timedelta(days=mode['leadTime'] + 14)
    days = (deadline - today).days
    
    if days < 0:
        return "urgent"
    elif days <= 7:
        return "week"
    elif days <= 30:
        return "month"
    return "plan"


def get_urgency_label(urgency):
    """紧急度标签"""
    return {
        "urgent": "🔴紧急",
        "week": "🟠本周启动",
        "month": "🟡本月备货",
        "plan": "🟢规划中",
        "past": "⚫已过"
    }.get(urgency, urgency)


def generate_festival_html(festivals):
    """生成 Festival Planner 的 HTML"""
    if not festivals:
        return '<div class="empty">暂无节日数据</div>'
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 统计紧急度
    stats = {"urgent": 0, "week": 0, "month": 0, "plan": 0, "past": 0}
    for f in festivals:
        urgency = get_urgency(f)
        stats[urgency] += 1
    
    # 找到最近的备货节点
    upcoming = None
    for f in festivals:
        urgency = get_urgency(f)
        if urgency != "past":
            f_date = datetime.strptime(f['date'], '%Y-%m-%d')
            mode = LOGISTICS_MODES["air"]
            deadline = f_date - timedelta(days=mode['leadTime'] + 14)
            if upcoming is None or deadline < upcoming['deadline']:
                upcoming = {"festival": f, "deadline": deadline, "urgency": urgency}
    
    # 生成 HTML
    html = f'''
    <div class="festival-header">
      <h2>📅 Festival Planner 2026 Jul - 2027 Jun | {len(festivals)} Events</h2>
      <div class="countdown">
        今日 <strong>{today}</strong>
        {f'''· 最近备货节点：<strong>{upcoming['festival']['icon']} {upcoming['festival']['name']}</strong>
           （{upcoming['festival']['date']}）· 选品截止 <strong>{upcoming['deadline'].strftime('%Y-%m-%d')}</strong>
           · <span class="badge {upcoming['urgency']}">{get_urgency_label(upcoming['urgency'])}</span>''' if upcoming else ''}
      </div>
    </div>
    
    <div class="stat-cards">
      <div class="stat-card urgent"><div class="num">{stats['urgent']}</div><div class="label">🔴 紧急（已过截止）</div></div>
      <div class="stat-card week"><div class="num">{stats['week']}</div><div class="label">🟠 本周必须启动</div></div>
      <div class="stat-card month"><div class="num">{stats['month']}</div><div class="label">🟡 本月需备货</div></div>
      <div class="stat-card plan"><div class="num">{stats['plan']}</div><div class="label">🟢 规划观察中</div></div>
    </div>
    
    <div class="month-nav">
      {"".join(f'<a href="#month-{m}">{m}月</a>' for m in range(1, 13))}
    </div>
    
    <div class="filter-bar">
      <div class="filter-group">
        <label>品类</label>
        <select id="filterCategory">
          <option value="">全部</option>
          <option value="decor">🎃装饰</option>
          <option value="gift">🎁礼品</option>
          <option value="apparel">👕服饰</option>
          <option value="home">🏠家居</option>
        </select>
      </div>
      <div class="filter-group">
        <label>月份</label>
        <select id="filterMonth">
          <option value="">全部</option>
          {"".join(f'<option value="{m}">{m}月</option>' for m in range(1, 13))}
        </select>
      </div>
      <div class="filter-group">
        <label>紧急度</label>
        <select id="filterUrgency">
          <option value="">全部</option>
          <option value="urgent">🔴紧急</option>
          <option value="week">🟠本周</option>
          <option value="month">🟡本月</option>
          <option value="plan">🟢规划</option>
          <option value="past">⚫已过</option>
        </select>
      </div>
      <input type="text" id="filterSearch" placeholder="搜索节日/SKU/关键词...">
      <button id="resetFilter">重置</button>
    </div>
    
    <div class="festival-list">
    '''
    
    # 按月份分组
    by_month = {}
    for f in festivals:
        month = f.get('month', 0)
        if month not in by_month:
            by_month[month] = []
        by_month[month].append(f)
    
    # 生成月份卡片
    for month in range(1, 13):
        if month not in by_month:
            continue
        fests = sorted(by_month[month], key=lambda x: x['date'])
        
        html += f'''
      <div class="month-section" id="month-{month}">
        <h2>{month}月 ({len(fests)})</h2>
        <div class="festival-cards">
        '''
        
        for f in fests:
            urgency = get_urgency(f)
            importance = f.get('importance', 'A')
            products = f.get('products', [])
            
            # 生成产品表格
            products_html = ""
            if products:
                products_html = '''
      <div class="products-section">
        <h4>选品建议</h4>
        <div class="product-table-wrap">
          <table class="product-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>品类</th>
                <th>成本</th>
                <th>售价</th>
                <th>毛利率</th>
                <th>匹配度</th>
                <th>风险</th>
                <th>关键词</th>
              </tr>
            </thead>
            <tbody>
            '''
                for p in products:
                    risk_cls = {
                        "低": "risk-low",
                        "中": "risk-mid",
                        "高": "risk-high"
                    }.get(p.get('riskLevel', ''), 'risk-mid')
                    
                    keywords_html = "".join(
                        f'<a class="amazon-kw" href="https://www.amazon.co.uk/s?k={kw}" target="_blank">🛒 {kw}</a>'
                        for kw in p.get('keywords', [])[:3]
                    )
                    
                    products_html += f'''
              <tr>
                <td><strong>{p.get('sku', '')}</strong><br><span style="color:var(--text-muted);font-size:11px">{p.get('skuEn', '')}</span></td>
                <td>{p.get('category', '')}</td>
                <td>{p.get('costRange', '')}</td>
                <td>{p.get('priceRange', '')}</td>
                <td>{p.get('margin', '')}</td>
                <td>{"★" * p.get('matchScore', 0)}{"☆" * (5 - p.get('matchScore', 0))}</td>
                <td><span class="risk {risk_cls}">{p.get('riskLevel', '')}</span></td>
                <td class="kw-cell">{keywords_html}</td>
              </tr>
                    '''
                
                products_html += '''
            </tbody>
          </table>
        </div>
      </div>
                '''
            
            # 验证指引
            validation_html = ""
            validation = f.get('validation', {})
            if validation:
                validation_html = '''
      <div class="validation-section">
        <h4>验证指引</h4>
        <ul>
                '''
                if validation.get('googleTrends'):
                    validation_html += f'<li><strong>Google Trends:</strong> {", ".join(validation["googleTrends"][:3])}</li>'
                if validation.get('amazonCheck'):
                    validation_html += f'<li><strong>Amazon检查:</strong> {validation["amazonCheck"]}</li>'
                if validation.get('sourcing'):
                    validation_html += f'<li><strong>1688搜索:</strong> {validation["sourcing"]}</li>'
                validation_html += '''
        </ul>
      </div>
                '''
            
            html += f'''
      <div class="festival-card" data-urgency="{urgency}" data-category="{f.get('category', '')}" data-month="{month}">
        <div class="card-header" onclick="this.parentElement.classList.toggle('expanded')">
          <div class="card-title">
            <span class="icon">{f.get('icon', '📅')}</span>
            <span>{f.get('name', '')}</span>
            <span class="name-en">{f.get('nameEn', '')}</span>
            {"<span class='badge importance-S'>S级</span>" if importance == 'S' else ''}
            <span class="badge {urgency}">{get_urgency_label(urgency)}</span>
          </div>
          <div class="card-meta">
            {f.get('date', '')} · {f.get('category', '')} | {len(products)} SKUs
          </div>
        </div>
        <div class="card-body">
          {products_html}
          {validation_html}
        </div>
      </div>
            '''
        
        html += '''
        </div>
      </div>
        '''
    
    html += '''
    </div>
    '''
    
    return html


if __name__ == '__main__':
    festivals = load_festivals()
    print(f"✅ 加载了 {len(festivals)} 个节日")
    for f in festivals[:3]:
        print(f"   - {f['icon']} {f['name']} ({f['date']})")
