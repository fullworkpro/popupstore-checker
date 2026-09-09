#!/usr/bin/env python3
"""策展导入 CLI — 把 WorkBuddy 产出的快闪 JSON 写入待发布队列。

用法（在任意目录执行均可，脚本会自动切到 backend/ 以保证 SQLite 相对路径正确）：
    python scripts/import_curated.py                      # 扫描 backend/data/inbox/*.json
    python scripts/import_curated.py data/inbox/x.json    # 导入单个文件
    python scripts/import_curated.py --dry-run            # 只预览，不落库
    python scripts/import_curated.py --no-archive         # 导入后不移入 done/

导入成功后在后台「待发布」中可见，人工审核确认后再发布。
"""
import argparse
import logging
import os
import sys

# 切到 backend 目录：DATABASE_URL 默认为 sqlite:///./data/popstore.db（相对 CWD）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from app.core.database import SessionLocal  # noqa: E402
from app.crawler.curated_importer import import_file, import_inbox, INBOX_DIR  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def main() -> int:
    ap = argparse.ArgumentParser(description="导入策展快闪 JSON 到待发布队列")
    ap.add_argument("path", nargs="?", default=None,
                    help="单个 JSON 文件路径；省略则扫描 data/inbox/")
    ap.add_argument("--dry-run", action="store_true", help="只预览不落库")
    ap.add_argument("--no-archive", action="store_true", help="导入后不移入 done/")
    args = ap.parse_args()

    os.makedirs(INBOX_DIR, exist_ok=True)
    db = SessionLocal()
    try:
        if args.path:
            total, added, errors = import_file(
                db, args.path, archive=not args.no_archive, dry_run=args.dry_run
            )
            print(f"文件 {args.path}：共 {total} 条，新增 {added} 条")
            for e in errors:
                print(f"  ! {e}")
        else:
            s = import_inbox(db, archive=not args.no_archive, dry_run=args.dry_run)
            print(f"扫描 {INBOX_DIR}：{s['files']} 个文件，共 {s['total']} 条，新增 {s['added']} 条")
            for e in s["errors"]:
                print(f"  ! {e}")
            if s["files"] == 0:
                print(f"提示：把 WorkBuddy 产出的 JSON 放到 {os.path.abspath(INBOX_DIR)} 后重跑")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
