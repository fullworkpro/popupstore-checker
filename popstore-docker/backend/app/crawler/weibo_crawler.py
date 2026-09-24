"""微博爬虫 — 基于 m.weibo.cn 移动端 JSON 接口，抓取二次元快闪原创微博。

两种模式（互斥，按配置择优）：
A. 账号监控（首选）：监控配置的官方/品牌账号时间线（containerid=107603{uid}），
   抓取【原创】且含「快闪/快闪店」的帖子。游客即可读取时间线，比搜索接口限流轻得多，
   且直接锁定目标品牌，命中精准。适合「监测良笑goodsmile/名创优品/TOPTOY…是否发了快闪」。
B. 全站关键词搜索（备选）：对二次元 IP 关键词（龙珠/原神/…）做全站搜索，筛选出
   原创+快闪+命中 IP 的帖子。覆盖广但搜索接口 ok=-100 限流极重，作为账号未配置时的兜底。

若配置了有效 uid 的账号 → 走 A；否则 → 走 B。
"""

import json
import logging
import random
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.crawler.base_crawler import BaseCrawler
from app.core.config import settings

logger = logging.getLogger("crawler.weibo")

# IP / 作品名别名词典：把「标题 + 账号名」归一成标准作品名做标签。
# 只放作品名（如「初音未来」），不再塞「快闪」「二次元」这类通用词和厂商名。
# 新增 IP 时在这里加一行即可：标准名 -> 可能出现的别名/关键词（小写匹配）。
IP_ALIASES = {
    "初音未来": ["初音未来", "初音", "miku", "初音ミク", "racing miku"],
    "吉伊卡哇": ["chiikawa", "吉伊卡哇", "吉伊", "乌萨奇", "哈奇", "乌萨奇&京韵脊兽"],
    "宝可梦": ["宝可梦", "pokemon", "pokémon", "皮卡丘", "精灵宝可梦"],
    "偶像梦幻祭": ["ensemblestars", "ensemble stars", "偶像梦幻祭", "あんスタ"],
    "原神": ["原神", "genshin"],
    "崩坏：星穹铁道": ["崩坏星穹铁道", "星穹铁道", "星铁", "honkai: star rail"],
    "绝区零": ["绝区零", "zenless", "zzz"],
    "鸣潮": ["鸣潮", "wuthering"],
    "碧蓝航线": ["碧蓝航线", "azur lane"],
    "第五人格": ["第五人格", "identity v"],
    "胜利女神：妮姬": ["胜利女神", "nikke", "妮姬"],
    "新世纪福音战士": ["新世纪福音战士", "福音战士", "evangelion", "eva"],
    "明日方舟": ["明日方舟", "arknights"],
    "蔚蓝档案": ["蔚蓝档案", "blue archive"],
    "少女前线": ["少女前线", "girls' frontline"],
    "咒术回战": ["咒术回战", "jujutsu"],
    "孤独摇滚": ["孤独摇滚", "ぼっち・ざ・ろっく"],
    "间谍过家家": ["间谍过家家", "spy×family", "spy x family"],
    "鬼灭之刃": ["鬼灭之刃", "鬼灭"],
    "名侦探柯南": ["名侦探柯南", "柯南"],
    "三丽鸥": ["三丽鸥", "sanrio", "hellokitty", "hello kitty", "库洛米", "美乐蒂", "玉桂狗"],
    "迪士尼": ["迪士尼", "disney", "疯狂动物城"],
    "蜡笔小新": ["蜡笔小新"],
    "哆啦A梦": ["哆啦a梦", "哆啦A梦", "机器猫"],
    "JOJO的奇妙冒险": ["jojo", "jojo的奇妙冒险", "乔乔的奇妙冒险", "jojo奇妙冒险"],
    "银魂": ["银魂", "gintama", "坂田银时"],
    "犬夜叉": ["犬夜叉", "inuyasha"],
    "全知读者视角": ["全知读者视角", "omniscient reader", "全知读者"],
}

# 账号名里需要剥掉的噪声后缀（厂商/地区/认证词），仅在没匹配到 IP 时用作兜底标签
_ACCOUNT_NOISE = re.compile(
    r"(官方微博|官方旗舰店|官方|旗舰店|中国|分公司|丨.*|[（(].*?[)）]|【.*?】|\s+)")


def derive_ip_tags(title: str, organizer: str, matched: List[str] = None) -> List[str]:
    """标签只放作品名（IP），最多 2 个。

    v1.4.24 起不再用账号名兜底：账号名是厂商/店名（如「XX主题餐厅」），不是 IP，
    塞进 tags 会污染标签。找不到 IP 时退回配置里的关键词——关键词本身就是 IP 名
    （见 CrawlerConfig.keywords）；再没有就留空，交给人工补。
    """
    text = f"{title or ''} {organizer or ''} {' '.join(matched or [])}".lower()
    hits = [ip for ip, aliases in IP_ALIASES.items() if any(a.lower() in text for a in aliases)]
    if hits:
        return hits[:2]
    ips = [m.strip() for m in (matched or []) if m and m.strip()]
    return ips[:2]

CJK = r"[\u4e00-\u9fff]"

# ─────────────────────────── 反爬/限流参数 ───────────────────────────
# 微博 m.weibo.cn 搜索接口对「未限速的批量请求」极其敏感：
# 连续请求会在第 1~2 次后返回 ok=-100（请求过快/需登录），导致后续全挂。
# 因此必须做「请求间隔 + 关键词间大间隔 + 退避重试」。
REQUEST_INTERVAL = 5.0   # 同一关键词内两次请求（翻页/长文）的最小间隔（秒），含随机抖动
KEYWORD_INTERVAL = 60.0  # 两个关键词之间的额外间隔（秒）；限流严重时可继续加大（如 120）
MAX_RETRIES = 3          # 遇到 ok=-100 / 连接中断 时的最大重试次数
RETRY_BACKOFF = 20.0     # 退避基数（秒）：第 1/2/3 次重试分别等 20/40/60 秒
# 连接池空闲阈值（秒）：两次请求间隔超过此值时，服务端（或 WAF）多半已单方面关闭
# keep-alive 连接，客户端复用这条「死连接」会直接抛
#   ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
# 关键词间隔 60s 远大于微博的 keep-alive 超时，故必须在发请求前主动丢弃连接池。
CONN_IDLE_RESET = 20.0


def _mount_retry_adapter(session: "requests.Session") -> None:
    """给 Session 挂上连接层重试（urllib3 Retry）。

    requests 默认 max_retries=0，一旦遇到「对端在返回响应前就断开连接」
    （RemoteDisconnected / Connection aborted）不会重试，异常会直接冒泡到调用方，
    表现为整个关键词被跳过。这里在更底层补上 connect/read 重试，读接口是幂等 GET，安全。
    """
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        try:
            retry = Retry(
                total=2, connect=2, read=2, status=2,
                backoff_factor=1.0,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET"]),
                raise_on_status=False,
            )
        except TypeError:  # urllib3 < 1.26 老参数名
            retry = Retry(
                total=2, connect=2, read=2, status=2,
                backoff_factor=1.0,
                status_forcelist=(429, 500, 502, 503, 504),
                method_whitelist=frozenset(["GET"]),
                raise_on_status=False,
            )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    except Exception as e:  # 装不上也不影响主流程（上层还有自己的重试）
        logger.warning("[weibo] 连接重试适配器装载失败（忽略）: %s", e)


class WeiboSearchError(Exception):
    """搜索接口返回非预期结果（HTTP 非 200 / 非 JSON 等）。"""


class WeiboRateLimitError(WeiboSearchError):
    """搜索接口返回 ok=-100：可能是请求过快被限流，也可能是 Cookie 失效需登录。"""


# ─────────────────────────── 纯函数：可离线单测 ───────────────────────────
def parse_weibo_time(s: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """解析 m.weibo.cn 的 created_at 字符串，返回 naive 本地时间。

    支持：刚刚 / X分钟前 / X小时前 / X天前 / 今天|昨天|前天 HH:MM /
    MM月DD日[ HH:MM] / YYYY-MM-DD[ HH:MM] / MM-DD[ HH:MM] /
    英文带时区 "Wed Aug 26 21:27:58 +0800 2026"。
    无法解析返回 None（调用方保守包含，但不作为翻页停止条件）。
    """
    if not s:
        return None
    s = s.strip()
    now = now or datetime.now()

    # 英文带时区
    m = re.match(
        r"^[A-Za-z]{3}\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+\+0800\s+(\d{4})$",
        s,
    )
    if m:
        mon = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }.get(m.group(1))
        if mon:
            return datetime(int(m.group(6)), mon, int(m.group(2)),
                            int(m.group(3)), int(m.group(4)), int(m.group(5)))

    if s == "刚刚":
        return now
    m = re.match(r"^(\d+)\s*分钟前$", s)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.match(r"^(\d+)\s*小时前$", s)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.match(r"^(\d+)\s*天前$", s)
    if m:
        return now - timedelta(days=int(m.group(1)))

    offset = None
    if s.startswith("今天"):
        offset = 0
    elif s.startswith("昨天"):
        offset = 1
    elif s.startswith("前天"):
        offset = 2
    if offset is not None:
        rest = s[2:].strip()
        hh = mm = 0
        tm = re.match(r"^(\d{1,2}):(\d{2})$", rest)
        if tm:
            hh, mm = int(tm.group(1)), int(tm.group(2))
        base = now - timedelta(days=offset)
        return base.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # YYYY-MM-DD[ HH:MM]
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            int(m.group(4)) if m.group(4) else 0,
                            int(m.group(5)) if m.group(5) else 0)
        except ValueError:
            return None

    # MM月DD日[ HH:MM]
    m = re.match(r"^(\d{1,2})月(\d{1,2})日(?:[ T](\d{1,2}):(\d{2}))?", s)
    if m:
        return _build_md(int(m.group(1)), int(m.group(2)),
                         int(m.group(3)) if m.group(3) else 0,
                         int(m.group(4)) if m.group(4) else 0, now)

    # MM-DD[ HH:MM]
    m = re.match(r"^(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?", s)
    if m:
        return _build_md(int(m.group(1)), int(m.group(2)),
                         int(m.group(3)) if m.group(3) else 0,
                         int(m.group(4)) if m.group(4) else 0, now)

    logger.warning("[weibo] 无法解析时间: %r", s)
    return None


def _build_md(month: int, day: int, hh: int, mm: int, now: datetime) -> Optional[datetime]:
    try:
        dt = datetime(now.year, month, day, hh, mm)
        if dt > now:  # 跨年（如 1 月帖在 12 月抓取）
            dt = datetime(now.year - 1, month, day, hh, mm)
        return dt
    except ValueError:
        return None


def clean_html(html: str) -> str:
    """去除微博 HTML 标签，保留话题/@ 文字；<br> 转为换行。"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text(separator="")
    text = re.sub(r"\s*\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def extract_title(text: str) -> str:
    """取首行作为标题；以【…】开头则直接采用（含括号）。上限 80 字符。"""
    text = (text or "").strip()
    if not text:
        return ""
    first = text.split("\n", 1)[0].strip()
    if first.startswith("【") and "】" in first:
        return first[:80]
    if len(first) > 80:
        return first[:80] + "…"
    return first


def strip_bracket_prefix(s: str) -> str:
    """去掉开头连续的【…】括号（原标题里的城市/标签），避免与新加的城市前缀重复。"""
    s = (s or "").strip()
    while True:
        m = re.match(r"^【[^】]{0,30}】\s*", s)
        if not m:
            return s
        s = s[m.end():].strip()


def build_city_prefix(cities: List[str]) -> str:
    """标题城市前缀：1 个→【广州】；2~3 个→【上海、广州】；>3 个→【多地】。"""
    cs = [c for c in (cities or []) if c]
    if not cs:
        return ""
    if len(cs) > 3:
        return "【多地】"
    return "【" + "、".join(cs) + "】"


def build_title(text: str, cities: List[str]) -> str:
    """标题 = 【城市】+ 主题（主题行剥离原文自带的【…】后再拼，上限 80）。"""
    raw = (text or "").strip()
    core = ""
    if raw:
        core = strip_bracket_prefix(raw.split("\n", 1)[0].strip())
    title = f"{build_city_prefix(cities)}{core}".strip()
    return title[:80] + "…" if len(title) > 80 else title


_SUBTITLE_NOISE = re.compile(r"[\d\.]|https?://|@|#|地址|地点|时间|营业|开业|店|号|路|街|"
                             r"广场|商场|中心|预约|期间|每日")
_SUBTITLE_EMOJI = "✅🌟📍⏰🎁🔥✨🎉📌👉🕐📅🎊⚡️⭐️"


def extract_subtitle(text: str, title_line: str = "") -> str:
    """副标题 = 标题行之后的第一个「短句」，如「荒野心旅，自在驰骋」。

    判定：≤30 字符、不含数字/链接/@/#/地址时间类词、不是 emoji 符号行、不是【…】标签行。
    """
    lines = [(l or "").strip() for l in (text or "").split("\n")]
    lines = [l for l in lines if l]
    # 只看紧跟标题的那一行的下一行：副标题几乎总是紧挨标题，
    # 再往下就是地址/档期/细则，不该被误当成副标题。
    for l in lines[1:2]:
        if not l or l == (title_line or "").strip():
            continue
        if len(l) > 30 or _SUBTITLE_NOISE.search(l) or l[0] in _SUBTITLE_EMOJI:
            continue
        if strip_bracket_prefix(l) != l:
            continue
        return l
    return ""


def extract_description(text: str, title_line: str = "", subtitle: str = "") -> str:
    """详情 = 正文去掉标题行与副标题行后的部分（保留 ✅/🌟 这类活动细则段落）。"""
    lines = [(l or "").strip() for l in (text or "").split("\n")]
    body, dropped_title = [], False
    for l in lines:
        if not l:
            continue
        if not dropped_title and l == (title_line or "").strip():
            dropped_title = True
            continue
        if subtitle and l == subtitle:
            continue
        body.append(l)
    return "\n".join(body).strip()


# 「城市 + 各自档期」拆分用：支持 9月20日-10月7日 / 9.20-10.7 / 9/20-10/7 / 9月20日-25日
_RANGE_PATS = [
    r"(\d{1,2})月(\d{1,2})日\s*[~\-—–至到]+\s*(\d{1,2})月(\d{1,2})日",
    r"(\d{1,2})月(\d{1,2})日\s*[~\-—–至到]+\s*(\d{1,2})日",
    r"(\d{1,2})\.(\d{1,2})\s*[~\-—–至到]+\s*(\d{1,2})\.(\d{1,2})",
    r"(\d{1,2})/(\d{1,2})\s*[~\-—–至到]+\s*(\d{1,2})/(\d{1,2})",
]


def _parse_range(seg: str, year: int):
    """在一段文字里找第一个日期区间，返回 (start, end) 或 None。"""
    for p in _RANGE_PATS:
        m = re.search(p, seg or "")
        if not m:
            continue
        g = m.groups()
        try:
            if len(g) == 4:
                sm, sd, em, ed = (int(x) for x in g)
            else:
                sm, sd, ed = (int(x) for x in g)
                em = sm
            start = datetime(year, sm, sd)
            end = datetime(year, em, ed)
            if end < start:
                end = datetime(year + 1, em, ed)
            return start, end
        except ValueError:
            continue
    return None


def extract_city_schedules(text: str, cities: List[str], year: int = None):
    """[(city, start, end, line), …]：每个城市各自的档期 + 命中的那一行原文。

    用于「一篇微博里多个城市档期不同 → 拆成多条」。line 用来就地取该城市的地址。
    注意城市名常常先出现在标题的【上海、广州】里，那里的档期不属于任何城市，
    所以要按行找，且只在「下一行没提到别的城市」时才允许日期写在下一行。
    """
    year = year or datetime.now().year
    lines = (text or "").split("\n")
    out = []
    for c in cities or []:
        for i, line in enumerate(lines):
            if c not in line:
                continue
            rng, used = _parse_range(line.split(c, 1)[1], year), line
            if not rng and i + 1 < len(lines):
                nxt = lines[i + 1]
                # 下一行若提到别的城市，说明那是别家的档期，不能借来用
                if not any(o != c and o in nxt for o in (cities or [])):
                    rng, used = _parse_range(nxt, year), nxt
            if rng:
                out.append((c, rng[0], rng[1], used))
                break
    return out


def extract_date_range(text: str, year: Optional[int] = None) -> Tuple[Optional[datetime], Optional[datetime]]:
    """从正文中提取快闪档期：[开始, 结束]。仅单日则返回 (日, None)。"""
    year = year or datetime.now().year
    patterns = [
        r"(\d{1,2})月(\d{1,2})日\s*[~\-—至到]+\s*(\d{1,2})月(\d{1,2})日",
        r"(\d{1,2})\.(\d{1,2})\s*[~\-—至到]+\s*(\d{1,2})\.(\d{1,2})",
        r"(\d{1,2})/(\d{1,2})\s*[~\-—至到]+\s*(\d{1,2})/(\d{1,2})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if not m:
            continue
        try:
            sm, sd, em, ed = (int(x) for x in m.groups())
            start = datetime(year, sm, sd)
            end = datetime(year, em, ed)
            if end < start:
                end = datetime(year + 1, em, ed)
            return start, end
        except ValueError:
            continue
    # 单日（开幕）
    for p in [r"(\d{1,2})月(\d{1,2})日", r"(\d{1,2})\.(\d{1,2})", r"(\d{1,2})/(\d{1,2})"]:
        m = re.search(p, text)
        if m:
            try:
                d = datetime(year, int(m.group(1)), int(m.group(2)))
                return d, None
            except ValueError:
                continue
    return None, None


def extract_cities(text: str) -> List[str]:
    """从【城市】括号与正文中提取城市名（去重保序，最多 10）。"""
    cities: List[str] = []
    for br in re.findall(r"【([^】]{1,30})】", text):
        for part in re.split(r"[、,，/]", br):
            part = part.strip()
            if part:
                cities.append(part)
    known = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "重庆",
             "西安", "苏州", "天津", "长沙", "青岛", "厦门", "福州", "郑州", "济南",
             "合肥", "昆明", "贵阳", "哈尔滨", "沈阳", "大连", "宁波", "无锡", "佛山",
             "东莞", "珠海", "南宁", "海口", "石家庄", "太原", "南昌", "兰州", "常州",
             "嘉兴", "绍兴", "温州"]
    for c in known:
        if c in text and c not in cities:
            cities.append(c)
    seen, out = set(), []
    for c in cities:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:10]


def extract_addresses(text: str) -> List[str]:
    """启发式抽取具体地址（含 市/区/路/广场/商场…），噪声过滤后最多 5 条。

    过滤掉含「快闪」的匹配——那是活动/店铺名而非地址（如「名创优品快闪店」）。
    """
    pat = (
        CJK + r"{2,8}?(?:省|市|区|县|镇)?"
        + CJK + r"{0,12}?(?:路|街|道|大道|广场|商场|购物中心|中心|大厦|城|CC|号楼|号|店铺|店)"
        + r"(?:[\u4e00-\u9fff0-9A-Za-z#号层]+)?"
    )
    addrs = re.findall(pat, text)
    addrs = [a.strip() for a in addrs if len(a.strip()) >= 4 and "快闪" not in a]
    seen, out = set(), []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out[:5]


# 非活动类噪音：正文含「快闪」但其实是发货/抽选/中奖/售后等运营通知，不应入草稿。
# 新增排除词在此加一行即可（小写子串匹配，与 IP_ALIASES 同风格）。
NOISE_PATTERNS = (
    # 发货 / 售后
    "发货", "补款", "退款", "退货", "换货", "物流", "运单", "快递", "到货", "出库", "签收",
    # 抽选 / 中奖（购买资格抽选不是活动预告）
    "抽选", "抽签", "中签", "中奖", "开奖", "获奖名单", "名单公布", "购买资格", "预约资格",
    # 其它运营通知
    "停售", "售罄公告", "延期发货", "补货通知",
)

# 「周边上新 / 线上售卖」类文案词：命中时**并不直接排除**——
# 只要正文里同时有线下活动信号（门店、地址、开业、档期…）就仍是真快闪。
# 典型要排除的：品牌发「XX 快闪 周边上新 / 今晚开售 / 通贩开启」，没有可去的点位。
SALES_PATTERNS = (
    "上新", "开售", "发售", "预售", "通贩", "现货", "抢购", "补货", "限量发售",
    "线上发售", "全网首发", "购买链接", "拍下", "下单", "邮费", "包邮",
)

# 线下活动信号：命中任一即说明有实际可去的点位 / 档期
OFFLINE_SIGNALS = (
    "快闪店", "快闪空间", "主题店", "限定店", "门店", "店铺", "店址", "地址", "地点", "坐标",
    "商场", "购物中心", "开展", "开幕", "开业", "营业", "现场", "打卡", "展区", "展览", "展会",
)


def popup_reject_reason(text: str) -> Optional[str]:
    """返回排除原因（None = 通过），便于日志诊断与回归测试。"""
    if "快闪" not in text:
        return "不含「快闪」"
    for p in NOISE_PATTERNS:
        if p in text:
            return f"运营通知类噪音「{p}」"
    sales = [p for p in SALES_PATTERNS if p in text]
    if sales and not any(s in text for s in OFFLINE_SIGNALS):
        return f"疑似周边上新/线上售卖（{sales[0]}），无线下活动信息"
    return None


def is_popup_post(text: str) -> bool:
    """是否【活动类】快闪帖：含「快闪」且不是运营通知、也不是纯周边上新。"""
    return popup_reject_reason(text) is None


def is_anime_post(text: str, keywords: List[str]) -> Tuple[bool, List[str]]:
    """命中任一二次元 IP 关键词即视为二次元主题；返回 (是否, 命中词列表)。

    关键词即为具体 IP 名（龙珠/原神/鸣潮/chiikawa…），不再使用「二次元」这类泛词。
    """
    matched = [k for k in keywords if k and k in text]
    return bool(matched), matched


# ─────────────────────────── 爬虫实现 ───────────────────────────
class WeiboCrawler(BaseCrawler):
    source = "weibo"

    def __init__(self, db: Session, keywords: Optional[List[str]] = None,
                 accounts: Optional[List[dict]] = None,
                 cookie: Optional[str] = None, lookback_days: Optional[int] = None,
                 max_pages: Optional[int] = None,
                 uid_enabled: Optional[bool] = None,
                 keyword_enabled: Optional[bool] = None):
        super().__init__(db)
        self.keywords = keywords if keywords is not None else settings.CRAWLER_WEIBO_KEYWORDS
        self.accounts = accounts if accounts is not None else settings.CRAWLER_WEIBO_ACCOUNTS
        # 两种模式的独立开关（v1.3.1）。可同时为真：先跑 UID，再跑关键词补充。
        # 未显式传入时以 settings 默认（UID 开 / 关键词关）为准。
        self.uid_enabled = (
            uid_enabled if uid_enabled is not None else settings.CRAWLER_WEIBO_UID_ENABLED)
        self.keyword_enabled = (
            keyword_enabled if keyword_enabled is not None else settings.CRAWLER_WEIBO_KEYWORD_ENABLED)
        self.cookie = cookie if cookie is not None else settings.CRAWLER_WEIBO_COOKIE
        self.lookback_days = lookback_days if lookback_days is not None else settings.CRAWLER_WEIBO_LOOKBACK_DAYS
        self.max_pages = max_pages if max_pages is not None else settings.CRAWLER_WEIBO_MAX_PAGES
        # 反爬/限流参数
        self.request_interval = REQUEST_INTERVAL
        self.keyword_interval = KEYWORD_INTERVAL
        self.max_retries = MAX_RETRIES
        self.retry_backoff = RETRY_BACKOFF
        self._last_req_ts = 0.0  # 上次发请求的时间戳（用于间隔控制）
        self._auto_sub = False    # 是否成功自动获取了访客 SUB（用于 ok=-100 诊断）
        self._manual_cookie = False  # 是否使用了后台手填的 Cookie（v1.4.9，用于诊断区分）
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": settings.CRAWLER_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://m.weibo.cn/",
        })
        _mount_retry_adapter(self.session)
        # Cookie 不在初始化时设置；统一在 run() 开头由 _ensure_visitor_sub() 决定：
        # v1.4.9 起手填 Cookie 优先，未填时才自动领访客 SUB。

    # ── 网络：自动领取访客身份（免登录 Cookie）──
    def _fetch_visitor_sub(self) -> Optional[Tuple[str, Optional[str]]]:
        """两步法领取访客身份，返回 (sub, subp) 或 None。

        微博的访客(visitor)机制是「免登录」拿到一组临时 Cookie 来通过 WAF(山海):
          1) GET  passport.weibo.com/visitor/genvisitor   → 拿 tid（并让 session 记录占位 Cookie）
          2) POST passport.weibo.com/visitor/genvisitor2  → 用 tid 领取 sub + subp

        关键：m.weibo.cn 校验的是「SUB + SUBP 这一对」，仅设 SUB 而缺 SUBP 时
        WAF 仍会返回 HTTP 432（这正是旧版本「填了 Cookie 也 432 / 全 -100」的根因之一）。
        旧代码只 POST genvisitor2 且只取 sub、只设 SUB，所以 SUBP 缺失 → 432。
        本版本补全 subp，并先取 tid，最大化「当场新领」成功概率。
        """
        # Step 1: genvisitor → tid
        tid = ""
        try:
            self._throttle()
            g = self.session.get(
                "https://passport.weibo.com/visitor/genvisitor",
                params={"cb": "visitor_gray_callback", "from": "weibo"},
                timeout=20,
            )
            m = re.search(r'"tid"\s*:\s*"([^"]+)"', g.text or "")
            if m:
                tid = m.group(1)
        except Exception as e:
            logger.warning("[weibo] genvisitor 取 tid 失败（将退化直连 genvisitor2）: %s", e)

        # Step 2: genvisitor2 → sub + subp
        try:
            self._throttle()
            resp = self.session.post(
                "https://passport.weibo.com/visitor/genvisitor2",
                data={"cb": "visitor_gray_callback", "tid": tid, "from": "weibo"},
                timeout=20,
            )
            text = resp.text or ""
            sub = subp = None
            # 响应可能是 JSONP 包裹：visitor_gray_callback({...})
            jm = re.search(r'\{\s*"data"\s*:\s*\{.*?\}\s*\}', text, re.DOTALL)
            obj = None
            if jm:
                try:
                    obj = json.loads(jm.group(0))
                except Exception:
                    obj = None
            if obj:
                d = (obj.get("data") or {})
                sub = d.get("sub")
                subp = d.get("subp")
            else:
                # 退化：直接正则抓 sub / subp
                m = re.search(r'"sub"\s*:\s*"([^"]+)"', text)
                sub = m.group(1) if m else None
                m = re.search(r'"subp"\s*:\s*"([^"]+)"', text)
                subp = m.group(1) if m else None
            if sub:
                return sub, subp
            logger.warning("[weibo] genvisitor2 未解析到 SUB（响应前 160 字: %s）", text[:160])
            return None
        except Exception as e:
            logger.warning("[weibo] 自动获取访客 SUB 失败: %s", e)
            return None

    def _apply_manual_cookie(self) -> bool:
        """使用后台填写的（登录态）Cookie 作为唯一凭证。返回是否应用成功。"""
        ck = (self.cookie or "").strip()
        if not ck:
            return False
        self.session.cookies.clear()
        self.session.headers["Cookie"] = ck
        self._auto_sub = False
        self._manual_cookie = True
        logger.info("[weibo] 凭证：使用后台填写的微博 Cookie（登录态，读时间线/搜索权限最高）")
        return True

    def _apply_visitor_sub(self) -> bool:
        """领取当场新领的访客 SUB/SUBP 作为凭证（免登录），成功返回 True。"""
        res = self._fetch_visitor_sub()
        if not res:
            return False
        sub, subp = res
        self.session.cookies.clear()
        self.session.cookies.set("SUB", sub, domain=".weibo.com")
        if subp:
            self.session.cookies.set("SUBP", subp, domain=".weibo.com")
        self.session.headers.pop("Cookie", None)
        self._auto_sub = True
        self._manual_cookie = False
        logger.info("[weibo] 凭证：已自动领取访客 SUB%s", "/SUBP" if subp else "")
        return True

    def _ensure_visitor_sub(self) -> bool:
        """决定本次运行使用哪套凭证（v1.4.9 修正）。

        旧逻辑的重大缺陷：「访客 SUB 优先，手填 Cookie 仅在领取失败时兜底」，且领到访客 SUB 后
        会 clear 掉手工 Cookie。实测（2026-09-16）：
          - 无 SUB 的游客 Cookie      → 账号时间线 HTTP 432（WAF 拦截）
          - 访客 SUB+SUBP（genvisitor2）→ HTTP 200 但 ok=-100、0 条（能过 WAF，读不到内容）
          - 登录态 Cookie（浏览器直连） → 正常返回 cards
        即访客 SUB 只能破 432，内容仍要登录态；旧的"优先访客"会让用户在后台填的登录 Cookie
        完全失效，表现为「填了 Cookie 还是 0 条」。

        新逻辑：① 填了 Cookie → 直接用（登录态权限最高）；② 未填 → 领访客 SUB；③ 都无 → 裸请求。
        """
        if self._apply_manual_cookie():
            return True
        if self._apply_visitor_sub():
            return True
        logger.warning(
            "[weibo] 未填写 Cookie 且自动领取访客 SUB 失败（出口 IP 可能被 WAF 拦截），将尝试无 Cookie 请求"
        )
        return False

    # ── 网络：全站关键词搜索 ──
    def _throttle(self) -> None:
        """保证两次请求之间至少间隔 request_interval 秒（含随机抖动），规避微博限流。

        另外：距上次请求超过 CONN_IDLE_RESET 秒时，主动丢弃连接池。
        长间隔后 HTTP keep-alive 连接通常已被对端关闭，复用会得到 RemoteDisconnected；
        这里提前 close 掉（只关连接池，Cookie / headers 不受影响）强制下次新建连接。
        """
        if self._last_req_ts and (time.time() - self._last_req_ts) > CONN_IDLE_RESET:
            try:
                self.session.close()
            except Exception:
                pass
        gap = self.request_interval + random.uniform(0, 0.6)
        wait = gap - (time.time() - self._last_req_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_req_ts = time.time()

    # ── 网络：通用 getIndex 拉取（搜索 / 账号时间线共用）──
    def _get_index(self, containerid: str, page: int) -> Optional[List[dict]]:
        """调用 m.weibo.cn/api/container/getIndex，返回 cards；ok=-100 自动退避重试。

        containerid 由调用方构造：
          - 全站搜索： "100103type%3D1%26q%3D<kw>"
          - 账号时间线： "107603<uid>"（该账号「微博」tab 的标准 containerid）
        连续限流（ok=-100）达到上限返回 None（放弃该来源，避免无谓消耗配额）。
        """
        for attempt in range(self.max_retries + 1):
            try:
                self._throttle()
                resp = self.session.get(
                    "https://m.weibo.cn/api/container/getIndex",
                    params={"containerid": containerid, "page": page},
                    timeout=20,
                )
                if resp.status_code != 200:
                    raise WeiboSearchError(f"微博接口返回 HTTP {resp.status_code}")
                try:
                    data = resp.json()
                except Exception:
                    raise WeiboSearchError("微博接口返回非 JSON")
                if data.get("ok") != 1:
                    # ok=-100：请求过快被限流，或游客凭证被收紧
                    raise WeiboRateLimitError(f"ok!={data.get('ok')} msg={data.get('msg')}")
                return data.get("data", {}).get("cards", [])
            except WeiboRateLimitError as e:
                if attempt < self.max_retries:
                    backoff = self.retry_backoff * (attempt + 1)
                    logger.warning(
                        "[weibo] 被限流(ok=-100)，%.0f 秒后重试(%d/%d)",
                        backoff, attempt + 1, self.max_retries,
                    )
                    time.sleep(backoff)
                else:
                    logger.error("[weibo] 多次限流失败，放弃: %s", e)
            except requests.exceptions.RequestException as e:
                # 网络层异常：RemoteDisconnected / Connection aborted / Timeout 等。
                # 多为对端(或 WAF)在返回响应前主动断开，属于可重试错误；
                # 退避后重试，避免一次抖动就让整个关键词颗粒无收。
                if attempt < self.max_retries:
                    backoff = self.retry_backoff * (attempt + 1)
                    logger.warning(
                        "[weibo] 连接中断(%s)，%.0f 秒后重试(%d/%d)",
                        type(e).__name__, backoff, attempt + 1, self.max_retries,
                    )
                    time.sleep(backoff)
                else:
                    logger.error("[weibo] 多次连接中断，放弃: %s", e)
        return None

    def _search(self, keyword: str, page: int) -> Optional[List[dict]]:
        """全站搜索关键词（构造搜索 containerid）。"""
        containerid = "100103type%3D1%26q%3D" + quote(keyword)
        self.session.headers["Referer"] = f"https://m.weibo.cn/search?containerid={containerid}"
        return self._get_index(containerid, page)

    def _fetch_long_text(self, mid: str, fallback: str) -> str:
        if not mid:
            return fallback
        try:
            self._throttle()
            r = self.session.get(f"https://m.weibo.cn/statuses/show?id={mid}", timeout=15)
            if r.status_code == 200:
                t = r.json().get("data", {}).get("text", "")
                if t:
                    return clean_html(t)
        except Exception as e:
            logger.warning("[weibo] 长文抓取失败 mid=%s: %s", mid, e)
        return fallback

    def _collect_posts(self, keyword: str, since: datetime, until: datetime) -> List[dict]:
        """搜索某关键词，收集窗口内、原创、含「快闪」且命中 IP 的微博 mblog。"""
        posts: List[dict] = []
        for page in range(1, self.max_pages + 1):
            cards = self._search(keyword, page)
            if cards is None:
                # 连续被限流，放弃该关键词，避免无谓地消耗请求配额
                break
            if not cards:
                break
            stop = False
            for card in cards:
                mb = card.get("mblog")
                if not mb:
                    continue
                # 仅原创：转发的微博带有 retweeted_status
                if mb.get("retweeted_status"):
                    continue
                text = clean_html(mb.get("text", ""))
                if not is_popup_post(text):
                    continue
                ok_anime, matched = is_anime_post(text, self.keywords)
                if not ok_anime and keyword and keyword in text:
                    # 场馆优先：搜索词本身（如「静安大悦城」「动漫星城」）命中正文即收录。
                    # 理由：IP 名写法杂、召回低；场馆是固定点位，命中即可信且自带定位信息。
                    # 兼容：关键词仍为 IP 名时 is_anime_post 已命中，此分支不会触发。
                    ok_anime, matched = True, [keyword]
                if not ok_anime:
                    continue
                created = parse_weibo_time(mb.get("created_at"))
                if created is not None:
                    if created > until:
                        continue
                    if created < since:
                        stop = True
                        break
                posts.append((mb, matched, text, False))
            if stop:
                break
        return posts

    # ── 账号时间线监控（游客可读取、比搜索接口限流轻）──
    def _collect_account_posts(self, account: dict, since: datetime, until: datetime) -> List[dict]:
        """监控单个微博账号时间线，收集窗口内【原创】且含「快闪/快闪店」的微博。

        通过 containerid=107603{uid} 拉取该账号「微博」tab（游客即可读取，
        比全站搜索接口 ok=-100 概率低得多）。翻页直到帖子超出 since 窗口。
        account: {"name": 显示名, "uid": 数字 uid 字符串}
        返回 [(mb, [name], text, True), ...]，True 标记 account_mode。
        """
        uid = str(account.get("uid") or "").strip()
        name = account.get("name") or uid
        if not uid.isdigit():
            logger.warning("[weibo] 跳过账户 %s：未配置有效 UID（请在「爬虫」页面填写数字 UID）", name)
            return []
        containerid = f"107603{uid}"
        posts: List[tuple] = []
        for page in range(1, self.max_pages + 1):
            cards = self._get_index(containerid, page)
            if cards is None:
                # 连续被限流，放弃该账号
                break
            if not cards:
                break
            stop = False
            for card in cards:
                mb = card.get("mblog")
                if not mb:
                    continue
                # 仅原创：转发的微博带有 retweeted_status
                if mb.get("retweeted_status"):
                    continue
                text = clean_html(mb.get("text", ""))
                # 账号监控模式：账号本身即品牌，只需筛「快闪/快闪店」原创帖
                if not is_popup_post(text):
                    continue
                created = parse_weibo_time(mb.get("created_at"))
                if created is not None:
                    if created > until:
                        continue
                    if created < since:
                        stop = True
                        break
                posts.append((mb, [name], text, True))
            if stop:
                break
        logger.info("[weibo] 账户 %s 命中 %d 条（窗口内）", name, len(posts))
        return posts

    # ── 兼容基类关键词模式：单关键词抓取并返回解析后的待发布条目 ──
    def fetch(self, keyword: str) -> List[dict]:
        now = datetime.now()
        since = now - timedelta(days=self.lookback_days)
        items = []
        for mb, matched, text, account_mode in self._collect_posts(keyword, since, now):
            it = self._parse_mblog(mb, matched, text, account_mode=account_mode)
            if it:
                items.append(it)
        return items

    # ── 解析单条 ──
    def _parse_mblog(self, mb: dict, matched: List[str], text: str,
                     account_mode: bool = False) -> List[dict]:
        """解析一条微博 → 1 条或多条草稿。

        一条微博里不同城市档期不同（如「上海 9.20-10.7 / 广州 10.1-10.20」）时，
        按城市拆成多条，各自带自己的城市与档期（v1.4.24）。
        """
        bid = mb.get("bid") or mb.get("id")
        if not bid:
            return []
        user = mb.get("user") or {}
        uid = str(user.get("id") or user.get("idstr") or "")
        source_url = f"https://weibo.com/{uid}/{bid}" if uid else f"https://m.weibo.cn/detail/{bid}"

        raw_text = text
        if mb.get("isLongText"):
            raw_text = self._fetch_long_text(mb.get("id"), text)

        first_line = (raw_text or "").split("\n", 1)[0].strip()
        cities = extract_cities(raw_text)
        addresses = extract_addresses(raw_text)
        # 副标题：标题行之后的短句（如「荒野心旅，自在驰骋」）
        subtitle = extract_subtitle(raw_text, first_line)
        # 详情：正文去掉标题行/副标题行（保留 ✅🌟 活动细则）
        description = extract_description(raw_text, first_line, subtitle)
        start, end = extract_date_range(raw_text)

        pics = mb.get("pics") or []
        img_urls = []
        for p in pics:
            u = (p.get("large") or {}).get("url") or p.get("url") or ""
            if u:
                img_urls.append(u)
        cover = img_urls[0] if img_urls else ""

        organizer = user.get("screen_name", "")
        # 标签只放作品名（IP）；传「去括号后的主题」避免原标题里的【…】干扰命中
        tags = derive_ip_tags(strip_bracket_prefix(first_line), organizer, matched)

        # 多城市 + 各自档期不同 → 拆成多条
        schedules = extract_city_schedules(raw_text, cities)
        distinct = {(s, e) for _, s, e, _l in schedules}
        multi = len(schedules) >= 2 and len(distinct) >= 2

        def _pack(city_list, s, e, address, desc=None):
            meta = {
                "source_images": img_urls,       # 新浪图床直链，仅供参考，人工后续转存图床
                "raw_text": raw_text,
                "matched_keywords": matched,
                "needs_time": s is None,         # 时间仅在海报图 → 需人工补全
                "needs_address": not address,
                "images_need_upload": True,      # 图片由人工上传图床
                "split_by_city": len(city_list) == 1 and multi,  # 由多城市拆分而来
            }
            return {
                "title": build_title(raw_text, city_list),
                "subtitle": subtitle,
                "description": description if desc is None else desc,
                "cover_image": cover,
                "images": json.dumps(img_urls, ensure_ascii=False),
                "cities": json.dumps(
                    [{"city": c, "district": "", "address": address} for c in city_list],
                    ensure_ascii=False,
                ),
                "city": city_list[0] if city_list else "",
                "district": "",
                "address": address,
                "start_date": s,
                "end_date": e,
                "organizer": organizer,
                "reservation": "no",
                "tags": json.dumps(tags, ensure_ascii=False),
                "source_url": source_url,
                "crawl_meta": json.dumps(meta, ensure_ascii=False),
            }

        if multi:
            items = []
            for c, s, e, line in schedules:
                # 地址就取该城市所在行（各城市地址通常跟在城市名后面）
                line_addrs = extract_addresses(line) if line else []
                # 详情里去掉属于其它城市的行，避免每家都堆着别家的档期
                own_desc = "\n".join(
                    l for l in description.splitlines()
                    if not any(o != c and o in l for o in cities)
                ).strip()
                items.append(_pack([c], s, e,
                                   line_addrs[0] if line_addrs else "",
                                   own_desc or description))
            return items

        return [_pack(cities, start, end, addresses[0] if addresses else "")]

    # ── 运行态（断点续爬）──
    def _get_state(self):
        from app.models.store import CrawlerState
        return self.db.query(CrawlerState).filter(CrawlerState.source == "weibo").first()

    def _update_state(self, success: bool, error: str = ""):
        from app.models.store import CrawlerState
        st = self._get_state()
        if not st:
            st = CrawlerState(source="weibo")
            self.db.add(st)
        st.last_run_at = datetime.now()
        if success:
            st.last_success_at = datetime.now()
            st.last_error = ""
        else:
            st.last_error = error
        self.db.commit()

    # ── 主入口 ──
    def run(self) -> "object":
        from app.models.store import CrawlLog
        now = datetime.now()
        state = self._get_state()
        # 增量抓取，但保留 lookback_days 的「回看下限」：
        # 若只取「上次成功之后」，两次运行往往只隔几小时，品牌账号在这么窄的窗口里
        # 基本没有新快闪帖，会长期 found=0。因此取「上次成功时刻」与「now-N天」中更早者。
        floor = now - timedelta(days=self.lookback_days)
        if state and state.last_success_at:
            since = min(state.last_success_at, floor)
        else:
            since = floor
        until = now

        items_all: List[dict] = []
        errors: List[str] = []
        hit_stats: List[str] = []  # 每个目标命中条数，用于日志诊断
        seen: set = set()          # 运行内去重键（含城市）
        pending: List[dict] = []   # 已抓到但尚未落库的条目
        added = 0

        # 凭证选择（v1.4.9）：后台填写的登录态 Cookie 优先，未填时才自动领访客 SUB。
        # 领凭证失败不再整轮中止——可能手填 Cookie 仍可用，也可能后面只是零命中。
        try:
            self._ensure_visitor_sub()
        except Exception as e:  # noqa: BLE001
            errors.append(f"[credential] {e}")
            logger.error("[weibo] 凭证准备失败，继续尝试抓取: %s", e)

        # 模式选择（v1.3.1：两种模式各自独立开关，可同时启用）：
        #   ① 账号监控(UID)  —— 优先级最高，先跑；其命中在去重时先入为主。
        #   ② 全站关键词搜索 —— 作为 UID 的补充，排在 UID 之后跑。
        #   两者都关 → 无目标空跑（安全 no-op，仅记录一条日志）。
        accounts = [a for a in (self.accounts or [])
                    if a and str(a.get("uid") or "").strip().isdigit()]
        do_accounts = bool(self.uid_enabled) and bool(accounts)
        do_keywords = bool(self.keyword_enabled) and bool(self.keywords)

        parts = []
        if do_accounts:
            parts.append(f"账号监控({len(accounts)}个有效账号)")
        if do_keywords:
            parts.append(f"关键词补充({len(self.keywords)}个)")
        if self.uid_enabled and not accounts:
            parts.append("账号监控已启用但无有效UID(跳过)")
        if self.keyword_enabled and not self.keywords:
            parts.append("关键词已启用但无关键词(跳过)")
        mode_desc = " + ".join(parts) if parts else "均已停用（无目标空跑）"
        logger.info("[weibo] 模式: %s｜窗口 since=%s until=%s 每账号/词页数=%d",
                    mode_desc, since, until, self.max_pages)

        def _drain() -> int:
            """把 pending 里的条目落库（增量保存）。

            每跑完一个目标就调用一次：后续目标报错/中断时，前面抓到的内容已经在草稿里了。
            整批入库失败时逐条重试，避免一条脏数据拖垮整批。
            """
            if not pending:
                return 0
            batch: List[dict] = []
            for it in pending:
                key = f"{it.get('source_url') or ''}#{it.get('city') or ''}"
                if key in seen:
                    continue
                seen.add(key)
                batch.append(it)
            pending.clear()
            if not batch:
                return 0
            try:
                return self.save_items(batch)
            except Exception as e:  # noqa: BLE001
                errors.append(f"[save] {e}")
                logger.error("[weibo] 整批入库失败，改为逐条重试: %s", e)
                n = 0
                for it in batch:
                    try:
                        n += self.save_items([it])
                    except Exception as e2:  # noqa: BLE001
                        errors.append(f"[save:item] {str(e2)[:80]}")
                return n

        def _run_targets(targets, is_account: bool) -> None:
            """顺序抓取一组目标；单个目标失败不影响其余（错误汇总进 errors）。"""
            nonlocal added
            for t in targets:
                label = t.get("name") or t.get("uid") or "?"
                try:
                    if is_account:
                        hits = self._collect_account_posts(t, since, until)
                    else:
                        hits = self._collect_posts(label, since, until)
                    hit_stats.append(f"{label}×{len(hits)}")
                    for mb, matched, text, account_mode in hits:
                        try:
                            # 一条微博可能拆成多条（多城市不同档期）
                            for item in self._parse_mblog(mb, matched, text, account_mode=account_mode):
                                if item:
                                    items_all.append(item)
                                    pending.append(item)
                        except Exception as e:  # noqa: BLE001
                            # 单条解析异常不该让整个目标前功尽弃
                            errors.append(f"[{label}:parse] {str(e)[:80]}")
                            logger.error("[weibo] %s 解析单条失败: %s", label, e)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"[{label}] {e}")
                    logger.error("[weibo] %s 失败: %s", label, e)
                # 该目标的内容先落库，再继续下一个（即便后面失败也不丢）
                added += _drain()
                # 目标之间留大间隔（默认 60s），这是规避微博限流的关键
                time.sleep(self.keyword_interval)

        # ① UID 账号监控（优先）
        # ② 全站关键词搜索（补充，排在 UID 之后）
        # 整段包 try：任何一个目标/环节抛出未预期异常，前面已抓到的内容仍会在 finally 里落库。
        try:
            if do_accounts:
                _run_targets(accounts, True)
            if do_keywords:
                _run_targets([{"name": kw, "uid": ""} for kw in self.keywords], False)
        except Exception as e:  # noqa: BLE001
            errors.append(f"[fatal] {e}")
            logger.exception("[weibo] 抓取流程异常中断，已抓到的部分仍会入库: %s", e)
        finally:
            added += _drain()

        # ok=-100 诊断：区分「访客 SUB 也未生效（出口 IP 被 WAF 拦）/ 已用访客 SUB 仍被限流」
        if any("ok!=-100" in e for e in errors):
            if self._manual_cookie:
                logger.error(
                    "[weibo] ⚠️ 微博返回 ok=-100：本次用的是「爬虫」页面手填的 Cookie，仍被判为未登录，"
                    "多为 Cookie 已过期或复制不完整（务必含 SUB，最好连 SUBP 一起）。"
                    "请重新登录 m.weibo.cn 后复制整串 Cookie；若反复无效，可清空该输入框，"
                    "让系统自动领取访客 SUB（能过 WAF，但账号时间线大概率仍 -100）。"
                )
            elif not self._auto_sub:
                logger.error(
                    "[weibo] ⚠️ 微博返回 ok=-100，且自动访客 SUB 也未能生效："
                    "多为出口 IP 被微博 WAF(SHANHAI) 物理拦截（常见于数据中心/云服务器 IP），"
                    "此时连 genvisitor2 都被拦。请改用住宅/宽带网络出口，或在「爬虫」页面手动填写微博 Cookie。"
                )
            else:
                logger.error(
                    "[weibo] ⚠️ 微博返回 ok=-100：已用自动访客 SUB 仍多为请求过快被限流（已自动退避重试）。"
                    "若仍频繁出现，可继续加大 weibo_crawler.py 顶部的 KEYWORD_INTERVAL。"
                )

        # HTTP 432 诊断：请求在 HTTP 层被微博 WAF(山海) 直接拦截（不是 JSON 里的 ok=-100）。
        # 说明访客 SUB/SUBP 这一对凭证未被接受——最常见是 genvisitor2 未领到有效值，
        # 或本机出口 IP 被 WAF 物理拉黑（云/数据中心 IP 高发）。
        if any("HTTP 432" in e for e in errors):
            if self._manual_cookie:
                logger.error(
                    "[weibo] ⚠️ 微博接口返回 HTTP 432：本次用的是「爬虫」页面手填的 Cookie，仍被 WAF(山海) 拦截。"
                    "多为 Cookie 过期/不完整（缺 SUB 或 SUBP），或 NAS 出口 IP 被拉黑。"
                    "请重新登录后复制完整 Cookie；若 NAS 走云/机房 IP，建议改用本地宽带机器跑爬虫。"
                )
            elif self._auto_sub:
                logger.error(
                    "[weibo] ⚠️ 微博接口返回 HTTP 432：已自动领取访客 SUB/SUBP，但仍被 WAF 拦截。"
                    "多为「访客凭证刚领就被标记异常」或「出口 IP 被 WAF 物理拉黑」。可尝试："
                    "① 加大 weibo_crawler.py 顶部 KEYWORD_INTERVAL（降低请求密度）；"
                    "② 在「爬虫」页面手动填写有效微博 Cookie（住宅/宽带 IP 下通常稳定）。"
                )
            else:
                logger.error(
                    "[weibo] ⚠️ 微博接口返回 HTTP 432：自动访客 SUB 也未能领取成功（genvisitor2 本身被拦），"
                    "基本可判定为【出口 IP 被微博 WAF(山海) 物理拦截】（常见于云服务器/数据中心 IP）。"
                    "此时唯一的出路是在「爬虫」页面手动填写有效微博 Cookie（仅住宅宽带 IP 下有效）；"
                    "若 NAS 走的是云/机房 IP，则微博抓取基本不可用，建议改用本地宽带机器跑爬虫。"
                )

        # 连接层诊断：对端在返回响应前就断开（RemoteDisconnected / Connection aborted）。
        # 常见三类原因：① 长间隔后复用已被关闭的 keep-alive 连接（已由 CONN_IDLE_RESET 处理）；
        # ② WAF 判异常后单方面断连；③ 本地网络/代理抖动。
        if any(("RemoteDisconnected" in e or "Connection aborted" in e) for e in errors):
            logger.error(
                "[weibo] ⚠️ 出现连接被对端关闭（RemoteDisconnected）：已做退避重试仍失败。"
                "优先排查：① 是否在同一出口 IP 上并发跑了多个爬虫（本机 automation 与 NAS 会互相污染）；"
                "② 手填 Cookie 是否过期被 WAF 判异常；③ 若反复出现，"
                "可调大 weibo_crawler.py 顶部的 KEYWORD_INTERVAL（如 120）降低请求密度。"
            )

        # 水位线策略：只要本轮有错误就不推进 last_success_at，
        # 否则「跑到一半失败」会把没跑到的目标永久跳过；已入库的内容靠去重键自动跳过，不会重复。
        self._update_state(success=not errors, error="\n".join(errors)[:500])

        # 日志记录本次实际跑过的目标（UID 账号名在前、关键词补充在后），便于回溯
        _targets_logged: List[str] = []
        if do_accounts:
            _targets_logged += [a.get("name", "") for a in accounts]
        if do_keywords:
            _targets_logged += list(self.keywords)
        keyword_field = ",".join(_targets_logged)
        # 诊断摘要写进日志，便于在后台页面直接判断「没抓到」属于哪种情况
        hits_txt = "、".join(s for s in hit_stats if not s.endswith("×0")) or "全部目标 0 命中"
        diag = (f"[诊断] 窗口 {since:%m-%d %H:%M} ~ {until:%m-%d %H:%M}"
                f"（回看 {self.lookback_days} 天）｜{len(hit_stats)} 个目标｜命中：{hits_txt}"
                f"｜入库 {added} 条")
        _err_txt = "\n".join(errors)
        error_detail = f"{diag}\n{_err_txt}" if _err_txt else diag

        # 部分成功（有错但已救回一部分）记为 partial，全没入库才算 failed
        status = "success" if not errors else ("partial" if added else "failed")
        try:
            log = CrawlLog(
                source=self.source,
                keyword=keyword_field[:120],
                total_found=len(items_all),
                new_added=added,
                error_count=len(errors),
                error_detail=error_detail[:2000],
                status=status,
            )
            self.db.add(log)
            self.db.commit()
        except Exception as e:  # noqa: BLE001
            logger.error("[weibo] 写运行日志失败（已入库内容不受影响）: %s", e)
            log = None
        logger.info("[weibo] 完成(%s)：发现 %d，新增 %d，错误 %d",
                    status, len(items_all), added, len(errors))
        return log
