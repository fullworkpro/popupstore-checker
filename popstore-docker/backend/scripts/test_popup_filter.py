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
