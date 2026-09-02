"""快闪类型筛选实测 — 验证 /mini/stores 的 store_type 过滤，尤其是历史 NULL 行兜底。

关键回归点：store_type 列是后加的，老行值为 NULL。筛选「联名快闪」时
必须把 NULL 一并算进来，否则这些老数据会在小程序里凭空消失。
"""
import sys
from datetime import datetime, timedelta

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "backend")

from app.core.database import Base  # noqa: E402
from app.models.store import (  # noqa: E402
    Store,
    StoreStatus,
    STORE_TYPE_VALUES,
    DEFAULT_STORE_TYPE,
)
from app.services.archive import today_start_cn  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

today = today_start_cn()

# 数据：显式类型各一条 + 一条 store_type 为 NULL 的老数据
rows = [
    ("t_popup", "popup"),
    ("t_exhibition", "exhibition"),
    ("t_restaurant", "restaurant"),
    ("t_legacy_null", None),   # 老数据，列还没加时创建的
    ("t_junk", "not_a_type"),  # 脏数据，后端写入时会兜底，这里模拟极端情况
]
for sid, stype in rows:
    db.add(Store(
        id=sid,
        title=sid,
        status=StoreStatus.PUBLISHED.value,
        store_type=stype,
        start_date=today,
        end_date=today + timedelta(days=10),
    ))
db.commit()


def filter_by_type(query, store_type):
    """与 mini.py list_stores 中完全相同的过滤表达式。"""
    if store_type and store_type in STORE_TYPE_VALUES:
        if store_type == DEFAULT_STORE_TYPE:
            return query.filter(
                (Store.store_type == store_type) | (Store.store_type.is_(None))
            )
        return query.filter(Store.store_type == store_type)
    return query


def ids(store_type):
    q = db.query(Store).filter(Store.status == StoreStatus.PUBLISHED.value)
    q = filter_by_type(q, store_type)
    return sorted(r.id for r in q.all())


cases = [
    ("popup", ["t_legacy_null", "t_popup"]),          # 显式 popup + NULL 兜底
    ("exhibition", ["t_exhibition"]),
    ("restaurant", ["t_restaurant"]),
    (None, ["t_exhibition", "t_junk", "t_legacy_null", "t_popup", "t_restaurant"]),
    ("bogus", ["t_exhibition", "t_junk", "t_legacy_null", "t_popup", "t_restaurant"]),
]

ok = True
print(f"\n{'筛选类型':<14}{'期望命中':<46}{'实际命中':<46}{'结果'}")
print("-" * 122)
for stype, expect in cases:
    got = ids(stype)
    passed = got == sorted(expect)
    ok = ok and passed
    print(f"{str(stype):<14}{str(sorted(expect)):<46}{str(got):<46}{'PASS' if passed else 'FAIL'}")

print("\n" + ("ALL_TESTS_PASSED" if ok else "SOME_TESTS_FAILED"))
sys.exit(0 if ok else 1)
