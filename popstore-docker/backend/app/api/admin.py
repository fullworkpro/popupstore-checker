"""后台管理 API — 快闪店 CRUD、审核、统计、爬虫触发"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.core.database import get_db
from app.core.config import settings
from app.models.store import (
    Store, StoreStatus, CrawlLog, CrawlerState, CrawlerConfig,
    DEFAULT_STORE_TYPE, STORE_TYPE_VALUES,
)
from app.models.admin import Admin
from app.api.deps import get_current_admin
from app.crawler.config_store import get_or_create_config, apply_config_update
from app.crawler.scheduler import sync_scheduler
from app.services.archive import archive_expired_stores
from app.schemas.schemas import (
    StoreCreate, StoreUpdate, StoreResponse, StoreListResponse,
    ReviewRequest, CrawlLogResponse, CrawlLogListResponse,
    DashboardStats, MessageResponse, CrawlerConfigResponse, CrawlerConfigUpdate,
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
    store_type: Optional[str] = None,
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
    if store_type and store_type in STORE_TYPE_VALUES:
        # store_type 列是后加的，老行值为 NULL，一律按默认类型（联名快闪）对待，
        # 否则筛「联名快闪」时这些老数据会凭空消失。
        if store_type == DEFAULT_STORE_TYPE:
            q = q.filter(
                (Store.store_type == DEFAULT_STORE_TYPE) | (Store.store_type.is_(None))
            )
        else:
            q = q.filter(Store.store_type == store_type)
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


@router.post("/archive/run", response_model=MessageResponse)
def run_archive_now(
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    """手动触发一次归档：把「已发布且结束日期 < 今天」的快闪店置为已归档。

    与每日 03:15 的定时任务等价，用于立刻验证归档逻辑或临时清理。
    """
    n = archive_expired_stores(db, force=True)
    return MessageResponse(
        message=f"归档完成，本次归档 {n} 条" if n else "没有需要归档的快闪店"
    )


# ── 手动触发爬虫（后台异步，立即返回，避免长耗时请求被 nginx/浏览器超时 499）──
import threading

_thread_lock = threading.Lock()  # 仅用于本进程的线程计数，真正的并发防重由 scheduler 锁负责


@router.post("/crawl/trigger", response_model=MessageResponse)
def trigger_crawl(_: Admin = Depends(get_current_admin)):
    def _bg():
        from app.crawler.scheduler import run_all_crawlers
        try:
            run_all_crawlers()
        except Exception as e:  # 后台线程异常不应影响主流程，仅记录
            logger.error("[admin] 后台全量爬虫异常: %s", e)

    threading.Thread(target=_bg, daemon=True).start()
    return MessageResponse(
        message="爬虫已在后台启动（全量：微信/微博，小红书/抖音规划中），"
                "任务约需数十分钟，请稍后在「爬虫」页面查看「上次成功时间/待发布数/最近日志」，"
                "无需保持本页面打开。"
    )


# ── 爬虫配置 + 运行态（前端「爬虫」页面统一读取）──
def _build_crawler_status(db: Session) -> dict:
    cfg = get_or_create_config(db)
    state = db.query(CrawlerState).filter(CrawlerState.source == "weibo").first()
    draft_weibo = (
        db.query(func.count(Store.id))
        .filter(Store.source == "weibo", Store.status == StoreStatus.DRAFT.value)
        .scalar()
        or 0
    )
    last_log = (
        db.query(CrawlLog)
        .filter(CrawlLog.source == "weibo")
        .order_by(desc(CrawlLog.created_at))
        .first()
    )
    data = cfg.to_dict()
    data["last_success_at"] = state.last_success_at.isoformat() if state and state.last_success_at else None
    data["last_run_at"] = state.last_run_at.isoformat() if state and state.last_run_at else None
    data["last_error"] = state.last_error if state else ""
    data["pending_weibo_draft"] = draft_weibo
    data["last_log"] = last_log.to_dict() if last_log else None
    return data


@router.get("/crawler/config", response_model=CrawlerConfigResponse)
def get_crawler_config(db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    return _build_crawler_status(db)


@router.put("/crawler/config", response_model=CrawlerConfigResponse)
def update_crawler_config(
    payload: CrawlerConfigUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
):
    try:
        apply_config_update(db, payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 实时同步定时任务（排程 / 启停）
    sync_scheduler(db)
    return _build_crawler_status(db)


# ── 仅触发微博爬虫（后台异步，全站搜索原创二次元快闪微博，依据数据库配置）──
@router.post("/crawler/weibo/run", response_model=MessageResponse)
def run_weibo_crawler(_: Admin = Depends(get_current_admin)):
    def _bg():
        from app.crawler.scheduler import run_weibo_only
        try:
            run_weibo_only()
        except Exception as e:
            logger.error("[admin] 后台微博爬虫异常: %s", e)

    threading.Thread(target=_bg, daemon=True).start()
    return MessageResponse(
        message="微博爬虫已在后台启动。若已配置有效 UID 的监控账号则走「账号监控」模式（游客可读、限流轻），"
                "否则走「全站关键词搜索」。任务约需数十分钟，请稍后在「爬虫」页面查看"
                "「上次成功时间 / 待发布数 / 最近日志」，无需保持本页面打开。"
    )


# ── 爬虫运行态（兼容旧接口，内容同 /crawler/config 的运行态部分）──
@router.get("/crawler/state", response_model=dict)
def crawler_state(db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    return _build_crawler_status(db)


# ── 城市列表（用于筛选） ──
@router.get("/cities", response_model=list)
def list_cities(db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    results = db.query(Store.city).filter(Store.city != "").distinct().all()
    return sorted([r[0] for r in results if r[0]])
