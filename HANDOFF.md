# HANDOFF.md — 投资辅助站 (GitHub Pages) 接手文档

> 本文档最初由 WorkBuddy 于 2026-09-06 生成，**2026-09-20 由 Kimi Work 全面核实刷新**（路径迁移、Pages 阻塞已解决、三层架构落地）。
> 下一个 AI 接手时，请先读完 §0~§3，再按 §6 清单逐项推进。

---

## §0 · TL;DR

- **项目**：用户个人使用的 A 股投资辅助站（行情看板 + 投资知识库 + 心理辅助 + 决策工具 + 复盘比对 + 书单）
- **形态**：纯静态 GitHub Pages + GitHub Actions 后台抓数据，前端零 API 调用、只读仓库 JSON
- **仓库**：`git@github.com:goodniuniu/investment-assistant.git`（SSH 已配）
- **本地根目录**：`E:\Github\investment-assistant` ⚠️（旧文档写的 `E:\MyOutput\AI_Project\个人发展-研究投资-20260906` 已废弃）
- **线上 URL**：`https://goodniuniu.github.io/investment-assistant/`（**已正常访问，全站 200**）
- **状态**：✅ 数据管线每日自动运行正常（最新数据 2026-09-18）；✅ pytest 25 用例全过；✅ 页面共 8 个、导航 8 项
- **下一步**：见 §6 当前优先事项

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
| 配色 | 中国惯例：**红涨绿跌**（与美股相反） |
| 主题 | 浅色（用户 IDE 是 light theme） |
| 内容规模 | 知识库 54 条 / 心理偏差 10 张卡片 / 书单 50 本 × 9 方向 |

---

## §2 · 仓库与认证

| 项 | 值 |
| :--- | :--- |
| 仓库地址 | `git@github.com:goodniuniu/investment-assistant.git` |
| 用户名 | `goodniuniu`（GitHub API 验证存在） |
| 认证方式 | SSH（`~/.ssh/id_ed25519.pub`，已绑账号） |
| git 全局 user | `goodniuniu@gmail.com` |
| 远端 main 最新（2026-09-20 核查） | `b2c1b3d`（Actions 自动产生的数据 commit） |

### 2.1 近期提交历史（2026-09-20 核查）

```
b2c1b3d  chore(data): 更新市场数据 2026-09-18 22:38 CST   ← Actions 自动
814c90e  chore(data): 更新市场数据 2026-09-17 23:16 CST
66f825b  chore(data): 更新市场数据 2026-09-16 23:11 CST
4189596  chore(data): 更新市场数据 2026-09-15 23:15 CST
```

> 数据 commit 由 `daily-market.yml` 每个交易日自动产生；代码 commit 穿插其间，用 `git log --oneline` 查看全量。

---

## §3 · 文件清单与职责

### 3.1 完整文件树（2026-09-20 按磁盘实测）

```
E:\Github\investment-assistant\
├── README.md                              # 用户面向的项目说明
├── HANDOFF.md                             # 本文档
├── index.html                             # 首页（核心指标+情绪+信号+指数表+心理+新鲜度横幅）
├── .gitignore
├── .nojekyll                              # 告诉 Pages 不要按 Jekyll 编译
├── _pages_enable_result.txt               # 历史遗留调试产物（Pages API 403 记录），可删
├── .github/
│   └── workflows/
│       ├── daily-market.yml               # 定时抓数据（每日 17:30 北京时间，交易日）
│       ├── deploy-pages.yml               # push 到 main 即部署 Pages（含每日数据 commit）
│       └── ci.yml                         # push/PR 时跑 pytest + 脚本语法检查
├── pages/
│   ├── market.html                        # 行情看板（K线/情绪历史/板块热力/资金/宽基对照）
│   ├── knowledge.html                     # 知识库（54 条搜索+分类+展开+间隔复习）
│   ├── mindset.html                       # 心理模块（10偏差卡片/自评/日记）
│   ├── tools.html                         # 决策工具（凯利/仓位/止损/盈亏比/回撤）
│   ├── review.html                        # 复盘比对（信号×实际+5/+20日、规则战绩榜、情绪极端组）
│   ├── books.html                         # 书单（50 本 × 9 方向，导读/要点/上站实践指引）
│   └── mydata.html                        # 我的数据（本地存储统一导出/导入/清除）
├── assets/
│   ├── css/main.css                       # 样式系统（CSS 变量驱动浅色主题）
│   └── js/app.js                          # 数据加载/格式化/SVG 图表引擎
├── scripts/
│   ├── fetch_market.py                    # 主抓取入口（单文件、纯标准库）
│   ├── backfill_analysis.py               # 离线回填 analysis/history（已回填 91 个交易日）
│   ├── ai_comment.py                      # AI 增强（未配 Key 时静默降级）
│   └── lib/
│       ├── __init__.py
│       ├── http.py                        # 节流/指数退避/多域名轮换请求器
│       ├── eastmoney.py                   # 东方财富+新浪+腾讯接口封装
│       ├── indicators.py                  # MA/EMA/MACD/RSI/ATR/分位/回撤（纯 Python）
│       └── rules.py                       # 规则引擎：情绪6维+信号+心理关联+RULES_META(22条)
├── tests/                                 # pytest 25 用例（CI 强制跑）
│   ├── test_data_files.py                 # JSON 结构校验（知识/心理/书单引用闭合）
│   ├── test_indicators.py                 # 指标黄金用例
│   └── test_rules.py                      # 规则引擎用例
└── data/
    ├── analysis/latest.json               # 每日分析结果（前端读取这个，含 rules_meta）
    ├── analysis/history/YYYY-MM.json      # 分析留痕，按月归档（2026-04 ~ 2026-09，供 review.html）
    ├── market/latest.json                 # 原始市场快照
    ├── market/history/YYYY-MM.json        # 按月归档（当前为 2026-09.json）
    ├── meta/status.json                   # 新鲜度哨兵（last_success_at/ok/errors，首页 >10 天横幅）
    └── content/
        ├── knowledge.json                 # 知识库内容（54 条）
        ├── psychology.json                # 心理偏差模块（10 张卡片 + 清单 + 量表）
        └── books.json                     # 书单（50 本，关联知识条目 id，有 pytest 校验）
```

### 3.2 各文件职责简述

| 文件 | 入口/调用者 | 失败兜底 |
| :--- | :--- | :--- |
| `fetch_market.py` | Actions 调 `python scripts/fetch_market.py` | 每个接口独立 try/except，挂掉降级为 None |
| `ai_comment.py` | `fetch_market.py` 收尾时调用 | 未配 API Key → 静默返回规则引擎输出 |
| `backfill_analysis.py` | 手动离线回填历史分析 | 幂等，已回填样本标 `backfilled` 与实时区分 |
| `lib/http.py` | `lib/eastmoney.py` 用它发请求 | 限流时按指数退避；最后 fallback 失败 |
| `lib/eastmoney.py` | `fetch_market.py` 调它取数据 | 任何接口失败 → 对应字段为 None |
| `lib/indicators.py` | `lib/rules.py` 调它算指标 | 数据不够时返回 None，不抛 |
| `lib/rules.py` | `fetch_market.py` 调它生成分析 | 字段缺失时自动重新归一化情绪评分 |
| `daily-market.yml` | GitHub Actions 自动（交易日 17:30） | `continue-on-error: true` 让"无变化跳过"不报红 |
| `deploy-pages.yml` | push 到 main 自动部署 | `concurrency: pages` 防并发部署 |
| `ci.yml` | push/PR 自动 | 25 个 pytest 用例 + py_compile，失败即红 |

---

## §4 · 数据流全景

```
          ┌──────────────────────────────────────────────────────┐
          │   GitHub Actions (每日 17:30 北京时间, 仅交易日)        │
          │   ┌──────────────────────────────────────────────┐   │
          │   │ python scripts/fetch_market.py              │   │
          │   │   ├─ eastmoney.index_snapshot()             │   │
          │   │   ├─ eastmoney.index_kline() × 5 (沪深300/   │   │
          │   │   │   上证/深成/中证500/科创50)              │   │
          │   │   ├─ eastmoney.limit_pool()                 │   │
          │   │   ├─ eastmoney.fund_flow()                  │   │
          │   │   ├─ eastmoney.margin()                     │   │
          │   │   ├─ eastmoney.sector_rank()                │   │
          │   │   ├─ indicators.compute()                   │   │
          │   │   ├─ rules.build()  (含 RULES_META 22条)    │   │
          │   │   ├─ ai_comment.enhance()                   │   │
          │   │   ├─ 写 data/{market,analysis}/latest.json  │   │
          │   │   ├─ 追加 data/analysis/history/YYYY-MM.json│   │
          │   │   └─ 写 data/meta/status.json (新鲜度哨兵)  │   │
          │   └──────────────────────────────────────────────┘   │
          └──────────────────────────────────────────────────────┘
                                       │
                                       ▼
                          git commit & push (自动)
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
     ci.yml (pytest×25)      deploy-pages.yml           GitHub Pages
     测试与数据校验           部署站点产物              前端 8 页读 data/*.json
```

**关键设计**：前端 **不调任何 API**，**完全读仓库里的 JSON**。改前端代码 + push 即可即时生效（deploy-pages.yml 自动部署）；改数据 = 等下一次 Actions 跑（17:30 或手动触发）。

**本地持久化**（不经过 git）：决策日记 `invest_journal`、偏差自查 `invest_bias_checked`、交易清单 `invest_checklist`、知识复习 `invest_kb_review`（SM-2 简化 7 档）、阅读状态 `invest_books_status`——统一在 `pages/mydata.html` 导出/导入/清除。决策日记保存时会快照当日市场数据，供复盘比对。

---

## §5 · 当前状态（截至 2026-09-20 核查）

### ✅ 健康度结论（本次逐一实测）

| 项 | 结果 | 验证方式 |
| :--- | :--- | :--- |
| 数据管线 | ✅ 每日自动运行正常，最新数据 commit 至 **2026-09-18** | `git log` + `data/meta/status.json`（`ok: true`，errors 空，情绪 67.7） |
| 测试 | ✅ **pytest 25 用例全过** | 本地 `python -m pytest` 实测 `25 passed` |
| 线上站点 | ✅ 首页 + 全部 7 个子页 **HTTP 200** | curl 逐个实测 8 个 URL |
| 页面/导航 | ✅ 8 项：首页 + market/knowledge/mindset/tools/review/books/mydata | 磁盘 + 线上双重核实 |
| 内容规模 | ✅ 知识 54 条 / 心理 10 卡 / 书单 50 本 × 9 方向 | JSON 实测计数 |

### 📜 历史沿革（旧阻塞均已解决，仅留注记）

- **Pages 未启用阻塞（2026-09-06 已解决）**：根因是 Pages Source 选了 GitHub Actions 但仓库没有部署 workflow；修复 = 新增 `deploy-pages.yml`（push 即部署）。曾尝试的 `enable-pages.yml`（GITHUB_TOKEN 调 Pages API）会 403，已删除；`gh-pages` 分支已清理。`_pages_enable_result.txt` 是当时的调试残留。
- **全项目代码审查（2026-09-06 已解决）**：修复 12 项缺陷（P1×4：跌停 20cm 双重计数、risk_level 对 0 值误判、市场宽度图双轴失真、心理自评未归一化；P2×8 略）。部署 commit `e12ae6e`。
- **三层架构升级（2026-09-06 完成）**：从"每日评论生成器"升级为"理论学习实践比对平台"——`analysis/history/` 每日留痕 + `backfill_analysis.py` 回填 91 个交易日 + `meta/status.json` 新鲜度哨兵 + `ci.yml` 测试门禁 + `review.html` 信号复盘 + 知识库间隔复习 + `mydata.html` 本地数据管理。回填样本标 `backfilled`。
- **书单子栏目（2026-09-06 完成）**：`books.html` + `books.json`（50 本，每本含上站实践指引与知识条目关联，引用闭合有 pytest 校验）。
- 复盘基线：当时总体信号命中率约 32%（真实数据，规则并非都靠谱——这正是比对平台的意义）。

---

## §6 · 当前优先事项（给下一个 AI）

### 🔴 P0：正在进行的迭代（接续推进）

- [ ] **个人决策复盘深化**：`review.html` 已有信号×实际比对与规则战绩榜；决策日记已带市场快照。下一步方向：把用户自己的日记决策也纳入命中率统计（目前是规则信号维度的复盘，个人维度只做了一半）。
- [ ] **知识实例关联**：书单已关联知识条目 id（引用闭合）。下一步方向：反向打通——知识条目页显示"哪些书讲过这条"、信号触发时推荐相关书目章节，让"数据→原理→书单"闭环。

### 🟡 P1：已识别 TODO（沿用 §11，未动工）

1. **板块轮动周维度**：目前只有当日 top/bottom 排序，没做周环比。
2. **AI 解读 prompt 调优**：`ai_comment.py` 默认 prompt 可优化——用户此前说先观察，动手前先确认。
3. **分钟级 K 线（5min/15min/60min）**：目前只有日 K。

### 🟢 P2：日常健康检查（任何时候接手都可先跑一遍）

```bash
cd "E:/Github/investment-assistant"

# 1. 测试门禁
python -m pytest -q        # 期望 25 passed

# 2. 数据新鲜度
python -c "import json; print(json.load(open('data/meta/status.json',encoding='utf-8')))"

# 3. 线上抽查
curl -s -o /dev/null -w "%{http_code}\n" https://goodniuniu.github.io/investment-assistant/

# 4. 本地重跑管线（不带 --force 避免破坏线上数据；注意节流 ≥2.5s）
PYTHONIOENCODING=utf-8 python scripts/fetch_market.py --interval 3.0
```

期望：`status.json` 的 `ok: true` 且 `trade_date` 为最近交易日；线上 200；本地重跑后情绪覆盖率 100%、信号至少 2 条。

---

## §7 · 关键设计决策（不要重新做决策）

### 7.1 为什么不直接写 Python 后端？

GitHub Pages **只托管静态文件**。如果要 Python 后端，要么用 Render/Railway（成本）、要么 GitHub Actions 模拟（延迟大）。**用户接受这个延迟**：每天一次足够，投资决策不需分钟级。

### 7.2 为什么用规则引擎而不是纯 AI？

- **成本**：每天 AI 调用要钱
- **稳定性**：AI 偶发幻觉，规则引擎 100% 可重现
- **教育价值**：用户可以追问每条规则是什么（22 条规则的假设/适用环境已通过 `RULES_META` 随 latest.json 下发）
- **可降级**：AI Key 缺失时规则引擎独立可用

### 7.3 为什么多域名轮换？

东方财富 push2 限流极严（5 分钟内 3 次即封）。**实测**：push2 限流时 push2delay（同公司延迟接口）100% 可用。这是**经验之谈**，没有写在官方文档里。

### 7.4 为什么不用 `_config.yml` 走 Jekyll？

没用 Jekyll，纯粹静态托管。`.nojekyll` 已加防止意外。部署走 `deploy-pages.yml` 的 `actions/upload-pages-artifact` + `actions/deploy-pages`，不是 Jekyll 流水线。

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

### 8.2 东财高频请求限流是真实的

单 IP 单域名每分钟 >3 次就会触发。建议生产间隔 2.5~3 秒（脚本默认）。**调试时也要节流**——曾因调试脚本不节流把 IP 推到了限流列表。

### 8.3 不要把测试数据写进 git

`_smoke/`、`jobs.json`、`_p*.json` 等调试产物**必须在 commit 前清除**。`_pages_enable_result.txt` 是历史残留（Pages API 403 的调试记录），留着无害、删了也行。

### 8.4 本地 .git 损坏的恢复路径（本项目经历过一次）

```bash
# 1. 保留工作区
mkdir -p _backup
cp -a .nojekyll .gitignore README.md index.html pages assets scripts tests .github data _backup/

# 2. 删除损坏的 .git
rm -rf .git

# 3. 重建
git init -b main
git remote add origin git@github.com:goodniuniu/investment-assistant.git
git fetch --depth=999 origin main
git reset --hard origin/main
```

### 8.5 Windows + Git Bash 的后台进程

`(python -m http.server 8123 &)` 这类后台启动的进程在 Bash 退出后会被杀，导致连接失败。需要后台任务时使用 Agent 工具的 `run_in_background: true` 参数。

### 8.6 港美股接口实测不可用

KLINE_TARGETS 曾尝试扩港美股，公开免费接口实测不可用，最终只扩到 5 个 A 股指数（沪深300/上证/深成/中证500/科创50）。别再踩一遍。

---

## §9 · 用户画像（不要绕过这些偏好）

### 9.1 背景

- 广州海关科技处，负责党建、财务预算、技术设备
- 子女 2028 高考（早期规划中）
- 关注 Kimi 等 AI 平台的定价与成本

### 9.2 沟通偏好

- **简体中文**，指令简洁明确
- 偏好**目录树、表格**呈现结构化信息
- 注重**表格美观、信息统一、关键信息突出**
- 常使用 emoji
- 关注**费用、操作流程**等实际细节
- 重视**事实核查**——多 AI 交叉验证是常态

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
| 2 | `README.md` | 用户面向的项目说明 |
| 3 | `scripts/fetch_market.py` 头 50 行 | 看懂入口流程 |
| 4 | `scripts/lib/eastmoney.py` | 看懂数据接口清单 |
| 5 | `scripts/lib/rules.py` | 看懂规则引擎 + RULES_META |
| 6 | `data/analysis/latest.json` 顶层结构 | 看懂数据消费者期望 |
| 7 | `index.html` 前 50 行 + `assets/js/app.js` 头 30 行 | 看懂前端消费模式 |
| 8 | `.github/workflows/` 三个 yml | 看懂定时/部署/CI 逻辑 |
| 9 | `tests/` 三个测试文件 | 改代码前先看约束 |

---

## §11 · 已知 TODO（与 §6 联动）

- [ ] **前端基地址**：用户子路径 `/investment-assistant/`，所有 `fetch('/data/...')` 是相对路径，**当前能用**但若换 Pages 项目形态需调整
- [ ] **板块轮动周维度**：只做了当日 top/bottom 排序，没做周环比
- [ ] **AI 解读质量调优**：`ai_comment.py` 默认 prompt 可优化，但用户说先观察
- [ ] **历史 K 线 5min/15min/60min**：目前只有日 K
- [ ] **个人决策复盘**：日记快照已存，命中率统计待做（进行中）
- [ ] **知识实例关联**：书单→知识已闭合，知识→书单/信号→书目反向打通待做（进行中）

---

## §12 · 工具备忘

| 工具/路径 | 用途 |
| :--- | :--- |
| `~/.ssh/id_ed25519.pub` | GitHub SSH 密钥（已绑） |
| `python -m http.server 8123` | 本地静态预览（GitHub Pages 同源） |
| `python -m pytest -q` | 本地测试门禁（25 用例，改代码/数据后必跑） |
| GitHub API `repos/goodniuniu/investment-assistant/...` | 查 Actions run / workflows / Pages 状态 |
| `curl -s -o /dev/null -w "%{http_code}" <url>` | 线上页面抽查 |

---

**交接刷新时间**：2026-09-20（按磁盘与线上实测核实）  
**本次生成者**：Kimi Work  
**原始版本**：2026-09-06 by WorkBuddy  
**下次审查触发条件**：数据流异常 / 测试失败 / 用户提出新需求
