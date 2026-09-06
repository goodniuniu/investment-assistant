# -*- coding: utf-8 -*-
"""
技术指标计算。纯标准库实现，不依赖 numpy / pandas。

设计原则：数据不足时返回 None，绝不抛异常——历史数据长度不固定（新股、停牌、
接口降级都会导致长度变化），指标层必须对这些情况免疫。
"""

import math


def sma(values, n):
    """简单移动平均。返回与输入等长的列表，前 n-1 位为 None。"""
    if not values or n <= 0 or len(values) < n:
        return None
    out, s = [], 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def ema(values, n):
    """指数移动平均，采用 alpha = 2/(n+1)。"""
    if not values or n <= 0:
        return None
    a = 2.0 / (n + 1)
    out, prev = [], None
    for v in values:
        prev = v if prev is None else a * v + (1 - a) * prev
        out.append(prev)
    return out


def macd(closes, fast=12, slow=26, signal=9):
    """MACD：返回 {dif, dea, hist} 三条序列。"""
    if not closes or len(closes) < slow + signal:
        return None
    ef, es = ema(closes, fast), ema(closes, slow)
    dif = [f - s for f, s in zip(ef, es)]
    dea = ema(dif, signal)
    hist = [(d - s) * 2 for d, s in zip(dif, dea)]
    return {"dif": dif, "dea": dea, "hist": hist}


def rsi(closes, n=14):
    """RSI，采用 Wilder 平滑（与主流行情软件一致）。"""
    if not closes or len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:n]) / n
    avg_l = sum(losses[:n]) / n
    out = [None] * (n + 1)
    for i in range(n, len(gains)):
        avg_g = (avg_g * (n - 1) + gains[i]) / n
        avg_l = (avg_l * (n - 1) + losses[i]) / n
        if avg_l == 0:
            # 完全无波动时 RSI 取 50（0/0 的惯例约定），有涨无跌为 100
            out.append(100.0 if avg_g > 0 else 50.0)
        else:
            rs = avg_g / avg_l
            out.append(100 - 100 / (1 + rs))
    # 补齐长度，使 out 与 closes 等长
    while len(out) < len(closes):
        out.insert(0, None)
    return out[:len(closes)]


def atr(rows, n=14):
    """真实波幅均值。rows 需含 high/low/close。"""
    if not rows or len(rows) < n + 1:
        return None
    trs = []
    for i in range(1, len(rows)):
        h, l = rows[i]["high"], rows[i]["low"]
        pc = rows[i - 1]["close"]
        if None in (h, l, pc):
            trs.append(None)
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    valid = [t for t in trs if t is not None]
    if len(valid) < n:
        return None
    a = sum(valid[:n]) / n
    for t in valid[n:]:
        a = (a * (n - 1) + t) / n
    return a


def volatility(closes, n=20, annualize=True):
    """收益波动率。annualize=True 时年化（乘 sqrt(250)）。"""
    if not closes or len(closes) < n + 1:
        return None
    window = closes[-(n + 1):]
    rets = []
    for i in range(1, len(window)):
        if window[i - 1]:
            rets.append(math.log(window[i] / window[i - 1]))
    if len(rets) < 2:
        return None
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    sd = math.sqrt(var)
    return sd * math.sqrt(250) * 100 if annualize else sd * 100


def percentile_rank(values, value):
    """value 在历史序列中的分位数（0-100）。"""
    if not values or value is None:
        return None
    arr = [v for v in values if v is not None]
    if not arr:
        return None
    below = sum(1 for v in arr if v < value)
    return round(below / len(arr) * 100, 1)


def max_drawdown(closes):
    """区间最大回撤（百分比，正数表示回撤幅度）。"""
    if not closes or len(closes) < 2:
        return None
    peak = closes[0]
    mdd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            mdd = max(mdd, (peak - c) / peak * 100)
    return round(mdd, 2)


def consecutive(closes):
    """末尾连续上涨(正)/下跌(负)的天数。"""
    if not closes or len(closes) < 2:
        return 0
    n = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            step = 1
        elif closes[i] < closes[i - 1]:
            step = -1
        else:
            break
        if n == 0 or (n > 0) == (step > 0):
            n += step
        else:
            break
    return n


def volume_ratio(rows, n=5):
    """量比：最新成交量 / 过去 n 日均值。"""
    if not rows or len(rows) < n + 1:
        return None
    vols = [r.get("volume") for r in rows[-(n + 1):-1]]
    vols = [v for v in vols if v]
    last = rows[-1].get("volume")
    if not vols or not last:
        return None
    return round(last / (sum(vols) / len(vols)), 3)


def ma_alignment(closes, mas):
    """
    均线排列判断。mas 为 [(周期, 值), ...] 按周期从小到大。
    返回 'bull'(多头排列) / 'bear'(空头排列) / 'mixed'(交织) / None
    """
    if closes is None or not closes or len(mas) < 3 or any(v is None for _, v in mas):
        # 任一关键均线缺失（历史不足）时不给排列结论，保证"多/空头排列"语义完整
        return None
    vals = [v for _, v in mas]
    last = closes[-1]
    up = all(a > b for a, b in zip(vals, vals[1:])) and last > vals[0]
    down = all(a < b for a, b in zip(vals, vals[1:])) and last < vals[0]
    if up:
        return "bull"
    if down:
        return "bear"
    return "mixed"


def cross(prev_a, prev_b, curr_a, curr_b):
    """判断金叉/死叉：返回 'golden' / 'dead' / None。"""
    if None in (prev_a, prev_b, curr_a, curr_b):
        return None
    if prev_a <= prev_b and curr_a > curr_b:
        return "golden"
    if prev_a >= prev_b and curr_a < curr_b:
        return "dead"
    return None


def summarize(rows):
    """
    从日K序列中一次性算出分析所需的核心指标。
    返回 dict，字段缺失时为 None，供规则引擎使用。
    """
    if not rows or len(rows) < 30:
        return None
    closes = [r["close"] for r in rows if r.get("close") is not None]
    if len(closes) < 30:
        return None

    result = {
        "last_date": rows[-1].get("date"),
        "last_close": closes[-1],
        "bars": len(rows),
    }

    mas = {}
    for n in (5, 10, 20, 60, 120, 250):
        s = sma(closes, n)
        mas["ma%d" % n] = s[-1] if s else None
    result.update(mas)

    result["ma_alignment"] = ma_alignment(closes, [
        (5, mas.get("ma5")), (10, mas.get("ma10")),
        (20, mas.get("ma20")), (60, mas.get("ma60")),
    ])

    m = macd(closes)
    if m:
        result["macd"] = {
            "dif": round(m["dif"][-1], 3),
            "dea": round(m["dea"][-1], 3),
            "hist": round(m["hist"][-1], 3),
            "cross": cross(m["dif"][-2], m["dea"][-2], m["dif"][-1], m["dea"][-1]),
        }
    else:
        result["macd"] = None

    r = rsi(closes, 14)
    result["rsi14"] = round(r[-1], 2) if r and r[-1] is not None else None

    _atr14 = atr(rows, 14)
    result["atr14"] = round(_atr14, 2) if _atr14 else None
    _vol20 = volatility(closes, 20)
    result["volatility20"] = round(_vol20, 2) if _vol20 else None
    result["volume_ratio"] = volume_ratio(rows, 5)
    result["consecutive"] = consecutive(closes)

    # 价格与成交额的年内（250日）分位
    result["price_percentile_250"] = percentile_rank(closes[-250:], closes[-1])
    amounts = [r.get("amount") for r in rows[-250:]]
    result["amount_percentile_250"] = percentile_rank(amounts, rows[-1].get("amount"))
    # 成交量分位：腾讯/新浪备用源不返回成交额，用它作为量能的兜底度量
    volumes = [r.get("volume") for r in rows[-250:]]
    result["volume_percentile_250"] = percentile_rank(volumes, rows[-1].get("volume"))

    # 区间涨跌与最大回撤
    for label, n in (("ret5", 5), ("ret20", 20), ("ret60", 60), ("ret250", 250)):
        if len(closes) > n and closes[-n - 1]:
            result[label] = round((closes[-1] / closes[-n - 1] - 1) * 100, 2)
        else:
            result[label] = None
    result["max_drawdown_250"] = max_drawdown(closes[-250:])

    return result
