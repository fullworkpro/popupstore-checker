"""微博爬虫「标签=作品名」回归测试（v1.4.10）。

背景：旧逻辑 tags = ["快闪"] + 匹配到的关键词，导致良笑goodsmile 的
「RACING MIKU 2026上海快闪」被打成 ["快闪", "良笑goodsmile"] —— 通用词 + 厂商名，
不是用户想要的。用户要求：标签只放作品名（IP），如「初音未来」。

覆盖：
  1) 标题命中别名 → 输出标准 IP 名
  2) 账号名命中别名 → 输出标准 IP 名
  3) 大小写 / 全角半角不敏感
  4) 同时命中多个 → 最多 2 个
  5) 都没命中 → 退化成清洗后的账号名（去掉 官方/旗舰店/地区 等噪声）
  6) 账号名为空且无命中 → 空列表
  7) 不再出现「快闪」「二次元」这类通用词
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crawler.weibo_crawler import derive_ip_tags  # noqa: E402

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}: got={got} want={want}")
    if ok:
        PASS += 1
    else:
        FAIL += 1


print("— 1) 标题命中别名 → 标准 IP 名 —")
check("RACING MIKU（厂商账号）",
      derive_ip_tags("🏁RACING MIKU 2026上海快闪正式定档！", "良笑goodsmile"), ["初音未来"])
check("初音未来直书",
      derive_ip_tags("初音未来快闪店来啦", "谷谷逛谷GuGuGuGu"), ["初音未来"])
check("chiikawa 小写",
      derive_ip_tags("吉伊卡哇快闪店｜9月25日北京见", "chiikawa吉伊卡哇官方微博"), ["吉伊卡哇"])
check("原神官方账号",
      derive_ip_tags("原神主题快闪", "原神"), ["原神"])

print("— 2) 账号名命中（标题无 IP）—")
check("崩坏星穹铁道", derive_ip_tags("快闪店开业", "崩坏星穹铁道"), ["崩坏：星穹铁道"])
check("EnsembleStars", derive_ip_tags("快闪店开业", "EnsembleStars旗舰店丨上海"), ["偶像梦幻祭"])
check("新世纪福音战士", derive_ip_tags("快闪来啦", "新世纪福音战士_中国"), ["新世纪福音战士"])

print("— 3) 大小写不敏感 —")
check("POKEMON 大写", derive_ip_tags("POKEMON 快闪", "宝可梦pokemon"), ["宝可梦"])
check("NIKKE 大写", derive_ip_tags("NIKKE 快闪", "胜利女神新的希望"), ["胜利女神：妮姬"])

print("— 4) 多命中只取 2 个 —")
r = derive_ip_tags("原神 x 崩坏星穹铁道 联动快闪", "谷谷逛谷")
check("多 IP 截断为 2", len(r) <= 2 and "原神" in r, True)

print("— 5) 无 IP 命中 → 用配置里的关键词（关键词本身即 IP 名），不再用账号名 —")
# v1.4.24：账号名是厂商/店名（如「XX主题餐厅」），不是 IP，不能当标签
check("TOPTOY 官方（无关键词）", derive_ip_tags("SISI 新品", "TOPTOY官方"), [])
check("带地区后缀（无关键词）", derive_ip_tags("新品", "XX品牌旗舰店丨上海"), [])
check("退回关键词 JOJO", derive_ip_tags("主题餐厅开业", "XX主题餐厅", ["JOJO的奇妙冒险"]),
      ["JOJO的奇妙冒险"])
check("关键词优先于账号名", derive_ip_tags("快闪", "XX主题餐厅", ["银魂"]), ["银魂"])

print("— 5b) 新增 IP 词典条目 —")
check("JOJO 标题命中", derive_ip_tags("JOJO的奇妙冒险 快闪", "XX店"), ["JOJO的奇妙冒险"])
check("银魂 标题命中", derive_ip_tags("银魂DISCO主题快闪", "XX店"), ["银魂"])
check("犬夜叉 标题命中", derive_ip_tags("犬夜叉三十周年快闪", "XX店"), ["犬夜叉"])

print("— 6) 全空 → 空列表 —")
check("无标题无账号", derive_ip_tags("", ""), [])

print("— 7) 不含通用词 —")
r = derive_ip_tags("快闪店开业", "良笑goodsmile")
check("无『快闪』标签", "快闪" not in r, True)
check("无『二次元』标签", "二次元" not in r, True)

print(f"\n通过 {PASS} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
