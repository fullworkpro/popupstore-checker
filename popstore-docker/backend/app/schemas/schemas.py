"""Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re

from app.models.store import STORE_TYPE_VALUES, DEFAULT_STORE_TYPE

# 纯日期 YYYY-MM-DD 检测（前端日期选择器回传的格式）
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_date_value(v):
    """前端日期选择器回传纯日期 'YYYY-MM-DD'，后端字段是 datetime，需补零时刻
    转成 'YYYY-MM-DDT00:00:00' 才能被 pydantic 解析；空串/None 统一转 None。"""
    if v is None or v == "" or v == "null":
        return None
    if isinstance(v, str) and _DATE_ONLY_RE.match(v):
        return v + "T00:00:00"
    return v


# ── 认证 ──
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class TokenPayload(BaseModel):
    sub: str  # admin_id
    username: str


# ── 快闪店 ──
class StoreBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    subtitle: Optional[str] = ""
    description: Optional[str] = ""
    cover_image: Optional[str] = ""
    images: Optional[str] = "[]"
    cities: Optional[str] = "[]"
    city: Optional[str] = ""
    district: Optional[str] = ""
    address: Optional[str] = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    organizer: Optional[str] = ""
    reservation: Optional[str] = "no"
    store_type: Optional[str] = DEFAULT_STORE_TYPE     # popup 联名快闪 / exhibition 特展 / restaurant 联名餐厅
    tags: Optional[str] = "[]"
    source: Optional[str] = "manual"
    source_url: Optional[str] = ""

    @validator("reservation", pre=True, always=True)
    def _norm_reservation(cls, v):
        return v if v in ("required", "advance", "no") else "no"

    @validator("store_type", pre=True, always=True)
    def _norm_store_type(cls, v):
        # 未知/空值一律回退默认类型（联名快闪），避免脏数据导致小程序筛选失效
        return v if v in STORE_TYPE_VALUES else DEFAULT_STORE_TYPE

    # 前端日期选择器回传纯日期 "YYYY-MM-DD"，后端字段是 datetime，
    # 需补零时刻转为 "YYYY-MM-DDT00:00:00"；空串/None 统一转 None。
    @validator("start_date", "end_date", pre=True)
    def _normalize_dates(cls, v):
        return _normalize_date_value(v)


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    cover_image: Optional[str] = None
    images: Optional[str] = None
    cities: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    organizer: Optional[str] = None
    reservation: Optional[str] = None
    store_type: Optional[str] = None
    tags: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None

    @validator("start_date", "end_date", pre=True)
    def _normalize_dates_update(cls, v):
        return _normalize_date_value(v)

    @validator("reservation")
    def _check_reservation(cls, v):
        if v is None:
            return None
        return v if v in ("required", "advance", "no") else "no"

    @validator("store_type")
    def _check_store_type(cls, v):
        if v is None:
            return None
        return v if v in STORE_TYPE_VALUES else DEFAULT_STORE_TYPE


class StoreResponse(StoreBase):
    id: str
    status: str
    view_count: int
    share_count: int
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StoreListResponse(BaseModel):
    items: List[StoreResponse]
    total: int
    page: int
    page_size: int


# ── 审核 ──
class ReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(published|rejected|archived)$")
    comment: Optional[str] = ""


# ── 爬虫日志 ──
class CrawlLogResponse(BaseModel):
    id: str
    source: str
    keyword: str
    total_found: int
    new_added: int
    error_count: int
    error_detail: str
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CrawlLogListResponse(BaseModel):
    items: List[CrawlLogResponse]
    total: int
    page: int
    page_size: int


# ── 统计 ──
class DashboardStats(BaseModel):
    total_stores: int
    published_count: int
    draft_count: int
    archived_count: int
    total_views: int
    total_crawls: int
    recent_stores: List[StoreResponse]


# ── 通用 ──
class MessageResponse(BaseModel):
    message: str


# ── 爬虫配置（前端「爬虫」页面）──
class CrawlerConfigResponse(BaseModel):
    enabled: bool
    weibo_keywords: List[str]                       # 二次元 IP 关键词（全站搜索用）
    weibo_accounts: List[dict] = []                 # 账号监控：[{"name","uid"}]，uid 空表示未配置
    weibo_uid_enabled: bool = True                  # 账号监控（UID）模式开关，优先级最高
    weibo_keyword_enabled: bool = False             # 全站关键词搜索开关，作为 UID 的补充
    weibo_max_pages: int                           # 每个关键词最多翻几页
    has_cookie: bool                               # 是否已配置微博 Cookie
    xhs_enabled: bool = False                      # 小红书开关（规划中）
    has_xhs_cookie: bool = False
    douyin_enabled: bool = False                   # 抖音开关（规划中）
    has_douyin_cookie: bool = False
    schedule: List[str]
    lookback_days: int
    # 运行态（只读）
    last_success_at: Optional[str] = None
    last_run_at: Optional[str] = None
    last_error: str = ""
    pending_weibo_draft: int = 0
    last_log: Optional[dict] = None


class CrawlerConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    weibo_keywords: Optional[List[str]] = None
    weibo_accounts: Optional[List[dict]] = None
    weibo_uid_enabled: Optional[bool] = None
    weibo_keyword_enabled: Optional[bool] = None
    weibo_max_pages: Optional[int] = None
    schedule: Optional[List[str]] = None
    lookback_days: Optional[int] = None
    weibo_cookie: Optional[str] = None
    xhs_enabled: Optional[bool] = None
    xhs_cookie: Optional[str] = None
    douyin_enabled: Optional[bool] = None
    douyin_cookie: Optional[str] = None
