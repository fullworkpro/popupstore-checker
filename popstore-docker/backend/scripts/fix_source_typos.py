"""修正 stores.source 的拼写/中文脏值，并给出修正前后统计。

背景：来源值本应是 manual / crawler / weibo / curated 这类英文枚举，
历史上出现过拼写颠倒的「cruated」、中文「微博」等写法，前端映射表里没有就原样露出英文。

用法：
    python scripts/fix_source_typos.py            # 预览（dry-run，默认）
    python scripts/fix_source_typos.py --apply    # 实际写库

库路径默认 backend/data/popstore.db（与运行配置一致），可用 --db 指定。
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 允许的正常取值（白名单）
VALID = ("manual", "crawler", "weibo", "curated", "wechat", "xiaohongshu", "douyin")

# 脏值 → 标准值（只列需要纠正的；白名单内的原样保留）
FIX = {
    "cruated": "curated",     # 拼写颠倒，最常见
    "curate": "curated",
    "curation": "curated",
    "微博": "weibo",
    "爬虫": "crawler",
    "手动": "manual",
    "策展导入": "curated",
    "": "manual",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写库（默认只预览）")
    ap.add_argument("--db", default=None, help="SQLite 路径，默认 backend/data/popstore.db")
    args = ap.parse_args()

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = args.db or os.path.join(here, "data", "popstore.db")
    if not os.path.exists(db_path):
        raise SystemExit(f"找不到数据库：{db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT source, COUNT(*) FROM stores GROUP BY source")
    before = cur.fetchall()
    print("修正前：")
    for src, n in before:
        print(f"  {src!r:16} × {n}")

    plan = []
    for src, n in before:
        if src is None:
            continue
        if src in VALID:
            continue
        target = FIX.get((src or "").strip().lower()) or FIX.get((src or "").strip())
        if not target:
            print(f"  [跳过] 未知来源值 {src!r}，请在 scripts/fix_source_typos.py 的 FIX 里补一条映射")
            continue
        plan.append((target, src, n))

    if not plan:
        print("\n无需修正。")
        return

    print("\n待修正：")
    for target, src, n in plan:
        print(f"  {src!r} → {target!r}  （{n} 条）")

    if not args.apply:
        print("\n[dry-run] 未写库，加 --apply 生效。")
        return

    for target, src, _ in plan:
        cur.execute("UPDATE stores SET source = ? WHERE source = ?", (target, src))
    conn.commit()
    print("\n已写库。修正后：")
    for src, n in cur.execute("SELECT source, COUNT(*) FROM stores GROUP BY source"):
        print(f"  {src!r:16} × {n}")
    conn.close()


if __name__ == "__main__":
    main()
