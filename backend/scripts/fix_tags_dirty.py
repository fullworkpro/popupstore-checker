"""修复历史脏 tags —— 默认 dry-run，确认无误后加 --apply 才真正写库。

背景：curated_importer 曾用 `list(item.get("tags") or [])`，tags 为 JSON 字符串时
被逐字符拆成 ['[', '"', '吉', '伊', '卡', '哇', '"', ']']，且自动追加「快闪」和厂商名。
代码侧已修（_coerce_tags + 不再补通用词），本脚本用于清洗**已入库**的历史条目。

判定为「脏」的规则：
  · 含 JSON 碎片（[ ] { } " '）
  · 含长度为 1 的碎片（拆字特征）
  · 含通用词「快闪」「二次元」
  · 含与 organizer 相同的项（厂商名当标签）

重算策略：优先用 weibo_crawler.derive_ip_tags(title, organizer) 推作品名；
推导不出则退化为「去掉脏项后的剩余标签」。
"""
import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.crawler.curated_importer import _coerce_tags          # noqa: E402
from app.crawler.weibo_crawler import derive_ip_tags           # noqa: E402
from scripts.crawl_local_push import api_get, login, read_secret, PASS_FILE  # noqa: E402

JUNK = {"[", "]", "{", "}", '"', "'"}
GENERIC = {"快闪", "快闪店", "二次元", "联名", "动漫"}


def is_dirty(tags, organizer: str) -> bool:
    if not tags:
        return False
    for t in tags:
        if t in JUNK:
            return True
        if len(t) <= 1 and not t.isalnum():
            return True
        if len(t) == 1:
            return True          # 单字 = 拆字特征
        if t in GENERIC:
            return True
        if organizer and t == organizer.strip():
            return True
    return False


def rebuild(title: str, organizer: str, tags) -> list:
    new = derive_ip_tags(title, organizer, [])
    if new:
        return new
    return [t for t in (tags or []) if t not in JUNK and t not in GENERIC and len(t) > 1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://192.168.50.147:9114/api/v1")
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", default=None)
    ap.add_argument("--status", default="draft,published")
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只打印）")
    args = ap.parse_args()

    password = read_secret(args.password, PASS_FILE, "POPSTORE_ADMIN_PASSWORD", "后台密码")
    token = login(args.base_url, args.username, password)

    import urllib.request
    dirty = []
    for st in args.status.split(","):
        page = 1
        while True:
            d = api_get(args.base_url, token,
                        f"/admin/stores?status={st}&page={page}&page_size=50")
            rows = d.get("items") or []
            for s in rows:
                raw = s.get("tags")
                try:
                    tags = json.loads(raw) if isinstance(raw, str) else (raw or [])
                except Exception:
                    tags = _coerce_tags(raw)
                if is_dirty(tags, s.get("organizer") or ""):
                    dirty.append((s, tags))
            if len(rows) < 50 or page >= 20:
                break
            page += 1

    print(f"扫描到脏标签条目：{len(dirty)} 条\n")
    for s, tags in dirty:
        title = s.get("title") or ""
        new = rebuild(title, s.get("organizer") or "", tags)
        print(f"[{s.get('status')}] {title[:34]}")
        print(f"   旧: {tags}")
        print(f"   新: {new}")
        if args.apply:
            payload = json.dumps({"tags": json.dumps(new, ensure_ascii=False)}).encode()
            req = urllib.request.Request(
                f"{args.base_url}/admin/stores/{s.get('id')}", data=payload, method="PUT",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=30).read()
            print("   → 已更新")

    if not args.apply and dirty:
        print("\n（dry-run，未写库。确认无误后加 --apply）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
