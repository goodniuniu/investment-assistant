# 投资辅助站 · 一个零成本的 A 股学习与决策伴侣

> 一个**纯静态、可托管在 GitHub Pages** 的个人投资学习平台。  
> 后台用 GitHub Actions 每日自动抓取 A 股行情 → 规则引擎生成结构化解读 → 配对投资知识与心理提醒。  
> 面向自己的投资研究,不构成任何投资建议。

---

## ✨ 它能做什么

| 模块 | 内容 |
| :--- | :--- |
| **首页** | 当日情绪温度 · 关键信号 · 指数概览 · 心理偏差预警 |
| **行情看板** | 指数 K 线与均线 · MACD/RSI/ATR · 情绪历史曲线 · 涨跌家数 · 板块热力 · 资金/融资融券 |
| **投资知识库** | 54 个条目,覆盖估值 · 技术分析 · 宏观 · 资产配置 · 风险管理 · 行为金融 |
| **投资心理** | 10 张认知偏差卡片 · 交易前/卖前清单 · 情绪自评量表 · 决策日记 (本地存储) |
| **决策工具** | 凯利公式 · 仓位管理 · 止盈止损 · 盈亏比 · 最大回撤推算 |

每个市场信号都会**关联到对应的知识条目和心理偏差**——这正是核心设计:把数据、原理、自律串成一条线。

---

## 🚀 快速开始

### 本地预览(已经搭建好)

```bash
# 项目根目录起一个静态服务器(GitHub Pages 同源)
python -m http.server 8123
# 浏览器打开
open http://127.0.0.1:8123/
```

### 立即手动跑一次数据管线

```bash
# 节流间隔 2.5 秒,免费接口建议 ≥2 秒,避免被东财限流
python scripts/fetch_market.py --interval 2.5
```

产出:
- `data/market/latest.json` —— 当前快照(指数/K线/板块/涨停/资金)
- `data/analysis/latest.json` —— 当日解读(情绪/信号/心理提醒)
- `data/market/history/YYYY-MM.json` —— 按月归档的情绪历史

非交易日会自动跳过、**不产生空 commit**。

---

## 🏗️ 架构

```
┌─────────────────────────┐                    ┌──────────────────────────┐
│   GitHub Actions         │                    │    你的 GitHub Pages      │
│   (每日 17:30 北京时间)  │                    │    (浏览器静态托管)        │
│                          │                    │                          │
│  fetch_market.py ────────┼── push JSON ───────▶  index.html               │
│   │   ┌──────────────┐   │                    │   ├─ pages/market.html    │
│   │   │ 东方财富/     │   │                    │   ├─ pages/knowledge.html │
│   │   │ 新浪/腾讯     │   │                    │   ├─ pages/mindset.html   │
│   │   │ 备用源        │   │                    │   └─ pages/tools.html     │
│   │   └──────────────┘   │                    │                          │
│   │                       │                    │   assets/ (CSS / JS)     │
│  rules.py                │   静态读取 JSON     │   data/   (JSON 仓库)     │
│   ├─ 技术指标            │   渲染图表与解读    │                          │
│   ├─ 情绪评分 (6 维)    │                    │                          │
│   ├─ 信号识别            │                    │                          │
│   └─ 心理关联            │                    │                          │
└─────────────────────────┘                    └──────────────────────────┘
```

**为什么这样设计?** GitHub Pages 是纯静态托管,没有传统后端。零成本方案就是:`Actions 定时跑脚本 → 把数据写成 JSON 提交回仓库 → 网页读取 JSON 渲染`。

---

## 📁 目录结构

```
.
├── index.html               # 首页:市场状态+信号+心理提醒
├── pages/
│   ├── market.html          # 行情看板:K线/情绪历史/板块
│   ├── knowledge.html       # 投资知识库(54条)
│   ├── mindset.html         # 投资心理:偏差/清单/日记
│   └── tools.html           # 决策工具:计算器
├── assets/
│   ├── css/main.css         # 浅色主题,红涨绿跌(中国惯例)
│   └── js/app.js            # 公共:数据加载/格式化/SVG图表引擎
├── data/
│   ├── market/
│   │   ├── latest.json          # 当日快照(125KB,含K线)
│   │   └── history/YYYY-MM.json # 按月归档(每日轻量数据)
│   ├── analysis/
│   │   └── latest.json          # 当日完整解读(情绪/信号/心理)
│   └── content/
│       ├── knowledge.json       # 知识库(54 条目 × 11 字段)
│       └── psychology.json      # 心理模块(10 偏差 + 清单 + 量表)
├── scripts/
│   ├── fetch_market.py      # 主抓取脚本
│   ├── ai_comment.py        # 可选 AI 深度解读
│   └── lib/
│       ├── http.py              # 节流+多域名轮换+指数退避
│       ├── eastmoney.py         # 东财接口封装(每个接口可独立降级)
│       ├── indicators.py        # MA/EMA/MACD/RSI/ATR/分位数
│       └── rules.py             # 趋势/量能/宽度/情绪/信号/心理
├── .github/workflows/
│   └── daily-market.yml     # 定时工作流(每日 17:30 北京时间)
└── README.md
```

---

## ⚙️ 数据源与可降级设计

主要数据来自**东方财富公开接口**,内置**多域名轮换 + 备用源**(主要场景):

| 类别 | 主源 | 备用源 | 降级策略 |
| :--- | :--- | :--- | :--- |
| 指数实时 | push2delay.eastmoney | sina / tencent | 失败时该指数缺失 |
| 历史日K | push2his.eastmoney | web.ifzq.gtimg (腾讯) | 走备用则成交额字段为空 |
| 涨停池 | push2ex | (单源,失败则无涨停) | 跳过相关信号 |
| 板块涨跌 | datacenter-web | — | 失败则无板块热力 |
| 资金流 | push2 | (单源) | 跳过量能分量 |
| 融资融券 | 东方财富数据中心 | — | 跳过杠杆情绪 |

**核心约定:任何接口失败都不阻断主流程。** 情绪评分会自动按可用维度重新归一化权重。

---

## 🤖 可选 AI 深度解读(不配置也能跑)

未配置任何 Key 时,系统只用规则引擎,**完全可用**。

接入 Kimi 或 GLM 后,会生成"今日市场总结"长文+知识点串联。

```bash
# 1. 在 GitHub 仓库 Settings → Secrets and variables → Actions 添加:
#    AI_API_KEY   = sk-xxxxxxxxxxxxxxxx
#    AI_BASE_URL  = https://api.moonshot.cn/v1   (Kimi)
#                   或 https://open.bigmodel.cn/api/paas/v4  (智谱 GLM)
#    AI_MODEL     = moonshot-v1-8k   或   glm-4-flash

# 2. 工作流会自动调用;本地调试:
AI_API_KEY=sk-xxx AI_BASE_URL=https://api.moonshot.cn/v1 \
  AI_MODEL=moonshot-v1-8k \
  python scripts/fetch_market.py --interval 2.5
```

---

## ⏰ GitHub Pages 部署

1. 把本仓库推到 GitHub
2. Settings → Pages → Build and deployment → Source = **GitHub Actions**
3. Actions 会自动跑工作流:首次执行后 `data/analysis/latest.json` 与 `data/market/latest.json` 出现,网页立刻可访问
4. 定时任务在**每个交易日 17:30 北京时间**跑 (cron: `30 9 * * 1-5`,UTC)
5. 非交易日和失败时**不会产生空 commit**

### 手动触发 & 调试

- Actions 页 → "Daily Market Data" → Run workflow
- 加参数 `interval=3.0` 可调整节流(数据源严格时建议放宽)

---

## 📚 内容来源说明

- **行情数据**:东方财富公开行情接口,新浪财经、腾讯财经作为备用
- **技术指标与规则**:经典技术分析教材 + A 股实战经验
- **知识库**:综合 CFA/CME/行为金融经典教材
- **认知偏差**:参考 Kahneman《思考,快与慢》/Thaler《助推》

**所有内容仅供学习研究,不构成任何投资建议。**

---

## ⚠️ 免责声明

本项目所有数据来自公开第三方接口,可能存在延迟或错误。  
项目本身不收取任何费用、不提供投资建议、不承担任何投资损失责任。  
市场有风险,投资需谨慎——决策前请独立思考并咨询专业人士。

---

## 🛠️ 本地开发小贴士

```bash
# 仅看前端(不更新数据)
python -m http.server 8123

# 重新生成当前数据
python scripts/fetch_market.py --interval 2.5 --force

# 跳过 AI(默认就跳过)
python scripts/fetch_market.py --interval 2.5 --skip-ai

# 校验 JSON 与字段
python -c "import json; print(json.dumps(json.load(open('data/analysis/latest.json')), ensure_ascii=False, indent=2)[:500])"
```

数据抓取脚本在 Windows / Linux / macOS 均可运行,标准库零依赖(不引入 numpy/pandas)。
