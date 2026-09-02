"""归档逻辑实测 — 用内存 SQLite 验证「结束日期 < 今天」的已发布活动会被归档。

覆盖边界：昨天(应归档) / 今天(不该归档，当天仍在进行) / 明天 / 无结束日期 /
        非 published 状态 / 已归档(幂等)。
"""
import sys
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "backend")

from app.core.database import Base  # noqa: E402
from app.models.store import Store, StoreStatus, DEFAULT_STORE_TYPE  # noqa: E402
from app.services.archive import archive_expired_stores, today_start_cn  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

today = today_start_cn()
cases = [
    ("A-昨天结束", StoreStatus.PUBLISHED.value, today - timedelta(days=1), "archived"),
    ("B-今天结束", StoreStatus.PUBLISHED.value, today, "published"),
    ("C-明天结束", StoreStatus.PUBLISHED.value, today + timedelta(days=1), "published"),
    ("D-无结束日期", StoreStatus.PUBLISHED.value, None, "published"),
    ("E-昨天但草稿", StoreStatus.DRAFT.value, today - timedelta(days=1), "draft"),
    ("F-昨天但已归档", StoreStatus.ARCHIVED.value, today - timedelta(days=1), "archived"),
    ("G-上周结束", StoreStatus.PUBLISHED.value, today - timedelta(days=7), "archived"),
]

for name, status, end, _ in cases:
    db.add(Store(
        id="id_" + name,
        title=name,
        status=status,
        store_type=DEFAULT_STORE_TYPE,
        end_date=end,
        start_date=today - timedelta(days=30),
    ))
db.commit()

n = archive_expired_stores(db, force=True)
print(f"\n本次归档条数: {n}（期望 2：A-昨天结束、G-上周结束）\n")

ok = True
print(f"{'用例':<16}{'期望状态':<12}{'实际状态':<12}{'结果'}")
print("-" * 52)
for name, status, end, expect in cases:
    got = db.query(Store).filter(Store.id == "id_" + name).first().status
    passed = got == expect
    ok = ok and passed
    print(f"{name:<16}{expect:<12}{got:<12}{'PASS' if passed else 'FAIL'}")

# 幂等性：再跑一次不应重复归档
n2 = archive_expired_stores(db, force=True)
print(f"\n重复执行归档条数: {n2}（期望 0，验证幂等）")
ok = ok and n2 == 0

print("\n" + ("ALL_TESTS_PASSED" if ok else "SOME_TESTS_FAILED"))
sys.exit(0 if ok else 1)
