# Product Radar — Amazon UK 选品雷达

多源产品发现雷达系统，聚合 Amazon UK、TikTok Shop、Google Trends、Reddit、英国节日规划五个数据源，自动扫描、评分、过滤、生成可视化选品平台。

> 零成本部署：GitHub Actions + GitHub Pages，无需服务器。专为 Amazon UK 铺货型卖家设计。

## 特性

- **多源信号融合** — Amazon BSR + TikTok 热门 + Google Trends + Reddit 讨论 + 节日规划，五源交叉验证
- **节日驱动选品** — 61 个英国节日，海运/卡航/快铁物流时效倒推，自动触发季节性扫描
- **用户反馈学习** — 从用户拒绝的产品中提取模式，持续改进过滤规则
- **4 Tab 统一平台** — 趋势发现 / 雷达扫描 / 节日选品 / 选品看板
- **零成本部署** — GitHub Actions 定时扫描 + GitHub Pages 静态托管

## 架构

```
数据采集层 (5 源)
  Amazon UK · TikTok Shop · Google Trends · Reddit · UK Festival Planner
      │
      ▼
处理生成层 (Python + GitHub Actions)
  scanner.py → scoring_engine → signal_fusion → calc_profit
  festival_engine → generate_portal.py / generate_platform.py
      │
      ▼
展示门户层 (GitHub Pages)
  门户 (generate_portal.py) → iframe 聚合三模块
    ├─ 📡 跨境雷达 (kj-news-radar 独立仓库)
    ├─ 🎯 选品平台 (4 Tab，本仓库生成)
    └─ 📊 产品分析 (product-analysis 独立仓库)
```

## 快速开始

### 直接访问

打开 [liyuhong168.github.io/product-radar](https://liyuhong168.github.io/product-radar/) 即可使用。

### 本地运行

```bash
git clone https://github.com/liyuhong168/product-radar.git
cd product-radar

# 运行扫描（需要 Python 3.10+）
pip install requests beautifulsoup4 playwright
python3 run_scan_v2.py

# 生成选品平台页面
python3 generate_platform.py

# 生成门户页面
python3 generate_portal.py

# 本地预览
python3 -m http.server 8080
# 访问 http://localhost:8080/output/
```

## 配置说明

主配置文件 `config.json`：

| 字段 | 说明 | 当前值 |
|------|------|--------|
| `price_range` | 选品价格区间 (GBP) | £5.99 – £12.99 |
| `max_weight_g` | 最大重量 | 200g |
| `max_package_dimensions` | 最大包装尺寸 (cm) | 30 × 21 × 6 |
| `min_profit_margin` | 最低利润率 | 20% |
| `max_reviews` | 最大评论数（蓝海阈值） | 200 |
| `min_rating` | 最低评分 | 3.5 |
| `forbidden_keywords` | 禁售关键词清单 | 100+ 项 |
| `sources` | 数据源配置 | Amazon UK / TikTok / Google Trends / Reddit |
| `cost_structure` | 成本结构 | VAT 16.7% / 佣金 15% / 广告 10% / FBA |

## 数据源矩阵

| 层级 | 源类型 | 数据源 |
|------|--------|--------|
| Amazon | 官方 | BSR / New Releases / Movers & Shakers |
| TikTok | 第三方 | fastmoss / kalodata / shoplus |
| 趋势 | 官方 | Google Trends (geo=GB) |
| 社区 | Reddit | CasualUK / AskUK / FrugalUK / AmazonUK / UKFrugal |
| 节日 | 外部 | uk-festival-planner (61 节日 / 300+ SKU) |

## 模块说明

### 选品平台 (generate_platform.py V5)

4 个 Tab 统一平台：

| Tab | 维度 | 数据源 | 功能 |
|-----|------|--------|------|
| 趋势发现 | 关键词 | `data/discovery/*.json` | 趋势评分、信号条形图、Amazon/1688 跳转 |
| 雷达扫描 | 产品 | `data/channels/*.json` | 状态筛选、利润过滤、CSV 导出 |
| 节日选品 | 时间 | uk-festival-planner | 紧急度分级、物流截止日倒推 |
| 选品看板 | 流程 | 三源自动注入 | 三列看板、GitHub API 同步 |

### 门户 (generate_portal.py V3)

左侧导航 + 右侧 iframe，Apple 风格设计系统。`MODULES` 列表配置化，新增板块只需加一项。

### 跨境雷达 (kj-news-radar)

独立仓库，20+ 源 24h 资讯聚合，纯关键词打分（零 LLM 消耗）。详见 [kj-news-radar](https://github.com/liyuhong168/kj-news-radar)。

### 产品分析 (product-analysis)

独立仓库，75 个 ASIN 静态页，覆盖 322/007/027 店。详见 [product-analysis](https://github.com/liyuhong168/product-analysis)。

## GitHub Actions

| Workflow | 触发 | 功能 |
|----------|------|------|
| `update.yml` | push to main | 部署 output/ 到 GitHub Pages |
| `update-status.yml` | 手动触发 | 更新单个产品状态 |
| `status-sync.yml` | repository_dispatch | 看板状态同步（安全改造后） |

定时扫描由 WSL2 上的 `cron_scan.sh` 驱行（非 GitHub Actions），调用链：

```
cron_scan.sh (timeout 800s)
  ├─ run_scan_v2.py        # 扫描 + 过滤 + 评分
  ├─ bsr_scraper.py         # BSR 数据补充
  ├─ generate_platform.py   # 生成选品平台 HTML
  └─ github_api_push.py     # 推送到 GitHub
```

## 文件结构

```
product-radar/
├── config.json              # 主配置（参数/类目/禁售词）
├── cron_scan.sh             # 定时扫描入口
├── run_scan_v2.py           # 扫描引擎（cron 调用）
├── generate_platform.py     # 选品平台生成器 V5
├── generate_portal.py       # 门户生成器 V3
├── scanner.py               # 产品过滤规则
├── scoring_engine.py        # 评分引擎
├── signal_fusion.py         # 多源信号融合
├── calc_profit.py           # 利润计算
├── festival_engine.py       # 节日引擎
├── bsr_scraper.py           # BSR 爬虫
├── feishu_push.py           # 飞书推送
├── bitable_sync.py          # 飞书多维表格同步
├── github_api_push.py       # GitHub API 推送
├── .github/workflows/       # CI/CD 工作流
├── data/                    # 扫描数据（channels/discovery）
├── output/                  # 生成的 HTML
├── shared/                  # 共享设计系统（oa-theme.css）
└── archived/                # 已弃用的旧版文件
```

## License

MIT
