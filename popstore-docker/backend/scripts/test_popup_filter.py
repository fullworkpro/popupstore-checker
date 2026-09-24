"""快闪活动帖过滤的回归测试 —— 排除发货/抽选/中奖等运营通知类噪音。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crawler.weibo_crawler import is_popup_post  # noqa: E402

CASES = [
    # (正文, 期望是否活动帖)
    ("RACING MIKU 2026 上海快闪正式定档！10月1日开幕", True),
    ("吉伊卡哇快闪店｜9月25日北京见", True),
    ("CHIIKAWA Baby 华中首展+主题快闪店等你赴约", True),
    ("名创优品HELLO KITTY优雅日常主题快闪 即将开启", True),
    ("宝可梦官方快闪店新店将在惠州华贸天地开业", True),
    # 噪音：发货 / 售后
    ("【怪盗圣少女上海快闪预购单发货通知】", False),
    ("NU: Carnival主题快闪发货公告", False),
    ("初音未来快闪周边退款说明", False),
    # 噪音：抽选 / 中奖
    ("宝可梦30周年庆典商品 限购区商品购买资格抽选", False),
    ("30周年庆典 幻彩未来纪念礼盒购买资格抽选", False),
    ("快闪活动中奖名单公布", False),
    # 噪音：周边上新 / 线上售卖（没有线下点位与档期）
    ("初音未来 快闪周边上新！今晚8点开售，全网通贩", False),
    ("【周边上新】名创优品 chiikawa 系列今晚上新，拍下即发货", False),
    ("EVA 新品预售开启｜限量发售，购买链接见评论", False),
    ("咒术回战 周边现货发售，包邮到家", False),
    # 反例：虽然提到上新/开售，但有线下活动信号 → 仍是真快闪，不能误杀
    ("chiikawa 快闪店 上海站 10月1日开业，现场周边上新一览", True),
    ("名创优品HELLO KITTY 快闪店｜地址：静安大悦城，9/25-10/8，周边开售", True),
    ("原神快闪店 广州天环广场开展，限定周边首发", True),
    # 非快闪（不含「快闪」，即便有线下信息也不收）
    ("原神主题店 广州天环广场开展，限定周边首发", False),
    # 非快闪
    ("今日新品上架，欢迎选购", False),
    ("", False),
]


def main() -> int:
    passed = failed = 0
    for text, want in CASES:
        got = is_popup_post(text)
        ok = got == want
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        if not ok:
            print(f"  ✗ {text[:28]!r} -> {got}, 期望 {want}")
    print(f"\n通过 {passed}/{passed + failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
