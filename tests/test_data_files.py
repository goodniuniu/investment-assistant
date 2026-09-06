# -*- coding: utf-8 -*-
"""数据文件结构校验：防止畸形 JSON 被提交后污染前端。"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


def test_analysis_latest_shape():
    a = _load("data/analysis/latest.json")
    assert DATE_RE.match(a["trade_date"]), "trade_date 应为 YYYY-MM-DD"
    assert 0 <= a["sentiment"]["score"] <= 100
    assert a["risk_level"] in ("low", "medium", "high")
    for s in a["signals"]:
        assert s["id"] and s["type"] in ("bull", "bear", "neutral")
        assert s["title"] and s["lesson"]


def test_market_latest_shape():
    m = _load("data/market/latest.json")
    assert isinstance(m["indexes"], list) and m["indexes"]
    for i in m["indexes"]:
        assert "name" in i and "pct" in i
    klines = m["klines"]
    assert "1.000001" in klines or "1.000300" in klines
    for rows in klines.values():
        assert rows and DATE_RE.match(rows[-1]["date"])


def test_content_knowledge_closed_refs():
    k = _load("data/content/knowledge.json")
    items = k["items"] if isinstance(k, dict) else k
    ids = {i["id"] for i in items}
    assert len(ids) == len(items), "知识条目 id 必须唯一"
    for i in items:
        for r in i.get("related") or []:
            assert r in ids, "知识 %s 引用了不存在的 %s" % (i["id"], r)


def test_content_psychology_shape():
    p = _load("data/content/psychology.json")
    assert len(p["biases"]) == 10
    bias_ids = {b["id"] for b in p["biases"]}
    for q in p["assessment"]["questions"]:
        assert q["bias"] in bias_ids, "自评题 %s 指向不存在的偏差" % q["id"]


def test_content_books_shape():
    b = _load("data/content/books.json")
    assert len(b["books"]) == 50, "首批书单应为 50 本"
    kids = {i["id"] for i in _load("data/content/knowledge.json")["items"]}
    cats = {c["id"] for c in b["categories"]}
    ids = set()
    for x in b["books"]:
        assert x["id"] not in ids, "书籍 id 重复: %s" % x["id"]
        ids.add(x["id"])
        assert x["category"] in cats
        for f in ("title", "author", "summary", "guide", "practice", "key_ideas", "level"):
            assert x.get(f), "书籍 %s 缺少字段 %s" % (x["id"], f)
        for ref in x.get("knowledge") or []:
            assert ref in kids, "书籍 %s 引用了不存在的知识条目 %s" % (x["id"], ref)


def test_history_files_idempotent_dates():
    for sub in ("market/history", "analysis/history"):
        d = os.path.join(ROOT, "data", sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".json"):
                continue
            data = _load("data/%s/%s" % (sub, fn))
            dates = [x["date"] for x in data["days"]]
            assert len(dates) == len(set(dates)), "%s/%s 存在重复日期" % (sub, fn)
            assert dates == sorted(dates), "%s/%s 日期未排序" % (sub, fn)


def test_analysis_history_signals_valid():
    d = os.path.join(ROOT, "data", "analysis", "history")
    if not os.path.isdir(d):
        return
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        data = _load("data/analysis/history/%s" % fn)
        for day in data["days"]:
            assert 0 <= (day.get("sentiment") or 50) <= 100
            for s in day.get("signals") or []:
                assert s["type"] in ("bull", "bear", "neutral")
                assert s["id"] and s["title"]
