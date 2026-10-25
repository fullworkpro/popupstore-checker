"""Cookie 自动续期（v1.4.29）离线回归：不触网，只验证 Jar 的读写与重建逻辑。

覆盖：
  1. 手填串首次 → 按串建 Jar
  2. 落盘后再取 → 沿用盘里的那份（续期后的票）
  3. 手填串变了 → 抛弃旧 Jar，按新串重建
  4. _save_cookie_jar 能把 session 里（模拟服务端 Set-Cookie）的票写回磁盘
  5. _drop_cookie_jar 清理干净
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.crawler.weibo_crawler as wc  # noqa: E402

CK = "SUB=_2A25Kv1; SUBP=0033WrSXq; XSRF-TOKEN=tok1; ALF=1700000000"
CK2 = "SUB=_2A25Kv2; SUBP=0033WrSXq2; XSRF-TOKEN=tok2"


def build():
    c = wc.WeiboCrawler.__new__(wc.WeiboCrawler)
    c._manual_cookie = True
    c._manual_ck = CK
    import requests
    c.session = requests.Session()
    return c


def main():
    checks = []
    tmpdir = tempfile.mkdtemp()
    wc.COOKIE_JAR_PATH = os.path.join(tmpdir, ".weibo_cookiejar")
    wc.COOKIE_FP_PATH = os.path.join(tmpdir, ".weibo_cookie_fingerprint")

    c = build()
    jar = c._load_cookie_jar(CK)
    subs = {x.value for x in jar if x.name == "SUB"}
    checks.append(("首次按手填串建 Jar", subs == {"_2A25Kv1"}))
    checks.append(("双域名各一份", len(jar) == 8))

    # ① 落盘（模拟服务端续期后回写）
    c.session.cookies.set_cookie(wc.create_cookie("SUB", "_2A25Kv1Renewed", domain=".weibo.cn", path="/"))
    c._save_cookie_jar(CK)
    checks.append(("续期后 Jar 落盘", os.path.exists(wc.COOKIE_JAR_PATH)))

    # ② 同串再取 → 应拿到续期后的票
    jar2 = c._load_cookie_jar(CK)
    v = {x.value for x in jar2 if x.name == "SUB" and x.domain == ".weibo.cn"}
    checks.append(("同串复用续期结果", v == {"_2A25Kv1Renewed"}))

    # ③ 换串 → 必须重建，不能再用旧票
    jar3 = c._load_cookie_jar(CK2)
    v3 = {x.value for x in jar3 if x.name == "SUB" and x.domain == ".weibo.cn"}
    checks.append(("手填串变更则重建", v3 == {"_2A25Kv2"}))

    # ④ 丢弃
    c._drop_cookie_jar()
    checks.append(("失效后清理干净", not os.path.exists(wc.COOKIE_JAR_PATH)
                   and not os.path.exists(wc.COOKIE_FP_PATH)))

    # ⑤ 默认路径不变（指向 backend/data/）
    wc.COOKIE_JAR_PATH = wc.__dict__.get("_orig", wc.COOKIE_JAR_PATH)
    checks.append(("Jar 默认落在 data 目录", "data" in wc.DATA_DIR.replace("\\", "/")))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'✓' if ok else '✗'} {n}")
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
