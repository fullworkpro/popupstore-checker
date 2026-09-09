"""后台「导入 JSON」接口实测 — POST /admin/stores/import-json

回归点：
1. dry_run=true 只校验不落库，逐条给出 ok / warn / dup / error。
2. 缺原文链接 / 日期 / 地址只警告不拦截（用户要靠链接传图，不能拦）。
3. 缺 title → error，不导入。
4. 重复判定：source_url 精确 + 标题指纹（限待发布范围），重复不计入新增。
5. 裸数组 [...] 与 {items:[...]} 两种写法都要支持（content-hunter 输出格式不固定）。
6. 空 items / 非法格式 → 400。
"""
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "backend")

from fastapi import HTTPException  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.store import Store, StoreStatus  # noqa: E402
from app.crawler.curated_importer import validate_items, import_items  # noqa: E402
from app.api.admin import import_json_stores  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  OK   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def new_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()


SAMPLE = [
    {  # 全字段，应 ok
        "title": "《孤独摇滚》原画主题快闪",
        "ip_name": "孤独摇滚", "venue": "静安大悦城", "city": "上海",
        "address": "静安大悦城南座3F", "start_date": "2026-09-04", "end_date": "2026-09-27",
        "source_url": "https://weibo.com/a/1", "confidence": 0.9,
    },
    {  # 缺链接/日期/地址 → warn，但仍可导入
        "title": "叛逆的鲁鲁修「秘林」主题快闪", "city": "上海",
    },
    {  # 缺 title → error
        "ip_name": "无标题条目", "city": "上海",
    },
    {  # 与本文件第 1 条标题重复（加空格标点）→ dup
        "title": "《孤独摇滚》原画主题快闪 ", "city": "上海",
    },
]

print("── 1. validate_items 分级 ──")
db = new_db()
res = validate_items(db, SAMPLE, "test-batch")
lv = [r["level"] for r in res]
check("4 条全部返回", len(res) == 4, f"got {len(res)}")
check("第1条 ok", lv[0] == "ok", f"got {lv[0]} issues={res[0]['issues']}")
check("第2条 warn（缺链接不拦截）", lv[1] == "warn", f"got {lv[1]}")
check("第2条提示含原文链接", any("原文链接" in i for i in res[1]["issues"]), str(res[1]["issues"]))
check("第3条 error（缺 title）", lv[2] == "error", f"got {lv[2]}")
check("第4条 dup（批次内标题重复）", lv[3] == "dup", f"got {lv[3]}")
check("校验阶段未落库", db.query(Store).count() == 0)

print("\n── 2. import_json_stores dry_run ──")
db = new_db()
out = import_json_stores(payload={"batch": "b1", "items": SAMPLE}, dry_run=True, db=db, _=None)
check("total=4", out["total"] == 4, str(out["total"]))
check("importable=2（ok+warn）", out["importable"] == 2, str(out["importable"]))
check("invalid=1", out["invalid"] == 1, str(out["invalid"]))
check("duplicated=1", out["duplicated"] == 1, str(out["duplicated"]))
check("added=0（dry_run 不落库）", out["added"] == 0, str(out["added"]))
check("库仍为空", db.query(Store).count() == 0)

print("\n── 3. 真正导入 ──")
db = new_db()
out = import_json_stores(payload={"batch": "b1", "items": SAMPLE}, dry_run=False, db=db, _=None)
check("added=2", out["added"] == 2, str(out["added"]))
check("库中有 2 条", db.query(Store).count() == 2, str(db.query(Store).count()))
check("均为 DRAFT", all(s.status == StoreStatus.DRAFT.value for s in db.query(Store).all()))
check("source=curated", all(s.source == "curated" for s in db.query(Store).all()))
check("store_type 默认 popup", all(s.store_type == "popup" for s in db.query(Store).all()))

print("\n── 4. 重复导入 → 新增 0 ──")
out2 = import_json_stores(payload={"batch": "b1", "items": SAMPLE}, dry_run=False, db=db, _=None)
check("二次 added=0", out2["added"] == 0, str(out2["added"]))
check("二次 duplicated≥2", out2["duplicated"] >= 2, str(out2["duplicated"]))
check("库中仍 2 条", db.query(Store).count() == 2, str(db.query(Store).count()))

print("\n── 5. 裸数组写法 ──")
db = new_db()
out3 = import_json_stores(payload=[{"title": "裸数组条目", "city": "广州"}], dry_run=False, db=db, _=None)
check("裸数组可导入 added=1", out3["added"] == 1, str(out3.get("added")))

print("\n── 6. 非法输入 → 400 ──")
for bad, label in [({}, "空对象"), ([], "空数组"), ("字符串", "字符串"), ({"items": "x"}, "items 非数组")]:
    try:
        import_json_stores(payload=bad, dry_run=True, db=new_db(), _=None)
        check(f"{label} 应报 400", False, "未抛异常")
    except HTTPException as e:
        check(f"{label} 报 400", e.status_code == 400, f"got {e.status_code}")

print("\n" + "=" * 46)
print(f"通过 {passed} 项，失败 {failed} 项")
print("ALL_TESTS_PASSED" if failed == 0 else "SOME_TESTS_FAILED")
sys.exit(0 if failed == 0 else 1)
