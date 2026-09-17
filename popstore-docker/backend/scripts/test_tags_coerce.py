"""tags 归一化的回归测试（防「一个字一个标签」复发）。

历史 bug：`list(item.get("tags") or [])` 遇到 JSON 字符串会逐字符拆开，
存成 ['[', '"', '吉', '伊', '卡', '哇', '"', ']', '快闪']。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crawler.curated_importer import _coerce_tags, normalize  # noqa: E402

CASES = [
    # (入参, 期望)
    (None, []),
    ("", []),
    ([], []),
    (["吉伊卡哇"], ["吉伊卡哇"]),
    ("吉伊卡哇", ["吉伊卡哇"]),
    ('["吉伊卡哇"]', ["吉伊卡哇"]),
    ('["初音未来","三丽鸥"]', ["初音未来", "三丽鸥"]),
    ("初音未来, 三丽鸥", ["初音未来", "三丽鸥"]),
    ("初音未来，三丽鸥、宝可梦", ["初音未来", "三丽鸥", "宝可梦"]),
    ('{"初音未来": 1}', ["初音未来"]),
    (["吉伊卡哇", "吉伊卡哇"], ["吉伊卡哇"]),          # 去重
    ([" ", "吉伊卡哇", ""], ["吉伊卡哇"]),             # 去空
    ('["[","]","\\"","吉伊卡哇"]', ["吉伊卡哇"]),      # 过滤 JSON 碎片
    (123, ["123"]),
]


def main() -> int:
    passed = failed = 0
    for raw, want in CASES:
        got = _coerce_tags(raw)
        ok = got == want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        if not ok:
            print(f"  ✗ _coerce_tags({raw!r}) -> {got!r}, 期望 {want!r}")

    # normalize：不再自动补「快闪」/ 厂商名
    n = normalize({"title": "CHIIKAWA快闪", "tags": '["吉伊卡哇"]', "venue": "某场馆"})
    got = json.loads(n["tags"])
    ok = got == ["吉伊卡哇"]
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    if not ok:
        print(f"  ✗ normalize tags -> {got!r}, 期望 ['吉伊卡哇']（不应含『快闪』/场馆名）")

    # normalize：tags 为空时回退 ip_name
    n2 = normalize({"title": "孤独摇滚快闪", "ip_name": "孤独摇滚"})
    got2 = json.loads(n2["tags"])
    ok = got2 == ["孤独摇滚"]
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    if not ok:
        print(f"  ✗ normalize 空 tags 回退 -> {got2!r}, 期望 ['孤独摇滚']")

    # venue 仍写入 crawl_meta（不进 tags）
    n3 = normalize({"title": "x", "tags": ["初音未来"], "venue": "上海某馆", "ip_name": "初音未来"})
    meta = json.loads(n3["crawl_meta"])
    ok = meta.get("venue") == "上海某馆" and json.loads(n3["tags"]) == ["初音未来"]
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    if not ok:
        print(f"  ✗ venue 应只进 meta：meta={meta.get('venue')!r} tags={n3['tags']!r}")

    print(f"\n通过 {passed}/{passed + failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
