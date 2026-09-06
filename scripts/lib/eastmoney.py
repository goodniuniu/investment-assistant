# -*- coding: utf-8 -*-
"""
东方财富公开接口封装。

接口无需注册、无需 token。所有函数在网络异常、限流或数据缺失时返回 None（或空结构），
由上层做降级处理——这是本项目能在无人值守的 Actions 里长期稳定运行的前提。

字段速查（东财 push2 f 系列）：
    f2 现价   f3 涨跌幅%   f4 涨跌额   f5 成交量(手)   f6 成交额(元)
    f12 代码  f13 市场(1沪/0深)  f14 名称
    f104 上涨家数  f105 下跌家数  f106 平盘家数
日K（push2his）klines 单条格式：
    日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
"""

from . import http

UT = "bd1d9ddb04089700cf9c27f6f7426281"
DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"
ZTPOOL = "https://push2ex.eastmoney.com/getTopicZTPool"

# 行情快照的多镜像地址，按顺序尝试。
# push2delay 是延迟行情节点，接口格式与 push2 完全一致，但访问压力小得多、
# 限流概率显著更低；本项目只在收盘后抓取日级数据，延迟 15 分钟无影响。
# push2 作为兜底，最后再试数字节点 82.push2。
PUSH2_HOSTS = [
    "https://push2delay.eastmoney.com/api/qt",
    "https://push2.eastmoney.com/api/qt",
    "https://82.push2.eastmoney.com/api/qt",
]
PUSH2HIS = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
# 日K的备用源（新浪，字段顺序与东财不同，需单独适配）
SINA_KLINE = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
              "CN_MarketData.getKLineData")


def _push2(path):
    """把 /api/qt 下的相对路径展开为全部镜像地址。"""
    return [h + path for h in PUSH2_HOSTS]

# 关注的核心指数：secid -> 展示名
INDEXES = [
    ("1.000001", "上证指数", "sh"),
    ("0.399001", "深证成指", "sz"),
    ("0.399006", "创业板指", "cyb"),
    ("1.000688", "科创50", "kc50"),
    ("1.000300", "沪深300", "hs300"),
    ("0.399905", "中证500", "zz500"),
    ("0.399852", "中证1000", "zz1000"),
    ("1.000016", "上证50", "sz50"),
]

# 用于计算技术指标的代表性指数（控制请求数量，避免限流）
KLINE_TARGETS = [
    ("1.000001", "上证指数"),
    ("0.399006", "创业板指"),
    ("1.000300", "沪深300"),
    ("0.399905", "中证500"),
    ("1.000688", "科创50"),
]


def _num(v):
    """东财部分字段在数据缺失时返回 '-' 或非数字，统一转成 float 或 None。"""
    if v is None or v == "-" or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def index_snapshot():
    """
    核心指数快照，含市场宽度（涨跌家数）。
    沪深两市的涨跌家数分别取自上证指数与深证成指快照的 f104/f105/f106。
    """
    secids = ",".join(s for s, _, _ in INDEXES)
    path = ("/ulist.np/get?fltt=2&invt=2&ut=%s&secids=%s"
            "&fields=f1,f2,f3,f4,f5,f6,f12,f13,f14,f104,f105,f106" % (UT, secids))
    js = http.get_json_any(_push2(path))
    if not js or not isinstance(js.get("data"), dict):
        return None

    diff = js["data"].get("diff") or []
    out = []
    for d in diff:
        out.append({
            "code": d.get("f12"),
            "name": d.get("f14"),
            "price": _num(d.get("f2")),
            "pct": _num(d.get("f3")),
            "change": _num(d.get("f4")),
            "volume": _num(d.get("f5")),
            "amount": _num(d.get("f6")),
            "up": _num(d.get("f104")),
            "down": _num(d.get("f105")),
            "flat": _num(d.get("f106")),
        })

    # 合并沪深两市宽度：沪市取上证，深市取深证成指
    sh = next((x for x in out if x["code"] == "000001"), None)
    sz = next((x for x in out if x["code"] == "399001"), None)
    breadth = None
    if sh and sz and None not in (sh["up"], sz["up"], sh["down"], sz["down"]):
        up = int(sh["up"] + sz["up"])
        down = int(sh["down"] + sz["down"])
        flat = int((sh["flat"] or 0) + (sz["flat"] or 0))
        total = up + down + flat
        breadth = {
            "up": up, "down": down, "flat": flat, "total": total,
            "up_ratio": round(up / total * 100, 2) if total else None,
            "up_down_ratio": round(up / down, 3) if down else None,
        }

    # 两市合计成交额（元）
    amount_total = None
    if sh and sz and sh.get("amount") and sz.get("amount"):
        amount_total = sh["amount"] + sz["amount"]

    return {"indexes": out, "breadth": breadth, "amount_total": amount_total}


def kline(secid, limit=250):
    """日K线（前复权）。返回 [{date, open, close, high, low, volume, amount, pct, turnover}]。"""
    url = ("%s?secid=%s&klt=101&fqt=1&lmt=%d&end=20500101&ut=%s"
           "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           % (PUSH2HIS, secid, limit, UT))
    js = http.get_json(url)
    if js and isinstance(js.get("data"), dict):
        rows = []
        for line in js["data"].get("klines") or []:
            p = line.split(",")
            if len(p) < 11:
                continue
            rows.append({
                "date": p[0],
                "open": _num(p[1]),
                "close": _num(p[2]),
                "high": _num(p[3]),
                "low": _num(p[4]),
                "volume": _num(p[5]),
                "amount": _num(p[6]),
                "amplitude": _num(p[7]),
                "pct": _num(p[8]),
                "turnover": _num(p[10]),
            })
        if rows:
            return rows

    # 备用源：腾讯（含成交量）→ 新浪（东财历史接口限流时的降级方案）
    return _kline_tencent(secid, limit) or _kline_sina(secid, limit)


def _kline_tencent(secid, limit):
    """
    腾讯日K备用源。返回字段：[日期, 开, 收, 高, 低, 成交量]，顺序与东财一致。
    腾讯不返回成交额，amount 置 None。
    """
    market, code = secid.split(".", 1)
    symbol = ("sh" if market == "1" else "sz") + code
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           "?param=%s,day,,,%d,qfq" % (symbol, limit))
    js = http.get_json(url)
    if not js or not isinstance(js.get("data"), dict):
        return None
    node = js["data"].get(symbol) or {}
    arr = node.get("qfqday") or node.get("day") or []
    rows, prev_close = [], None
    for p in arr:
        if len(p) < 6:
            continue
        close = _num(p[2])
        if close is None:
            continue
        pct = round((close / prev_close - 1) * 100, 3) if prev_close else None
        prev_close = close
        rows.append({
            "date": p[0][:10],
            "open": _num(p[1]),
            "close": close,
            "high": _num(p[3]),
            "low": _num(p[4]),
            "volume": _num(p[5]),
            "amount": None,      # 腾讯接口不返回成交额
            "amplitude": None,
            "pct": pct,
            "turnover": None,
        })
    return rows or None


def _kline_sina(secid, limit):
    """新浪日K备用源。secid 形如 1.000001 / 0.399006。"""
    market, code = secid.split(".", 1)
    symbol = ("sh" if market == "1" else "sz") + code
    url = "%s?symbol=%s&scale=240&ma=no&datalen=%d" % (SINA_KLINE, symbol, limit)
    js = http.get_json(url)
    if not js or not isinstance(js, list):
        return None
    rows = []
    prev_close = None
    for d in js:
        day = (d.get("day") or "")[:10]
        close = _num(d.get("close"))
        if not day or close is None:
            continue
        pct = round((close / prev_close - 1) * 100, 3) if prev_close else None
        prev_close = close
        rows.append({
            "date": day,
            "open": _num(d.get("open")),
            "close": close,
            "high": _num(d.get("high")),
            "low": _num(d.get("low")),
            "volume": _num(d.get("volume")),
            "amount": None,      # 新浪接口不返回成交额
            "amplitude": None,
            "pct": pct,
            "turnover": None,
        })
    return rows or None


def limit_up_pool(trade_date):
    """
    涨停板池。trade_date 格式 YYYYMMDD，必须是交易日，非交易日返回 None。
    返回 {count, max_streak, industries:[{name,count}], list:[...]}
    """
    url = ("%s?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt"
           "&Pageindex=0&pagesize=200&sort=fbt%%3Aasc&date=%s" % (ZTPOOL, trade_date))
    js = http.get_json(url)
    if not js or not isinstance(js.get("data"), dict):
        return None
    data = js["data"]
    pool = data.get("pool") or []
    industries = {}
    max_streak = 0
    for s in pool:
        hy = s.get("hybk") or "其他"
        industries[hy] = industries.get(hy, 0) + 1
        lbc = s.get("lbc") or 0
        if isinstance(lbc, (int, float)) and lbc > max_streak:
            max_streak = int(lbc)
    top_ind = sorted(industries.items(), key=lambda kv: -kv[1])[:8]
    return {
        "count": data.get("tc") if data.get("tc") is not None else len(pool),
        "max_streak": max_streak,
        "industries": [{"name": k, "count": v} for k, v in top_ind],
        "list": [{"code": s.get("c"), "name": s.get("n"),
                  "streak": s.get("lbc"), "industry": s.get("hybk")} for s in pool[:30]],
    }


def limit_down_count():
    """
    跌停家数。东财跌停池接口不稳定，改用全A按涨幅升序取前 200 只，
    统计跌幅 <= -9.7% 的家数。count 为总家数（10cm/20cm 板跌停均满足该阈值，
    不重复累计）；count_20 为其中 20cm 板的细分，count_10 = count - count_20。
    """
    path = ("/clist/get?pn=1&pz=200&po=0&np=1&fltt=2&invt=2&fid=f3&ut=%s"
            "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f3,f12,f14" % UT)
    js = http.get_json_any(_push2(path))
    if not js or not isinstance(js.get("data"), dict):
        return None
    diff = js["data"].get("diff") or []
    n10 = sum(1 for d in diff if (_num(d.get("f3")) is not None and _num(d.get("f3")) <= -9.7))
    n20 = sum(1 for d in diff if (_num(d.get("f3")) is not None and _num(d.get("f3")) <= -19.7))
    return {"count": n10, "count_10": n10 - n20, "count_20": n20}


def market_fund_flow():
    """大盘资金流（主力/超大单/大单/中单/小单净流入，单位元）。取最近若干日。"""
    path = ("/stock/fflow/kline/get?lmt=30&klt=101&ut=%s"
            "&secid=1.000001&secid2=0.399001"
            "&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
            % UT)
    js = http.get_json_any(_push2(path))
    if not js or not isinstance(js.get("data"), dict):
        return None
    rows = []
    for line in js["data"].get("klines") or []:
        p = line.split(",")
        if len(p) < 6:
            continue
        rows.append({
            "date": p[0],
            "main": _num(p[1]),      # 主力净流入
            "small": _num(p[2]),     # 小单净流入
            "mid": _num(p[3]),       # 中单净流入
            "big": _num(p[4]),       # 大单净流入
            "huge": _num(p[5]),      # 超大单净流入
        })
    return rows or None


def margin_balance():
    """融资融券市场统计。RZYE 融资余额、RZJME 融资净买入、LTSZ 流通市值、RZYEZB 融资余额占比。"""
    url = ("%s?reportName=RPTA_RZRQ_LSHJ&columns=ALL&sortColumns=dim_date&sortTypes=-1"
           "&pageSize=10&pageNumber=1&source=WEB&client=WEB" % DATACENTER)
    js = http.get_json(url)
    if not js or not isinstance(js.get("result"), dict):
        return None
    data = js["result"].get("data") or []
    if not data:
        return None
    series = []
    for d in data:
        date = (d.get("DIM_DATE") or "")[:10]
        series.append({
            "date": date,
            "financing_balance": _num(d.get("RZYE")),      # 融资余额(元)
            "financing_net_buy": _num(d.get("RZJME")),     # 融资净买入(元)
            "float_cap": _num(d.get("LTSZ")),              # 流通市值(元)
            "balance_ratio": _num(d.get("RZYEZB")),        # 融资余额/流通市值 %
        })
    return {"latest": series[0], "series": series}


def sectors(kind="industry", top=15):
    """
    板块涨幅榜。kind: industry(行业, m:90 t:2) / concept(概念, m:90 t:3)。
    同时取涨幅榜前 top 与资金流入前 top。
    """
    fs = "m:90+t:2+f:!50" if kind == "industry" else "m:90+t:3+f:!50"
    fields = "f2,f3,f12,f14,f62,f104,f105,f128,f136,f140,f184"
    path = ("/clist/get?pn=1&pz=%d&po=1&np=1&fltt=2&invt=2&fid=f3&ut=%s&fs=%s&fields=%s"
            % (top, UT, fs, fields))
    js = http.get_json_any(_push2(path))
    if not js or not isinstance(js.get("data"), dict):
        return None
    out = []
    for d in js["data"].get("diff") or []:
        out.append({
            "code": d.get("f12"),
            "name": d.get("f14"),
            "pct": _num(d.get("f3")),
            "main_flow": _num(d.get("f62")),
            "up": _num(d.get("f104")),
            "down": _num(d.get("f105")),
            "leader": d.get("f128"),
            "leader_pct": _num(d.get("f136")),
            "leader_code": d.get("f140"),
        })
    return out or None
