"""微博爬虫「凭证优先级」回归测试（v1.4.9）。

背景：旧逻辑是「访客 SUB 优先，手填 Cookie 仅在 genvisitor2 失败时兜底」，且领到访客 SUB 后
会 clear 掉手填 Cookie。实测访客 SUB 只能破 432（HTTP 200）但内容仍是 ok=-100，
导致「后台填了登录 Cookie 却依然 0 条」。v1.4.9 改为手填 Cookie 优先。

覆盖：
  1) 填了 Cookie → 直接用，不联网领访客 SUB
  2) 未填 Cookie → 自动领访客 SUB 生效
  3) 两者都无 → 返回 False，裸请求
  4) 空白字符串视为未填
  5) 手填生效时 cookie jar 被清空，headers["Cookie"] 唯一权威
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crawler.weibo_crawler import WeiboCrawler  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def make(cookie, visitor_ret=None):
    """构造爬虫实例；visitor_ret 为 None 表示模拟 genvisitor2 失败。"""
    c = WeiboCrawler.__new__(WeiboCrawler)          # 跳过 __init__，避免 DB/网络依赖
    c.cookie = cookie
    c._auto_sub = False
    c._manual_cookie = False
    c._last_req_ts = 0.0
    import requests
    c.session = requests.Session()
    c.visited = []

    def _fake_fetch():
        c.visited.append("fetch_visitor_sub")
        return visitor_ret

    c._fetch_visitor_sub = _fake_fetch
    return c


print("== 1) 填了 Cookie：直接用登录态，不领访客 SUB ==")
ck = "SUB=_2Axxx; SUBP=0033yyy"
c = make(ck, visitor_ret=("sub_auto", "subp_auto"))
ok = c._ensure_visitor_sub()
check("返回 True", ok is True)
check("headers 里是手填 Cookie", c.session.headers.get("Cookie") == ck,
      f"got={c.session.headers.get('Cookie')!r}")
check("未调用 genvisitor2", c.visited == [], f"visited={c.visited}")
check("_manual_cookie=True", c._manual_cookie is True)
check("_auto_sub=False", c._auto_sub is False)

print("== 2) 未填 Cookie：自动领访客 SUB ==")
c = make(None, visitor_ret=("sub_auto", "subp_auto"))
ok = c._ensure_visitor_sub()
check("返回 True", ok is True)
check("调用了 genvisitor2", c.visited == ["fetch_visitor_sub"], f"visited={c.visited}")
check("headers 无手工 Cookie", "Cookie" not in c.session.headers)
check("cookie jar 里有 SUB", c.session.cookies.get("SUB") == "sub_auto")
check("cookie jar 里有 SUBP", c.session.cookies.get("SUBP", domain=".weibo.com") == "subp_auto"
      or c.session.cookies.get("SUBP") == "subp_auto")
check("_auto_sub=True", c._auto_sub is True)
check("_manual_cookie=False", c._manual_cookie is False)

print("== 3) 未填 Cookie 且领取失败：裸请求 ==")
c = make(None, visitor_ret=None)
ok = c._ensure_visitor_sub()
check("返回 False", ok is False)
check("headers 无 Cookie", "Cookie" not in c.session.headers)
check("_auto_sub=False", c._auto_sub is False)
check("_manual_cookie=False", c._manual_cookie is False)

print("== 4) 空白字符串视为未填 ==")
c = make("   ", visitor_ret=("sub_auto", "subp_auto"))
ok = c._ensure_visitor_sub()
check("返回 True", ok is True)
check("走了访客分支", c._auto_sub is True and c._manual_cookie is False)

print("== 5) 手填生效时清空 cookie jar ==")
c = make(ck, visitor_ret=("sub_auto", "subp_auto"))
c.session.cookies.set("SUB", "old_value", domain=".weibo.com")
c._ensure_visitor_sub()
check("jar 已清空", len(list(c.session.cookies)) == 0,
      f"jar={[(x.name, x.value) for x in c.session.cookies]}")

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
