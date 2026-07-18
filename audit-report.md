# Product Radar 项目审查报告

审查日期：2026-07-18  
审查范围：线上 GitHub Pages、Python 扫描与生成脚本、前端生成逻辑、Cloudflare Worker、GitHub Actions、依赖清单和发布脚本。

## 结论摘要

项目当前可以部署运行，但安全边界、状态同步一致性、跨平台兼容性和可维护性存在明显问题。最高优先级是：

1. 浏览器端保存 GitHub 写权限 Token，XSS 后可被窃取。
2. 外部数据被拼入 `innerHTML`、内联事件和 URL，存在存储型 XSS 风险。
3. Worker 的域名后缀校验可能接受伪造主机名。
4. 状态同步采用整份 JSON 覆盖，并发时会静默丢数据。
5. 前端把“事件已被 GitHub 接收”显示成“同步成功”，实际写入失败时用户无法感知。
6. 扫描器使用 Unix 专属 `SIGALRM`，在 Windows 上不能正常运行。

## 优先级说明

- **P0**：需要优先处理，可能导致凭据泄露、代码仓库被滥用或跨站脚本执行。
- **P1**：会造成数据丢失、错误状态或核心功能不可用，应尽快处理。
- **P2**：明确的安全、可靠性、性能或可复现性隐患。
- **P3**：工程质量和维护风险，短期不一定导致故障，但会放大后续问题。
- **P4**：低风险坏味道和清理项。

---

## P0：浏览器端将 GitHub Token 保存到 `localStorage`

位置：`generate_platform.py`，约第 458-505 行生成的前端代码。

### 问题

前端把 GitHub Token 保存到浏览器 `localStorage`，随后直接携带该 Token 请求 GitHub API 的 `repository_dispatch` 接口。

### 影响

任何能在该页面执行 JavaScript 的代码都可以读取 `localStorage` 中的 Token。可能的攻击链如下：

```text
外部数据污染或脚本注入
        -> 存储型 XSS
        -> 读取 localStorage 中的 GitHub Token
        -> 触发 GitHub Actions 或进一步滥用仓库写权限
```

实际影响取决于 Token 的权限范围，但这已经违反了高权限凭据不应暴露给长期运行的浏览器脚本这一基本原则。

### 建议

优先改为服务端代理或 GitHub App，让浏览器永远拿不到仓库写权限。

如果短期内无法重构，至少应做到：

- 使用专用、最低权限 Token；
- 设置过期时间；
- 不把 Token 持久化到 `localStorage`；
- 提供明确的清除入口；
- 限制可触发的仓库事件和输入内容；
- 记录每次同步的结果，不把 API 接收事件当成写入成功。

---

## P0：外部数据进入 HTML、内联事件和 URL，存在存储型 XSS

位置：`generate_platform.py`，约第 540-1030 行生成的页面代码。

### 问题

项目使用 `innerHTML` 和内联事件拼接产品数据，例如产品标识、产品名、图片地址、Amazon 链接、趋势词等字段会进入 HTML 属性或 JavaScript 代码。

典型模式包括：

```js
container.innerHTML = items.map(item => `...`).join('');

onclick="setSt('${value}', '${key}', this)"

href="${url}"
src="${imageUrl}"
```

项目中的 `esc()` 只适合 HTML 文本转义，不能同时保证以下语境安全：

- JavaScript 字符串；
- `onclick` 等事件属性；
- `href`、`src` 等 URL 属性；
- 模板字符串和嵌套引号。

### 影响

上游抓取数据或生成文件一旦被污染，恶意内容可能在 GitHub Pages 页面执行。结合前端 GitHub Token 问题，风险会从页面篡改升级为凭据窃取和仓库操作。

### 建议

- 删除内联 `onclick`、`onchange` 等事件属性；
- 使用 `addEventListener` 绑定事件；
- 使用 `dataset` 传递产品标识和状态键；
- 使用 DOM API 的 `textContent`、`setAttribute` 设置数据；
- 所有 URL 通过 `new URL()` 解析并校验协议和主机；
- 不要把未经校验的外部数据直接放入 `innerHTML`；
- 对输入数据做 schema 校验和长度限制；
- 增加一条带引号、反斜杠、HTML 标签和 URL 协议的回归测试。

---

## P1：Cloudflare Worker 的域名后缀判断可能被绕过

位置：`cloudflare-worker.js`，约第 20 行。

### 问题

Worker 使用类似以下逻辑判断目标主机：

```js
target.hostname.endsWith(allowedDomain)
```

单纯的字符串后缀匹配没有检查主机边界。类似 `evilamazon.co.uk` 这样的主机名可能满足 `endsWith('amazon.co.uk')`，但并不属于 Amazon。

### 影响

攻击者可能构造指向自有域名的 URL，绕过目标域名限制，让 Worker 代理请求到未授权主机。

### 建议

使用精确匹配或带点号边界的匹配：

```js
const allowed =
  hostname === 'amazon.co.uk' ||
  hostname === 'www.amazon.co.uk' ||
  hostname.endsWith('.amazon.co.uk');
```

同时应限制：

- 只允许 `https:`；
- 只允许无显式端口或端口 `443`；
- 拒绝 URL 中的用户名和密码；
- 主机名使用小写规范化后再比较；
- 路径和查询参数也进行白名单校验。

---

## P1：状态同步采用整份 JSON 覆盖，并发会丢数据

位置：`generate_platform.py` 约第 430-485 行、`.github/workflows/status-sync.yml`。

### 问题

浏览器每次修改状态时提交完整的状态对象，workflow 再把整份 JSON 写回仓库，而不是提交单个产品或单个字段的增量修改。

### 可复现的丢数据场景

```text
用户 A 基于旧状态修改产品 1
用户 B 基于同一个旧状态修改产品 2
A 写入完整 JSON
B 使用旧 JSON 覆盖 A 的完整 JSON
```

最终可能只保留 B 的修改，A 的修改会被静默覆盖。

### 建议

优先级从高到低：

1. 将同步接口改成单个产品状态的增量更新；
2. 使用当前文件 SHA 做乐观锁，SHA 变化时拒绝写入并要求重新加载；
3. workflow 配置 `concurrency`，避免同一文件并行写入；
4. 为状态文件增加 schema 版本和更新时间；
5. 为覆盖冲突记录日志并向用户明确提示。

客户端时间戳只能帮助比较数据新旧，不能代替服务端并发控制。

---

## P1：前端显示“同步成功”，但只确认了 GitHub 接收事件

位置：`generate_platform.py` 约第 460-520 行。

### 问题

前端调用 `repository_dispatch` 后，根据 API 成功响应立即显示同步成功。

但 `repository_dispatch` 的成功响应只表示 GitHub 接收了事件，不代表：

- workflow 已经启动；
- workflow 校验通过；
- commit 成功；
- push 成功；
- Pages 已完成部署；
- 后续没有被并发写入覆盖。

### 影响

用户可能看到“已同步”，刷新页面后状态却消失，形成错误的业务反馈。

### 建议

把状态拆成明确的阶段：

```text
请求已发送 -> workflow 执行中 -> 仓库写入成功 -> Pages 部署完成
```

页面至少应支持：

- 事件 ID 或请求 ID；
- workflow 执行状态查询；
- 失败提示；
- 重试；
- 写入失败时恢复或标记本地未同步状态。

---

## P1：`run_scan_v2.py` 使用 Unix 专属 `SIGALRM`

位置：`run_scan_v2.py`，约第 380-400 行。

### 问题

代码使用：

```python
signal.signal(signal.SIGALRM, handler)
signal.alarm(120)
```

`SIGALRM` 和 `signal.alarm()` 是 Unix 环境能力，Windows 不支持这套超时机制。

### 影响

扫描器在 Windows 上运行到该逻辑时会失败。当前本机 Python 启动器还存在独立的运行时启动问题，但那不是代码编译结果；即使修好 Python 环境，`SIGALRM` 仍然是跨平台缺陷。

### 建议

改用以下跨平台方案之一：

- Playwright 自带 timeout；
- `threading.Timer`；
- `concurrent.futures`；
- 将单个扫描任务放进独立进程，由父进程负责超时和回收。

如果生产环境明确只支持 Linux，应在 README、workflow 和运行检查中明确写出，不要让 Windows 用户误以为可以运行。

---

## P2：iframe 的 `error` 事件不能可靠识别 HTTP 404/500

位置：`generate_portal.py`，约第 190-220 行。

### 问题

门户通过 iframe 加载子页面，并依赖 iframe 的 `error` 事件判断加载失败。但远程服务器返回 HTTP 404 或 500 时，浏览器通常仍会触发 `load`，不一定触发 `error`。

### 影响

门户可能出现以下错误体验：

- 子页面已 404，但门户显示加载完成；
- 右侧区域空白，用户不知道是远程页面失败；
- 跨域 iframe 内部 JavaScript 报错无法被门户直接捕获。

### 建议

- 为每个子页面提供健康检查或版本探针；
- 增加加载超时；
- 在 iframe 页面内输出明确的版本和状态标识；
- 对 `load` 后的内容做可验证的成功条件判断；
- 把网络失败、HTTP 错误和页面内部错误区分展示。

---

## P2：`postMessage('*')` 缺少来源和消息内容校验

位置：`generate_platform.py` 约第 1110 行以及门户接收端。

### 问题

页面使用类似以下方式发送消息：

```js
window.parent.postMessage(
  { type: 'oa-set-height', height: measuredHeight },
  '*'
);
```

发送目标使用 `*`，接收方也没有严格验证 `event.origin`、消息类型和高度范围。

### 影响

当前消息主要用于调整 iframe 高度，直接形成高危漏洞的概率有限，但通信边界过宽，可能导致：

- 恶意父页面嵌入页面并接收消息；
- 任意页面向接收端发送伪造高度消息；
- 异常高度造成布局破坏或资源消耗。

### 建议

- 固定允许的门户 origin；
- 接收端检查 `event.origin` 和 `event.source`；
- 只接受指定消息类型；
- 要求高度是有限的正数；
- 设置合理最大高度，拒绝异常值。

---

## P2：外部链接和图片地址没有协议、主机白名单

位置：`generate_platform.py` 约第 570-800 行。

### 问题

以下数据字段会直接进入链接或图片：

- `image_url`；
- `amazon_url`；
- `amazon_search_url`；
- `search_1688_url`。

代码主要判断字段是否存在，没有充分限制协议和主机。

### 影响

恶意或异常数据可能生成：

- `javascript:` URL；
- `data:` URL；
- 任意第三方页面链接；
- 追踪或钓鱼地址；
- 不受控图片请求。

### 建议

对 URL 做统一校验，只允许明确的 HTTPS 主机。例如：

- Amazon UK 的允许主机；
- 1688 的允许主机；
- Google Trends 的允许主机；
- 图片使用允许的 CDN 或站点自身资源。

更稳妥的做法是将图片下载后存储到站点自己的静态资源目录，避免页面运行时加载任意外部地址。

---

## P2：依赖只设置最低版本，没有锁定版本和浏览器版本

位置：`requirements.txt`。

当前依赖使用类似以下下限约束：

```text
requests>=2.31.0
urllib3>=2.0.0
playwright>=1.40.0
playwright-stealth>=2.0.0
```

### 问题

没有发现 `requirements.lock`、`uv.lock` 或 `poetry.lock` 等完整锁文件，也没有看到 Python Playwright 包与 Chromium 浏览器二进制一起锁定。

### 影响

同一个 workflow 在不同日期可能安装不同版本，导致：

- 抓取行为发生变化；
- 浏览器协议不兼容；
- 反爬特征变化；
- 依赖发布破坏兼容性后，自动任务突然失败；
- 无法复现历史结果。

这不是“所有依赖都已经过时”的证据，但它是明确的可复现性和供应链管理问题。

### 建议

- 固定 Python 版本；
- 生成并提交 lockfile；
- 固定 Playwright Python 包版本；
- 固定对应浏览器版本或使用官方一致的安装步骤；
- 定期通过 Dependabot 或升级 PR 更新依赖；
- 在 CI 中增加依赖安装和扫描器启动检查。

---

## P3：多个 workflow 可能同时写同一个仓库

位置：

- `.github/workflows/status-sync.yml`；
- `.github/workflows/update-status.yml`；
- `.github/workflows/update.yml`。

### 问题

扫描、状态同步和 Pages 部署都可能产生 commit 或 push。没有统一的仓库写入队列和明确的并发策略。

### 影响

可能出现：

- push 冲突；
- 一个 workflow 覆盖另一个 workflow 的文件；
- Pages 部署拿到不一致的数据组合；
- 前端显示成功但远程 commit 失败。

### 建议

将仓库写操作集中到单一 workflow，或至少：

- 配置明确的 `concurrency.group`；
- 对同一分支的写操作串行化；
- push 失败时重新获取最新分支并做安全重试；
- 使用路径级别的写入隔离；
- 对生成数据做 schema 和完整性校验后再提交。

---

## P3：`generate_platform.py` 职责过重，安全边界难以维护

文件：`generate_platform.py`，约 1146 行。

### 问题

同一个 Python 文件同时负责：

- 数据加载；
- 状态处理；
- JSON 序列化；
- HTML 拼接；
- CSS 拼接；
- JavaScript 拼接；
- iframe 和门户逻辑；
- 状态同步交互；
- 错误和调试信息展示。

### 影响

不同输出语境混在超大字符串模板中，容易产生：

- HTML 转义和 JavaScript 转义混用；
- 修复一处逻辑时破坏另一处页面；
- 难以做单元测试；
- 难以进行安全扫描；
- 修改后只能依赖整页人工检查。

### 建议拆分

```text
data_loader.py
state_store.py
template_renderer.py
templates/platform.html
assets/platform.js
assets/platform.css
schema.py
```

数据应通过统一 JSON 序列化进入模板，页面事件和渲染逻辑放到独立 JavaScript 文件中。

---

## P3：缺失数据、抓取失败和真实数值混用

位置：`generate_platform.py` 约第 930-1030 行及相关渲染逻辑。

### 问题

部分字段在缺失时默认为空字符串或 `0`，同时页面还展示调试和错误信息。

### 影响

用户可能无法区分：

```text
真实数值为 0
没有抓到数据
抓取失败
数据尚未计算
字段不适用
```

例如利润为 `0` 与“利润计算失败”对选品判断完全不是一回事。

### 建议

统一数据 schema，至少区分：

```json
{
  "value": null,
  "status": "missing|ok|failed|not_applicable",
  "error": null
}
```

页面只在数据状态为 `ok` 时展示数值；失败和缺失使用不同的 UI 状态，不要用默认数字掩盖错误。

---

## P4：存在两套发布路径

位置：`github_api_push.py` 以及 GitHub Actions 发布流程。

### 问题

项目同时保留常规 GitHub Actions 发布和自定义 GitHub API 上传逻辑。`github_api_push.py` 的职责是绕过 `git push`，形成第二套发布机制。

### 风险

- 本地文件和远程仓库状态不一致；
- 两套认证和权限策略；
- API 上传成功但 Pages 尚未部署；
- 维护者不清楚应该使用哪条发布链路；
- 两条路径的校验规则可能不同。

### 建议

除非有明确的网络或权限约束，否则保留一条发布路径。若必须保留 API 上传脚本，应补充：

- 明确使用场景；
- dry-run；
- 文件 schema 校验；
- 幂等性；
- 远端 commit SHA 校验；
- 上传后的部署状态检查。

---

## P4：`target="_blank"` 链接未统一使用 `rel`

位置：`generate_platform.py` 约第 900-930 行及页面生成的外部链接。

### 问题

页面使用了多个 `target="_blank"` 链接，但没有统一加：

```html
rel="noopener noreferrer"
```

现代浏览器对部分场景已有默认缓解，但显式添加仍然是低成本的兼容性和安全措施。

### 建议

统一生成：

```html
<a href="..." target="_blank" rel="noopener noreferrer">...</a>
```

---

## 验证边界

本轮审查确认了源码结构、线上入口、生成器、workflow、依赖和发布脚本中的问题，但存在以下验证限制：

- 线上主页和关键静态页面可以访问；
- Git 工作区没有保留审查期间误加的代码修改；
- 没有执行 commit 或 push；
- 本机 Python 启动器指向损坏或不存在的运行时，未完成本地 Python 编译和脚本运行验证；
- `node` 不在当前 PATH，未完成 Worker JavaScript 解析验证；
- YAML 解析工具不可用，未完成 workflow 的机器解析验证；
- 因此不能声称项目“完整运行通过”，也不能把静态审查结果当成端到端测试结果。

## 推荐修复顺序

### 第一阶段：先封住高风险入口

1. 立即撤销并轮换已经在浏览器使用过的 GitHub Token；
2. 删除浏览器端仓库写权限，迁移到服务端或 GitHub App；
3. 删除内联事件和不安全的 `innerHTML` 数据注入；
4. 给所有外部 URL 增加协议和主机白名单；
5. 修复 Worker 的主机边界匹配。

### 第二阶段：修复数据一致性和自动化可靠性

1. 状态同步改为增量更新或 SHA 乐观锁；
2. 给所有仓库写 workflow 增加并发控制；
3. 把“事件已接收”和“数据已写入”分成不同状态；
4. 将 `SIGALRM` 替换成跨平台超时；
5. 增加 workflow、生成文件和 Pages 部署的失败反馈。

### 第三阶段：治理依赖和代码结构

1. 固定 Python、Playwright 和浏览器版本；
2. 生成 lockfile；
3. 拆分 `generate_platform.py`；
4. 给数据 schema 增加 `null/status/error` 语义；
5. 统一发布路径；
6. 增加静态检查、单元测试和最小端到端 smoke test。

## 最终判断

项目目前更像是一个能工作的自动化原型，而不是已经完成安全边界和可复现构建治理的生产系统。最需要优先处理的不是视觉或代码格式，而是浏览器凭据暴露、数据注入、远程写入权限和并发覆盖问题。只要这四类问题没有解决，继续扩展功能会不断放大风险和维护成本。
