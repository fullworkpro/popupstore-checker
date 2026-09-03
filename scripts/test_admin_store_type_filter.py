"""后台「快闪类型」筛选实测 — 验证 /admin/stores 的 store_type 过滤与类型中文名返回。

回归点：
1. store_type 列是后加的，老行值为 NULL。筛「联名快闪」时必须把 NULL 一并算进来，
   否则这些老数据会在后台列表里凭空消失（与 mini.py 同一套口径）。
2. 非法类型值不当筛选条件（返回全部），避免脏参数导致列表空白、误以为没数据。
3. StoreResponse 必须带上 store_type_label，否则前端兜底会把所有店都显示成「联名快闪」。
"""
import sys
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "backend")

from app.core.database import Base  # noqa: E402
from app.models.store import (  # noqa: E402
    Store,
    StoreStatus,
    STORE_TYPE_VALUES,
    DEFAULT_STORE_TYPE,
)
from app.schemas.schemas import StoreResponse  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

rows = [
    ("t_popup", "popup"),
    ("t_exhibition", "exhibition"),
    ("t_restaurant", "restaurant"),
    ("t_legacy_null", None),   # 老数据，列还没加时创建的
    ("t_junk", "not_a_type"),  # 脏数据，模拟极端情况
]
for sid, stype in rows:
    db.add(Store(
        id=sid,
        title=sid,
        status=StoreStatus.DRAFT.value,
        store_type=stype,
        start_date=today,
        end_date=today + timedelta(days=10),
    ))
db.commit()


def filter_by_type(query, store_type):
    """与 admin.py list_stores 中完全相同的过滤表达式。"""
    if store_type and store_type in STORE_TYPE_VALUES:
        if store_type == DEFAULT_STORE_TYPE:
            return query.filter(
                (Store.store_type == store_type) | (Store.store_type.is_(None))
            )
        return query.filter(Store.store_type == store_type)
    return query


def ids(store_type):
    q = filter_by_type(db.query(Store), store_type)
    return sorted(r.id for r in q.all())


ok = True

# ── 1) 筛选行为 ──
cases = [
    ("popup", ["t_legacy_null", "t_popup"]),   # 显式 popup + NULL 兜底
    ("exhibition", ["t_exhibition"]),
    ("restaurant", ["t_restaurant"]),
    (None, ["t_exhibition", "t_junk", "t_legacy_null", "t_popup", "t_restaurant"]),
    ("", ["t_exhibition", "t_junk", "t_legacy_null", "t_popup", "t_restaurant"]),
    ("bogus", ["t_exhibition", "t_junk", "t_legacy_null", "t_popup", "t_restaurant"]),
]
print(f"\n{'筛选类型':<14}{'期望命中':<48}{'实际命中':<48}{'结果'}")
print("-" * 126)
for stype, expect in cases:
    got = ids(stype)
    passed = got == sorted(expect)
    ok = ok and passed
    print(f"{str(stype):<14}{str(sorted(expect)):<48}{str(got):<48}{'PASS' if passed else 'FAIL'}")

# ── 2) 类型中文名随响应返回 ──
label_cases = [
    ("t_popup", "联名快闪"),
    ("t_exhibition", "特展"),
    ("t_restaurant", "联名餐厅"),
    ("t_legacy_null", "联名快闪"),   # NULL 兜底成默认类型
]
print(f"\n{'行':<18}{'期望类型名':<16}{'实际类型名':<16}{'结果'}")
print("-" * 60)
for sid, expect in label_cases:
    store = db.query(Store).filter(Store.id == sid).first()
    resp = StoreResponse.model_validate(store)
    got = resp.store_type_label
    passed = got == expect
    ok = ok and passed
    print(f"{sid:<18}{expect:<16}{str(got):<16}{'PASS' if passed else 'FAIL'}")

print("\n" + ("ALL_TESTS_PASSED" if ok else "SOME_TESTS_FAILED"))
sys.exit(0 if ok else 1)
