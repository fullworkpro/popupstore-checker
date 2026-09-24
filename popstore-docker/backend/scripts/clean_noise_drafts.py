"""清理历史噪音草稿（运营通知类 + 纯周边上新/线上售卖类）。

判定逻辑直接复用爬虫的 `popup_reject_reason()`，保证与抓取时口径一致。

用法：
    python scripts/clean_noise_drafts.py            # 只列出命中噪音的草稿
    python scripts/clean_noise_drafts.py --apply    # 确认无误后真删
    python scripts/clean_noise_drafts.py --all-drafts  # 列出全部草稿（排查用）

凭据从 backend/data/.admin_password 读取，不外传。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)

from app.crawler.weibo_crawler import popup_reject_reason  # noqa: E402

BASE = os.environ.get("POPSTORE_API", "http://192.168.50.147:9114/api/v1")
DATA_DIR = os.path.join(BACKEND_ROOT, "data")


def _req(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"[HTTP {e.code}] {method} {path}: {e.read().decode()[:400]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"[网络错误] {method} {path}: {e.reason}")


def login() -> str:
    pw_path = os.path.join(DATA_DIR, ".admin_password")
    if not os.path.exists(pw_path):
        raise SystemExit(f"缺少凭据文件：{pw_path}")
    with open(pw_path, encoding="utf-8") as f:
        password = f.read().strip()
    data = _req("POST", "/auth/login", body={"username": "admin", "password": password})
    token = data.get("access_token") or data.get("token")
    if not token:
        raise SystemExit(f"登录未返回 token：{str(data)[:200]}")
    return token


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行删除")
    ap.add_argument("--all-drafts", action="store_true", help="列出全部草稿")
    ap.add_argument("--status", default="draft")
    args = ap.parse_args()

    token = login()
    print(f"[登录] OK  {BASE}")

    page = 1
    drafts: list[dict] = []
    while True:
        data = _req("GET", f"/admin/stores?status={args.status}&page=1&page_size=100", token)
        # 接口无分页翻页需求时总量 <=100，直接取回即可
        drafts = data.get("items") or data.get("results") or []
        break

    print(f"[查询] status={args.status} 共 {len(drafts)} 条")

    hits = []
    for s in drafts:
        title = (s.get("title") or "").strip()
        desc = (s.get("description") or "")[:200]
        text = title + " " + desc
        # 解析后的字段不一定还带「快闪」二字（标题已改为【城市】起头），
        # 只在这种情况下做噪音判定，避免把正常草稿误判删除。
        reason = popup_reject_reason(text) if "快闪" in text else None
        if args.all_drafts:
            flag = "NOISE" if reason else "     "
            print(f"  {flag} #{s.get('id')} [{s.get('source')}] {title}  {reason or ''}")
        if reason:
            hits.append((s, reason))

    print(f"\n[命中噪音] {len(hits)} 条")
    for s, reason in hits:
        print(f"  #{s.get('id')} [{s.get('source')}] {s.get('title')}  <- {reason}")

    if not hits:
        return
    if not args.apply:
        print("\n（dry-run）确认无误后加 --apply 执行删除")
        return

    ok = fail = 0
    for s, _ in hits:
        try:
            _req("DELETE", f"/admin/stores/{s.get('id')}", token)
            print(f"  [删除] #{s.get('id')} {s.get('title')}")
            ok += 1
        except SystemExit as e:
            print(f"  [失败] #{s.get('id')}: {e}")
            fail += 1
    print(f"\n[完成] 删除成功 {ok} 条，失败 {fail} 条")


if __name__ == "__main__":
    sys.exit(main())
