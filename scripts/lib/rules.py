# -*- coding: utf-8 -*-
"""
规则引擎：把原始行情翻译成「可理解、可学习」的结论。

设计取向：
  1. 只描述市场正在发生什么，以及这类情形在历史上通常意味着什么，**不做个股推荐、
     不给买卖点位**。结论一律落到「观察什么、警惕什么、复习哪个知识点」。
  2. 每个信号都绑定知识点 id，页面据此跳转到知识库对应条目，形成「现象 → 原理」闭环。
  3. 所有阈值集中在此文件，便于后续调参与回测校准。
"""

# ---------------------------------------------------------------- 阈值配置
THRESHOLDS = {
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "breadth_hot": 75,        # 上涨家数占比高于此值视为普涨
    "breadth_cold": 25,       # 低于此值视为普跌
    "limit_up_hot": 80,       # 涨停家数过热
    "limit_up_cold": 25,      # 涨停家数冰点
    "volume_ratio_high": 1.5,
    "volume_ratio_low": 0.7,
    "volatility_high": 30,    # 年化波动率 %
    "volatility_low": 12,
    "amount_hot_yi": 20000,   # 两市成交额（亿元）
    "amount_cold_yi": 7000,
}


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _lin(value, lo, hi):
    """把 value 从 [lo, hi] 线性映射到 [0, 100]，超出区间则截断。"""
    if value is None or hi == lo:
        return None
    return _clamp((value - lo) / (hi - lo) * 100)


def _fmt_yi(v):
    """元 → 亿元字符串。"""
    if v is None:
        return "—"
    return "%.0f 亿" % (v / 1e8)


# ---------------------------------------------------------------- 情绪温度
def sentiment_score(ctx):
    """
    情绪温度 0-100。50 为中性。
    六个分量加权；任一分量缺失时，用剩余分量按权重重新归一化，保证结果始终可比。
    """
    comp = []

    # 1) 价格动量：近 20 日涨跌幅
    comp.append(("momentum", _lin(ctx.get("ret20"), -12, 12), 22))

    # 2) 市场宽度：全市场上涨家数占比
    b = ctx.get("breadth") or {}
    comp.append(("breadth", _lin(b.get("up_ratio"), 22, 78), 20))

    # 3) 量能：优先成交额分位；备用源缺成交额时降级为成交量分位
    vol_score = ctx.get("amount_percentile_250")
    if vol_score is None:
        vol_score = ctx.get("volume_percentile_250")
    comp.append(("volume", vol_score, 13))

    # 4) 赚钱效应：涨停家数（跌停家数做惩罚）
    zt = ctx.get("limit_up_count")
    if zt is not None:
        s = _lin(zt, 15, 90)
        dt = ctx.get("limit_down_count") or 0
        if dt >= 30:
            s = _clamp(s - 15)
        elif dt >= 10:
            s = _clamp(s - 7)
        comp.append(("profit_effect", s, 20))
    else:
        comp.append(("profit_effect", None, 20))

    # 5) 杠杆情绪：融资余额近 5 日变化
    comp.append(("leverage", _lin(ctx.get("margin_change_5d_pct"), -1.5, 1.5), 10))

    # 6) 主力资金：净流入强度（亿元）
    mf = ctx.get("main_flow_yi")
    comp.append(("fund_flow", _lin(mf, -400, 400), 15))

    used = [(n, s, w) for n, s, w in comp if s is not None]
    if not used:
        return None
    total_w = sum(w for _, _, w in used)
    score = sum(s * w for _, s, w in used) / total_w

    return {
        "score": round(score, 1),
        "components": [{"name": n, "score": round(s, 1), "weight": round(w / total_w * 100, 1)}
                       for n, s, w in used],
        "coverage": round(total_w / sum(w for _, _, w in comp) * 100, 1),
    }


def sentiment_label(score):
    if score is None:
        return "数据不足", "无法评估"
    if score >= 85:
        return "极度亢奋", "市场情绪接近历史高位，赚钱效应强但风险快速累积"
    if score >= 70:
        return "偏热", "情绪积极，赚钱效应较好，需开始关注拥挤度"
    if score >= 58:
        return "温和偏暖", "情绪略偏乐观，结构性机会为主"
    if score >= 43:
        return "中性", "多空力量相对均衡，缺乏明确方向"
    if score >= 30:
        return "偏冷", "情绪低迷，观望氛围较浓"
    if score >= 18:
        return "低迷", "市场悲观，抛压主导，但也意味着定价开始有吸引力"
    return "冰点", "极度悲观，往往是长期投资者逐步布局的窗口，但需承受继续下跌的心理压力"


# ---------------------------------------------------------------- 信号识别
def detect_signals(ctx):
    """
    识别当前市场特征信号。
    每个信号包含：类型(多/空/中性)、数据依据、知识点讲解、关联知识点 id。
    """
    sig = []
    T = THRESHOLDS

    close = ctx.get("last_close")
    pct = ctx.get("pct")
    align = ctx.get("ma_alignment")
    macd = ctx.get("macd") or {}
    rsi = ctx.get("rsi14")
    vr = ctx.get("volume_ratio")
    b = ctx.get("breadth") or {}
    up_ratio = b.get("up_ratio")
    zt = ctx.get("limit_up_count")
    dt = ctx.get("limit_down_count")
    vol = ctx.get("volatility20")
    amount_yi = ctx.get("amount_yi")

    # --- 趋势结构 ---
    if align == "bull":
        sig.append({
            "id": "ma_bull",
            "type": "bull",
            "title": "均线多头排列",
            "evidence": _evidence_ma(ctx),
            "lesson": "短中长期均线自下而上依次排列且价格站在最上方，说明各周期持仓者平均成本"
                       "都在盈利，趋势的自我强化机制正在运转。多头排列是趋势跟踪者最愿意加仓的"
                       "形态，但它属于**滞后确认**——均线由价格算出，往往在趋势走了相当一段后才"
                       "成形。真正需要注意的是排列被破坏的那一刻：短期均线跌破中期均线，通常比"
                       "价格跌破某条均线更有预警意义。",
            "knowledge": ["tech-moving-average", "tech-trend"],
        })
    elif align == "bear":
        sig.append({
            "id": "ma_bear",
            "type": "bear",
            "title": "均线空头排列",
            "evidence": _evidence_ma(ctx),
            "lesson": "均线自上而下排列且价格位于最下方，意味着各周期买入者普遍被套，每一次反弹"
                       "都会遇到解套盘的抛压，趋势具有自我延续性。空头排列中抢反弹的难度显著高于"
                       "上升趋势中回调买入——因为你面对的不是暂时的获利回吐，而是持续的解套供给。"
                       "空头排列的终结信号通常是：指数不再创新低、成交量萎缩、随后放量收复短期均线。",
            "knowledge": ["tech-moving-average", "tech-trend", "risk-drawdown"],
        })
    else:
        sig.append({
            "id": "ma_mixed",
            "type": "neutral",
            "title": "均线交织，趋势不明",
            "evidence": _evidence_ma(ctx),
            "lesson": "均线相互缠绕说明各周期成本趋于一致，市场处于无趋势的震荡状态。这是趋势跟踪"
                       "策略最容易反复止损亏钱的阶段——信号频繁出现又频繁失效。应对方式有二：降低"
                       "仓位等待方向明朗，或改用区间思路（高抛低吸）并严格控制单次风险敞口。识别"
                       "震荡市本身，就是一种能力。",
            "knowledge": ["tech-trend", "tech-limits", "allocation-position-sizing"],
        })

    # --- MACD ---
    cross_type = macd.get("cross")
    if cross_type == "golden":
        sig.append({
            "id": "macd_golden",
            "type": "bull",
            "title": "MACD 金叉",
            "evidence": "DIF %.2f 上穿 DEA %.2f，柱状线 %.2f" % (
                macd.get("dif") or 0, macd.get("dea") or 0, macd.get("hist") or 0),
            "lesson": "DIF 上穿 DEA 表示短期均线组与长期均线组的差距由缩小转为扩大，动能方向发生"
                       "反转。要理解 MACD 的本质是**两条指数均线的距离**，因此它天然滞后。金叉在"
                       "趋势市中有效，在震荡市中会频繁假信号。提高胜率的关键不是换指标，而是把"
                       "MACD 与趋势结构结合：多头排列中的金叉，可靠性远高于空头排列中的金叉。",
            "knowledge": ["tech-macd", "tech-limits"],
        })
    elif cross_type == "dead":
        sig.append({
            "id": "macd_dead",
            "type": "bear",
            "title": "MACD 死叉",
            "evidence": "DIF %.2f 下穿 DEA %.2f，柱状线 %.2f" % (
                macd.get("dif") or 0, macd.get("dea") or 0, macd.get("hist") or 0),
            "lesson": "死叉代表上涨动能衰竭。单一死叉信号很弱——在强势上升趋势中，死叉后价格常常"
                       "仅小幅回调便继续上行。真正值得警惕的是**二次死叉**：价格创出新高但 MACD 未"
                       "同步创出新高（顶背离），说明推动上涨的资金力量在减弱，这是趋势可能反转的"
                       "较早警示。",
            "knowledge": ["tech-macd", "tech-divergence", "tech-limits"],
        })

    # --- RSI ---
    if rsi is not None:
        if rsi >= T["rsi_overbought"]:
            sig.append({
                "id": "rsi_overbought",
                "type": "bear",
                "title": "RSI 超买",
                "evidence": "RSI(14) = %.1f，处于 %.0f 以上超买区" % (rsi, T["rsi_overbought"]),
                "lesson": "RSI 衡量的是一段时间内上涨幅度占总波动幅度的比例。高于 70 只说明**短期"
                           "上涨过快**，绝不意味着必须下跌。这是最常见的误用。在强势牛市中，RSI 可以"
                           "在超买区停留数周甚至数月，此时依据 RSI 卖出会错过主升浪。超买的正确用法"
                           "是：作为**不再追高**的提示，而非**立即卖出**的信号；只有配合价格形态破位"
                           "或量能萎缩，才构成减仓理由。",
                "knowledge": ["tech-rsi", "tech-limits"],
            })
        elif rsi <= T["rsi_oversold"]:
            sig.append({
                "id": "rsi_oversold",
                "type": "bull",
                "title": "RSI 超卖",
                "evidence": "RSI(14) = %.1f，处于 %.0f 以下超卖区" % (rsi, T["rsi_oversold"]),
                "lesson": "超卖说明短期抛压释放较充分，但同样不等于见底。在单边下跌趋势中，RSI 会"
                           "反复钝化——屡次超卖而价格继续新低，俗称「超卖之后还有超卖」。真正有参考"
                           "价值的是**底背离**：价格创出新低，而 RSI 未同步创出新低，说明下跌动能在"
                           "衰弱。抄底前请确认这一点，而不是看到 RSI 低于 30 就行动。",
                "knowledge": ["tech-rsi", "tech-divergence", "risk-stop-loss"],
            })

    # --- 量价组合 ---
    if vr is not None and pct is not None:
        if vr >= T["volume_ratio_high"] and pct > 0:
            sig.append({
                "id": "vol_up_price_up",
                "type": "bull",
                "title": "放量上涨",
                "evidence": "量比 %.2f（5 日均量的 %.0f%%），指数 %+.2f%%" % (vr, vr * 100, pct),
                "lesson": "价涨量增是最健康的上涨形态：更多资金愿意在更高价位买入，需求真实。但要"
                           "区分位置——低位放量上涨通常是资金介入的信号，而**连续上涨后的高位放量**"
                           "则可能是主力借人气派发。判断依据在于后续：健康放量后价格能守住涨幅，"
                           "而派发放量后往往快速回落并跌破放量当日低点。",
                "knowledge": ["tech-volume-price", "sentiment-fund-flow"],
            })
        elif vr >= T["volume_ratio_high"] and pct < 0:
            sig.append({
                "id": "vol_up_price_down",
                "type": "bear",
                "title": "放量下跌",
                "evidence": "量比 %.2f，指数 %+.2f%%，成交额 %s" % (vr, pct, _fmt_yi(ctx.get("amount_total"))),
                "lesson": "放量下跌意味着抛压被大量承接的同时仍有更大规模卖出，多空分歧剧烈。若发生"
                           "在下跌初期，往往是趋势性下跌的确认；若发生在**长期下跌后的低位**，则可能"
                           "是恐慌盘集中出清，属于最后一跌的特征之一，常伴随成交额的阶段性地量见天量。"
                           "区分关键在于情绪温度与市场宽度是否同时处于极端低位。",
                "knowledge": ["tech-volume-price", "sentiment-cycle", "behavior-herding"],
            })
        elif vr <= T["volume_ratio_low"] and abs(pct) < 0.6:
            sig.append({
                "id": "vol_dry",
                "type": "neutral",
                "title": "缩量整理",
                "evidence": "量比仅 %.2f，指数 %+.2f%%，交投清淡" % (vr, pct),
                "lesson": "地量往往出现在两种场景：一是趋势中场的休整（健康），二是趋势末端的枯竭"
                          "（变盘前兆）。单看成交量无法区分，需结合位置判断——上涨途中的缩量回调是"
                          "正常洗盘；高位横盘缩量则意味着承接力量不足，方向选择临近。此时不宜重仓"
                          "押注方向，等待放量突破更稳妥。",
                "knowledge": ["tech-volume-price", "allocation-position-sizing"],
            })

    # --- 市场宽度 ---
    if up_ratio is not None:
        if up_ratio >= T["breadth_hot"]:
            sig.append({
                "id": "breadth_hot",
                "type": "bull",
                "title": "普涨格局",
                "evidence": "全市场 %d 家上涨 / %d 家下跌，上涨占比 %.1f%%" % (
                    b.get("up", 0), b.get("down", 0), up_ratio),
                "lesson": "市场宽度衡量的是**参与度**，它比指数涨跌更真实。指数由权重股决定，可以"
                           "在多数个股下跌时依然收红；而宽度指标反映的是赚钱效应是否扩散到多数股票。"
                           "普涨说明行情基础扎实。但要留意：持续极端普涨（上涨占比连续超过 80%）往往"
                           "出现在情绪周期的高潮阶段，此时更应关注风险而非收益。",
                "knowledge": ["sentiment-market-breadth", "sentiment-cycle"],
            })
        elif up_ratio <= T["breadth_cold"]:
            sig.append({
                "id": "breadth_cold",
                "type": "bear",
                "title": "普跌格局",
                "evidence": "全市场 %d 家上涨 / %d 家下跌，上涨占比 %.1f%%" % (
                    b.get("up", 0), b.get("down", 0), up_ratio),
                "lesson": "多数个股下跌说明是系统性抛压，而非个别板块的问题。此时分散持仓无法规避"
                           "风险——因为所有资产的相关性在下跌中趋近于 1，这正是分散化在极端行情中"
                           "失效的原因。真正能保护你的是**仓位**与**资产类别配置**（如股债搭配），"
                           "而不是在股票内部换仓。",
                "knowledge": ["sentiment-market-breadth", "allocation-diversification",
                              "allocation-asset-allocation"],
            })
        elif pct is not None and abs(pct) > 0.8 and up_ratio < 45 and pct > 0:
            sig.append({
                "id": "index_divergence_breadth",
                "type": "neutral",
                "title": "指数与宽度背离",
                "evidence": "指数 %+.2f%%，但上涨家数仅占 %.1f%%（%d 涨 / %d 跌）" % (
                    pct, up_ratio, b.get("up", 0), b.get("down", 0)),
                "lesson": "指数上涨而多数个股下跌，说明涨幅集中在少数权重股上，这是典型的**结构性"
                           "行情**或**护盘行情**。此时指数失真，用指数判断市场冷暖会产生严重偏差。"
                           "对多数投资者而言，这类行情赚钱难度反而更高。判断市场真实状态，请始终"
                           "同时看指数与市场宽度这两个维度。",
                "knowledge": ["sentiment-market-breadth", "market-index-system"],
            })

    # --- 涨跌停 ---
    if zt is not None:
        if zt >= T["limit_up_hot"]:
            sig.append({
                "id": "limit_up_hot",
                "type": "bear",
                "title": "涨停家数过热",
                "evidence": "涨停 %d 家、跌停 %d 家，最高连板 %d 板" % (
                    zt, dt or 0, ctx.get("max_streak") or 0),
                "lesson": "涨停家数是短线情绪最直接的体温计。数量激增说明游资活跃、赚钱效应强，但"
                           "也意味着市场进入高换手、高博弈阶段。历史经验是：涨停家数从高位快速回落"
                           "（例如腰斩）时，往往伴随短线情绪退潮与指数调整。因此过热期参与短线，"
                           "必须预先想好退出条件，而不是等情绪转冷再做决定——那时流动性已消失。",
                "knowledge": ["sentiment-limit-up", "risk-liquidity", "behavior-herding"],
            })
        elif zt <= T["limit_up_cold"]:
            sig.append({
                "id": "limit_up_cold",
                "type": "bull",
                "title": "涨停家数冰点",
                "evidence": "涨停仅 %d 家、跌停 %d 家" % (zt, dt or 0),
                "lesson": "涨停稀少说明短线资金离场、市场缺乏赚钱效应，情绪处于周期低谷。情绪冰点"
                           "对长线投资者是机会窗口（定价更合理），但对短线交易者则是最难受的时期。"
                           "关键提醒：**冰点不等于底**，它只说明悲观已被较充分定价。从冰点到反转"
                           "之间可能还有漫长磨底，所以要分批而非一次性投入。",
                "knowledge": ["sentiment-limit-up", "sentiment-cycle", "allocation-position-sizing"],
            })

    # --- 波动率 ---
    if vol is not None:
        if vol >= T["volatility_high"]:
            sig.append({
                "id": "vol_high",
                "type": "bear",
                "title": "波动率显著抬升",
                "evidence": "20 日年化波动率 %.1f%%（高于 %.0f%% 阈值）" % (vol, T["volatility_high"]),
                "lesson": "波动率上升意味着不确定性加剧，单日大幅涨跌的概率增加。这直接影响两件事："
                           "一是同等仓位下你的账面波动变大，容易触发情绪化操作；二是止损位更容易被"
                           "随机波动扫掉。理性的应对是**降低仓位以维持恒定的风险敞口**——波动率翻倍"
                           "时仓位应减半，这样你承担的实际风险才与之前相当。这是风险平价的核心思想。",
                "knowledge": ["sentiment-volatility", "risk-position-risk", "allocation-position-sizing"],
            })
        elif vol <= T["volatility_low"]:
            sig.append({
                "id": "vol_low",
                "type": "neutral",
                "title": "波动率处于低位",
                "evidence": "20 日年化波动率 %.1f%%（低于 %.0f%% 阈值）" % (vol, T["volatility_low"]),
                "lesson": "低波动代表市场平静、分歧小。平静往往是变盘的前奏，但方向未知——低波动"
                           "之后既可能向上突破，也可能向下突破。因此低波动期适合做两件事：一是检查"
                           "持仓是否过度集中于单一逻辑，二是在风险预算允许范围内提前布局，而不是等"
                           "波动放大后再被动反应。",
                "knowledge": ["sentiment-volatility", "risk-black-swan"],
            })

    # --- 成交额 ---
    if amount_yi is not None:
        if amount_yi >= T["amount_hot_yi"]:
            sig.append({
                "id": "amount_hot",
                "type": "neutral",
                "title": "成交额高企",
                "evidence": "两市合计成交 %.0f 亿元" % amount_yi,
                "lesson": "天量成交意味着大量换手——有人买就有人卖，分歧巨大。天量往往出现在趋势的"
                           "中后段而非起点。它不构成看空理由，但提示你：此时市场定价已充分反映当前"
                           "信息，继续大幅上行需要**新增的**资金或**超预期的**基本面。把成交额与"
                           "指数位置结合看，比单独看成交额更有意义。",
                "knowledge": ["sentiment-fund-flow", "tech-volume-price"],
            })
        elif amount_yi <= T["amount_cold_yi"]:
            sig.append({
                "id": "amount_cold",
                "type": "neutral",
                "title": "成交额萎缩",
                "evidence": "两市合计成交仅 %.0f 亿元" % amount_yi,
                "lesson": "地量反映观望情绪浓厚，多空双方都不愿出手。地价见地量是常见的底部特征，"
                           "但地量之后可能还有更低的量。对长线投资者，缩量下跌区的定投成本更优；"
                           "对短线交易者，低流动性环境下冲击成本高，应减少交易频率。",
                "knowledge": ["tech-volume-price", "cost-slippage", "cost-transaction"],
            })

    # --- 融资余额 ---
    margin = ctx.get("margin_change_5d_pct")
    if margin is not None:
        if margin >= 1.2:
            sig.append({
                "id": "margin_hot",
                "type": "bear",
                "title": "杠杆资金快速流入",
                "evidence": "融资余额近 5 日变化 %+.2f%%" % margin,
                "lesson": "融资余额是市场中最敏锐也最脆弱的资金。快速加杠杆说明风险偏好上升，短期"
                           "有助推作用；但杠杆资金具有**强平机制**，一旦市场反向波动，强制平仓会形成"
                           "「下跌→平仓→再下跌」的负反馈。2015 年的教训是：杠杆推动的上涨，会以更快"
                           "的速度还回去。观察融资余额的意义，在于感知市场的脆弱程度。",
                "knowledge": ["sentiment-margin", "risk-black-swan", "behavior-overconfidence"],
            })
        elif margin <= -1.2:
            sig.append({
                "id": "margin_cold",
                "type": "bull",
                "title": "杠杆资金撤离",
                "evidence": "融资余额近 5 日变化 %+.2f%%" % margin,
                "lesson": "融资资金撤离意味着杠杆盘在去化，市场脆弱性下降。这通常是筑底过程中的"
                           "必要一环——不把杠杆清洗干净，反弹就缺乏持续性。但去杠杆的过程本身是"
                           "痛苦的，往往伴随持续的阴跌。因此这是一个**观察确认项**而非**买入信号**。",
                "knowledge": ["sentiment-margin", "risk-drawdown"],
            })

    # --- 主力资金 ---
    mf = ctx.get("main_flow_yi")
    if mf is not None:
        if mf <= -300:
            sig.append({
                "id": "fund_outflow",
                "type": "bear",
                "title": "主力资金大幅净流出",
                "evidence": "主力资金净流出 %.0f 亿元" % abs(mf),
                "lesson": "资金流数据由逐笔成交按单子大小分类统计而来，它反映的是**大单的方向**，"
                           "机构真实意图无法直接观测——大单可以通过拆单隐藏，也可以通过对倒制造假象。"
                           "因此资金流是参考而非结论。持续净流出结合价格下跌，才是较为可靠的弱势信号；"
                           "若资金流出而价格不跌，则说明承接力量强，反而值得关注。",
                "knowledge": ["sentiment-fund-flow", "tech-volume-price"],
            })
        elif mf >= 300:
            sig.append({
                "id": "fund_inflow",
                "type": "bull",
                "title": "主力资金净流入",
                "evidence": "主力资金净流入 %.0f 亿元" % mf,
                "lesson": "资金净流入说明大单主动买入占优。同样要提醒：单日数据噪音极大，参考价值"
                           "有限；**连续性**才是关键——连续 3-5 日净流入的说服力远高于单日巨额流入。"
                           "此外，资金流入若伴随股价不涨，需警惕是否有大单在掩护出货。",
                "knowledge": ["sentiment-fund-flow"],
            })

    return sig


def _evidence_ma(ctx):
    parts = []
    for k in ("ma5", "ma10", "ma20", "ma60"):
        v = ctx.get(k)
        if v is not None:
            parts.append("%s=%.0f" % (k.upper(), v))
    tail = "，收盘 %.0f" % ctx["last_close"] if ctx.get("last_close") else ""
    return "、".join(parts) + tail


# ---------------------------------------------------------------- 心理提示
def psychology_alerts(ctx, sentiment):
    """根据当前市场环境，提示最容易被触发的心理偏差。"""
    alerts = []
    score = (sentiment or {}).get("score")
    b = ctx.get("breadth") or {}
    up_ratio = b.get("up_ratio")
    pct = ctx.get("pct")
    vr = ctx.get("volume_ratio")
    zt = ctx.get("limit_up_count")

    if score is not None and score >= 70:
        alerts.append({
            "bias": "behavior-overconfidence",
            "level": "high",
            "text": "情绪偏热时，人容易把「市场上涨」等同于「自己判断正确」。请区分运气与能力："
                    "把近期的盈利按「当时买入的理由」逐条写下来，看看到底是逻辑兑现，还是仅仅"
                    "踩中了行情。牛市是检验投资体系最差的时机，因为它奖励错误的行为。",
        })
        alerts.append({
            "bias": "behavior-herding",
            "level": "high",
            "text": "周围人都在赚钱时，FOMO（害怕错过）会推动你在最高点加大投入。此时应当问自己："
                    "如果现在空仓，我愿意在今天的价格买入吗？如果答案是否定的，那你继续持有的"
                    "理由就只剩下「已经赚了」——而成本价与市场无关。",
        })
    if score is not None and score <= 32:
        alerts.append({
            "bias": "behavior-loss-aversion",
            "level": "high",
            "text": "亏损带来的痛苦约为同等盈利快感的两倍，这在低迷期会被放大到让人无法理性思考。"
                    "若你已经不敢打开账户，请先把「要不要卖」这个问题推迟 24 小时，并把决策标准"
                    "写成文字：卖出理由应该是**逻辑变了**，而不是**价格跌了**。",
        })
        alerts.append({
            "bias": "behavior-recency",
            "level": "medium",
            "text": "连续下跌后，大脑会默认这种状态将永远持续。请主动回看历史：每一次市场冰点之后"
                    "都出现了修复，区别只在于耗时。把当前情绪温度与一年前的读数做对比，用数据"
                    "校正直觉。",
        })
    if up_ratio is not None and up_ratio <= 30:
        alerts.append({
            "bias": "behavior-confirmation",
            "level": "medium",
            "text": "普跌时最容易做的事，是不断寻找支持「还要跌」的证据，而忽略反向信息。请刻意"
                    "列出三条与你当前判断相反的事实。真正的风险不是看错，而是只让自己看到一边。",
        })
    if zt is not None and zt >= 80:
        alerts.append({
            "bias": "behavior-gambler",
            "level": "high",
            "text": "涨停板密集时，「连板规律」「必涨形态」之类的错觉会格外强烈。涨停之间并无"
                    "统计上的依赖关系，历史序列不产生概率优势。若你发现自己在使用「都涨这么多了"
                    "该跌了」或「已经跌这么多该反弹了」这类推理，请停下来——这是赌徒谬误。",
        })
    if vr is not None and vr >= 1.8 and (pct or 0) < -1:
        alerts.append({
            "bias": "behavior-disposition",
            "level": "medium",
            "text": "急跌时，多数人会卖掉盈利的持仓而留下亏损的——因为卖出亏损意味着承认错误。"
                    "这个「处置效应」是长期收益的隐形杀手。请按**预期收益率**而非**盈亏状态**"
                    "来排序你的持仓，逐个回答：如果现在空仓，会买它吗？",
        })
    if not alerts:
        alerts.append({
            "bias": "behavior-anchoring",
            "level": "low",
            "text": "市场缺乏明确方向时，最容易被「成本价」锚定：涨到成本就想卖，跌破成本就死扛。"
                    "成本价是你个人的历史数字，市场对此一无所知。请用「当前价格 vs 当前价值」"
                    "替代「当前价格 vs 我的成本」来思考。",
        })
    return alerts


# ---------------------------------------------------------------- 纪律建议
def discipline_checklist(ctx, sentiment, risk_level):
    """给出纪律层面的行动清单（不含任何具体标的或点位建议）。"""
    items = []
    score = (sentiment or {}).get("score")

    items.append({
        "title": "核对仓位与风险预算",
        "detail": "当前波动率 %s。若波动率较你建仓时明显抬升，同等仓位承担的风险已经变大，"
                  "应考虑减仓至风险敞口与当初一致，而不是维持名义仓位不变。" % (
                      "%.1f%%" % ctx["volatility20"] if ctx.get("volatility20") else "数据不足"),
        "knowledge": "risk-position-risk",
    })

    if risk_level == "high":
        items.append({
            "title": "重新确认最坏情况",
            "detail": "高风险环境下的核心问题不是「能赚多少」，而是「如果再跌 20%，我能否不动如山」。"
                      "请在纸上写下这个数字并确认它在可承受范围内，否则现在就该降低仓位。",
            "knowledge": "risk-drawdown",
        })
    elif risk_level == "low":
        items.append({
            "title": "检查是否因恐慌而低配",
            "detail": "低风险环境里常见的错误是长期空仓等待「更好的价格」。请确认当前仓位与你的"
                      "长期配置目标一致，而非由近期情绪决定。",
            "knowledge": "allocation-asset-allocation",
        })

    if score is not None and score >= 70:
        items.append({
            "title": "预设退出条件",
            "detail": "在情绪高涨时提前写下减仓触发条件（例如情绪温度回落至某值、指数跌破某条均线），"
                      "并承诺执行。行情火热时做的决定，质量通常最低。",
            "knowledge": "risk-stop-loss",
        })
    if score is not None and score <= 32:
        items.append({
            "title": "采用分批而非一次性决策",
            "detail": "低迷期不应重仓押注「这就是底」。分批建仓的价值不在于提高收益，而在于让你在"
                      "判断错误时仍有余地和心态继续执行计划。",
            "knowledge": "allocation-position-sizing",
        })

    items.append({
        "title": "记录本次决策",
        "detail": "写下今天你的判断、依据与操作。一个月后回看，你会清楚看到自己是被逻辑驱动，"
                  "还是被情绪驱动——这是提升投资能力最有效也最被忽视的方法。",
        "knowledge": "behavior-hindsight",
    })
    return items


def risk_level(ctx, sentiment):
    """综合风险等级：low / medium / high。"""
    score = (sentiment or {}).get("score")
    vol = ctx.get("volatility20")
    score_risk = 0
    if score is not None:
        # 极度亢奋与极度低迷都意味着风险上升（方向不同）
        score_risk = max(0, abs(score - 50) - 18) / 32 * 100
    vol_risk = _lin(vol, 15, 40) or 30
    margin = ctx.get("margin_change_5d_pct")
    lev_risk = _lin(abs(margin or 0), 0.5, 2.5) or 20
    total = score_risk * 0.4 + vol_risk * 0.35 + lev_risk * 0.25
    if total >= 55:
        return "high", round(total, 1)
    if total >= 30:
        return "medium", round(total, 1)
    return "low", round(total, 1)


def build(ctx):
    """规则引擎总入口，输出完整分析结论。"""
    senti = sentiment_score(ctx)
    label, label_desc = sentiment_label((senti or {}).get("score"))
    level, level_score = risk_level(ctx, senti)
    signals = detect_signals(ctx)

    return {
        "sentiment": senti,
        "sentiment_label": label,
        "sentiment_desc": label_desc,
        "risk_level": level,
        "risk_score": level_score,
        "signals": signals,
        "psychology": psychology_alerts(ctx, senti),
        "discipline": discipline_checklist(ctx, senti, level),
    }
