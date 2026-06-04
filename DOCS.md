# 🔍 Product Radar — 选品雷达系统完整开发文档

> 版本：v3 | 最后更新：2026-06-04
> 本文档面向团队负责人Lee，详细记录系统每个模块的工作原理、数据流、配置项和已知问题。

---

## 目录

1. [项目概述与目标](#1-项目概述与目标)
2. [系统架构图](#2-系统架构图)
3. [完整文件结构](#3-完整文件结构)
4. [数据流（扫描→过滤→评分→HTML→部署）](#4-数据流)
5. [数据源模块详解](#5-数据源模块详解)
6. [6层过滤漏斗](#6-6层过滤漏斗)
7. [评分引擎v3](#7-评分引擎v3)
8. [市场情报模块](#8-市场情报模块)
9. [HTML仪表盘功能](#9-html仪表盘功能)
10. [config.json 全字段说明](#10-configjson-全字段说明)
11. [部署方案](#11-部署方案)
12. [定时任务集成](#12-定时任务集成)
13. [已知限制与陷阱](#13-已知限制与陷阱)
14. [v3升级日志](#14-v3升级日志)

---

## 1. 项目概述与目标

### 什么是选品雷达？

Product Radar（选品雷达）是一个**跨境电商选品自动化系统**，专为Amazon UK（英国亚马逊）市场设计。系统从8个独立数据源采集产品和趋势信号，经过6层过滤和18维度评分，最终输出一个可交互的HTML仪表盘，帮助Lee快速发现**低竞争、高利润、有趋势信号**的产品。

### 核心目标

| 目标 | 说明 |
|------|------|
| **蓝海选品** | 找到评论少（5-100条）、价格适中（£5.59-10）、利润率高（≥20%）的产品 |
| **多源验证** | 同一个产品被TikTok、Google Trends、HotUKDeals等多个独立来源同时提到 → 信号更强 |
| **自动化** | 每天定时扫描、评分、生成报告，推送到飞书群 |
| **可操作** | 每个产品卡片有1688找货源按钮、3档采购成本估算、状态跟踪（待评估→找供应商→已采样→已上架） |

### 目标市场

- **平台**：Amazon UK（amazon.co.uk）
- **币种**：GBP（英镑），汇率 `1 GBP ≈ 7.3 CNY`（config中配置）
- **价格区间**：£5.59 - £10.00（小件轻量商品）
- **重量限制**：≤300g
- **体积限制**：≤100ml（液体）、≤32cm（长度）

---

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        数据采集层 (Sources)                          │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Amazon   │ │ TikTok   │ │ Google   │ │ Reddit   │ │AnySearch │  │
│  │ UK       │ │ Shop     │ │ Trends   │ │ Demand   │ │ Trends   │  │
│  │ (curl)   │ │(AnySearch│ │(AnySearch│ │(AnySearch│ │(24查询   │  │
│  │          │ │ CLI)     │ │ CLI)     │ │ CLI)     │ │8源组)    │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       │            │            │            │            │         │
│       ▼            ▼            ▼            ▼            ▼         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              关键词匹配层 (Keyword Matching)                 │    │
│  │  TikTok品类 → Amazon产品名匹配 (≥2 hits)                    │    │
│  │  Google趋势关键词 → Amazon产品名匹配 (≥2 hits)              │    │
│  │  Reddit讨论词 → Amazon产品名匹配 (≥2 hits)                  │    │
│  │  HotUKDeals/Temu/Etsy/YouTube → 品类关键词匹配              │    │
│  └─────────────────────────┬───────────────────────────────────┘    │
└────────────────────────────┼────────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     数据处理层 (Processing)                          │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ 去重     │ →  │ 6层过滤  │ →  │ 市场情报 │ →  │ 18维度   │      │
│  │ Dedup    │    │ Funnel   │    │ Market   │    │ 评分     │      │
│  │ (by ASIN)│    │          │    │ Intel    │    │ Scoring  │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│                                                                     │
└────────────────────────────┼────────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      输出层 (Output)                                 │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  HTML仪表盘 (generate_html_v2.py)                            │   │
│  │  - 12个渠道标签页                                             │   │
│  │  - 搜索/价格/利润率/品类筛选                                  │   │
│  │  - 产品卡片（评分、信号徽章、1688按钮、3档成本、状态按钮）    │   │
│  │  - CSV导出                                                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ JSON快照     │  │ 历史记录     │  │ Git Push →   │              │
│  │ data/channels│  │ data/history │  │ GitHub Pages │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 完整文件结构

```
product-radar/
├── config.json              # 核心配置：业务规则、品类、成本结构、评分权重
├── scanner.py               # 核心引擎v1：过滤、利润计算、禁选关键词（v1用）
├── run_scan_v2.py           # ★v2主程序：多源聚合、匹配、过滤、评分、保存、生成HTML
├── scoring_engine.py        # ★评分引擎v3：18维度加权评分 + 信号投票系统
├── market_intelligence.py   # ★市场情报：供需指数 + 趋势背离检测
├── generate_html_v2.py      # ★HTML生成器：12标签页仪表盘 + 状态跟踪
├── run_scan.py              # v1扫描器（旧版，单列表输出）
├── generate_html.py         # v1 HTML生成器（旧版）
├── update.sh                # v1一键部署脚本
├── update_v2.sh             # v2一键部署脚本
│
├── sources/                 # 数据源模块
│   ├── amazon_uk.py         # Amazon UK：curl抓取新品榜/畅销榜/心愿榜/送礼榜
│   ├── amazon_search.py     # Amazon搜索（已废弃：反爬虫封锁）
│   ├── tiktok_shop.py       # TikTok：AnySearch提取热门品类关键词
│   ├── google_trends.py     # Google Trends：AnySearch获取趋势需求信号
│   ├── reddit_demand.py     # Reddit：AnySearch获取用户真实需求
│   └── anysearch_trends.py  # ★AnySearch多源趋势：24查询×8源组，品类热度评分
│
├── data/
│   ├── channels/            # v2渠道JSON快照（每日）
│   │   ├── 2026-06-04.json           # 主数据：产品列表+统计
│   │   ├── 2026-06-04-rejected.json  # 被过滤产品+原因
│   │   └── 2026-06-04-trends.json    # AnySearch趋势原始数据
│   ├── history/             # 每日扫描历史（用于趋势检测）
│   │   └── 2026-06-04.json
│   ├── snapshots/           # v1快照（旧版）
│   └── last_categories_v2.json  # 品类轮转记录
│
├── output/
│   ├── v2.html              # ★v2仪表盘HTML（GitHub Pages部署此文件）
│   └── index.html           # v1仪表盘（旧版）
│
└── .github/workflows/
    └── update.yml           # GitHub Pages自动部署workflow
```

**标★的文件是v2/v3核心文件，日常运行只涉及这些。**

---

## 4. 数据流

### 完整执行流程（`run_scan_v2.py` → `main()`）

```
步骤1/7  Amazon UK抓取
         │  amazon_uk.py → fetch(max_per_channel_type=8)
         │  - 从4种渠道类型（新品榜/畅销榜/心愿榜/送礼榜）各随机选8个品类
         │  - 每个品类用curl抓取HTML，正则解析ASIN/标题/价格/评论/评分
         │  - 品类轮转：每次优先选上次没扫的品类
         │  - 强制GBP cookie："lc-main=en_GB; i18n-prefs=GBP"
         │  输出：~100-200个产品（含ASIN、名称、价格、评论数、品类、渠道标记）
         ▼
步骤2/7  AnySearch多源趋势分析
         │  anysearch_trends.py → fetch_trend_signals()
         │  - 8个源组（tiktok/hotukdeals/temu/etsy/youtube/google_trends/reddit/market_intel）
         │  - 每组3个查询，共24个AnySearch CLI调用
         │  - 分析结果：统计品类关键词出现次数 → 归一化到0-100分
         │  - 季节性加成：当季品类×1.3
         │  - 跨源验证：≥3个源提到的品类额外+15分
         │  输出：trend_data（品类热度0-100 + 跨源验证 + 需求关键词）
         ▼
步骤3/7  TikTok品类匹配
         │  tiktok_shop.py → fetch()
         │  - AnySearch搜索"TikTok Shop UK trending products"等4个查询
         │  - 提取已知品类关键词（59个预设品类）+ 编号列表提取
         │  - match_keywords_to_products()：TikTok关键词 vs Amazon产品名
         │  - 要求≥2个关键词命中（单字≥5字母，短语计双倍权重）
         │  输出：为匹配的Amazon产品添加"TikTok趋势"来源标签
         ▼
步骤4/7  Google Trends验证
         │  google_trends.py → fetch_demand_signals()
         │  - AnySearch搜索"Google Trends UK trending products"等3个查询
         │  - extract_trending_keywords()：从63个预设趋势词中匹配
         │  - enrich_google_trends()：要求产品名中有≥2个趋势关键词
         │  输出：匹配产品标记 google_trend="rising" + 来源"Google趋势"
         ▼
步骤5/7  Reddit需求信号
         │  reddit_demand.py → fetch_demand_signals()
         │  - AnySearch搜索"reddit CasualUK best cheap finds"等4个查询
         │  - enrich_reddit()：产品名词（≥5字母）在Reddit文本中匹配≥2个
         │  - 排除34个通用词（that/this/with/from等）
         │  输出：匹配产品添加"Reddit需求"来源标签
         ▼
步骤6/7  AnySearch多源丰富
         │  enrich_from_trend_data()
         │  - 将HotUKDeals/Temu/Etsy/YouTube的趋势关键词匹配到Amazon产品
         │  - 匹配规则：关键词≥5字母且出现在产品NAME中（不是category字段）
         │  输出：匹配产品添加"HotUKDeals热帖"/"Temu热销"/"Etsy趋势"/"YouTube种草"标签
         ▼
步骤6b   去重
         │  dedup_products()
         │  - 按ASIN去重，合并来源标签
         │  - 优先级：new_releases > wished > 其他
         ▼
步骤7/7  过滤 + 评分
         │  filter_products() → 6层漏斗（见第6节）
         │  market_intelligence.py → analyze_market()
         │  - 计算每个品类的供需比
         │  - 检测趋势背离（连续扫描数据对比）
         │  scoring_engine.py → score_all_products()
         │  - 18维度加权评分（见第7节）
         │  assign_channel_tags() → 为每个产品分配渠道标签数组
         ▼
输出      保存 → 生成HTML → 部署
          - data/channels/YYYY-MM-DD.json（主数据）
          - data/channels/YYYY-MM-DD-rejected.json（被拒产品）
          - data/channels/YYYY-MM-DD-trends.json（趋势数据）
          - data/history/YYYY-MM-DD.json（历史记录）
          - output/v2.html（仪表盘HTML）
```

---

## 5. 数据源模块详解

### 5.1 Amazon UK (`sources/amazon_uk.py`)

**原理**：用`curl`直接抓取Amazon UK品类页面HTML，正则解析产品信息。

**核心函数**：
- `fetch(max_per_channel_type=8)` — 主入口，返回产品列表
- `_curl_fetch(url)` — curl抓取，强制GBP
- `_parse_amazon_page(html, category, channel_type)` — 正则解析HTML

**4种渠道类型**：

| 渠道 | URL模式 | 说明 | 数据价值 |
|------|---------|------|----------|
| `new_releases` | `/gp/new-releases/{cat}/` | 新品榜 | ⭐⭐⭐ 最高：代表新趋势 |
| `bsr` | `/gp/bestsellers/{cat}/` | 畅销榜 | ⭐⭐ 参考：但多为红海 |
| `wished` | `/gp/most-wished-for/{cat}/` | 心愿榜 | ⭐⭐⭐ 高：代表未满足需求 |
| `gifts` | `/gp/gifts/{cat}/` | 送礼榜 | ⭐ 可能返回0（地理限制） |

**品类轮转机制**：
- 总共14个品类：Kitchen, Garden, DIY, Sports, Bathroom, Cleaning, Office, Automotive, Lighting, Storage, Crafts, Bedding, Pets, Home
- 每次每种渠道类型随机选8个品类，优先选上次没扫的
- 轮转记录保存在 `data/last_categories_v2.json`

**HTML解析正则**：
```python
ASIN:   data-asin="([A-Z0-9]{10})"
标题:   <img[^>]*alt="([^"]{15,300})"
价格:   £(\d+\.\d{2})
评论:   >(\d[\d,]*)</span>\s*</a>  或  (\d[\d,]+)\s*(?:ratings?|reviews?)
评分:   (\d+\.?\d?)\s*out of\s*5
```

**GBP强制Cookie**：
```
lc-main=en_GB; i18n-prefs=GBP
```
> ⚠️ 没有这个cookie，从中国服务器抓到的价格是人民币！

**不工作的页面**：
- Movers & Shakers：地理封锁（从中国IP返回空内容）
- Search页面：反爬虫封锁（返回HTTP 202空内容）

---

### 5.2 TikTok Shop (`sources/tiktok_shop.py`)

**原理**：不直接访问TikTok（需要JS渲染），而是通过AnySearch CLI搜索TikTok相关文章，提取热门品类关键词。

**核心函数**：
- `fetch()` — 主入口，返回品类列表（伪装为产品格式）
- `_run_anysearch(query)` — 调用AnySearch CLI
- `_extract_trending_categories(text)` — 从搜索结果提取品类

**搜索查询（4个）**：
1. `"TikTok Shop UK trending products under 10 pounds 2026"`
2. `"TikTok made me buy it UK viral products summer 2026"`
3. `"trending TikTok products UK home kitchen accessories gadgets"`
4. `"TikTok viral products under 10 UK small items useful"`

**品类提取方法**：
1. **预设品类匹配**：59个已知TikTok热门品类（kitchen gadgets, phone case, led lights等）
2. **编号列表提取**：正则 `\d+[.)]\s*([A-Za-z][a-z]+(?:\s+[a-z]+){1,4})`
3. **趋势模式提取**：`(?:trending|popular|viral|best selling)\s+([a-z\s]+?)`

**输出格式**：每个品类作为伪产品返回，`sources: ["TikTok趋势"]`，用于后续关键词匹配。

---

### 5.3 Google Trends (`sources/google_trends.py`)

**原理**：通过AnySearch搜索Google Trends相关文章，提取趋势关键词。

**核心函数**：
- `fetch_demand_signals()` — 返回合并的搜索结果文本
- `extract_trending_keywords(signals_text)` — 从63个预设词中匹配

**搜索查询（3个）**：
1. `"Google Trends UK trending products rising summer 2026"`
2. `"UK consumer trending products summer 2026 popular"`
3. `"trending products UK summer 2026 what people buying"`

**预设趋势词（63个）**：涵盖夏季品类（garden, outdoor, bbq, camping...）、运动品类（fitness, yoga, cycling...）、节日品类（world cup, football, festival...）、家居品类（storage, organizer, cleaning...）

**匹配规则**：产品名中需要≥2个趋势关键词才标记为"Google趋势上升"。

---

### 5.4 Reddit Demand (`sources/reddit_demand.py`)

**原理**：通过AnySearch搜索Reddit UK相关帖子，提取用户真实需求信号。

**核心函数**：
- `fetch_demand_signals()` — 返回合并的搜索结果文本

**搜索查询（4个）**：
1. `"reddit CasualUK best cheap finds Amazon under 10 pounds"`
2. `"reddit AskUK what small item improved your life"`
3. `"reddit FrugalUK best value small purchases Amazon"`
4. `"site:reddit.com UK Amazon haul small items useful 2026"`

**匹配规则**（在`run_scan_v2.py`的`enrich_reddit()`中）：
- 产品名词（≥5字母）在Reddit文本中出现≥2个
- 排除34个通用词：that, this, with, from, have, been, your, they, will, more, than, what, when, very, just, like, would, could, should, about, these, those, here, there, some, each, much, many

---

### 5.5 AnySearch多源趋势 (`sources/anysearch_trends.py`)

**原理**：这是v2的**核心创新**。通过AnySearch CLI执行24个搜索查询（8个源组×每组3个查询），收集所有结果后统计品类关键词频率，生成品类热度评分。

**核心函数**：
- `fetch_trend_signals()` — 主入口，返回(trend_data, raw_results)
- `_analyze_trends(results, source_names)` — 分析搜索结果
- `_run_anysearch(query, domain, max_results, freshness)` — CLI调用
- `match_product_to_trends(product, trend_data)` — 产品趋势匹配

**8个源组（24个查询）**：

| 源组 | 查询数 | 示例查询 |
|------|--------|----------|
| `tiktok` | 3 | "TikTok Shop UK trending products summer 2026" |
| `hotukdeals` | 3 | "site:hotukdeals.com Amazon UK best deals trending" |
| `temu` | 3 | "Temu UK best sellers trending products summer" |
| `etsy` | 3 | "Etsy UK trending products summer 2026 best sellers" |
| `youtube` | 3 | "site:youtube.com Amazon UK haul best finds under £10 2026" |
| `google_trends` | 3 | "UK trending products summer 2026 popular buying" |
| `reddit` | 3 | "site:reddit.com UK Amazon best cheap finds under £10" |
| `market_intel` | 3 | "Amazon UK best sellers small items 2026 trending accessories" |

**分析流程**：
1. **关键词计数**：20个品类（kitchen/garden/bathroom/cleaning/car/office/storage/lighting/pets/sports/crafts/bedding/travel/phone/beauty/home decor/baby/kitchen_gadgets/eco/seasonal）×每品类5-10个关键词，统计在所有搜索结果中出现次数
2. **季节性加成**：当季品类×1.3倍（夏季：garden/outdoor/bbq等；冬季：christmas/candle/blanket等）
3. **归一化**：除以最大值×100，得到0-100分
4. **跨源验证**：≥3个源组提到的品类额外+15分，记录跨源数量
5. **需求关键词**：从搜索结果中提取引号内短语和编号列表项

**输出结构**：
```python
{
    "category_scores": {"kitchen": 85, "garden": 72, ...},  # 品类热度0-100
    "category_evidence": {"kitchen": ["kitchen", "gadget", "mug"]},  # 命中的关键词
    "source_signals": {"tiktok": {"kitchen": 3, "garden": 2}, ...},  # 每源每品类计数
    "cross_validated": {"kitchen": 5, "garden": 4},  # ≥3源验证的品类
    "demand_keywords": ["kitchen gadget", "storage box", ...],  # 热门需求词
    "season": "summer",
    "total_queries": 24,
    "total_results_chars": 45000
}
```

### 5.6 市场情报模块 (`market_intelligence.py`)

详见[第8节](#8-市场情报模块)。

---

## 6. 6层过滤漏斗

过滤在 `run_scan_v2.py` 的 `filter_products()` 函数中执行。**顺序很重要**——每层都会淘汰一部分产品。

### 漏斗流程图

```
全部产品（~150-200个）
    │
    ▼ 第1层：禁选品类/关键词
    │  scanner.py → is_forbidden()
    │  120+个禁选关键词 + 体积/重量检测
    │  淘汰：液体、电子、玩具、服装、家具等
    │  剩余：~100-120个
    ▼
    │ 第2层：大品牌排除
    │  81个品牌黑名单（Amazon Basics, Nike, Bosch, IKEA等）
    │  匹配：brand in product_name_lower
    │  淘汰：~10-20个
    ▼
    │ 第3层：评论数范围
    │  min_reviews = 5（基本需求验证）
    │  max_reviews = 100（红海排除）
    │  新品榜(new_releases)豁免最小评论数
    │  评分 < 4.0 也淘汰（退货风险）
    │  淘汰：~30-50个
    ▼
    │ 第4层：价格区间
    │  £5.59 ≤ price ≤ £10.00
    │  淘汰：~20-40个
    ▼
    │ 第5层：利润率
    │  calc_profit() 计算完整成本
    │  margin ≥ 20%
    │  淘汰：~10-20个
    ▼
    │ 第6层：过季标记
    │  不淘汰，但标记 off_season=True → 评分-20
    │
    ▼
通过产品（~5-15个）
```

### 各层详解

#### 第1层：禁选品类/关键词（`is_forbidden()`）

**关键词匹配方式**：使用**词边界正则**避免误杀：
```python
# "paint" 应该匹配 "paint" 但不匹配 "painter" 或 "painters"
pattern = r'(?<![a-z])' + re.escape(kw.strip()) + r'(?![a-z])'  # 纯字母词
re.escape(kw)  # 含空格/特殊字符的短语直接转义匹配
```

**禁选关键词分类（120+个）**：

| 分类 | 示例关键词 |
|------|-----------|
| 儿童/玩具 | toy, kids, children, baby, infant, action figure, plush, doll |
| 化妆品/护肤 | makeup, lipstick, cream, lotion, serum, skincare |
| 食品/药品 | food, snack, vitamin, supplement, pill |
| 宠物食品 | pet food, dog food, cat food, cat litter |
| 服装 | dress, shirt, shoes, trousers, clothing |
| 电子/电池 | lithium, battery, charger, electronic, usb powered, mains powered |
| 风扇类 | ceiling fan, desk fan, tower fan, neck fan, portable fan（精确匹配，不误杀"fantastic"） |
| 家具 | furniture, chair, wardrobe, mattress |
| 液体/化学 | liquid, fluid, gel, oil, glue, adhesive, resin, epoxy, bleach, detergent |
| 洗护用品 | shampoo, conditioner, body wash, mouthwash, sunscreen |
| 涂料/喷漆 | paint, emulsion, varnish, spray, aerosol |
| 饮料/香水 | drink, beverage, juice, perfume, cologne |

**体积/重量检测**：
```python
max_ml = 100     # >100ml拒绝
max_l = 0.1      # 100ml = 0.1L
max_kg = 0.3     # 300g = 0.3kg

# 正则：
# 升：(\d+(?:\.\d+)?)\s*(?:l\b|litre|litres|liter|liters)
# 毫升：(\d+)\s*ml
# 千克：(\d+(?:\.\d+)?)\s*kg
# 克：(\d+)\s*(?:g\b|grams?)
```

#### 第2层：大品牌排除

**81个品牌**，涵盖：
- **Amazon自有**：amazon basics, solimo, mama bear, presto
- **家居大牌**：ikea, dunelm, john lewis, deconovo
- **运动大牌**：nike, adidas, puma, taylormade
- **电子大牌**：anker, samsung, apple, sony, logitech
- **厨房大牌**：kitchenaid, cuisinart, le creuset, oxo
- **宠物大牌**：purina, royal canin, frontline
- **工具大牌**：bosch, dewalt, makita, stanley
- **日化大牌**：procter gamble, unilever, colgate, dove

#### 第3层：评论数 + 评分

```python
min_reviews = 5           # 基本需求验证
max_reviews = 100         # 红海排除（config中配置）
min_rating = 4.0          # 退货风险排除

# 新品榜(new_releases)豁免最小评论数
if reviews < min_reviews and "new_releases" not in channel:
    reject  # 无验证产品
```

#### 第4层：价格区间

```python
price_range.min = 5.59    # config中配置
price_range.max = 10.00
```

#### 第5层：利润率计算（`calc_profit()`）

**成本公式（以£7.00商品为例）**：

| 成本项 | 计算方式 | 示例金额 |
|--------|----------|----------|
| VAT | price × 0.167 | £1.17 |
| 佣金 | price × 0.15（Home=8%, Pet=5%） | £1.05 |
| FBA | 固定 £1.28（Small Standard） | £1.28 |
| 广告 | price × 0.05 | £0.35 |
| 退货 | price × 0.03 | £0.21 |
| 仓储 | price × 0.01 | £0.07 |
| 数字服务费 | 固定 £0.07 | £0.07 |
| 采购成本 | 固定 £1.00（config中sourcing_cost） | £1.00 |
| **总成本** | | **£5.20** |
| **净利润** | price - total_cost | **£1.80** |
| **利润率** | net_profit / price | **25.7%** |

#### 第6层：过季标记

```python
# 根据当前月份确定季节
month in (6,7,8) → summer
month in (12,1,2) → winter
month in (3,4,5) → spring
month in (9,10,11) → autumn

# 过季关键词（config中seasonal_categories）
# 例如夏天：christmas/halloween/winter/warm/heating/thermal/fleece/wool/knit → 标记过季
# 不淘汰，但评分-20
```

---

## 7. 评分引擎v3

### 位置：`scoring_engine.py`

### 设计理念

v3的核心改变：**基础分从50降到30**，更多依靠正向信号加分，惩罚更重。没有外部信号的产品会被大幅降权。

### 信号投票系统

产品信号分为**内部信号**（Amazon平台数据）和**外部信号**（独立需求来源）：

| 信号等级 | 外部源数量 | 评分影响 | 含义 |
|----------|-----------|----------|------|
| 🔴 强信号 | ≥3个外部源 | **+20** | 多个独立平台同时验证 |
| 🟠 中信号 | 2个外部源 | **+10** | 双重验证 |
| 🟡 弱信号 | 1个外部源 | **0** | 有验证但不够强 |
| ⚪ 仅Amazon | 0个外部源 | **-10** | 仅平台数据，无独立验证 |
| ⚪ 无信号 | 无任何信号 | **-15** | 完全无验证 |

**内部信号来源**：Amazon新品榜、畅销榜、心愿榜、送礼榜
**外部信号来源**：TikTok、Google Trends、HotUKDeals、Temu、Etsy、YouTube、Reddit

> ⚠️ 关键规则：**Amazon数据不算外部信号**。只有独立平台的需求信号才算"需求验证"。

### 完整评分权重表（`WEIGHTS`字典）

| 维度 | 权重 | 说明 |
|------|------|------|
| **基础分** | **30** | 所有产品起始分（v2是50） |
| **内部信号（Amazon平台）** | | |
| 新品榜 (new_releases) | +20 | 最强Amazon信号 |
| 心愿榜 (wished) | +15 | 代表未满足需求 |
| 送礼榜 (gifts) | +10 | 送礼需求 |
| **外部信号（独立平台）** | | |
| TikTok趋势匹配 | +20 | 品类关键词匹配 |
| Google趋势上升 | +15 | ≥2个关键词匹配 |
| HotUKDeals热帖 | +12 | 品类关键词匹配 |
| YouTube种草 | +10 | 品类关键词匹配 |
| Temu热销 | +8 | 品类关键词匹配 |
| Etsy趋势 | +6 | 品类关键词匹配 |
| Reddit提及 | +5 | ≥2个产品词匹配 |
| **信号投票** | | |
| 🔴 强信号(≥3外部源) | +20 | 替代旧的multi_source_boost |
| 🟠 中信号(2外部源) | +10 | |
| ⚪ 仅Amazon(0外部源) | -10 | 惩罚 |
| ⚪ 无信号 | -15 | 重罚 |
| **竞争度** | | |
| 低竞争(5-50评论) | +10 | 甜蜜区 |
| 中等(50-150评论) | +5 | |
| 零评论(非新品榜) | -15 | 风险惩罚 |
| 零评论(新品榜) | -8 | 新品可理解，小罚 |
| 评论<5 | -8 | 待验证 |
| **利润率** | | |
| ≥35% | +12 | 超高利润 |
| ≥30% | +8 | 高利润 |
| ≥25% | +4 | 较好利润 |
| **评分** | | |
| ≥4.5★ | +5 | 高评分加分 |
| **AnySearch品类趋势** | | |
| 热门品类(≥70分) | +15 | + 跨源验证额外加分 |
| 趋势品类(≥40分) | +8 | |
| 需求关键词命中 | +6 | |
| 跨源验证(每源) | +2 | 上限+8 |
| **季节性** | | |
| 当季热门 | +10 | 匹配{season}_hot关键词 |
| 过季产品 | **-20** | 匹配{season}_cold关键词 |
| **品类验证** | | |
| 品类不符 | **-10** | 产品名与品类不匹配 |
| 品类存疑 | **-5** | 低置信度 |
| **历史趋势** | | |
| 排名上升 | +10 | 连续2天排名改善 |
| 持续上升 | +8 | 连续3天评分递增 |
| **需求信号检查** | | |
| 无需求信号 | **-15** | 无任何外部信号 |

### 评分等级

| 分数范围 | 星级 | 标签 | 颜色 |
|----------|------|------|------|
| ≥100 | ⭐⭐⭐⭐⭐ | 🔥 强烈推荐 | 红色 #FF2D55 |
| 80-99 | ⭐⭐⭐⭐ | ⭐ 值得关注 | 橙色 #FF9500 |
| 60-79 | ⭐⭐⭐ | 👍 可以考虑 | 蓝色 #007AFF |
| 40-59 | ⭐⭐ | 👀 待观察 | 灰色 #8e8e93 |
| <40 | ⭐ | 💤 优先级低 | 浅灰 #c7c7cc |

### 品类自动校正（`_validate_category()`）

Amazon的品类标签经常不准。系统会：
1. 检查产品名中是否有对应品类的关键词（14个品类×每品类10-15个关键词）
2. 如果没有命中，尝试找到最匹配的品类
3. 自动更正并标记 `category_corrected: True`

---

## 8. 市场情报模块

### 位置：`market_intelligence.py`

### 8.1 供需指数（Supply-Demand Index）

**核心思想**：需求高+供应少 = 蓝海机会。

**计算公式**：
```
需求(Demand) = AnySearch品类热度评分（0-100）
供应(Supply) = ln(该品类Amazon总评论数 + 1)
供需比(Ratio) = Demand / Supply
```

**示例**：
- 品类"kitchen"：热度85，Amazon总评论1200条 → Supply = ln(1201) = 7.09 → Ratio = 85/7.09 = 12.0 → 🌊 深蓝海
- 品类"electronics"：热度60，Amazon总评论50000条 → Supply = ln(50001) = 10.82 → Ratio = 60/10.82 = 5.5 → 🌊 深蓝海
- 品类"clothing"：热度40，Amazon总评论200000条 → Supply = ln(200001) = 12.2 → Ratio = 40/12.2 = 3.3 → 💧 浅蓝海

**供需比等级**：

| 比值 | 标签 | 评分影响 | 含义 |
|------|------|----------|------|
| > 5 | 🌊 深蓝海 | **+20** | 高需求低供应，最佳机会 |
| > 3 | 💧 浅蓝海 | **+10** | 需求大于供应 |
| > 1 | ⚖️ 平衡 | **0** | 供需平衡 |
| < 1 | 🔴 红海 | **-15** | 供应过剩，竞争激烈 |
| supply=0, demand≥50 | 🌊 无竞品 | **+20** | 没找到竞品但有需求 |

**核心函数**：
- `compute_category_supply(products)` — 统计每个品类的总评论数和产品数
- `compute_supply_demand_ratio(cat_reviews, trend_data)` — 计算供需比
- `get_product_sd_score(product, sd_ratios)` — 获取产品的供需评分

### 8.2 趋势背离检测（Trend Divergence）

**核心思想**：如果品类热度在上升但Amazon排名还没变化 → **需求先行窗口期**，抢先入场。

**计算方式**：
```python
heat_change = (当前热度 - 上次热度) / max(上次热度, 1)

if heat_change > 0.3:    # 上升>30%
    direction = "rising"  → +15分
elif heat_change < -0.2:  # 下降>20%
    direction = "falling" → -10分
else:
    direction = "stable"  → 0分
```

**数据来源**：读取 `data/channels/*-trends.json` 历史文件，需要至少2天数据。

**核心函数**：
- `compute_trend_divergence(trend_data, history_days=3)` — 计算趋势背离
- `get_product_divergence_score(product, divergences)` — 获取产品的背离评分

---

## 9. HTML仪表盘功能

### 位置：`generate_html_v2.py`

### 9.1 渠道标签页（12个）

| 标签ID | 图标 | 名称 | 颜色 |
|--------|------|------|------|
| `new_releases` | 🆕 | Amazon新品榜 | #007AFF |
| `bsr` | 📈 | Amazon畅销榜 | #FF9500 |
| `wished` | 💝 | Amazon心愿榜 | #FF6B9D |
| `gifts` | 🎁 | Amazon送礼榜 | #AF52DE |
| `tiktok_verified` | 🎵 | TikTok热品 | #FF2D55 |
| `hotukdeals` | 🔥 | HotUKDeals | #FF3B30 |
| `temu_trending` | 🛒 | Temu热销 | #FF9500 |
| `etsy_trending` | 🎨 | Etsy趋势 | #FF6B9D |
| `youtube_review` | ▶️ | YouTube种草 | #FF0000 |
| `google_trends` | 📊 | Google趋势 | #34C759 |
| `multi_source` | 🔗 | 多源验证 | #5856D6 |
| `all` | 📋 | 全部 | #8e8e93 |

> ⚠️ 产品只出现一次，通过`channel_tags`数组标记属于哪些渠道。标签页切换时通过`tags.includes(currentChannel)`过滤。

### 9.2 筛选栏

- **搜索框**：按产品名搜索
- **价格筛选**：全部 / £5-7 / £7-8.5 / £8.5-10
- **利润率筛选**：全部 / ≥30% / ≥25% / ≥20%
- **品类筛选**：动态从数据中提取所有品类
- **排序**：评分↓ / 利润率↓ / 价格↑ / 评论数↑
- **CSV导出**：导出所有产品为CSV文件（UTF-8 BOM编码）

### 9.3 状态筛选

5种状态（保存在浏览器localStorage中）：

| 状态 | 标签 | 颜色 |
|------|------|------|
| `pending` | 待评估 | 灰色 |
| `supplier` | 找供应商 | 蓝色 |
| `sample` | 已采样 | 橙色 |
| `listed` | 已上架 | 绿色 |
| `rejected` | 不考虑 | 红色 |

> 状态数据保存在localStorage的`productRadar_v2_status`键中，按ASIN索引。刷新页面不丢失，但换浏览器/清缓存会丢失。

### 9.4 产品卡片

每个产品卡片包含：

1. **头部**：渠道徽章（颜色标签）+ 评分徽章（数字+星级）
2. **评分标签**：🔥强烈推荐 / ⭐值得关注 / 👍可以考虑 / 👀待观察 / 💤优先级低
3. **评分明细**：展开显示每个维度的加减分（如"+20 🆕 新品榜 | +20 🎵 TikTok | -10 ⚪ 仅Amazon"）
4. **产品名**：可点击跳转Amazon链接
5. **元数据**：价格 / 评分★ / 评论数 / 品类
6. **信号徽章**：
   - TikTok（红色）
   - Google↑（绿色）
   - 信号强度（🔴强/🟠中/🟡弱/⚪无）
   - 供需比（🌊深蓝海/💧浅蓝海/⚖️平衡/🔴红海）
   - 趋势背离（📈升温/📉降温）
7. **利润条**：可视化利润率（绿>30%/橙>20%/红<20%）
8. **成本明细**：可展开的详细成本分解
9. **1688找货源按钮**：橙色按钮，点击跳转1688搜索
   ```
   https://s.1688.com/selloffer/offer_search.htm?keywords={产品名URL编码}
   ```
10. **3档采购成本**：
    - 低档 £0.80（1688低价+空运）→ 显示对应利润率
    - 中档 £1.20（1688均价+空运）→ 显示对应利润率
    - 高档 £1.50（品牌供应商+卡航）→ 显示对应利润率
11. **状态按钮**：待评估 / 找供应商 / 已采样 / 已上架 / 不考虑

### 9.5 头部统计区

- 标题：🔍 选品雷达 v2
- 扫描信息：日期 / 时间 / 扫描数 / 通过数
- 渠道徽章：每个渠道的产品数量
- AnySearch趋势：Top 6品类 + 热度分数
- 供需比：Top 6品类 + 供需比标签

### 9.6 响应式设计

- 桌面：`grid-template-columns: repeat(auto-fill, minmax(340px, 1fr))`
- 移动端（<768px）：单列布局
- 字体：SF Pro Display / Inter / Noto Sans SC（中文）

---

## 10. config.json 全字段说明

### 10.1 基础市场配置

| 字段 | 值 | 说明 |
|------|-----|------|
| `target_market` | `"UK"` | 目标市场 |
| `platform` | `"Amazon"` | 目标平台 |
| `exchange_rate_cny_gbp` | `7.3` | 人民币兑英镑汇率 |

### 10.2 价格与利润

| 字段 | 值 | 说明 |
|------|-----|------|
| `price_range.min` | `5.59` | 最低价格（£） |
| `price_range.max` | `10.0` | 最高价格（£） |
| `min_profit_margin` | `0.2` | 最低利润率（20%） |
| `max_reviews` | `100` | 最大评论数（超过=红海） |
| `min_rating` | `4.0` | 最低评分（低于=退货风险） |

### 10.3 物理限制

| 字段 | 值 | 说明 |
|------|-----|------|
| `max_weight_g` | `300` | 最大重量（克） |
| `max_length_cm` | `32` | 最大长度（厘米） |
| `preferred_weight_g` | `100` | 偏好重量 |
| `preferred_thickness_cm` | `2.5` | 偏好厚度（用于FBA计算） |

### 10.4 成本结构 (`cost_structure`)

| 字段 | 值 | 说明 |
|------|-----|------|
| `vat_rate` | `0.167` | VAT税率（16.7%） |
| `commission_rate` | `0.15` | 默认佣金率（15%） |
| `commission_home` | `0.08` | Home/Kitchen品类佣金（8%） |
| `commission_pets` | `0.05` | Pet品类佣金（5%） |
| `ad_rate` | `0.05` | 广告费率（5%） |
| `return_rate` | `0.03` | 退货率（3%） |
| `storage_rate` | `0.01` | 仓储费率（1%） |
| `digital_service_fee` | `0.07` | 数字服务费（固定£0.07） |
| `fba_small_standard` | `1.28` | FBA小标准件费用 |
| `fba_large_standard` | `2.46` | FBA大标准件费用 |
| `sourcing_cost` | `1.0` | 默认采购成本（£1.00） |

### 10.5 禁选品类 (`forbidden_categories`)

26个品类标签：children, toys, baby, cosmetics, skincare, beauty_tools, food, medicine, supplements, health, clothing, shoes, apparel, fashion, furniture, large_items, electronics, battery, electrical, powered, petroleum, aerosol, flammable, weapons, knives, liquids, pet_food

### 10.6 禁选关键词 (`forbidden_keywords`)

120+个关键词，详见[第6层过滤](#第1层禁选品类关键词is_forbidden)。

### 10.7 数据源配置 (`sources`)

| 源 | 字段 | 说明 |
|----|------|------|
| `amazon_uk.enabled` | `true` | 启用Amazon |
| `amazon_uk.priority` | `"new_releases"` | 优先新品榜 |
| `amazon_uk.categories` | 18个品类 | 扫描品类列表 |
| `amazon_uk.urls` | 3种URL模板 | new_releases/bestsellers/movers_shakers |
| `tiktok_shop_uk.enabled` | `true` | 启用TikTok |
| `tiktok_shop_uk.platforms` | 3个平台URL | fastmoss/kalodata/shoplus |
| `google_trends_uk.enabled` | `true` | 启用Google Trends |
| `google_trends_uk.geo` | `"GB"` | 地理位置 |
| `reddit_demand.enabled` | `true` | 启用Reddit |
| `reddit_demand.subreddits` | 5个子版块 | CasualUK/AskUK/FrugalUK/AmazonUK/UKFrugal |

### 10.8 评分权重 (`scoring`)

| 字段 | 值 | 说明 |
|------|-----|------|
| `new_releases_bonus` | `25` | 新品榜加分（v1用，v3用WEIGHTS字典） |
| `tiktok_trending_bonus` | `25` | TikTok加分 |
| `google_rising_bonus` | `20` | Google趋势加分 |
| `multi_source_boost` | `20` | 多源加分 |
| `low_review_bonus` | `15` | 低评论加分 |
| `high_margin_bonus` | `10` | 高利润加分 |
| `seasonal_bonus` | `10` | 季节性加分 |
| `reddit_mention_bonus` | `5` | Reddit提及加分 |
| `bsr_top50_bonus` | `5` | BSR前50加分 |
| `bsr_top100_bonus` | `3` | BSR前100加分 |

> 注意：v3评分引擎使用自己的`WEIGHTS`字典，config中的scoring权重主要用于v1。

### 10.9 需求信号要求

| 字段 | 值 | 说明 |
|------|-----|------|
| `demand_signal_required` | `true` | 是否要求需求信号 |
| `demand_signal_sources` | `["new_releases", "tiktok", "google_trends"]` | 合格的需求信号源 |

### 10.10 输出配置 (`output`)

| 字段 | 值 | 说明 |
|------|-----|------|
| `max_recommendations` | `10` | 最大推荐数 |
| `snapshot_dir` | `"data/snapshots"` | v1快照目录 |
| `history_dir` | `"data/history"` | 历史记录目录 |
| `report_dir` | `"output"` | 报告输出目录 |

### 10.11 采购成本档位 (`sourcing_tiers`)

| 档位 | 成本 | 说明 |
|------|------|------|
| 低档 | £0.80 | 1688低价+空运 |
| 中档 | £1.20 | 1688均价+空运 |
| 高档 | £1.50 | 品牌供应商+卡航 |

### 10.12 大品牌黑名单 (`forbidden_brands`)

81个品牌，涵盖Amazon自有、家居、运动、电子、厨房、宠物、工具、日化等品类。详见[第2层过滤](#第2层大品牌排除)。

### 10.13 季节性品类 (`seasonal_categories`)

| 字段 | 说明 |
|------|------|
| `summer_hot` | 夏季热门：garden, outdoor, bbq, camping, travel, beach... (17个) |
| `summer_cold` | 夏季冷门：christmas, halloween, winter, warm, heating... (10个) |
| `winter_hot` | 冬季热门：christmas, halloween, warm, heating, blanket, candle... (15个) |
| `winter_cold` | 冬季冷门：bbq, camping, beach, swimming... (9个) |

---

## 11. 部署方案

### 11.1 本地扫描 + GitHub Pages部署

**核心设计决策**：扫描在本地执行，GitHub Actions只负责部署。

**原因**：
- Amazon从中国IP显示GBP价格（需GBP cookie），从美国IP显示USD价格
- GitHub Actions运行器在美国 → Amazon返回美国数据
- TikTok数据平台有地理限制

### 11.2 本地扫描流程

```bash
cd /home/lee/product-radar

# 方式1：运行v2完整扫描
python3 run_scan_v2.py

# 方式2：一键部署脚本
bash update_v2.sh
```

**`update_v2.sh`脚本内容**：
```bash
#!/bin/bash
cd /home/lee/product-radar
python3 run_scan_v2.py > /dev/null 2>&1
git add data/ output/ -f
git diff --cached --quiet && exit 0
git commit -m "auto-update $(date -u '+%Y-%m-%d %H:%M')"
git pull --rebase 2>/dev/null || true
git push
```

### 11.3 GitHub Pages Workflow

**文件**：`.github/workflows/update.yml`

```yaml
name: Deploy Product Radar
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: write
  pages: write
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: output
      - id: deployment
        uses: actions/deploy-pages@v4
```

**工作流程**：
1. 本地 `git push` 推送新数据
2. GitHub Actions自动触发
3. 将 `output/` 目录上传为Pages artifact
4. 部署到GitHub Pages

### 11.4 GitHub Pages启用

```bash
curl -X POST -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/{owner}/{repo}/pages" \
  -d '{"source":{"branch":"main","path":"/"},"build_type":"workflow"}'
```

### 11.5 缓存刷新

GitHub Pages缓存激进。部署后在URL加时间戳强制刷新：
```
https://username.github.io/product-radar/output/v2.html?t=202606041200
```

---

## 12. 定时任务集成

### 12.1 Cron扫描流程

选品雷达通过Hermes Agent的cron系统实现自动化：

1. **定时触发**：cron job每天定时执行
2. **执行扫描**：运行 `python3 run_scan_v2.py`
3. **生成报告**：HTML仪表盘 + JSON数据
4. **推送飞书**：通过 `feishu_post_push.py` 推送摘要到飞书群
5. **Git部署**：自动push到GitHub Pages

### 12.2 飞书推送格式

使用**双消息模式**：

**消息1**：富文本（`msg_type: "post"`）
```
🔍 选品发现 | 2026-06-04

1. Silicone Kitchen Gadget Set — 利润率28%（TikTok爆款+Google趋势）
2. Garden Solar Light Stake — 利润率32%（多源验证，夏季热门）
...

🔥 趋势要点：厨房品类热度85分（5源验证），花园品类72分
🌊 供需比：厨房 12.0（深蓝海），清洁 5.5（深蓝海）
```

**消息2**：纯文本URL（触发飞书文档预览卡片）
```
https://feishu.cn/docx/DOC_ID
```

> ⚠️ 必须用纯文本URL单独发一条消息，飞书才会自动生成文档预览卡片。用`{"tag": "a"}`格式化的链接不会触发预览。

### 12.3 推送脚本

```bash
python3 /home/lee/.hermes/scripts/feishu_post_push.py \
  --title "🔍 选品发现 | $(date +%Y-%m-%d)" \
  --products-file /tmp/products.txt \
  --trend "趋势要点" \
  --doc-id "飞书文档ID"
```

---

## 13. 已知限制与陷阱

### 13.1 Amazon抓取相关

| # | 问题 | 解决方案 |
|---|------|----------|
| 1 | **Amazon从中国IP显示人民币价格** | 必须用GBP Cookie：`lc-main=en_GB; i18n-prefs=GBP` |
| 2 | **Amazon Search页面反爬虫** | `/s?k=...` 返回空内容。只用品类页面 |
| 3 | **Movers & Shakers地理封锁** | 从中国IP返回空产品列表。跳过此渠道 |
| 4 | **Gift Ideas可能返回0产品** | 地理限制，保持轮转但期望值低 |
| 5 | **£5.59-10区间产品稀少** | 热门品类TOP产品多在£5以下或£15以上。需扫20+品类积累 |
| 6 | **评论2000+的红海产品** | Lee的批量测试模式（20件×20个）无法竞争，必须过滤 |

### 13.2 技术陷阱

| # | 问题 | 解决方案 |
|---|------|----------|
| 7 | **`\b`在正则中被转义为退格符(0x08)** | write_file/patch工具可能破坏`\b`。用`cat -v`验证 |
| 8 | **"paint"匹配"painter"** | 使用词边界正则：`r'(?<![a-z])paint(?![a-z])'` |
| 9 | **GitHub Pages缓存** | URL加`?t=timestamp`强制刷新 |
| 10 | **git push被拒绝** | 先`git pull --rebase`再push |
| 11 | **TikTok平台需要JS渲染** | 不直接访问，改用AnySearch搜索文章 |
| 12 | **Tavily免费额度（1000/月）** | 用AnySearch为主，Tavily为备 |
| 13 | **正则双重转义** | `\\d`和`\\s`必须是真实正则转义，不能是字面量 |
| 14 | **`scoring_engine.py`的BASE路径** | `Path(__file__).parent`（不是parent.parent，因为文件在项目根目录） |
| 15 | **`sources/`下文件的BASE路径** | `Path(__file__).parent.parent`（多一层目录） |
| 16 | **液体禁选词不够广** | 除基本词外，还需包含shampoo/conditioner/glue/perfume等25个词 |
| 17 | **频道标签ID必须匹配数据字段** | HTML中的tab ID必须和产品数据的`channel`字段一致 |
| 18 | **去重必须在评分前** | 正确顺序：采集→匹配→去重→过滤→评分→分配channel_tags |
| 19 | **channel_tags数组vs单字段** | 产品出现一次，用`channel_tags`数组标记所有所属渠道 |
| 20 | **容量/重量限制必须读config** | 不能硬编码，config可能变化 |

### 13.3 数据质量

| # | 问题 | 说明 |
|---|------|------|
| 21 | **Amazon品类标签不准** | 评分引擎会自动校正品类 |
| 22 | **AnySearch结果含噪音** | 文章标题、编辑内容可能被误匹配为产品 |
| 23 | **单一关键词匹配太弱** | Google/Reddit要求≥2个关键词命中 |
| 24 | **季节性判断基于月份** | 不考虑具体年份事件（如世界杯） |

---

## 14. v3升级日志

### v3 vs v2 核心变化

| 项目 | v2 | v3 |
|------|----|----|
| 基础分 | 50 | **30**（更依赖正向信号） |
| 信号分类 | 简单多源计数 | **内部/外部信号投票系统** |
| 信号惩罚 | 无 | **无外部信号-15，仅Amazon-10** |
| 评分维度 | ~12个 | **18个** |
| 评论数上限 | 300 | **100**（更严格蓝海过滤） |
| 评分过滤 | 无 | **≥4.0★**（排除退货风险） |
| 市场情报 | 无 | **供需指数 + 趋势背离** |
| 品类验证 | 无 | **自动校正 + 罚分** |
| 零评论处理 | 加分 | **惩罚-15**（风险而非机会） |
| 季节性 | 简单标记 | **当季+10 / 过季-20** |

### 新增模块

1. **`scoring_engine.py`**：独立评分引擎，18维度加权评分，`WEIGHTS`字典可独立调优
2. **`market_intelligence.py`**：供需指数（ln评论数）+ 趋势背离检测（连续扫描对比）
3. **信号投票系统**：`_classify_signal_sources()` → `_get_signal_confidence()` → 4级评分
4. **品类自动校正**：`_validate_category()` → 14品类×关键词匹配 → 自动更正

### 评分引擎v3关键函数

| 函数 | 作用 |
|------|------|
| `score_product(product, trend_data, history)` | 计算单个产品评分，返回(总分, 分解字典) |
| `score_all_products(products, trend_data, history)` | 批量评分+排序 |
| `_classify_signal_sources(product)` | 将信号分为内部/外部 |
| `_get_signal_confidence(internal, external_count)` | 计算信号置信度和评分影响 |
| `_has_demand_signal(product)` | 检查是否有外部需求信号 |
| `_validate_category(product)` | 品类验证和自动校正 |
| `get_score_label(score)` | 获取评分等级标签和颜色 |

### 市场情报关键函数

| 函数 | 作用 |
|------|------|
| `analyze_market(products, trend_data, history_days)` | 完整市场分析 |
| `compute_category_supply(products)` | 计算品类供应量（评论数） |
| `compute_supply_demand_ratio(cat_reviews, trend_data)` | 计算供需比 |
| `compute_trend_divergence(trend_data, history_days)` | 检测趋势背离 |
| `get_product_sd_score(product, sd_ratios)` | 获取产品供需评分 |
| `get_product_divergence_score(product, divergences)` | 获取产品背离评分 |

---

## 附录A：AnySearch CLI路径

```python
ANYSEARCH = str(Path.home() / ".hermes/skills/search/anysearch/scripts/anysearch_cli.py")
```

调用方式：
```bash
python3 ~/.hermes/skills/search/anysearch/scripts/anysearch_cli.py \
  search "查询内容" \
  --domain ecommerce \
  --max_results 8 \
  --freshness week \
  --zone intl
```

## 附录B：关键词匹配正则模板

```python
# 词边界匹配（纯字母关键词）
pattern = r'(?<![a-z])' + re.escape(kw) + r'(?![a-z])'

# 匹配≥2个关键词才算命中
match_count = sum(1 for kw in keywords if re.search(pattern, text))
if match_count >= 2:
    # 命中
```

## 附录C：品类关键词映射（14品类）

| 品类 | 关键词 |
|------|--------|
| kitchen | kitchen, cooking, baking, utensil, gadget, spice, mug, cup, pan, pot, chop, peel, slice, grater, measuring, timer, tray, bowl, plate |
| garden | garden, outdoor, plant, flower, patio, bbq, grill, solar, bird, hose, watering, lawn, hedge, seed, pot |
| diy | diy, tool, drill, screw, nail, hammer, wrench, pliers, tape measure, level, saw, clamp, socket, hex, torx, breaker |
| sports | sport, fitness, yoga, gym, exercise, resistance, mat, dumbbell, kettlebell, band, jump rope, grip, foam roller |
| bathroom | bathroom, shower, toilet, towel, soap, mirror, bath, shaver, razor, hook, organiser, dispenser |
| cleaning | clean, mop, duster, brush, sponge, vacuum, cloth, wipe, stain, lint, lint roller |
| office | desk, office, stationery, pen, notebook, organiser, laptop, mouse, keyboard, monitor, stand, file, folder, stapler, clip |
| automotive | car, vehicle, dashboard, phone holder, motor, tyre, wheel, wiper, seat, mat, tint, winch, tow, hitch, socket, ratchet, wrench, nut, bolt, fuse, led, light, flag, motorcycle, bike |
| lighting | led, light, lamp, night light, strip, fairy, solar light, bulb, lantern |
| storage | storage, organiser, box, basket, shelf, drawer, container, bag, pouch, rack |
| crafts | craft, art, paint, brush, stickers, tape, sewing, knit, crochet, needle, thread, fabric, scissors |
| bedding | bedding, pillow, blanket, sheet, duvet, cushion, throw, mattress, sleep |
| pets | pet, dog, cat, collar, leash, bed, grooming, litter, feeder, aquarium, fish, hamster, rabbit |
| home | home, decor, wall, candle, vase, frame, mirror, clock, hook, hanger, doormat |

---

*本文档由代码实际分析生成，所有函数名、权重值、配置字段均为源码中的真实值。*
