# -*- coding: utf-8 -*-
"""
AI 增强解读（可选）。

在 GitHub Actions 中配置以下 Secrets 即自动启用；未配置时静默返回原分析，不影响主流程。
    AI_API_KEY   必填，Kimi(Moonshot) 或 GLM(智谱) 的 API Key
    AI_BASE_URL 选填，默认 Kimi：https://api.moonshot.cn/v1
                 GLM 填：https://open.bigmodel.cn/api/paas/v4
    AI_MODEL    选填，默认 moonshot-v1-8k（GLM 可用 glm-4-flash）

所有厂商均采用 OpenAI 兼容的 /chat/completions 协议，因此一套代码通用。
"""

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "moonshot-v1-8k"
TIMEOUT = 90

SYSTEM_PROMPT = """你是一位严谨的 A 股市场投资教育者，服务对象是正在学习投资的个人投资者。

你的输出必须遵守以下铁律：
1. 绝不推荐任何具体股票、基金代码或买卖点位。
2. 不预测明日涨跌，不给出"必涨/必跌"结论。
3. 重点解释"市场正在发生什么""这类情形历史上通常意味着什么""此时最该注意的风险与纪律"。
4. 承认不确定性。当信号相互矛盾时，明确说出矛盾所在，而不是强行给出单一方向。
5. 语言克制、具体、有信息密度，避免空话与套话。不要使用感叹号堆砌情绪。
6. 面向中国投资者，理解 A 股的涨跌停、T+1、融资融券等制度背景。

输出严格为 JSON 格式，不要包含 markdown 代码块标记。"""


def _build_user_prompt(analysis, snapshot, ctx):
    """把结构化分析压缩成模型输入。控制长度以节省 token。"""
    snap = analysis.get("market_snapshot") or {}
    signals = analysis.get("signals") or []

    sig_lines = []
    for s in signals[:8]:
        sig_lines.append("- [%s] %s：%s" % (s.get("type"), s.get("title"), s.get("evidence")))

    payload = {
        "交易日": analysis.get("trade_date"),
        "基准指数": analysis.get("benchmark"),
        "收盘": snap.get("last_close"),
        "当日涨跌": "%s%%" % snap.get("pct") if snap.get("pct") is not None else None,
        "两市成交额": "%s 亿元" % snap.get("amount_yi") if snap.get("amount_yi") else None,
        "涨跌家数": snap.get("breadth"),
        "涨停家数": snap.get("limit_up_count"),
        "跌停家数": snap.get("limit_down_count"),
        "最高连板": snap.get("max_streak"),
        "主力资金": "%s 亿元" % snap.get("main_flow_yi") if snap.get("main_flow_yi") else None,
        "融资余额": "%s 亿元（5日 %s%%）" % (snap.get("margin_balance_yi"), snap.get("margin_change_5d_pct"))
                    if snap.get("margin_balance_yi") else None,
        "RSI14": snap.get("rsi14"),
        "年化波动率": snap.get("volatility20"),
        "均线": snap.get("ma"),
        "均线排列": snap.get("ma_alignment"),
        "MACD": snap.get("macd"),
        "价格年内分位": snap.get("price_percentile_250"),
        "情绪温度": (analysis.get("sentiment") or {}).get("score"),
        "情绪定性": analysis.get("sentiment_label"),
        "风险等级": analysis.get("risk_level"),
        "规则引擎识别到的信号": sig_lines,
        "领涨行业": [{"名称": s.get("name"), "涨幅": s.get("pct")}
                 for s in (snapshot.get("sectors", {}).get("industry") or [])[:6]],
    }

    return """以下是今日 A 股市场的量化数据，以及规则引擎识别出的信号。

数据：
%s

请基于以上信息，输出如下 JSON 结构（严格 JSON，无 markdown 标记）：

{
  "headline": "一句话概括今日市场状态，不超过 40 字，要具体不要空泛",
  "commentary": "3-4 段解读。第1段：今日市场发生了什么，数据背后的含义；第2段：当前处于什么阶段，这类阶段的历史特征；第3段：此时最需要注意的风险（要具体）；第4段：给个人投资者的纪律建议。每段 80-150 字，总长度 400-600 字。",
  "watchpoints": ["接下来 3-5 个交易日应重点观察的 3 个指标或现象，每条不超过 30 字，必须是可观测的客观事实而非主观判断"],
  "lesson_focus": "今日最值得复习的一个投资知识点名称（从以下选择：市场宽度、量价关系、情绪周期、均线系统、资金流、融资余额、波动率与仓位、处置效应、确认偏误、损失厌恶），并说明为什么今天特别相关，不超过 80 字",
  "contradictions": "若数据之间存在相互矛盾的信号，在此指出；若无明显矛盾则填空字符串"
}""" % json.dumps(payload, ensure_ascii=False, indent=1)


def _call_api(base_url, api_key, model, system, user):
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.4,
        "max_tokens": 1800,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        js = json.loads(resp.read().decode("utf-8", "ignore"))
    return js["choices"][0]["message"]["content"]


def _parse_json_maybe(text):
    """模型有时会在 JSON 外包 ```json 标记，做一次容错解析。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    try:
        return json.loads(t)
    except ValueError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except ValueError:
                return None
    return None


def enhance(analysis, snapshot, ctx):
    """
    用大模型补充解读。任何环节失败都返回原始 analysis，绝不抛异常。
    成功时 analysis["ai"] 被填充，且 engine 字段标记为 hybrid。
    """
    api_key = os.environ.get("AI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置 AI_API_KEY，使用规则引擎输出")

    base_url = os.environ.get("AI_BASE_URL", "").strip() or DEFAULT_BASE
    model = os.environ.get("AI_MODEL", "").strip() or DEFAULT_MODEL

    raw = _call_api(base_url, api_key, model, SYSTEM_PROMPT,
                    _build_user_prompt(analysis, snapshot, ctx))
    parsed = _parse_json_maybe(raw)
    if not parsed:
        raise RuntimeError("模型返回内容无法解析为 JSON")

    # 只接受预期字段，防止模型输出污染结构
    allowed = ("headline", "commentary", "watchpoints", "lesson_focus", "contradictions")
    ai = {k: parsed.get(k) for k in allowed if parsed.get(k)}
    if not ai.get("commentary"):
        raise RuntimeError("模型未返回 commentary 字段")

    ai["model"] = model
    ai["provider"] = "glm" if "bigmodel" in base_url else ("kimi" if "moonshot" in base_url else "custom")
    analysis["ai"] = ai
    analysis["engine"] = "hybrid"
    return analysis
