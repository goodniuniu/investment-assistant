# -*- coding: utf-8 -*-
"""
主抓取脚本：拉取 A 股市场数据 → 生成 data/market/ 与 data/analysis/。

产出：
    data/market/latest.json          当日完整快照
    data/market/history/YYYY-MM.json 按月归档的每日精简指标（供趋势曲线使用）
    data/analysis/latest.json        规则引擎分析结论

运行：
    python scripts/fetch_market.py            # 抓取 + 分析
    python scripts/fetch_market.py --dry-run  # 只抓取不落盘，用于验证接口

设计要点：
  - 所有接口失败均降级为 None，最终 JSON 中缺失字段标记 null，前端需容忍。
  - 请求节流由 lib/http.py 统一控制，防止触发东财限流。
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import eastmoney as em
from lib import http, indicators, rules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
MARKET_DIR = os.path.join(DATA_DIR, "market")
HIST_DIR = os.path.join(MARKET_DIR, "history")
ANALYSIS_DIR = os.path.join(DATA_DIR, "analysis")
CST = timezone(timedelta(hours=8))


def _log(msg):
    print("[%s] %s" % (datetime.now(CST).strftime("%H:%M:%S"), msg), flush=True)


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
    _log("写入 %s" % os.path.relpath(path, ROOT))


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


# ---------------------------------------------------------------- 数据抓取
def fetch_all():
    """按依赖顺序抓取全部数据。返回 (snapshot, errors)。"""
    errors = []

    _log("① 指数快照 …")
    snap = em.index_snapshot()
    if not snap:
        errors.append("index_snapshot")
        snap = None

    _log("② 指数日K（技术指标用）…")
    klines = {}
    for secid, name in em.KLINE_TARGETS:
        rows = em.kline(secid, limit=250)
        if rows:
            klines[secid] = {"name": name, "rows": rows}
            _log("   %s 获取 %d 条，最新 %s" % (name, len(rows), rows[-1]["date"]))
        else:
            errors.append("kline:%s" % name)
        time.sleep(0.3)

    # 以主基准（上证指数）的最新交易日为准
    trade_date = None
    if "1.000001" in klines:
        trade_date = klines["1.000001"]["rows"][-1]["date"]
    elif snap and snap.get("indexes"):
        trade_date = datetime.now(CST).strftime("%Y-%m-%d")
    _log("   最新交易日：%s" % trade_date)

    _log("③ 涨停板池 …")
    zt = None
    if trade_date:
        zt = em.limit_up_pool(trade_date.replace("-", ""))
        if not zt:
            errors.append("limit_up_pool")
    else:
        errors.append("limit_up_pool:no_trade_date")

    _log("④ 跌停统计 …")
    dt_stat = em.limit_down_count()
    if not dt_stat:
        errors.append("limit_down_count")

    _log("⑤ 大盘资金流 …")
    flow = em.market_fund_flow()
    if not flow:
        errors.append("market_fund_flow")

    _log("⑥ 融资融券 …")
    margin = em.margin_balance()
    if not margin:
        errors.append("margin_balance")

    _log("⑦ 行业板块 …")
    ind_sectors = em.sectors("industry", 20)
    if not ind_sectors:
        errors.append("sectors:industry")

    _log("⑧ 概念板块 …")
    con_sectors = em.sectors("concept", 20)
    if not con_sectors:
        errors.append("sectors:concept")

    snapshot = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "trade_date": trade_date,
        "indexes": (snap or {}).get("indexes"),
        "breadth": (snap or {}).get("breadth"),
        "amount_total": (snap or {}).get("amount_total"),
        "limit_up": zt,
        "limit_down": dt_stat,
        "fund_flow": flow[-10:] if flow else None,
        "margin": margin,
        "sectors": {"industry": ind_sectors, "concept": con_sectors},
        # 保留完整 250 条供指标计算（MA250、年内分位都需要足够样本）；
        # 落盘时会截断为 KEEP_BARS 条，避免 JSON 体积过大。
        "klines": {k: v["rows"] for k, v in klines.items()},
        "errors": errors,
    }
    return snapshot, errors


KEEP_BARS = 120


def trim_for_disk(snapshot, keep=KEEP_BARS):
    """返回用于落盘的快照副本：K 线截断，减小仓库体积与页面加载量。"""
    out = dict(snapshot)
    kl = snapshot.get("klines") or {}
    out["klines"] = {k: v[-keep:] for k, v in kl.items()}
    out["klines_note"] = "仅保留最近 %d 个交易日" % keep
    return out


# ---------------------------------------------------------------- 分析上下文
def build_context(snapshot):
    """把快照整理成规则引擎所需的扁平上下文。以沪深300为趋势基准。"""
    ctx = {
        "trade_date": snapshot.get("trade_date"),
        "generated_at": snapshot.get("generated_at"),
        "errors": snapshot.get("errors") or [],
    }

    # 趋势基准：优先沪深300（覆盖沪深两市龙头），缺失时回落到上证
    bench_id = "1.000300" if "1.000300" in (snapshot.get("klines") or {}) else "1.000001"
    rows = (snapshot.get("klines") or {}).get(bench_id)
    if rows:
        s = indicators.summarize(rows)
        if s:
            ctx.update(s)
            ctx["benchmark"] = "沪深300" if bench_id.endswith("000300") else "上证指数"

    # 指数快照中的当日涨跌幅
    idx = (snapshot.get("indexes") or [])
    sh = next((i for i in idx if i.get("code") == "000001"), None)
    if sh:
        ctx["pct"] = sh.get("pct")
        ctx["last_close"] = ctx.get("last_close") or sh.get("price")

    ctx["breadth"] = snapshot.get("breadth")
    ctx["amount_total"] = snapshot.get("amount_total")
    ctx["amount_yi"] = round(snapshot["amount_total"] / 1e8, 1) if snapshot.get("amount_total") else None

    if snapshot.get("limit_up"):
        ctx["limit_up_count"] = snapshot["limit_up"].get("count")
        ctx["max_streak"] = snapshot["limit_up"].get("max_streak")
    if snapshot.get("limit_down"):
        ctx["limit_down_count"] = snapshot["limit_down"].get("count")

    if snapshot.get("fund_flow"):
        ctx["main_flow_yi"] = round((snapshot["fund_flow"][-1].get("main") or 0) / 1e8, 1)

    margin = snapshot.get("margin") or {}
    series = margin.get("series") or []
    if len(series) >= 2:
        latest = series[0].get("financing_balance")
        prev5 = series[min(5, len(series) - 1)].get("financing_balance")
        if latest and prev5:
            ctx["margin_change_5d_pct"] = round((latest / prev5 - 1) * 100, 3)
        ctx["margin_balance_yi"] = round(latest / 1e8, 1) if latest else None
        ctx["margin_net_buy_yi"] = round((series[0].get("financing_net_buy") or 0) / 1e8, 1)
        ctx["margin_ratio"] = series[0].get("balance_ratio")

    return ctx


# ---------------------------------------------------------------- 历史归档
def append_history(snapshot, analysis):
    """
    把当日精简指标追加到 data/market/history/YYYY-MM.json。
    同一交易日重复运行时覆盖旧记录，保证幂等。
    """
    date = snapshot.get("trade_date")
    if not date:
        return False
    path = os.path.join(HIST_DIR, "%s.json" % date[:7])
    data = _read_json(path) or {"month": date[:7], "days": []}

    sh = next((i for i in (snapshot.get("indexes") or []) if i.get("code") == "000001"), None)
    cyb = next((i for i in (snapshot.get("indexes") or []) if i.get("code") == "399006"), None)
    hs300 = next((i for i in (snapshot.get("indexes") or []) if i.get("code") == "000300"), None)
    b = snapshot.get("breadth") or {}

    record = {
        "date": date,
        "sh_close": sh.get("price") if sh else None,
        "sh_pct": sh.get("pct") if sh else None,
        "cyb_pct": cyb.get("pct") if cyb else None,
        "hs300_pct": hs300.get("pct") if hs300 else None,
        "amount_yi": round(snapshot["amount_total"] / 1e8, 1) if snapshot.get("amount_total") else None,
        "up": b.get("up"),
        "down": b.get("down"),
        "up_ratio": b.get("up_ratio"),
        "limit_up": (snapshot.get("limit_up") or {}).get("count"),
        "limit_down": (snapshot.get("limit_down") or {}).get("count"),
        "max_streak": (snapshot.get("limit_up") or {}).get("max_streak"),
        "main_flow_yi": round((snapshot["fund_flow"][-1].get("main") or 0) / 1e8, 1)
                        if snapshot.get("fund_flow") else None,
        "sentiment": (analysis.get("sentiment") or {}).get("score"),
        "risk_level": analysis.get("risk_level"),
    }

    days = data.get("days") or []
    days = [d for d in days if d.get("date") != date]
    days.append(record)
    days.sort(key=lambda d: d.get("date") or "")
    data["days"] = days
    _write_json(path, data)
    return True


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只抓取校验，不写文件")
    ap.add_argument("--interval", type=float, default=2.0, help="请求最小间隔秒数")
    ap.add_argument("--skip-ai", action="store_true", help="跳过 AI 增强")
    ap.add_argument("--force", action="store_true",
                    help="强制覆盖写入（默认：交易日未变化时跳过，避免非交易日产生空提交）")
    args = ap.parse_args()

    http.set_interval(args.interval)

    if not http.is_network_available():
        _log("网络不可达，直接退出（Actions 中本次任务视为跳过）")
        return 2

    t0 = time.time()
    snapshot, errors = fetch_all()
    _log("抓取完成，耗时 %.1fs，失败项：%s" % (time.time() - t0, errors or "无"))

    if not snapshot.get("indexes") and not snapshot.get("klines"):
        _log("核心数据全部缺失，放弃生成本次结果")
        return 1

    if args.dry_run:
        print(json.dumps(snapshot, ensure_ascii=False)[:1500])
        return 0

    # 幂等保护：非交易日 / 数据无变化时跳过写入,避免空 commit。
    # 这里返回 0(成功跳过)而非非零值——GitHub Actions 不会把退出码 0 当作 failure。
    if not args.force:
        prev = _read_json(os.path.join(MARKET_DIR, "latest.json"))
        if prev and prev.get("trade_date") == snapshot.get("trade_date") and not args.dry_run:
            _log("交易日 %s 的数据已存在且无变化，跳过写入（用 --force 强制覆盖）"
                 % snapshot.get("trade_date"))
            # 仍写出 step summary 友好的注记,便于 GitHub UI 直接看到
            print("::notice::数据未变化，已跳过更新（exit code 0 = 成功跳过）")
            return 0

    ctx = build_context(snapshot)
    analysis = rules.build(ctx)
    analysis.update({
        "trade_date": ctx.get("trade_date"),
        "generated_at": ctx.get("generated_at"),
        "benchmark": ctx.get("benchmark"),
        "market_snapshot": {
            "last_close": ctx.get("last_close"),
            "pct": ctx.get("pct"),
            "amount_yi": ctx.get("amount_yi"),
            "breadth": ctx.get("breadth"),
            "limit_up_count": ctx.get("limit_up_count"),
            "limit_down_count": ctx.get("limit_down_count"),
            "max_streak": ctx.get("max_streak"),
            "main_flow_yi": ctx.get("main_flow_yi"),
            "margin_balance_yi": ctx.get("margin_balance_yi"),
            "margin_change_5d_pct": ctx.get("margin_change_5d_pct"),
            "margin_net_buy_yi": ctx.get("margin_net_buy_yi"),
            "margin_ratio": ctx.get("margin_ratio"),
            "rsi14": ctx.get("rsi14"),
            "volatility20": ctx.get("volatility20"),
            "volume_ratio": ctx.get("volume_ratio"),
            "ma": {k: ctx.get(k) for k in ("ma5", "ma10", "ma20", "ma60")},
            "ma_alignment": ctx.get("ma_alignment"),
            "macd": ctx.get("macd"),
            "price_percentile_250": ctx.get("price_percentile_250"),
            "ret20": ctx.get("ret20"),
            "ret60": ctx.get("ret60"),
            "max_drawdown_250": ctx.get("max_drawdown_250"),
        },
        "context": ctx,
        "data_errors": errors,
        "engine": "rules",
    })

    # AI 增强（可选）：未配置 Key 时静默跳过
    if not args.skip_ai:
        try:
            from ai_comment import enhance
            analysis = enhance(analysis, snapshot, ctx)
        except Exception as e:  # 任何异常都不影响主流程
            _log("AI 增强跳过：%s" % e)

    _write_json(os.path.join(MARKET_DIR, "latest.json"), trim_for_disk(snapshot))
    _write_json(os.path.join(ANALYSIS_DIR, "latest.json"), analysis)
    append_history(snapshot, analysis)

    s = analysis.get("sentiment") or {}
    _log("情绪温度 %s（%s）｜风险 %s｜识别信号 %d 条"
         % (s.get("score"), analysis.get("sentiment_label"),
            analysis.get("risk_level"), len(analysis.get("signals") or [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
