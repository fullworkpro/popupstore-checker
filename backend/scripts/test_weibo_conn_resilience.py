"""微博爬虫「连接中断」韧性回归测试（离线，不发真实请求）。

覆盖 v1.4.21 的三处修复：
  1. _get_index 遇到 requests 网络异常（RemoteDisconnected / Connection aborted / Timeout）
     会退避重试，而不是直接抛给上层导致整个关键词被放弃；
  2. 重试耗尽后返回 None（放弃该目标），不抛异常；
  3. _throttle 在两次请求间隔超过 CONN_IDLE_RESET 时主动丢弃连接池，
     避免复用已被对端关闭的 keep-alive 连接；
  4. Session 装载了 urllib3 连接层重试适配器。

运行（在 backend/ 目录下）：
  python scripts/test_weibo_conn_resilience.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock  # noqa: E402

import requests  # noqa: E402

from app.crawler.weibo_crawler import (  # noqa: E402
    CONN_IDLE_RESET,
    WeiboCrawler,
)

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (f" — {extra}" if extra else ""))


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def new_crawler():
    c = WeiboCrawler(db=None)
    c.request_interval = 0.0
    c.retry_backoff = 0.0
    c.max_retries = 3
    c._last_req_ts = 0.0
    return c


def test_retry_then_success():
    print("\n[1] 连接中断后重试成功")
    c = new_crawler()
    ok_payload = {"ok": 1, "data": {"cards": [{"mblog": {"id": 1}}]}}
    boom = requests.exceptions.ConnectionError(
        "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
    )
    with mock.patch.object(c.session, "get", side_effect=[boom, _Resp(ok_payload)]) as g, \
            mock.patch("app.crawler.weibo_crawler.time.sleep") as slp:
        cards = c._get_index("100103type%3D1%26q%3Dtest", 1)
    check("第 1 次断连后自动重试并拿到 cards", cards == ok_payload["data"]["cards"], f"cards={cards}")
    check("确实发起了 2 次请求", g.call_count == 2, f"call_count={g.call_count}")
    check("重试前做了退避等待", slp.call_count >= 1, f"sleep={slp.call_count}")


def test_exhaust_returns_none():
    print("\n[2] 重试耗尽后返回 None（不抛异常）")
    c = new_crawler()
    boom = requests.exceptions.ConnectionError("Connection aborted.")
    with mock.patch.object(c.session, "get", side_effect=boom) as g, \
            mock.patch("app.crawler.weibo_crawler.time.sleep"):
        try:
            cards = c._get_index("cid", 1)
            raised = None
        except Exception as e:  # noqa: BLE001
            cards, raised = None, e
    check("未向外抛异常", raised is None, f"raised={raised!r}")
    check("返回 None 表示放弃该目标", cards is None)
    check("共尝试 1+3 次", g.call_count == 4, f"call_count={g.call_count}")


def test_throttle_idle_reset():
    print("\n[3] 长空闲后丢弃连接池")
    c = new_crawler()
    with mock.patch.object(c.session, "close") as cl:
        c._last_req_ts = time.time() - (CONN_IDLE_RESET + 5)
        c._throttle()
        idle_closed = cl.call_count
    check(f"空闲 > {CONN_IDLE_RESET}s 时 session.close() 被调用", idle_closed == 1, f"count={idle_closed}")

    c2 = new_crawler()
    with mock.patch.object(c2.session, "close") as cl2:
        c2._last_req_ts = time.time()  # 刚请求过
        c2._throttle()
        busy_closed = cl2.call_count
    check("短间隔内不重建连接（不误伤正常节流）", busy_closed == 0, f"count={busy_closed}")


def test_retry_adapter_mounted():
    print("\n[4] 连接层重试适配器已装载")
    c = new_crawler()
    ad = c.session.get_adapter("https://m.weibo.cn")
    r = getattr(ad, "max_retries", None)
    check("adapter 带 Retry 配置", r is not None and getattr(r, "total", 0) >= 1,
          f"total={getattr(r, 'total', None)}")


def main():
    print("== 微博爬虫连接韧性测试 ==")
    test_retry_then_success()
    test_exhaust_returns_none()
    test_throttle_idle_reset()
    test_retry_adapter_mounted()
    print(f"\n结果：{len(PASS)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        for f in FAIL:
            print("  ✗ " + f)
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
