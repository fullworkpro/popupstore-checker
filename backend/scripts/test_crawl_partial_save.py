"""爬虫容错回归测试 —— 中途报错时，已抓到的内容必须已经落草稿（v1.4.25）。

场景：账号 A 抓到 1 条 → 账号 B 抛异常 → 断言 A 的内容已在库里，且日志记为 partial。
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.models.store import Store, StoreStatus, CrawlLog, CrawlerState  # noqa: E402
from app.crawler.weibo_crawler import WeiboCrawler  # noqa: E402

ITEM = {
    "title": "【上海】chiikawa 快闪店",
    "subtitle": "测试用",
    "description": "正文",
    "city": "上海",
    "source_url": "https://weibo.com/1/TESTPARTIAL",
    "tags": "[]",
    "images": "[]",
    "cities": "[]",
    "crawl_meta": "{}",
}


def main() -> int:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    crawler = WeiboCrawler(db, keywords=[], accounts=[], max_pages=1)
    crawler.keyword_interval = 0
    crawler.keyword_enabled = False
    crawler.uid_enabled = True
    crawler._ensure_visitor_sub = lambda: None  # 离线：跳过领凭证

    accounts = [{"name": "A", "uid": "111"}, {"name": "B", "uid": "222"}]
    crawler.accounts = accounts

    def fake_collect(account, since, until):
        if account["name"] == "A":
            return [({"id": 1}, ["chiikawa"], "chiikawa 快闪店 上海", True)]
        raise RuntimeError("模拟账号 B 抓取失败")

    crawler._collect_account_posts = fake_collect
    crawler._parse_mblog = lambda *a, **k: [dict(ITEM)]

    log = crawler.run()

    saved = db.query(Store).filter(Store.source_url == ITEM["source_url"]).all()
    state = db.query(CrawlerState).filter(CrawlerState.source == "weibo").first()
    checks = [
        ("账号 A 抓到的内容已落草稿", len(saved) == 1),
        ("状态为草稿", bool(saved) and saved[0].status == StoreStatus.DRAFT.value),
        ("运行日志记为 partial", log is not None and log.status == "partial"),
        ("错误被记录", log is not None and log.error_count >= 1),
        ("新增数=1", log is not None and log.new_added == 1),
        ("发现数=1", log is not None and log.total_found == 1),
        # 有错就不推进增量水位线，否则没跑到的目标会被永久跳过
        ("有错不推进 last_success_at", state is None or state.last_success_at is None),
        ("last_error 有值", state is not None and bool(state.last_error)),
    ]
    failed = 0
    for name, ok in checks:
        print(("  ✓ " if ok else "  ✗ ") + name)
        failed += 0 if ok else 1
    print(f"\n通过 {len(checks) - failed}/{len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
