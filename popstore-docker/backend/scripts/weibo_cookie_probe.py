"""微博 Cookie 健康体检（给 automation / 人工排查用）。

做的事和浏览器每次打开页面时一样：打一次轻量接口让票据滑动续期，然后报告登录态。

用法：
    python scripts/weibo_cookie_probe.py            # 用后台/本机 Cookie 文件探一次
    python scripts/weibo_cookie_probe.py --keep     # 只续期，不抓任何内容（推荐每天跑）

退出码：0=已登录 / 1=失效 / 2=无法判定（网络或 WAF）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from app.core.config import settings  # noqa: E402
from app.crawler.weibo_crawler import (  # noqa: E402
    COOKIE_JAR_PATH, WeiboCrawler,
)


def main() -> int:
    ck = (settings.CRAWLER_WEIBO_COOKIE or "").strip()
    if not ck:
        ck_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", ".weibo_cookie")
        ck_path = os.path.normpath(ck_path)
        if os.path.exists(ck_path):
            ck = open(ck_path, encoding="utf-8").read().strip()
    if not ck:
        print("❌ 没找到 Cookie：请先在后台「爬虫」页粘贴，或放到 backend/data/.weibo_cookie")
        return 2

    crawler = WeiboCrawler.__new__(WeiboCrawler)  # 不连库，只用网络层
    crawler.keywords = []
    crawler.accounts = []
    crawler.max_pages = 1
    crawler.request_interval = 2
    crawler.keyword_interval = 2
    crawler.max_retries = 1
    crawler.retry_backoff = 2
    crawler._last_req_ts = 0.0
    crawler._auto_sub = False
    crawler._manual_cookie = False
    crawler._manual_ck = ""
    import requests

    crawler.session = requests.Session()
    crawler.session.headers.update({
        "User-Agent": settings.CRAWLER_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://m.weibo.cn/",
    })
    crawler.cookie = ck
    crawler._apply_manual_cookie()

    login = crawler._probe_login()
    crawler._save_cookie_jar(ck)

    jar_hint = "已启用自动续期（%s）" % COOKIE_JAR_PATH
    if login is True:
        print(f"✅ 登录态正常｜{jar_hint}")
        return 0
    if login is False:
        crawler._drop_cookie_jar()
        print("❌ Cookie 已失效（data.login=false），请重新登录 m.weibo.cn 后复制整串 Cookie")
        return 1
    print("⚠️ 无法判定（请求失败，可能是网络或 WAF 432），稍后重试")
    return 2


if __name__ == "__main__":
    sys.exit(main())
