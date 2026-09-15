"""本机（宽带出口）跑微博爬虫，把命中的快闪直接推送到后台待发布。

为什么需要它：NAS 容器里跑微博爬虫会全量 HTTP 432，而同一出口 IP 的本机可以正常访问，
所以把「抓取」搬到本机，只把结果通过后台接口推进去。落库后是 status=DRAFT，
在「快闪店管理」里审核后小程序才可见。

用法示例：
  # 1) 先试跑，只生成 JSON、不推送（推荐首次验证用）
  python scripts/crawl_local_push.py --dry-run --max-accounts 2 --pages 1

  # 2) 正式跑：抓最近 3 天，推到后台
  python scripts/crawl_local_push.py --days 3

  # 3) 只推送已生成的 JSON（跳过抓取）
  python scripts/crawl_local_push.py --from-json backend/data/outbox/weibo-20260916-2000.json

凭据（都不入库，需自己建）：
  后台密码 : backend/data/.admin_password（一行），或环境变量 POPSTORE_ADMIN_PASSWORD
  微博Cookie: backend/data/.weibo_cookie（一行，浏览器登录后复制的整串，务必含 SUB）
  两者也可分别用 --password / --cookie 直接传（不推荐，会留在命令行历史里）。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_BASE = "http://192.168.50.147:9114/api/v1"
PASS_FILE = BACKEND_DIR / "data" / ".admin_password"
COOKIE_FILE = BACKEND_DIR / "data" / ".weibo_cookie"
OUTBOX = BACKEND_DIR / "data" / "outbox"


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ── 后台交互 ────────────────────────────────────────────────
def login(base: str, username: str, password: str, timeout=20) -> str:
    import urllib.parse
    import urllib.request
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{base}/auth/login", data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    token = d.get("access_token")
    if not token:
        raise RuntimeError(f"登录失败：响应里没有 access_token（{str(d)[:120]}）")
    return token


def api_get(base: str, token: str, path: str, timeout=20):
    import urllib.request
    req = urllib.request.Request(f"{base}{path}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def api_post_json(base: str, token: str, path: str, payload: dict, timeout=120):
    import urllib.request
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}", data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def read_secret(cli_value, file_path: Path, env_name: str, what: str) -> str:
    """优先命令行 → 环境变量 → 文件（文件需自己建，不入库）。"""
    if cli_value:
        return cli_value.strip()
    v = os.getenv(env_name)
    if v:
        return v.strip()
    if file_path.exists():
        v = file_path.read_text(encoding="utf-8").strip()
        if v:
            return v
    raise SystemExit(
        f"缺少{what}：请把内容写入 {file_path}（一行，已加入 .gitignore），"
        f"或设置环境变量 {env_name}，或用命令行参数传入。"
    )


# ── 抓取 ────────────────────────────────────────────────────
def build_crawler(accounts, keywords, cookie, lookback_days, pages, uid_on, kw_on):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.store import Base
    from app.crawler.weibo_crawler import WeiboCrawler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    return WeiboCrawler(
        db=db, keywords=keywords or [], accounts=accounts or [],
        cookie=cookie, lookback_days=lookback_days, max_pages=pages,
        uid_enabled=uid_on, keyword_enabled=kw_on,
    )


def collect(crawler, accounts, keywords, since, until, interval, kw_on):
    """只收集不落库：复用爬虫的解析逻辑，返回待推送条目。"""
    items, errors = [], []
    for acc in accounts:
        name = acc.get("name") or acc.get("uid")
        try:
            hits = crawler._collect_account_posts(acc, since, until)
            for mb, matched, text, account_mode in hits:
                it = crawler._parse_mblog(mb, matched, text, account_mode=account_mode)
                if it:
                    items.append(it)
            log(f"  账号 {name}: 命中 {len(hits)} 条")
        except Exception as e:
            errors.append(f"[{name}] {e}")
            log(f"  账号 {name}: 失败 {e}")
        time.sleep(interval)

    if kw_on and keywords:
        for kw in keywords:
            try:
                hits = crawler._collect_posts(kw, since, until)
                for mb, matched, text, account_mode in hits:
                    it = crawler._parse_mblog(mb, matched, text, account_mode=account_mode)
                    if it:
                        items.append(it)
                log(f"  关键词 {kw}: 命中 {len(hits)} 条")
            except Exception as e:
                errors.append(f"[{kw}] {e}")
                log(f"  关键词 {kw}: 失败 {e}")
            time.sleep(interval)
    return items, errors


def normalize(items):
    """datetime → 字符串，保证可 JSON 序列化并符合 import-json 的入参口径。"""
    out = []
    for it in items:
        it = dict(it)
        for k in ("start_date", "end_date"):
            v = it.get(k)
            if isinstance(v, datetime):
                it[k] = v.strftime("%Y-%m-%d")
            elif v is None:
                it.pop(k, None)
        it.setdefault("store_type", "popup")
        out.append(it)
    return out


def summarize(res):
    """统计 import-json 返回结果。"""
    rows = res.get("results") or res.get("items") or []
    if not rows:
        return {"total": 0}
    cnt = {}
    for r in rows:
        lvl = r.get("level") or r.get("status") or "?"
        cnt[lvl] = cnt.get(lvl, 0) + 1
    return {"total": len(rows), **cnt}


# ── 主流程 ──────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", default=None)
    ap.add_argument("--token", default=None, help="直接给 JWT，跳过登录（调试用）")
    ap.add_argument("--cookie", default=None)
    ap.add_argument("--days", type=int, default=3, help="抓取最近 N 天的微博")
    ap.add_argument("--max-accounts", type=int, default=0, help="只跑前 N 个账号（0=全部）")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--interval", type=int, default=8, help="账号之间的间隔秒数")
    ap.add_argument("--keywords", action="store_true", help="同时跑全站关键词（限流重，默认关）")
    ap.add_argument("--dry-run", action="store_true", help="只抓不推")
    ap.add_argument("--from-json", default=None, help="跳过抓取，直接推送该 JSON 文件")
    ap.add_argument("--out", default=None, help="输出 JSON 路径（默认 data/outbox/时间戳.json）")
    args = ap.parse_args()

    if args.from_json:
        payload = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        items = payload.get("items", payload if isinstance(payload, list) else [])
        log(f"从文件载入 {len(items)} 条：{args.from_json}")
    else:
        if args.token:
            token = args.token
            log("使用传入的 token，跳过登录")
        else:
            password = read_secret(args.password, PASS_FILE, "POPSTORE_ADMIN_PASSWORD", "后台密码")
            log("登录后台…")
            token = login(args.base_url, args.username, password)
        cfg = api_get(args.base_url, token, "/admin/crawler/config")
        accounts = [a for a in (cfg.get("weibo_accounts") or [])
                    if str(a.get("uid") or "").strip().isdigit()]
        if args.max_accounts:
            accounts = accounts[:args.max_accounts]
        keywords = cfg.get("weibo_keywords") or []
        lookback = cfg.get("lookback_days") or args.days
        uid_on = bool(cfg.get("weibo_uid_enabled", True))
        # Cookie：优先命令行/文件；后台接口若某天返回明文则以其为准
        cookie = None
        try:
            cookie = read_secret(args.cookie, COOKIE_FILE, "WEIBO_COOKIE", "微博 Cookie")
        except SystemExit:
            if not cfg.get("has_cookie"):
                raise
            log("本地没有 Cookie 文件，但后台已配置 Cookie（本脚本无法读取明文，将尝试无 Cookie 抓取）")
        log(f"后台配置：{len(accounts)} 个有效账号 / 关键词 {len(keywords)} 个 / 回看 {lookback} 天")

        until = datetime.now()
        since = until - timedelta(days=args.days)
        log(f"抓取窗口：{since:%Y-%m-%d %H:%M} ~ {until:%Y-%m-%d %H:%M}")

        crawler = build_crawler(accounts, keywords, cookie, lookback, args.pages,
                                uid_on, args.keywords)
        crawler._ensure_visitor_sub()
        items, errors = collect(crawler, accounts, keywords, since, until,
                                args.interval, args.keywords)
        items = normalize(items)
        log(f"共命中 {len(items)} 条，错误 {len(errors)} 条")
        for e in errors[:5]:
            log("  " + e)

    # 落盘
    OUTBOX.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else OUTBOX / f"weibo-{datetime.now():%Y%m%d-%H%M}.json"
    out_path.write_text(
        json.dumps({"batch": f"local-crawl-{datetime.now():%Y%m%d-%H%M}", "items": items},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    log(f"已写入 {out_path}")

    if args.dry_run or not items:
        if not items:
            log("没有命中任何条目，跳过推送。")
        else:
            log("--dry-run：已跳过推送。")
        return 0

    if args.token:
        token = args.token
    else:
        password = read_secret(args.password, PASS_FILE, "POPSTORE_ADMIN_PASSWORD", "后台密码")
        token = login(args.base_url, args.username, password)
    payload = {"batch": f"local-crawl-{datetime.now():%Y%m%d-%H%M}", "items": items}
    log(f"推送 {len(items)} 条到后台…")
    res = api_post_json(args.base_url, token, "/admin/stores/import-json?dry_run=false", payload)
    log("推送结果：" + json.dumps(summarize(res), ensure_ascii=False))
    for r in (res.get("results") or [])[:10]:
        log(f"  - [{r.get('level')}] {r.get('title')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
