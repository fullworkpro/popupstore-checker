"""后台管理 API — 快闪店 CRUD、审核、统计、爬虫触发"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.core.database import get_db
from app.core.config import settings
from app.models.store import Store, StoreStatus, CrawlLog
from app.models.admin import Admin
from app.api.deps import get_current_admin
from app.schemas.schemas import (
    StoreCreate, StoreUpdate, StoreResponse, StoreListResponse,
    ReviewRequest, CrawlLogResponse, CrawlLogListResponse,
    DashboardStats, MessageResponse,
)

router = APIRouter(prefix="/admin", tags=["后台管理"])


# ── 仪表盘 ──
@router.get("/dashboard", response_model=DashboardStats)
def dashboard(db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    total = db.query(Store).count()
    published = db.query(Store).filter(Store.status == StoreStatus.PUBLISHED.value).count()
    draft = db.query(Store).filter(Store.status == StoreStatus.DRAFT.value).count()
    archived = db.query(Store).filter(Store.status == StoreStatus.ARCHIVED.value).count()
    total_views = db.query(func.sum(Store.view_count)).scalar() or 0
    total_crawls = db.query(CrawlLog).count()

    recent = (
        db.query(Store)
        .order_by(desc(Store.created_at))
        .limit(10)
        .all()
    )

    return DashboardStats(
        total_stores=total,
        published_count=published,
        draft_count=draft,
        archived_count=archived,
        total_views=total_views,
        total_crawls=total_crawls,
        recent_stores=[StoreResponse.model_validate(s) for s in recent],
    )


# ── 列表 ──
@router.get("/stores", response_model=StoreListResponse)
def list_stores(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    city: Optional[str] = None,
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    q = db.query(Store)
    if status:
        q = q.filter(Store.status == status)
    if city:
        q = q.filter(Store.city == city)
    if source:
        q = q.filter(Store.source == source)
    if keyword:
        q = q.filter(Store.title.contains(keyword))

    total = q.count()
    items = q.order_by(desc(Store.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return StoreListResponse(
        items=[StoreResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── 详情 ──
@router.get("/stores/{store_id}", response_model=StoreResponse)
def get_store(store_id: str, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="快闪店不存在")
    return StoreResponse.model_validate(store)


# ── 新建 ──
@router.post("/stores", response_model=StoreResponse, status_code=201)
def create_store(
    data: StoreCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    store = Store(**data.model_dump())
    store.status = StoreStatus.DRAFT.value
    db.add(store)
    db.commit()
    db.refresh(store)
    return StoreResponse.model_validate(store)


# ── 编辑 ──
@router.put("/stores/{store_id}", response_model=StoreResponse)
def update_store(
    store_id: str,
    data: StoreUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="快闪店不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(store, key, val)

    db.commit()
    db.refresh(store)
    return StoreResponse.model_validate(store)


# ── 删除 ──
@router.delete("/stores/{store_id}", response_model=MessageResponse)
def delete_store(
    store_id: str,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="快闪店不存在")
    db.delete(store)
    db.commit()
    return MessageResponse(message="已删除")


# ── 审核/发布 ──
@router.post("/stores/{store_id}/review", response_model=StoreResponse)
def review_store(
    store_id: str,
    review: ReviewRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="快闪店不存在")

    store.status = review.status
    store.reviewed_by = admin.id
    store.reviewed_at = datetime.now(timezone.utc)
    store.review_comment = review.comment or ""

    db.commit()
    db.refresh(store)
    return StoreResponse.model_validate(store)


# ── 图片上传 ──
# 允许的图片文件头（magic number）签名 → 扩展名
_IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": ".jpg",            # JPEG / JPG
    b"\x89PNG\r\n\x1a\n": ".png",       # PNG
    b"GIF87a": ".gif",                  # GIF87a
    b"GIF89a": ".gif",                  # GIF89a
    # WEBP 为 RIFF 容器，需二次校验偏移 8 处的 "WEBP" 标记，单独处理
}


def _detect_image_ext(content: bytes) -> Optional[str]:
    """通过文件头（magic number）识别真实图片类型，返回扩展名或 None。

    不信任客户端声明的 content_type，所有上传都按字节校验，
    仅放行 jpg/jpeg/gif/png/webp。
    """
    if len(content) < 12:
        return None
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    for sig, ext in _IMAGE_SIGNATURES.items():
        if content[: len(sig)] == sig:
            return ext
    return None


@router.post("/upload", response_model=dict)
async def upload_image(
    file: UploadFile = File(...),
    _: Admin = Depends(get_current_admin),
):
    content = await file.read()

    # 1) 文件头校验（不信任客户端声明的 content_type / 文件后缀）
    ext = _detect_image_ext(content)
    if ext is None:
        raise HTTPException(status_code=400, detail="仅支持 JPG/JPEG/PNG/GIF/WEBP 图片")

    # 2) 大小校验
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"图片大小不能超过 {settings.MAX_UPLOAD_SIZE_MB}MB")

    # 3) 按上传年月日分目录（NAS 映射目录，自动建目录归档）
    now = datetime.now()
    date_parts = [str(now.year), f"{now.month:02d}", f"{now.day:02d}"]
    abs_dir = os.path.join(settings.UPLOAD_DIR, *date_parts)
    os.makedirs(abs_dir, exist_ok=True)

    # 4) 混淆文件名（不使用原始文件名，避免冲突与信息泄露）
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(abs_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    # 5) 返回相对路径（URL 一律用正斜杠，前端按当前域名解析，适配 NAS / 反代 / 多端场景）
    url = "/static/" + "/".join(date_parts) + "/" + filename
    return {"url": url, "filename": filename}


# ── 爬虫日志 ──
@router.get("/crawl-logs", response_model=CrawlLogListResponse)
def list_crawl_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    q = db.query(CrawlLog).order_by(desc(CrawlLog.created_at))
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return CrawlLogListResponse(
        items=[CrawlLogResponse.model_validate(log) for log in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── 手动触发爬虫 ──
@router.post("/crawl/trigger", response_model=MessageResponse)
def trigger_crawl(_: Admin = Depends(get_current_admin)):
    try:
        from app.crawler.scheduler import run_all_crawlers
        result = run_all_crawlers()
        return MessageResponse(message=f"爬虫已触发: {result}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"爬虫执行失败: {str(e)}")


# ── 城市列表（用于筛选） ──
@router.get("/cities", response_model=list)
def list_cities(db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    results = db.query(Store.city).filter(Store.city != "").distinct().all()
    return sorted([r[0] for r in results if r[0]])
