"""多城市导入回归测试。

覆盖 normalize/_build_cities 的三种写法：
  1) cities 对象数组（带 district/address）
  2) cities 字符串数组（只有城市名）
  3) 旧的单值 city / district / address
并验证主城市取 cities[0]、预览标签「上海 等 3 城」。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.crawler.curated_importer import _build_cities, normalize  # noqa: E402

FAILED = []


def check(name, got, expect):
    ok = got == expect
    if not ok:
        FAILED.append(name)
    flag = "OK  " if ok else "FAIL"
    print(f"  {flag} {name}: got={got!r} expect={expect!r}")


print("=== 1. cities 对象数组（多城带地址）===")
item = {
    "title": "三丽鸥全国巡展",
    "cities": [
        {"city": "上海", "district": "静安区", "address": "静安大悦城 3F"},
        {"city": "广州", "district": "天河区", "address": "正佳广场 1F"},
        {"city": "成都", "district": "锦江区", "address": "IFS 5F"},
    ],
    "start_date": "2026-09-20",
    "end_date": "2026-10-20",
}
lst, city, dist, addr = _build_cities(item)
check("地点条数", len(lst), 3)
check("主城市 = cities[0]", city, "上海")
check("主分区", dist, "静安区")
check("主地址", addr, "静安大悦城 3F")
n = normalize(item)
check("cities JSON 条数", len(__import__("json").loads(n["cities"])), 3)
check("city 字段", n["city"], "上海")
check("address 字段", n["address"], "静安大悦城 3F")

print("=== 2. cities 字符串数组（只有城市名）===")
item2 = {"title": "多城快闪", "cities": ["上海", "广州"], "address": "待定"}
lst2, city2, dist2, addr2 = _build_cities(item2)
check("地点条数", len(lst2), 2)
check("主城市", city2, "上海")
check("第二城", lst2[1]["city"], "广州")
check("无 district 时填空串", lst2[0]["district"], "")
# 多城写法下顶层 address 归属不明，不回填（避免把"待定"错挂到上海）
check("多城不回填顶层 address", addr2, "")

# 单城字符串数组：顶层地址归属明确，应回填补全
lst2b, city2b, dist2b, addr2b = _build_cities({"title": "单城", "cities": ["上海"], "district": "静安区", "address": "静安大悦城"})
check("单城回填 district", dist2b, "静安区")
check("单城回填 address", addr2b, "静安大悦城")

print("=== 3. 旧单值写法（向后兼容）===")
item3 = {"title": "单城快闪", "city": "北京", "district": "朝阳区", "address": "三里屯"}
lst3, city3, dist3, addr3 = _build_cities(item3)
check("地点条数", len(lst3), 1)
check("主城市", city3, "北京")
check("主地址", addr3, "三里屯")

print("=== 4. 异常/边界 ===")
lst4, city4, _, addr4 = _build_cities({"title": "无地点"})
check("完全无地点 → 空列表", lst4, [])
check("主城市为空", city4, "")

lst5, city5, _, _ = _build_cities({"title": "脏数据", "cities": [{"city": ""}, {"no_city": 1}, None, " 深圳 "]})
check("过滤空城市名", len(lst5), 1)
check("保留有效城市", city5, "深圳")

lst6, city6, _, _ = _build_cities({"title": "cities 为空数组", "cities": [], "city": "杭州"})
check("cities 空则回退单值", city6, "杭州")

print("=== 5. 多城市条目 normalize 后 store_type 默认 ===")
n5 = normalize({"title": "默认类型", "cities": ["上海", "广州"]})
check("未给 store_type → popup", n5["store_type"], "popup")
n6 = normalize({"title": "餐厅", "store_type": "restaurant", "city": "上海"})
check("显式 restaurant", n6["store_type"], "restaurant")

print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败：{FAILED}")
    sys.exit(1)
print("✅ ALL_TESTS_PASSED")
