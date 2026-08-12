"""Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime


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

    # 日期选择器在清空时可能回传空串 ""，pydantic 无法解析为 datetime → 422。
    # 这里在解析前把空串/None 统一转成 None，避免新增/编辑快闪店因空日期失败。
    @validator("start_date", "end_date", pre=True)
    def _empty_date_to_none(cls, v):
        if v is None or v == "" or v == "null":
            return None
        return v


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
