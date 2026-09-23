"""微博爬虫「字段口径」回归测试（v1.4.24）。

用户明确的落库口径：
  1) 标题以【城市】起头：1 个→【广州】；2~3 个→【上海、广州】；>3 个→【多地】
  2) tags 只放动漫 IP，不要副标题 / 主题餐厅之类的词
  3) 「荒野心旅，自在驰骋」这类短句 → subtitle
  4) ✅🌟 活动细则段落 → description（且不再重复标题/副标题）
  5) 一条微博里不同城市档期不同 → 拆成多条

全部离线：直接调解析函数，不发网络请求。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crawler.weibo_crawler import (  # noqa: E402
    build_title, build_city_prefix, extract_subtitle, extract_description,
    extract_cities, extract_city_schedules, derive_ip_tags,
)

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}\n         got ={got!r}\n         want={want!r}")
    if ok:
        PASS += 1
    else:
        FAIL += 1


print("— 1) 标题以【城市】起头 —")
check("单城市",
      build_title("犬夜叉三十周年快闪\n正文…", ["广州"]), "【广州】犬夜叉三十周年快闪")
check("两城市",
      build_title("银魂快闪\n正文…", ["上海", "广州"]), "【上海、广州】银魂快闪")
check("三城市",
      build_title("全知读者视角 × animate cafe", ["北京", "上海", "广州"]),
      "【北京、上海、广州】全知读者视角 × animate cafe")
check("四城市→多地",
      build_title("全知读者视角 × animate cafe", ["北京", "上海", "广州", "成都"]),
      "【多地】全知读者视角 × animate cafe")
check("原标题自带的【…】被替换而不是叠加",
      build_title("【上海】银魂快闪\n正文", ["广州"]), "【广州】银魂快闪")
check("无城市则不加前缀",
      build_title("银魂快闪\n正文", []), "银魂快闪")
check("城市前缀构造",
      (build_city_prefix(["广州"]), build_city_prefix(["上海", "广州"]),
       build_city_prefix(["a", "b", "c", "d"]), build_city_prefix([])),
      ("【广州】", "【上海、广州】", "【多地】", ""))

print("— 2) tags 只要动漫 IP —")
check("副标题不当标签",
      derive_ip_tags("荒野心旅，自在驰骋", "XX主题餐厅", ["银魂"]), ["银魂"])
check("店名不当标签",
      derive_ip_tags("JOJO的奇妙冒险 快闪", "XX主题餐厅"), ["JOJO的奇妙冒险"])

print("— 3) 副标题 = 标题后的短句 —")
text3 = ("犬夜叉三十周年快闪\n"
         "荒野心旅，自在驰骋\n"
         "📍地点：广州天河城\n"
         "✅快闪限定新品\n")
check("取到副标题", extract_subtitle(text3, "犬夜叉三十周年快闪"), "荒野心旅，自在驰骋")
check("含地址的行不是副标题", extract_subtitle("标题\n广州天河城地址\n正文", "标题"), "")
check("emoji 行不是副标题", extract_subtitle("标题\n✅快闪限定新品\n", "标题"), "")

print("— 4) description = 正文去掉标题/副标题 —")
desc = extract_description(text3, "犬夜叉三十周年快闪", "荒野心旅，自在驰骋")
check("保留活动细则段", desc.count("✅") == 1 and "地点" in desc, True)
check("不再重复标题", "犬夜叉三十周年快闪" not in desc, True)
check("不再重复副标题", "荒野心旅" not in desc, True)

print("— 5) 多城市不同档期 → 拆分 —")
text5 = ("【上海、广州】银魂快闪\n"
         "上海 9月20日-10月7日 静安大悦城\n"
         "广州 10月1日-10月20日 天河城\n")
cities = extract_cities(text5)
sched = extract_city_schedules(text5, cities)
check("识别出 2 个城市各自的档期", len(sched) == 2, True)
check("两个档期不同（才该拆）", sched[0][1:3] != sched[1][1:3], True)
check("拆出来的标题各自带城市",
      [build_title(text5, [c]) for c, _s, _e, _l in sched],
      ["【上海】银魂快闪", "【广州】银魂快闪"])
check("各自命中自己那一行（用于取地址）",
      [l.strip() for _c, _s, _e, l in sched],
      ["上海 9月20日-10月7日 静安大悦城", "广州 10月1日-10月20日 天河城"])

text5b = "【上海、广州】银魂快闪\n9月20日-10月7日\n两地同步\n"
sched_b = extract_city_schedules(text5b, extract_cities(text5b))
check("档期相同则不拆", len({(s, e) for _c, s, e, _l in sched_b}) <= 1, True)

print(f"\n通过 {PASS} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
