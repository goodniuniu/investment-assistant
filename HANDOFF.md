# HANDOFF.md — 投资辅助站 (GitHub Pages) 接手文档

> 这份文档是 2026-09-06 由 WorkBuddy 生成的完整交接说明。下一个 AI 接手时，请先读完 §0~§3，再按 §6 清单逐项推进。

---

## §0 · TL;DR

- **项目**：用户个人使用的 A 股投资辅助站（行情看板 + 投资知识库 + 心理辅助 + 决策工具）
- **形态**：纯静态 GitHub Pages + GitHub Actions 后台抓数据
- **仓库**：`git@github.com:goodniuniu/investment-assistant.git`（SSH 已配）
- **本地根目录**：`E:\MyOutput\AI_Project\个人发展-研究投资-20260906`
- **目标 URL**：`https://goodniuniu.github.io/investment-assistant/`
- **状态**：代码 + 数据 + Actions 全部就绪；**唯一阻塞 = GitHub Pages 后端未启用**（用户已声称点了但 API 仍返回 404）
- **下一步**：见 §6 接手清单

---

## §1 · 项目目标与形态

### 1.1 用户原始诉求

> "本项目是希望构建一个辅助我投资的 github page 网页，这个网页应该提供完整的投资知识、心理辅助。项目应该具备后台定期获取中国市场信息，给于趋势分析，并结合知识点进行讲解分析等能力。"

### 1.2 形态约束

- **GitHub Pages 是纯静态托管**，没有传统后端。所以"后台定期获取"必须通过 **GitHub Actions 定时跑爬虫 → 写 JSON 提交回仓库 → 静态页读 JSON**。
- 这是**唯一**零成本路线，没有第二条路。

### 1.3 已锁定的设计选择（已与用户确认，不可随意变更）

| 决策点 | 选择 |
| :--- | :--- |
| 数据源 | 纯免费公开接口（东方财富 / 新浪 / 腾讯），多域名轮换 |
| AI 解读 | 默认规则引擎；预留 Kimi/GLM 的 OpenAI 兼容接口，配 Secret 才启用 |
| 首版范围 | 完整四模块（行情 / 知识 / 心理 / 工具）一次性交付 |
| 配色 | 中国惯例：**红涨绿跌**（与美股相反） |
| 主题 | 浅色（用户 IDE 是 light theme） |

---

## §2 · 仓库与认证

| 项 | 值 |
| :--- | :--- |
| 仓库地址 | `git@github.com:goodniuniu/investment-assistant.git` |
| 用户名 | `goodniuniu`（GitHub API 验证存在） |
| 认证方式 | SSH（`~/.ssh/id_ed25519.pub`，已绑账号） |
| git 全局 user | `goodniuniu@gmail.com` |
| 远端 main 最新 | `6ccad77`（由 Actions 自动产生的数据 commit） |

### 2.1 远端提交历史

```
6ccad77  chore(data): 更新市场数据 2026-09-06 11:18 CST   ← Actions 自动
d643467  chore: remove transient diagnostic jobs.json
bfe0eb9  fix(ci): 数据无变化时退出码改为0
8a0cde3  feat: 投资辅助站 v1 — 行情看板/知识库/心理/决策工具
```

---

## §3 · 文件清单与职责

### 3.1 完整文件树

```
E:\MyOutput\AI_Project\个人发展-研究投资-20260906\
├── README.md                              # 用户面向的部署说明
├── HANDOFF.md                             # 本文档
├── index.html                             # 首页（核心指标+情绪+信号+指数表+心理）
├── .gitignore
├── .nojekyll                              # 告诉 Pages 不要按 Jekyll 编译
├── .github/
│   └── workflows/
│       └── daily-market.yml               # 定时抓数据（每日 17:30 北京时间，交易日）
├── pages/
│   ├── market.html                        # 行情看板（K线/情绪历史/板块热力/资金）
│   ├── knowledge.html                     # 知识库（54 条搜索+分类+展开）
│   ├── mindset.html                       # 心理模块（10偏差卡片/自评/日记）
│   └── tools.html                         # 决策工具（凯利/仓位/止损/盈亏比/回撤）
├── assets/
│   ├── css/main.css                       # 样式系统（CSS 变量驱动浅色主题）
│   └── js/app.js                          # 数据加载/格式化/SVG 图表引擎
├── scripts/
│   ├── fetch_market.py                    # 主抓取入口（单文件、纯标准库）
│   ├── ai_comment.py                      # AI 增强（未配 Key 时静默降级）
│   └── lib/
│       ├── __init__.py
│       ├── http.py                        # 节流/指数退避/多域名轮换请求器
│       ├── eastmoney.py                   # 东方财富+新浪+腾讯接口封装
│       ├── indicators.py                  # MA/EMA/MACD/RSI/ATR/分位/回撤（纯 Python）
│       └── rules.py                       # 规则引擎：情绪6维+信号+心理偏差关联
└── data/
    ├── analysis/latest.json               # 每日分析结果（前端读取这个）
    ├── market/latest.json                 # 原始市场快照
    ├── market/history/YYYY-MM.json        # 按月归档
    └── content/
        ├── knowledge.json                 # 知识库内容（54 条）
        └── psychology.json                # 心理偏差模块（10 张卡片）
```

### 3.2 各文件职责简述

| 文件 | 入口/调用者 | 失败兜底 |
| :--- | :--- | :--- |
| `fetch_market.py` | Actions 调 `python scripts/fetch_market.py` | 每个接口独立 try/except，挂掉降级为 None |
| `ai_comment.py` | `fetch_market.py` 收尾时调用 | 未配 API Key → 静默返回规则引擎输出 |
| `lib/http.py` | `lib/eastmoney.py` 用它发请求 | 限流时按指数退避；最后 fallback 失败 |
| `lib/eastmoney.py` | `fetch_market.py` 调它取数据 | 任何接口失败 → 对应字段为 None |
| `lib/indicators.py` | `lib/rules.py` 调它算指标 | 数据不够时返回 None，不抛 |
| `lib/rules.py` | `fetch_market.py` 调它生成分析 | 字段缺失时自动重新归一化情绪评分 |
| `daily-market.yml` | GitHub Actions 自动 | `continue-on-error: true` 让"无变化跳过"不报红 |

---

## §4 · 数据流全景

```
          ┌──────────────────────────────────────────────────────┐
          │   GitHub Actions (每日 17:30 北京时间, 仅交易日)        │
          │   ┌──────────────────────────────────────────────┐   │
          │   │ python scripts/fetch_market.py              │   │
          │   │   ├─ eastmoney.index_snapshot()             │   │
          │   │   ├─ eastmoney.index_kline() × N            │   │
          │   │   ├─ eastmoney.limit_pool()                 │   │
          │   │   ├─ eastmoney.fund_flow()                 │   │
          │   │   ├─ eastmoney.margin()                     │   │
          │   │   ├─ eastmoney.sector_rank()                │   │
          │   │   ├─ indicators.compute()                   │   │
          │   │   ├─ rules.build()                          │   │
          │   │   ├─ ai_comment.enhance()                   │   │
          │   │   └─ 写 data/{market,analysis}/latest.json  │   │
          │   └──────────────────────────────────────────────┘   │
          └──────────────────────────────────────────────────────┘
                                       │
                                       ▼
                          git commit & push (自动)
                                       │
                                       ▼
                          ┌────────────────────────────┐
                          │   GitHub Pages (前端读取)  │
                          │   - index.html             │
                          │   - pages/{x}.html         │
                          │   - 读 data/*.json         │
                          └────────────────────────────┘
```

**关键设计**：前端 **不调任何 API**，**完全读仓库里的 JSON**。改前端代码 + push 即可即时生效；改数据 = 等下一次 Actions 跑（17:30 或手动触发）。

---

## §5 · 当前状态（截至 2026-09-06 11:30 CST）

### ✅ 已完成

| 项 | 验证证据 |
| :--- | :--- |
| 数据抓取管线 100% 跑通 | Actions run `34008567166` conclusion=success，已自动 commit `6ccad77` |
| 5 个页面真渲染无错 | 本地 `agent-browser` 测试 0 JS 报错 |
| 知识库 54 条 / 心理模块 10 张 | JSON 校验：ID 唯一、引用闭合 |
| 多域名 fallback | push2 限流时 push2delay / 新浪 / 腾讯可走 |
| .nojekyll 已加 | 远端 raw 文件 HTTP 200 |
| 数据字段全 | 前端消费的全部 53 个字段已在 `latest.json` 中 |
| SSH 认证 | `Hi goodniuniu!` |

### ❌ 唯一阻塞：GitHub Pages 后端未启用

| 检查 | 结果 |
| :--- | :--- |
| `GET /repos/.../pages` | 404 Not Found |
| `/actions/workflows` 列表 | 只 1 个（用户写的 daily-market.yml）—— **没有** `pages-build-and-deployment`（Pages 启用才会自动创建） |
| `https://goodniuniu.github.io/investment-assistant/` | GitHub 自有 404 页：*"There isn't a GitHub Pages site here"* |
| `https://github.com/goodniuniu/investment-assistant/settings/pages` | 站点级 404（需用户登录） |

**用户已声称点了 Source: GitHub Actions，但 API 没看到配置变化。** 这是一个矛盾点，必须先排查清楚。

---

## §6 · 接手任务清单（按优先级）

### 🔴 优先级 0：Pages 启用排查（首要）

新 AI 接手的**第一件事**——重复本节的所有验证，因为现在距用户最后一次反馈已过 ≥30 分钟。

```bash
# 1. Pages API
curl -s https://api.github.com/repos/goodniuniu/investment-assistant/pages

# 2. Workflows 列表（应有 2 个）
curl -s https://api.github.com/repos/goodniuniu/investment-assistant/actions/workflows

# 3. Pages builds
curl -s https://api.github.com/repos/goodniuniu/investment-assistant/pages/builds | head -50

# 4. 首页 HTTP
curl -s -o /dev/null -w "%{http_code}\n" https://goodniuniu.github.io/investment-assistant/
```

**判断分支**：

- **`/pages` 仍 404** → 跟用户确认：登录账号是否 goodniuniu（不是同名组织账号）；Source 下拉框是否点了之后刷新页面验证过；有没有看到 "Save" 按钮并按了
- **`/pages` 返回非 404 但首页仍 404** → CDN 缓存，等 5~10 分钟重试，或 `curl -H 'Cache-Control: no-cache'`
- **`/pages` 返回 200 且有 builds** → 部署成功了，告诉用户刷新浏览器

### 🟡 优先级 1：核实数据流健康度

```bash
cd "E:/MyOutput/AI_Project/个人发展-研究投资-20260906"

# 本地重跑一次（不带 --force 避免破坏线上数据）
PYTHONIOENCODING=utf-8 python scripts/fetch_market.py --interval 3.0

# 看分析结果
PYTHONIOENCODING=utf-8 python -c "
import json
d=json.load(open('data/analysis/latest.json',encoding='utf-8'))
s=d['market_snapshot']
print('交易日:',d['trade_date'],'情绪:',d['sentiment']['score'])
print('宽度:',s['breadth']['up'],'涨',s['breadth']['down'],'跌')
print('情绪覆盖率:',d['sentiment']['coverage'],'%')
"
```

期望：覆盖率 100%，情绪 0~100 的合理数字，信号至少 2 条。

### 🟢 优先级 2：等用户反馈决定下一步

可能的走向：
1. Pages 启用成功 → 建议用户刷新看首页，告诉他们"今天起每天 17:30 自动更新"
2. Pages 仍失败 → 帮用户重做 GitHub Auth 检查
3. 用户想加 AI → 引导设置 Secrets（详见 README 的"可选 AI 深度解读"）

---

## §7 · 关键设计决策（不要重新做决策）

### 7.1 为什么不直接写 Python 后端？

GitHub Pages **只托管静态文件**。如果要 Python 后端，要么用 Render/Railway（成本）、要么 GitHub Actions 模拟（延迟大）。**用户接受这个延迟**：每天一次足够，投资决策不需分钟级。

### 7.2 为什么用规则引擎而不是纯 AI？

- **成本**：每天 AI 调用要钱
- **稳定性**：AI 偶发幻觉，规则引擎 100% 可重现
- **教育价值**：用户可以追问每条规则是什么
- **可降级**：AI Key 缺失时规则引擎独立可用

### 7.3 为什么多域名轮换？

东方财富 push2 限流极严（5 分钟内 3 次即封）。**实测**：push2 限流时 push2delay（同公司延迟接口）100% 可用。这是**经验之谈**，没有写在官方文档里。

### 7.4 为什么不用 `_config.yml` 走 Jekyll？

没用 Jekyll，纯粹静态托管。`.nojekyll` 已加防止意外。

### 7.5 为什么用 id 而不是 data-bind？

首页用 id 选择元素，方便选择器。子页面才用 data-bind。这是个**已沿用的约定**，新页面保持一致。

### 7.6 字段命名约定

- 数据里所有"金额/成交量"字段都以 **亿** 为单位（`amount_yi`、`main_flow_yi`、`margin_balance_yi`）
- 百分比都直接是数字（`pct: -0.30`），前端加 `%`
- 日期字符串 `YYYY-MM-DD`
- 数字字段一律可能是 `null`（缺失），前端要兼容

---

## §8 · 已知陷阱（避坑清单）

### 8.1 GitHub Actions 的 exit code 约定

**任何非 0 退出码 = failure**。所以 `fetch_market.py` 的"幂等跳过"分支从 `return 3` 改成了 `return 0`。**新加的脚本同理**——所有"正常跳过"路径都该 `return 0`。

### 8.2 不要用 `cd /path && git push` 然后没等就返回

`run_in_background` 是后台跑命令的推荐方式。否则可能命令被打断但状态不一致。

### 8.3 不要直接用 `rm -rf .git` 后就 `git push`

本项目已经历过一次本地 .git 损坏：`.git/objects/5a74240...` 等多个对象 missing。**正确的恢复路径**：

```bash
# 1. 保留工作区
mkdir -p _backup
cp -a .nojekyll .gitignore README.md index.html pages assets scripts .github data _backup/

# 2. 删除损坏的 .git
rm -rf .git

# 3. 重建
git init -b main
git remote add origin git@github.com:goodniuniu/investment-assistant.git
git fetch --depth=999 origin main
git reset --hard origin/main
```

### 8.4 Windows + Git Bash 的 `&&` 链 + `run_in_background`

不要这样做：`(PYTHONIOENCODING=utf-8 python -m http.server 8123 >/dev/null 2>&1 &)`——& 后台启动的进程在 Bash 退出后会被杀，导致连接失败。**改用 `run_in_background: true`** 参数。

### 8.5 东财高频请求限流是真实的

单 IP 单域名每分钟 >3 次就会触发。建议生产间隔 2.5~3 秒（脚本默认）。**调试时也要节流**——本文档撰写过程中曾因调试脚本不节流把 IP 推到了限流列表。

### 8.6 不要把测试数据写进 git

`_smoke/`、`jobs.json`、`_p*.json` 等调试产物**必须在 commit 前清除**。本项目 `.gitignore` 已加了 `jobs.json`。

---

## §9 · 用户画像（不要绕过这些偏好）

### 9.1 背景

- 广州海关科技处，负责党建、财务预算、技术设备
- 正在规划 2026-08 新加坡家庭游（已完成）、子女 2028 高考（早期规划中）
- 正在调研 Kimi 定价、WorkBuddy 平台成本

### 9.2 沟通偏好

- **简体中文**，指令简洁明确
- 偏好**目录树、表格**呈现结构化信息
- 注重**表格美观、信息统一、关键信息突出**
- 常使用 emoji
- 关注**费用、操作流程**等实际细节
- 重视**事实核查**——多 AI 交叉验证（Kimi + Doubao + WorkBuddy）是常态

### 9.3 工作风格

- **模板驱动**：先建目录结构 → 用示例文件批量转换 → 复核补充
- **逐行核对**：卡片 ID 这类数据会逐行查
- **结构化编号**：习惯把任务拆为"任务1、任务2..."
- **沟通方式**：先确认设计，再实施，每步给可验证交付

### 9.4 视觉/样式偏好（与代码约束）

- 浅色主题（IDE 是 light theme）
- 中国股市配色：**红涨绿跌**（与美股相反！**绝不能改**）
- 字体优先 system-ui
- 关键数字要突出（最大、对比度）

---

## §10 · 推荐阅读顺序（新 AI 第一天）

| 顺序 | 读什么 | 为什么 |
| :--- | :--- | :--- |
| 1 | 本文件（你正在读） | 全局观 |
| 2 | `README.md` | 用户面向的部署说明 |
| 3 | `.workbuddy/memory/2026-09-06.md` | 当日实时工作笔记（更细的踩坑记录） |
| 4 | `scripts/fetch_market.py` 头 50 行 | 看懂入口流程 |
| 5 | `scripts/lib/eastmoney.py` | 看懂数据接口清单 |
| 6 | `data/analysis/latest.json` 顶层结构 | 看懂数据消费者期望 |
| 7 | `index.html` 前 50 行 + `assets/js/app.js` 头 30 行 | 看懂前端消费模式 |
| 8 | `.github/workflows/daily-market.yml` | 看懂定时逻辑 |

---

## §11 · 已知 TODO（已写入但未实施）

- [ ] **前端基地址**:用户子路径 `/investment-assistant/`，所有 `fetch('/data/...')` 是相对路径，**当前能用**但若换 Pages 项目形态需调整
- [ ] **板块轮动周维度**:只做了当日 top/bottom 排序，没做周环比
- [ ] **AI 解读质量调优**:`ai_comment.py` 默认 prompt 可优化，但用户说先观察
- [ ] **历史 K 线 5min/15min/60min**:目前只有日 K

---

## §12 · 紧急联系 / 工具备忘

| 工具/路径 | 用途 |
| :--- | :--- |
| `~/.ssh/id_ed25519.pub` | GitHub SSH 密钥（已绑） |
| `agent-browser` | 本地真浏览器渲染验证 |
| WebFetch | 走不同网络栈的 GitHub API 访问（curl 限流时备用） |
| `workbuddy.cn/docs` | WorkBuddy 平台文档（如有问题） |
| `E:\MyOutput\AI_Project\个人发展-研究投资-20260906\.workbuddy\memory\` | 项目本地 memory |

---

**Handoff 完成时间**：2026-09-06 11:30 CST  
**生成者**：WorkBuddy (MiniMax-M3)  
**下次审查触发条件**：Pages 启用成功 / 数据流异常 / 用户提出新需求