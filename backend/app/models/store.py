"""快闪店数据模型"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, Float, Enum as SAEnum
from app.core.database import Base
import enum


class StoreStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class StoreSource(str, enum.Enum):
    MANUAL = "manual"
    CRAWLER = "crawler"
    WECHAT = "wechat"
    XIAOHONGSHU = "xiaohongshu"
    WEIBO = "weibo"


# 快闪类型（小程序首页筛选 + 后台录入时使用）
#   popup       联名快闪（默认）
#   exhibition  特展
#   restaurant  联名餐厅
STORE_TYPES = [
    {"value": "popup", "label": "联名快闪"},
    {"value": "exhibition", "label": "特展"},
    {"value": "restaurant", "label": "联名餐厅"},
]
STORE_TYPE_VALUES = [t["value"] for t in STORE_TYPES]
DEFAULT_STORE_TYPE = "popup"


def store_type_label(value: str) -> str:
    """快闪类型 code → 中文名；未知/空值回退默认类型名。"""
    for t in STORE_TYPES:
        if t["value"] == value:
            return t["label"]
    return STORE_TYPES[0]["label"]


class Store(Base):
    __tablename__ = "stores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False, index=True)
    subtitle = Column(String(300), default="")
    description = Column(Text, default="")
    cover_image = Column(String(500), default="")          # 封面图 URL
    images = Column(Text, default="[]")                     # JSON 数组，多图
    cities = Column(Text, default="[]")                     # JSON 数组，多城市：[{city, district, address}]
    city = Column(String(50), default="", index=True)       # 主城市（cities[0]），用于筛选/兼容
    district = Column(String(50), default="")
    address = Column(String(300), default="")               # 主地址（cities[0]）
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    start_date = Column(DateTime, nullable=True, index=True)
    end_date = Column(DateTime, nullable=True)
    organizer = Column(String(200), default="")             # 主办方/品牌
    reservation = Column(String(20), default="no")          # 预约方式: required(需预约)/advance(前期需预约)/no(无需预约)
    store_type = Column(String(20), default=DEFAULT_STORE_TYPE, index=True)  # 快闪类型: popup/exhibition/restaurant
    tags = Column(String(500), default="[]")                # JSON 数组
    source = Column(String(20), default=StoreSource.MANUAL.value)
    source_url = Column(String(500), default="")            # 原始链接
    status = Column(String(20), default=StoreStatus.DRAFT.value, index=True)
    view_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)

    # 审核信息
    reviewed_by = Column(String(36), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_comment = Column(Text, default="")

    # 爬虫原始提取信息（JSON）：源图URL、原始正文、命中关键词、待人工补全字段标记
    # needs_time / needs_address / images_need_upload 为 True 时表示该项需人工在待发布中补全。
    crawl_meta = Column(Text, default="{}")

    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "description": self.description,
            "cover_image": self.cover_image,
            "images": self.images,
            "cities": self.cities,
            "city": self.city,
            "district": self.district,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "organizer": self.organizer,
            "reservation": self.reservation,
            "store_type": self.store_type or DEFAULT_STORE_TYPE,
            "store_type_label": store_type_label(self.store_type),
            "tags": self.tags,
            "source": self.source,
            "source_url": self.source_url,
            "status": self.status,
            "view_count": self.view_count,
            "share_count": self.share_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(20), nullable=False)
    keyword = Column(String(100), default="")
    total_found = Column(Integer, default=0)
    new_added = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    error_detail = Column(Text, default="")
    status = Column(String(20), default="success")  # success / partial / failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "keyword": self.keyword,
            "total_found": self.total_found,
            "new_added": self.new_added,
            "error_count": self.error_count,
            "error_detail": self.error_detail,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CrawlerState(Base):
    """爬虫运行态 — 记录各数据源上次成功执行时间，实现「断点续爬 / 时间窗追爬」。

    since = last_success_at or (now - lookback)；until = now。
    定时任务若连续多天未执行，窗口自然覆盖「上次成功 → 现在」，从而追爬遗漏的微博。
    """

    __tablename__ = "crawler_state"

    source = Column(String(20), primary_key=True)        # 如 'weibo'
    last_success_at = Column(DateTime, nullable=True)    # 上次成功完成的时刻
    last_run_at = Column(DateTime, nullable=True)        # 上次尝试时刻（含失败）
    last_error = Column(Text, default="")                # 最近一次错误信息
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CrawlerConfig(Base):
    """爬虫运行时配置（单例，key 固定 'global'）。

    配置通过前端「爬虫」页面读写，落库后即为运行时真值；
    config.py 中的 CRAWLER_* 仅作为首次建表时的种子默认值。
    各数据源独立开关/凭据，便于后续扩展（微博已落地，小红书/抖音规划中）。
    """

    __tablename__ = "crawler_config"

    key = Column(String(20), primary_key=True, default="global")
    enabled = Column(Boolean, default=True)                       # 总开关（定时任务是否运行）
    # 微博：按「二次元 IP 关键词」全站搜索原创快闪微博（UID 的补充模式，优先级低于 UID）
    weibo_keywords = Column(Text, default="[]")                   # JSON: ["龙珠","原神",...] IP 名列表
    weibo_max_pages = Column(Integer, default=3)                  # 每个关键词最多翻几页
    weibo_cookie = Column(Text, default="")                       # 可选：WAF 拦截时的浏览器 Cookie
    # 微博：按「账号」监控时间线（首选模式，游客可读、限流轻）—— JSON: [{"name","uid"}, ...]
    weibo_accounts = Column(Text, default="[]")
    # 两种模式各自独立的启停开关（v1.3.1）：
    #   两者可同时启用，执行顺序为「先 UID 账号监控 → 再全站关键词补充」，
    #   UID 命中优先（去重时先入为主），关键词结果作为补充。
    weibo_uid_enabled = Column(Boolean, default=True)             # 账号监控开关（默认开，优先级最高）
    weibo_keyword_enabled = Column(Boolean, default=False)        # 全站关键词搜索开关（默认关，作为补充）
    # 小红书（规划中）
    xhs_enabled = Column(Boolean, default=False)
    xhs_cookie = Column(Text, default="")
    # 抖音（规划中）
    douyin_enabled = Column(Boolean, default=False)
    douyin_cookie = Column(Text, default="")
    # 通用
    schedule = Column(Text, default='["02:00","13:00"]')          # JSON: ["HH:MM", ...]（Asia/Shanghai）
    lookback_days = Column(Integer, default=1)                    # 首次无成功记录时回看天数
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        import json as _json
        def _j(v, default):
            try:
                return _json.loads(v) if isinstance(v, str) else v
            except Exception:
                return default
        return {
            "key": self.key,
            "enabled": self.enabled,
            "weibo_keywords": _j(self.weibo_keywords, []),
            "weibo_accounts": _j(self.weibo_accounts, []),
            # None（列刚补、未回填）时给保守默认：UID 开、关键词关
            "weibo_uid_enabled": True if self.weibo_uid_enabled is None else bool(self.weibo_uid_enabled),
            "weibo_keyword_enabled": False if self.weibo_keyword_enabled is None else bool(self.weibo_keyword_enabled),
            "weibo_max_pages": self.weibo_max_pages,
            "has_cookie": bool(self.weibo_cookie),
            "xhs_enabled": self.xhs_enabled,
            "has_xhs_cookie": bool(self.xhs_cookie),
            "douyin_enabled": self.douyin_enabled,
            "has_douyin_cookie": bool(self.douyin_cookie),
            "schedule": _j(self.schedule, ["02:00", "13:00"]),
            "lookback_days": self.lookback_days,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
