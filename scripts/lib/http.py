# -*- coding: utf-8 -*-
"""
HTTP 请求层。

东方财富公开接口对高频访问会限流（表现为连接被直接断开、RemoteDisconnected），
因此这里统一做三件事：
  1. 全局最小请求间隔（节流），避免触发限流；
  2. 失败后指数退避重试；
  3. 所有异常收敛为 None，由上层决定降级策略，绝不让单个接口失败中断整条流水线。
"""

import json
import random
import socket
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "close",
}

# 模块级节流状态：保证任意两次请求之间至少间隔 MIN_INTERVAL 秒
_MIN_INTERVAL = 2.0
_last_call = [0.0]
_stats = {"ok": 0, "fail": 0}


def set_interval(seconds):
    global _MIN_INTERVAL
    _MIN_INTERVAL = max(0.0, float(seconds))


def stats():
    return dict(_stats)


def _throttle():
    wait = _MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def get_text(url, tries=4, timeout=20, base_delay=3.0):
    """GET 文本，失败重试。全部失败返回 None。"""
    for attempt in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "ignore")
            _stats["ok"] += 1
            return body
        except Exception:
            _stats["fail"] += 1
            if attempt == tries - 1:
                return None
            # 指数退避 + 抖动，避免多个失败请求同时重试
            time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 1.5))
    return None


def get_json(url, tries=4, timeout=20, base_delay=3.0):
    """GET 并解析 JSON。解析失败或业务码异常返回 None。"""
    text = get_text(url, tries=tries, timeout=timeout, base_delay=base_delay)
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def get_json_any(urls, tries=2, timeout=20, base_delay=2.0):
    """
    依次尝试多个镜像地址，返回首个成功解析的 JSON。

    存在意义：东财 push2 主域名对高频访问限流严重（直接断开连接），
    而 push2delay（延迟行情）节点压力小得多且接口格式完全一致。
    日级数据场景（收盘后抓取）下延迟行情与实时行情等价，因此优先走 delay 节点。
    """
    for url in urls:
        js = get_json(url, tries=tries, timeout=timeout, base_delay=base_delay)
        if js:
            return js
    return None


def is_network_available(host="push2.eastmoney.com", timeout=8):
    """探测网络连通性，供 Actions 在离线环境下快速降级。"""
    try:
        socket.create_connection((host, 443), timeout=timeout).close()
        return True
    except OSError:
        return False


class FetchError(Exception):
    pass
