# -*- coding: utf-8 -*-
"""
历史分析回填：用仓库内已有的数据离线重建过去各交易日的分析结论。

数据来源（全部离线，不发网络请求）：
    data/market/latest.json        指数 K 线（约 120 个交易日）
    data/market/history/YYYY-MM.json 每日宽度/涨跌停/成交额等薄指标

限制：
    融资融券、主力资金流没有逐日历史，回填日的这两个维度缺失，
    情绪分按剩余维度重新归一化，记录标记 backfilled=True 以示区别。

运行：
    python scripts/backfill_analysis.py            # 回填缺失日期（不覆盖已有）
    python scripts/backfill_analysis.py --force    # 覆盖已有的非回填记录
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import indicators, rules
from fetch_market import ANALYSIS_HIST_DIR, HIST_DIR, CST, _read_json, append_analysis_history

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_market_history():
    """合并全部月度历史文件，返回 {date: record}。"""
    records = {}
    hist_dir = os.path.join(ROOT, HIST_DIR) if os.path.isabs(HIST_DIR) else HIST_DIR
    if not os.path.isdir(hist_dir):
        return records
    for fn in sorted(os.listdir(hist_dir)):
        if not fn.endswith(".json"):
            continue
        data = _read_json(os.path.join(hist_dir, fn)) or {}
        for d in data.get("days") or []:
            if d.get("date"):
                records[d["date"]] = d
    return records


def load_analysis_history():
    """已归档的分析历史，返回 {date: record}。"""
    records = {}
    if not os.path.isdir(ANALYSIS_HIST_DIR):
        return records
    for fn in sorted(os.listdir(ANALYSIS_HIST_DIR)):
        if not fn.endswith(".json"):
            continue
        data = _read_json(os.path.join(ANALYSIS_HIST_DIR, fn)) or {}
        for d in data.get("days") or []:
            if d.get("date"):
                records[d["date"]] = d
    return records


def build_ctx_for_date(date, bench_rows, bench_name, hist_rec):
    """用截至 date 的 K 线切片 + 当日薄指标构造规则引擎上下文。"""
    rows = [r for r in bench_rows if r.get("date") <= date]
    ctx = {"trade_date": date, "errors": []}
    if len(rows) >= 30:  # 指标至少需要一个月的样本
        s = indicators.summarize(rows)
        if s:
            ctx.update(s)
    ctx["benchmark"] = bench_name

    # 当日涨跌与收盘：优先用 K 线本身（与基准口径一致）
    if len(rows) >= 2:
        prev, last = rows[-2], rows[-1]
        if last.get("close") and prev.get("close"):
            ctx["last_close"] = last["close"]
            ctx["pct"] = round((last["close"] / prev["close"] - 1) * 100, 2)

    # 宽度 / 涨跌停 / 成交额来自月度归档
    if hist_rec:
        b = {}
        if hist_rec.get("up") is not None:
            b["up"] = hist_rec["up"]
        if hist_rec.get("down") is not None:
            b["down"] = hist_rec["down"]
        if hist_rec.get("up_ratio") is not None:
            b["up_ratio"] = hist_rec["up_ratio"]
        ctx["breadth"] = b or None
        ctx["amount_yi"] = hist_rec.get("amount_yi")
        ctx["limit_up_count"] = hist_rec.get("limit_up")
        ctx["limit_down_count"] = hist_rec.get("limit_down")
        ctx["max_streak"] = hist_rec.get("max_streak")

    # 融资融券 / 主力资金：无逐日历史，保持缺失（规则引擎自动归一化）
    return ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="覆盖已存在的非回填记录（默认只回填缺失日期）")
    ap.add_argument("--min-bars", type=int, default=30,
                    help="生成分析所需的最少 K 线数量")
    args = ap.parse_args()

    market = _read_json(os.path.join(ROOT, "data", "market", "latest.json"))
    if not market or not market.get("klines"):
        print("缺少 data/market/latest.json 的 K 线数据，先运行 fetch_market.py")
        return 1

    # 基准与实时管线保持一致：优先沪深300
    klines = market["klines"]
    bench_id = "1.000300" if "1.000300" in klines else "1.000001"
    bench_name = "沪深300" if bench_id == "1.000300" else "上证指数"
    bench_rows = klines[bench_id]
    dates = [r["date"] for r in bench_rows]
    print("基准 %s，K 线覆盖 %s ~ %s（%d 根）"
          % (bench_name, dates[0], dates[-1], len(bench_rows)))

    hist = load_market_history()
    done = load_analysis_history()

    written = skipped = 0
    for i, date in enumerate(dates):
        rows_n = i + 1
        if rows_n < args.min_bars:
            continue
        if date in done and not (args.force and not done[date].get("backfilled")):
            skipped += 1
            continue
        if date not in hist:
            # 没有当日宽度数据也能算，只是情绪覆盖度低一些；继续生成
            pass

        ctx = build_ctx_for_date(date, bench_rows, bench_name, hist.get(date))
        analysis = rules.build(ctx)
        analysis["trade_date"] = date
        analysis["generated_at"] = datetime.now(CST).isoformat(timespec="seconds")
        analysis["engine"] = "rules-backfill"
        append_analysis_history(analysis, backfilled=True)
        written += 1

    print("回填完成：写入 %d 天，跳过已有 %d 天" % (written, skipped))
    print("提示：回填日缺少融资/资金流维度，命中率统计时会与实时数据区分展示")
    return 0


if __name__ == "__main__":
    sys.exit(main())
