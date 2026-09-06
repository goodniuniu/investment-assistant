# -*- coding: utf-8 -*-
"""指标计算黄金用例：全部为手算/已知参照的固定输入输出。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from lib import indicators  # noqa: E402


def test_sma_basic():
    out = indicators.sma([1, 2, 3, 4, 5], 3)
    assert out == [None, None, 2.0, 3.0, 4.0]


def test_sma_insufficient():
    assert indicators.sma([1, 2], 3) is None


def test_ema_converges():
    # EMA(无穷长恒定序列) 应收敛到常数
    out = indicators.ema([5.0] * 50, 5)
    assert abs(out[-1] - 5.0) < 1e-9


def test_macd_known():
    m = indicators.macd([10 + 0.1 * i for i in range(60)])
    assert m is not None
    # 持续上行 → DIF > DEA > 0，柱为正
    assert m["dif"][-1] > m["dea"][-1] > 0
    assert m["hist"][-1] > 0


def test_rsi_all_up():
    # 一路上涨 → RSI = 100
    r = indicators.rsi([1 + i for i in range(20)], 14)
    assert abs(r[-1] - 100.0) < 1e-6


def test_rsi_all_flat():
    r = indicators.rsi([5.0] * 20, 14)
    assert r[-1] == 50.0


def test_volatility_zero_for_flat():
    assert indicators.volatility([5.0] * 30, 20) == 0.0


def test_volume_ratio():
    # 注意不能用 [dict]*6（浅拷贝同一对象）
    rows = [{"close": 1, "volume": 100} for _ in range(6)]
    rows[-1]["volume"] = 200
    assert indicators.volume_ratio(rows, 5) == 2.0


def test_percentile_rank():
    # 语义：严格小于目标值的比例（below / n * 100）
    closes = list(range(1, 101))  # 1..100
    assert indicators.percentile_rank(closes, 100) == 99.0
    assert indicators.percentile_rank(closes, 1) == 0.0
    assert indicators.percentile_rank(closes, 50) == 49.0


def test_max_drawdown():
    # 100 → 50 → 80：最大回撤 50%
    assert indicators.max_drawdown([100, 50, 80]) == 50.0
    assert indicators.max_drawdown([1, 2, 3]) == 0.0


def test_ma_alignment_bull_bear_none():
    up = [10 + 0.1 * i for i in range(30)]
    mas_up = [(5, indicators.sma(up, 5)[-1]), (10, indicators.sma(up, 10)[-1]),
              (20, indicators.sma(up, 20)[-1])]
    assert indicators.ma_alignment(up, mas_up) == "bull"

    down = list(reversed(up))
    mas_dn = [(5, indicators.sma(down, 5)[-1]), (10, indicators.sma(down, 10)[-1]),
              (20, indicators.sma(down, 20)[-1])]
    assert indicators.ma_alignment(down, mas_dn) == "bear"

    # 关键均线缺失 → None（回归用例：曾静默丢弃 None 给出误导结论）
    assert indicators.ma_alignment(up, [(5, 1.0), (10, None), (20, 0.9)]) is None


def test_consecutive():
    assert indicators.consecutive([1, 2, 3, 2, 4, 5]) == 2  # 末尾连涨2天
    assert indicators.consecutive([3, 2, 1]) == -2          # 末尾连跌2天
