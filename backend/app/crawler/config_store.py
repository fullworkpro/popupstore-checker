"""爬虫配置存取 — 运行时配置存于 crawler_config 表（单例 key='global'）。

config.py 中的 CRAWLER_* 仅作为首次建表时的种子默认值；
此后一切配置以数据库为准，由前端「爬虫」页面读写。

字段说明：
- weibo_keywords：二次元 IP 关键词列表（龙珠/原神/鸣潮/chiikawa…），用于全站搜索原创快闪微博（备选模式）；
- weibo_accounts：微博账号监控列表 [{"name","uid"}]，监控官方/品牌账号时间线抓原创快闪帖（首选模式）；
- weibo_max_pages：每个关键词/账号最多翻几页；
- weibo_cookie / xhs_cookie / douyin_cookie：各平台登录凭据（敏感，仅存库）；
- xhs_enabled / douyin_enabled：其它平台开关（当前未实现，调度器会跳过）。
"""
import json
import logging
import re
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.store import CrawlerConfig

logger = logging.getLogger("crawler.config")

_SEED_DEFAULTS = {
    "enabled": settings.CRAWLER_ENABLED,
    "weibo_keywords": settings.CRAWLER_WEIBO_KEYWORDS,
    "weibo_accounts": settings.CRAWLER_WEIBO_ACCOUNTS,
    "weibo_uid_enabled": settings.CRAWLER_WEIBO_UID_ENABLED,
    "weibo_keyword_enabled": settings.CRAWLER_WEIBO_KEYWORD_ENABLED,
    "weibo_max_pages": settings.CRAWLER_WEIBO_MAX_PAGES,
    "weibo_cookie": settings.CRAWLER_WEIBO_COOKIE,
    "xhs_enabled": settings.CRAWLER_XHS_ENABLED,
    "xhs_cookie": settings.CRAWLER_XHS_COOKIE,
    "douyin_enabled": settings.CRAWLER_DOUYIN_ENABLED,
    "douyin_cookie": settings.CRAWLER_DOUYIN_COOKIE,
    "schedule": settings.CRAWLER_SCHEDULE,
    "lookback_days": settings.CRAWLER_WEIBO_LOOKBACK_DAYS,
}

_RE_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _seed_json(key: str, value) -> str:
    """列表/字典字段存库前转 JSON 字符串。"""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def get_or_create_config(db: Session) -> CrawlerConfig:
    """返回全局爬虫配置；若无则按 settings 种子创建；若为旧行则回填缺失字段。"""
    cfg = db.query(CrawlerConfig).filter(CrawlerConfig.key == "global").first()
    if cfg is None:
        cfg = CrawlerConfig(key="global")
        cfg.enabled = _SEED_DEFAULTS["enabled"]
        cfg.weibo_keywords = _seed_json("weibo_keywords", _SEED_DEFAULTS["weibo_keywords"])
        cfg.weibo_accounts = _seed_json("weibo_accounts", _SEED_DEFAULTS["weibo_accounts"])
        cfg.weibo_uid_enabled = _SEED_DEFAULTS["weibo_uid_enabled"]
        cfg.weibo_keyword_enabled = _SEED_DEFAULTS["weibo_keyword_enabled"]
        cfg.weibo_max_pages = _SEED_DEFAULTS["weibo_max_pages"]
        cfg.weibo_cookie = _SEED_DEFAULTS["weibo_cookie"]
        cfg.xhs_enabled = _SEED_DEFAULTS["xhs_enabled"]
        cfg.xhs_cookie = _SEED_DEFAULTS["xhs_cookie"]
        cfg.douyin_enabled = _SEED_DEFAULTS["douyin_enabled"]
        cfg.douyin_cookie = _SEED_DEFAULTS["douyin_cookie"]
        cfg.schedule = _seed_json("schedule", _SEED_DEFAULTS["schedule"])
        cfg.lookback_days = _SEED_DEFAULTS["lookback_days"]
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        logger.info("[crawler-config] 已用 settings 种子初始化爬虫配置")
        return cfg

    # 旧行回填（v1.2.1 升级而来可能缺 weibo_keywords 等列，迁移后为空）
    def _list(v):
        try:
            return json.loads(v) if isinstance(v, str) else v
        except Exception:
            return None

    dirty = False
    # 注意：仅当该列从未设置（值为 None / 解析失败）才回填种子；
    # 若用户曾显式清空为 []，则保留空值（表示「关闭该模式」），不再强制填回。
    kw = _list(cfg.weibo_keywords)
    if kw is None:  # 未设置 → 用种子默认值填充
        cfg.weibo_keywords = _seed_json("weibo_keywords", _SEED_DEFAULTS["weibo_keywords"])
        dirty = True
    acc = _list(cfg.weibo_accounts)
    if acc is None:  # 未设置 → 用种子默认值填充（含 10 个品牌账号）
        cfg.weibo_accounts = _seed_json("weibo_accounts", _SEED_DEFAULTS["weibo_accounts"])
        dirty = True
    # 模式开关（v1.3.1 新增列）：未设置时回填默认「UID 开、关键词关」
    if cfg.weibo_uid_enabled is None:
        cfg.weibo_uid_enabled = _SEED_DEFAULTS["weibo_uid_enabled"]
        dirty = True
    if cfg.weibo_keyword_enabled is None:
        cfg.weibo_keyword_enabled = _SEED_DEFAULTS["weibo_keyword_enabled"]
        dirty = True
    if cfg.weibo_max_pages is None:
        cfg.weibo_max_pages = _SEED_DEFAULTS["weibo_max_pages"]
        dirty = True
    if cfg.xhs_enabled is None:
        cfg.xhs_enabled = _SEED_DEFAULTS["xhs_enabled"]
        dirty = True
    if cfg.douyin_enabled is None:
        cfg.douyin_enabled = _SEED_DEFAULTS["douyin_enabled"]
        dirty = True
    if dirty:
        db.commit()
        db.refresh(cfg)
        logger.info("[crawler-config] 已回填缺失字段")
    return cfg


def get_config(db: Session) -> CrawlerConfig:
    """等同 get_or_create，语义化别名。"""
    return get_or_create_config(db)


def config_to_dict(cfg: CrawlerConfig) -> dict:
    return cfg.to_dict()


def validate_schedule(times: List[str]) -> List[str]:
    """校验 ["HH:MM", ...]，返回规范化列表；非法项抛 ValueError。"""
    out: List[str] = []
    if not isinstance(times, list) or not times:
        raise ValueError("排程时刻不能为空，至少包含一个 HH:MM")
    for t in times:
        t = str(t).strip()
        if not _RE_HHMM.match(t):
            raise ValueError(f"排程时刻格式非法: {t!r}（应为 HH:MM，如 02:00）")
        out.append(t)
    return out


def validate_keywords(keywords: List[str]) -> List[str]:
    """校验二次元 IP 关键词列表，返回去空白、去重后的列表。

    允许为空：当已配置「账号监控」有效 UID 时，关键词仅作为兜底，可清空。
    仅当完全没有账号、又清空关键词时，run() 会退化为无目标空跑（安全 no-op）。
    """
    if not isinstance(keywords, list):
        raise ValueError("微博关键词必须是数组")
    out = []
    for k in keywords:
        k = str(k).strip()
        if k and k not in out:
            out.append(k)
    return out


def validate_accounts(accounts) -> List[dict]:
    """校验微博监控账号列表 [{"name","uid"}]，返回规范化的列表。

    - 每个元素必须是 {name, uid} 对象；
    - name 必填；
    - uid 允许为空（暂未配置，前端填好后再补），但非空时必须是纯数字（微博主页 /u/ 后的数字）。
    """
    if not isinstance(accounts, list):
        raise ValueError("微博监控账号必须是数组")
    out = []
    for a in accounts:
        if not isinstance(a, dict):
            raise ValueError("每个账号必须是 {name, uid} 对象")
        name = str(a.get("name") or "").strip()
        uid = str(a.get("uid") or "").strip()
        if not name:
            raise ValueError("账号 name 不能为空")
        if uid and not uid.isdigit():
            raise ValueError(f"账号「{name}」的 uid 必须是数字（微博主页 /u/ 后的数字）")
        out.append({"name": name, "uid": uid})
    return out


def apply_config_update(db: Session, payload: dict) -> CrawlerConfig:
    """将前端提交的配置合并写入数据库，返回更新后的配置。

    payload 字段均为可选（部分更新）。
    """
    cfg = get_or_create_config(db)

    if "enabled" in payload and payload["enabled"] is not None:
        cfg.enabled = bool(payload["enabled"])

    if "weibo_keywords" in payload and payload["weibo_keywords"] is not None:
        kws = payload["weibo_keywords"]
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.replace("\n", ",").split(",") if k.strip()]
        cfg.weibo_keywords = _seed_json("weibo_keywords", validate_keywords(kws))

    if "weibo_accounts" in payload and payload["weibo_accounts"] is not None:
        cfg.weibo_accounts = _seed_json("weibo_accounts", validate_accounts(payload["weibo_accounts"]))

    # 两种模式的独立开关（v1.3.1）：可同时启用，执行顺序 UID → 关键词补充
    if "weibo_uid_enabled" in payload and payload["weibo_uid_enabled"] is not None:
        cfg.weibo_uid_enabled = bool(payload["weibo_uid_enabled"])

    if "weibo_keyword_enabled" in payload and payload["weibo_keyword_enabled"] is not None:
        cfg.weibo_keyword_enabled = bool(payload["weibo_keyword_enabled"])

    if "weibo_max_pages" in payload and payload["weibo_max_pages"] is not None:
        try:
            mp = int(payload["weibo_max_pages"])
        except (TypeError, ValueError):
            raise ValueError("每关键词搜索页数必须是正整数")
        if mp < 1 or mp > 20:
            raise ValueError("每关键词搜索页数应在 1~20 之间")
        cfg.weibo_max_pages = mp

    if "schedule" in payload and payload["schedule"] is not None:
        cfg.schedule = _seed_json("schedule", validate_schedule(payload["schedule"]))

    if "lookback_days" in payload and payload["lookback_days"] is not None:
        try:
            d = int(payload["lookback_days"])
        except (TypeError, ValueError):
            raise ValueError("回看天数必须是正整数")
        if d < 0 or d > 365:
            raise ValueError("回看天数应在 0~365 之间")
        cfg.lookback_days = d

    if "weibo_cookie" in payload:  # 允许清空
        cfg.weibo_cookie = str(payload["weibo_cookie"] or "")

    # 其它平台（当前未实现，仅存储配置，供后续扩展）
    if "xhs_enabled" in payload and payload["xhs_enabled"] is not None:
        cfg.xhs_enabled = bool(payload["xhs_enabled"])
    if "xhs_cookie" in payload:
        cfg.xhs_cookie = str(payload["xhs_cookie"] or "")
    if "douyin_enabled" in payload and payload["douyin_enabled"] is not None:
        cfg.douyin_enabled = bool(payload["douyin_enabled"])
    if "douyin_cookie" in payload:
        cfg.douyin_cookie = str(payload["douyin_cookie"] or "")

    db.commit()
    db.refresh(cfg)
    logger.info("[crawler-config] 配置已更新 enabled=%s 关键词数=%d 排程=%s",
                cfg.enabled, len(json.loads(cfg.weibo_keywords)), cfg.schedule)
    return cfg
