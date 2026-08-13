"""Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re

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
    tags: Optional[str] = "[]"
    source: Optional[str] = "manual"
    source_url: Optional[str] = ""

    @validator("reservation", pre=True, always=True)
    def _norm_reservation(cls, v):
        return v if v in ("required", "advance", "no") else "no"

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
