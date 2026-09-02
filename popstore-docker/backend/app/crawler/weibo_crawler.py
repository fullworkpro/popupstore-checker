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

CJK = r"[\u4e00-\u9fff]"

# ─────────────────────────── 反爬/限流参数 ───────────────────────────
# 微博 m.weibo.cn 搜索接口对「未限速的批量请求」极其敏感：
# 连续请求会在第 1~2 次后返回 ok=-100（请求过快/需登录），导致后续全挂。
# 因此必须做「请求间隔 + 关键词间大间隔 + 退避重试」。
REQUEST_INTERVAL = 5.0   # 同一关键词内两次请求（翻页/长文）的最小间隔（秒），含随机抖动
KEYWORD_INTERVAL = 60.0  # 两个关键词之间的额外间隔（秒）；限流严重时可继续加大（如 120）
MAX_RETRIES = 3          # 遇到 ok=-100 时的最大重试次数
RETRY_BACKOFF = 20.0     # 退避基数（秒）：第 1/2/3 次重试分别等 20/40/60 秒


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


def is_popup_post(text: str) -> bool:
    return "快闪" in text


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
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": settings.CRAWLER_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://m.weibo.cn/",
        })
        # Cookie 不在初始化时设置；统一在 run() 开头由 _ensure_visitor_sub() 决定：
        # 优先用当场新领的访客 SUB，失败才回退用户填写的 Cookie。

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

    def _ensure_visitor_sub(self) -> bool:
        """领取访客 SUB/SUBP 并作为【首选】凭证，彻底解决「填了过期 Cookie 反而全 -100/432」的坑。

        关键修正（旧版本的重大缺陷）：
          旧逻辑是「只要用户在页面填了 Cookie 就跳过 visitor 自动领取」。
          但用户手动填的 Cookie 往往是几天前复制的、早已过期，于是每条请求都
          返回 ok=-100 / HTTP 432（需要登录态）——表现就是「重新构建了还是被限流」。

        新逻辑：
          1) 无论用户是否填 Cookie，都先尝试领取一个【当场新领】的访客 SUB+SUBP；
          2) 成功则把它作为唯一凭证（清掉任何手工 Cookie，避免过期登录态干扰）；
          3) 仅当 genvisitor2 自身失败（出口 IP 被微博 WAF 物理拦截）时，才回退
             到用户填写的 Cookie；二者皆无则裸请求（搜索大概率 -100，属预期）。
        """
        res = self._fetch_visitor_sub()
        if res:
            sub, subp = res
            self.session.cookies.clear()
            self.session.cookies.set("SUB", sub, domain=".weibo.com")
            if subp:
                self.session.cookies.set("SUBP", subp, domain=".weibo.com")
            # 清掉可能的手工 Cookie 头，让 cookie jar 成为唯一权威来源
            self.session.headers.pop("Cookie", None)
            self._auto_sub = True
            logger.info("[weibo] 已自动获取访客 SUB%s（首选凭证，不受你填写的 Cookie 是否过期影响）",
                        "/SUBP" if subp else "")
            return True
        # genvisitor2 失败：回退到用户手动 Cookie（若有）
        if self.cookie:
            self.session.cookies.clear()
            self.session.headers["Cookie"] = self.cookie
            logger.warning(
                "[weibo] 自动获取访客 SUB 失败（出口 IP 或被 WAF 拦截），回退使用你填写的 Cookie"
            )
            return True
        logger.warning(
            "[weibo] 自动获取访客 SUB 失败且未填 Cookie（出口 IP 可能被 WAF 拦截），将尝试无 Cookie 请求"
        )
        return False

    # ── 网络：全站关键词搜索 ──
    def _throttle(self) -> None:
        """保证两次请求之间至少间隔 request_interval 秒（含随机抖动），规避微博限流。"""
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
                     account_mode: bool = False) -> Optional[dict]:
        bid = mb.get("bid") or mb.get("id")
        if not bid:
            return None
        user = mb.get("user") or {}
        uid = str(user.get("id") or user.get("idstr") or "")
        source_url = f"https://weibo.com/{uid}/{bid}" if uid else f"https://m.weibo.cn/detail/{bid}"

        raw_text = text
        if mb.get("isLongText"):
            raw_text = self._fetch_long_text(mb.get("id"), text)

        title = extract_title(raw_text)
        start, end = extract_date_range(raw_text)
        cities = extract_cities(raw_text)
        addresses = extract_addresses(raw_text)

        pics = mb.get("pics") or []
        img_urls = []
        for p in pics:
            u = (p.get("large") or {}).get("url") or p.get("url") or ""
            if u:
                img_urls.append(u)
        cover = img_urls[0] if img_urls else ""

        organizer = user.get("screen_name", "")
        if account_mode:
            # 账号监控模式：账号本身就是品牌，tag 用「快闪」+ 账号名，不再套「二次元」
            tags = ["快闪"] + [k for k in matched if k not in ("联名",)]
        else:
            tags = ["快闪", "二次元"] + [k for k in matched if k not in ("联名",)]
        meta = {
            "source_images": img_urls,       # 新浪图床直链，仅供参考，人工后续转存图床
            "raw_text": raw_text,
            "matched_keywords": matched,
            "needs_time": start is None,     # 时间仅在海报图 → 需人工补全
            "needs_address": len(addresses) == 0,
            "images_need_upload": True,      # 图片由人工上传图床
        }
        cities_json = json.dumps(
            [{"city": c, "district": "", "address": ""} for c in cities],
            ensure_ascii=False,
        )

        return {
            "title": title,
            "subtitle": "",
            "description": raw_text,
            "cover_image": cover,
            "images": json.dumps(img_urls, ensure_ascii=False),
            "cities": cities_json,
            "city": cities[0] if cities else "",
            "district": "",
            "address": addresses[0] if addresses else "",
            "start_date": start,
            "end_date": end,
            "organizer": organizer,
            "reservation": "no",
            "tags": json.dumps(tags, ensure_ascii=False),
            "source_url": source_url,
            "crawl_meta": json.dumps(meta, ensure_ascii=False),
        }

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
        if state and state.last_success_at:
            since = state.last_success_at
        else:
            since = now - timedelta(days=self.lookback_days)
        until = now

        # 自动领取访客 SUB 并作为【首选】凭证（无论是否填了 Cookie 都会先尝试领取，
        # 解决「填了过期 Cookie 反而全 -100」的坑）。NAS 住宅 IP 一般直接成功，
        # 数据中心 IP 若被 WAF 物理拦截则自动回退到用户手动 Cookie。
        self._ensure_visitor_sub()

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

        items_all: List[dict] = []
        errors: List[str] = []

        def _run_targets(targets, is_account: bool) -> None:
            """顺序抓取一组目标；单个目标失败不影响其余（错误汇总进 errors）。"""
            for t in targets:
                label = t.get("name") or t.get("uid") or "?"
                try:
                    if is_account:
                        hits = self._collect_account_posts(t, since, until)
                    else:
                        hits = self._collect_posts(label, since, until)
                    for mb, matched, text, account_mode in hits:
                        item = self._parse_mblog(mb, matched, text, account_mode=account_mode)
                        if item:
                            items_all.append(item)
                except Exception as e:
                    errors.append(f"[{label}] {e}")
                    logger.error("[weibo] %s 失败: %s", label, e)
                # 目标之间留大间隔（默认 60s），这是规避微博限流的关键
                time.sleep(self.keyword_interval)

        # ① UID 账号监控（优先）
        if do_accounts:
            _run_targets(accounts, True)
        # ② 全站关键词搜索（补充，排在 UID 之后）
        if do_keywords:
            _run_targets([{"name": kw, "uid": ""} for kw in self.keywords], False)

        # ok=-100 诊断：区分「访客 SUB 也未生效（出口 IP 被 WAF 拦）/ 已用访客 SUB 仍被限流」
        if any("ok!=-100" in e for e in errors):
            if not self._auto_sub:
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
            if self._auto_sub:
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

        # 运行内去重
        seen, uniq = set(), []
        for it in items_all:
            if it["source_url"] in seen:
                continue
            seen.add(it["source_url"])
            uniq.append(it)

        new_added = 0
        try:
            new_added = self.save_items(uniq)
        except Exception as e:
            errors.append(f"[save] {e}")
            logger.error("[weibo] 入库失败: %s", e)

        self._update_state(success=not errors, error="\n".join(errors)[:500])

        # 日志记录本次实际跑过的目标（UID 账号名在前、关键词补充在后），便于回溯
        _targets_logged: List[str] = []
        if do_accounts:
            _targets_logged += [a.get("name", "") for a in accounts]
        if do_keywords:
            _targets_logged += list(self.keywords)
        keyword_field = ",".join(_targets_logged)
        log = CrawlLog(
            source=self.source,
            keyword=keyword_field[:120],
            total_found=len(items_all),
            new_added=new_added,
            error_count=len(errors),
            error_detail="\n".join(errors)[:2000],
            status="failed" if errors else "success",
        )
        self.db.add(log)
        self.db.commit()
        logger.info("[weibo] 完成：发现 %d，新增 %d，错误 %d", len(items_all), new_added, len(errors))
        return log
