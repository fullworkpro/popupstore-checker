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
