# -*- coding: utf-8 -*-
"""规则引擎黄金用例：阈值行为、0 值边界、缺失维度归一化、元数据完备性。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from lib import rules  # noqa: E402


def _ctx(**kw):
    base = {
        "trade_date": "2026-01-05",
        "last_close": 3000.0, "pct": 1.0,
        "ma5": 2990.0, "ma10": 2980.0, "ma20": 2970.0, "ma60": 2950.0,
        "ma_alignment": "bull",
        "macd": {"dif": 10.0, "dea": 5.0, "hist": 5.0, "cross": None},
        "rsi14": 55.0, "volatility20": 18.0, "volume_ratio": 1.1,
        "breadth": {"up": 2500, "down": 2000, "up_ratio": 55.0},
        "amount_yi": 12000.0,
        "limit_up_count": 50, "limit_down_count": 5, "max_streak": 3,
        "margin_balance_yi": 18000.0, "margin_change_5d_pct": 0.3,
        "main_flow_yi": -50.0,
        "price_percentile_250": 45.0, "ret20": 2.0, "ret60": 5.0,
        "max_drawdown_250": 10.0,
    }
    base.update(kw)
    return base


def test_risk_level_zero_values_not_defaulted():
    # 回归用例：波动率恰为下界(15)、杠杆变化为 0 时是合法低风险 0 分，
    # 曾因 `or 30` 被误替换为默认中风险值
    lvl, score = rules.risk_level(
        _ctx(volatility20=15.0, margin_change_5d_pct=0.0), {"score": 50})
    assert lvl == "low"
    assert score == 0.0


def test_risk_level_missing_uses_defaults():
    lvl, _ = rules.risk_level(_ctx(volatility20=None, margin_change_5d_pct=None),
                              {"score": 50})
    # 全部缺失 → 0.35*30 + 0.25*20 = 15.5 → low
    assert lvl == "low"


def test_sentiment_renormalize_on_missing_dims():
    s = rules.sentiment_score(_ctx(main_flow_yi=None, margin_change_5d_pct=None))
    assert s["score"] is not None and 0 <= s["score"] <= 100
    assert s["coverage"] < 100  # 缺失维度被归一化，覆盖度下降


def test_signals_have_meta_and_knowledge():
    ctx = _ctx(ma_alignment="bear", rsi14=75.0, volume_ratio=2.0,
               breadth={"up": 100, "down": 4400, "up_ratio": 2.0})
    sigs = rules.detect_signals(ctx)
    assert sigs, "应至少识别出信号"
    ids = {s["id"] for s in sigs}
    assert "ma_bear" in ids
    assert "rsi_overbought" in ids
    for s in sigs:
        assert s["id"] in rules.RULES_META, "信号 %s 缺少元数据" % s["id"]
        assert s.get("knowledge"), "信号 %s 缺少知识点关联" % s["id"]
        assert s["type"] in ("bull", "bear", "neutral")


def test_rules_meta_covers_all_threshold_ids():
    # 元数据键与阈值键存在概念交集（如 rsi_overbought），全部应有元数据
    for key in ("rsi_overbought", "rsi_oversold", "vol_high", "vol_low"):
        assert key in rules.RULES_META


def test_build_full_shape():
    a = rules.build(_ctx())
    for key in ("sentiment", "sentiment_label", "risk_level", "signals",
                "psychology", "discipline", "rules_meta"):
        assert key in a
    assert 0 <= a["sentiment"]["score"] <= 100
