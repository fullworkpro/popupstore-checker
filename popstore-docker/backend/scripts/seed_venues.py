#!/usr/bin/env python3
"""场馆优先配置种子 — 把 venues.json 的场馆/品牌写入 crawler_config。

背景：按 IP 名搜快闪召回率低（IP 写法杂、官方公告未必带全称）；
场馆是固定点位，公告必发且自带定位信息，故改为场馆优先。

用法（任意目录执行均可，脚本会切到 backend/）：
    python scripts/seed_venues.py                 # 预览：只打印将要写入的内容
    python scripts/seed_venues.py --apply         # 真正写入 crawler_config
    python scripts/seed_venues.py --apply --replace   # 覆盖式写入（默认是与现有值合并去重）
    python scripts/seed_venues.py --accounts-only # 只写 weibo_accounts，不动关键词

注意：
  - 默认「合并」而非「覆盖」，不会清掉后台页面已配置的关键词/账号。
  - 场馆 UID 大多留空（venues.json 中 weibo_uid=""），写入后爬虫会跳过；
    请在后台「爬虫」页面补齐数字 UID，账号监控模式才真正生效。
  - 账号监控（UID）模式限流远低于全站关键词搜索，是首选模式。
"""
import argparse
import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from app.core.database import SessionLocal  # noqa: E402
from app.crawler.config_store import get_config, apply_config_update  # noqa: E402

VENUES_JSON = os.path.join(BACKEND_DIR, "app", "crawler", "venues.json")


def build_from_venues(data: dict) -> tuple:
    """由 venues.json 生成 (关键词列表, 账号列表)。"""
    keywords, accounts = [], []

    def add_kw(name):
        if name and name not in keywords:
            keywords.append(name)

    for v in data.get("venues", []):
        # 只把「主场馆」作为搜索词；watch 级场馆太泛（如「北京路」容易误伤）
        if v.get("tier") == "primary" or v.get("acg_main"):
            add_kw(v["name"])
        if v.get("weibo_name"):
            accounts.append({"name": v["weibo_name"], "uid": v.get("weibo_uid") or ""})

    for b in data.get("brands", []):
        add_kw(b["name"])
        if b.get("weibo_name"):
            accounts.append({"name": b["weibo_name"], "uid": b.get("weibo_uid") or ""})

    return keywords, accounts


def main() -> int:
    ap = argparse.ArgumentParser(description="写入场馆优先配置")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认只预览）")
    ap.add_argument("--replace", action="store_true", help="覆盖而非合并")
    ap.add_argument("--accounts-only", action="store_true", help="只写账号列表")
    args = ap.parse_args()

    with open(VENUES_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    new_kw, new_acc = build_from_venues(data)

    db = SessionLocal()
    try:
        cfg = get_config(db)
        old_kw = json.loads(cfg.weibo_keywords or "[]")
        old_acc = json.loads(cfg.weibo_accounts or "[]")

        if args.replace:
            kw = new_kw
        else:
            kw = old_kw + [k for k in new_kw if k not in old_kw]

        if args.replace:
            acc = new_acc
        else:
            known = {a.get("name") for a in old_acc}
            acc = old_acc + [a for a in new_acc if a["name"] not in known]

        print("── 关键词（weibo_keywords）──")
        for k in kw:
            mark = "+" if k not in old_kw else " "
            print(f" {mark} {k}")
        print(f" 合计 {len(kw)} 个（原 {len(old_kw)} → 新增 {len(kw) - len(old_kw)}）")

        print("\n── 监控账号（weibo_accounts）──")
        for a in acc:
            mark = "+" if a["name"] not in {x.get("name") for x in old_acc} else " "
            uid = a.get("uid") or "⚠ 待填UID（爬虫会跳过）"
            print(f" {mark} {a['name']}  uid={uid}")
        print(f" 合计 {len(acc)} 个（原 {len(old_acc)} → 新增 {len(acc) - len(old_acc)}）")

        empty_uid = [a["name"] for a in acc if not a.get("uid")]
        if empty_uid:
            print(f"\n⚠ {len(empty_uid)}/{len(acc)} 个账号缺 UID，账号监控不会生效。")
            print("  请在后台「爬虫」页面，或直接在 app/crawler/venues.json 中补齐数字 UID 后重跑。")

        if not args.apply:
            print("\n[预览模式] 未写入。加 --apply 生效。")
            return 0

        payload = {"weibo_accounts": acc}
        if not args.accounts_only:
            payload["weibo_keywords"] = kw
        apply_config_update(db, payload)
        print("\n[已写入] crawler_config 更新完成。")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
